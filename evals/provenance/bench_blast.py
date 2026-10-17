"""Benchmark A: retraction / blast radius, baton graph vs. a flat notes file searched with grep.

Usage: PYTHONPATH=src python -B evals/provenance/bench_blast.py [n_scenarios]
Ground truth is generated, never inferred: the true derivation DAG is the oracle.
"""

import json
import os
import random
import re
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(__file__))
from common import RESULTS_DIR, mean, median, new_store, pr  # noqa: E402

from baton.core import decisions, provenance  # noqa: E402

FILES = ["src/app/%s.py" % n for n in (
    "client", "server", "config", "db", "cache", "auth", "queue", "retry", "limits", "logging",
    "metrics", "router", "schema", "billing", "search", "export", "import", "session", "worker", "util")]
TOPICS = [  # (phrase used in the decision, different wording used by a paraphrased reference)
    ("client timeout", "how long callers wait"), ("retry backoff", "the delay between attempts"),
    ("cache ttl", "how long entries live"), ("page size", "rows returned per request"),
    ("token expiry", "session lifetime"), ("queue depth", "pending work ceiling"),
    ("log level", "verbosity setting"), ("batch size", "chunking of writes"),
    ("pool size", "number of connections"), ("rate limit", "request throttle"),
    ("schema version", "the migration number"), ("retention window", "how long data is kept"),
    ("hash algorithm", "digest choice"), ("locale default", "fallback language"),
    ("max upload", "largest accepted file"), ("shard count", "partition fan-out"),
    ("poll interval", "how often we check"), ("lock scope", "granularity of locking"),
    ("error format", "shape of failures"), ("date format", "timestamp rendering"),
    ("index choice", "which column is indexed"), ("tls minimum", "oldest protocol allowed"),
    ("flush policy", "when buffers are written"), ("id scheme", "identifier layout")]
VERBS = ["set", "raise", "lower", "pin", "switch", "standardise", "cap", "default"]
VALUES = ["5s", "30s", "64", "128", "256", "off", "on", "v2", "utf-8", "10%", "1h", "24h"]
KINDS = ["interface", "config", "storage", "rename", "note", "note", "note"]
AUTHORS = ["alice", "bob", "carol", "dave"]

PROFILES = {  # (id, quote, paraphrase) probabilities for how a note cites its source
    "ids": (1.0, 0.0, 0.0),
    "quotes": (0.0, 1.0, 0.0),
    "mixed": (0.5, 0.25, 0.25),
    "paraphrase": (0.0, 0.0, 1.0),
    "id_noise": (1.0, 0.0, 0.0),  # as "ids", plus unrelated notes that merely mention a tainted id
}


def gen_structure(seed, n_total=200):
    """Returns items in a random topological order. Each item: id, kind, text, files, topic, parents, tree."""
    rng = random.Random(seed)
    items = {}

    def mk(iid, kind, tree, level, parents, topic_pool=None, file_pool=None):
        topic = rng.choice(topic_pool or TOPICS)
        fl = rng.sample(file_pool or FILES, rng.choice([1, 1, 2]))
        text = "%s %s to %s in %s" % (rng.choice(VERBS), topic[0], rng.choice(VALUES), " and ".join(fl))
        items[iid] = dict(id=iid, kind=kind, text=text, files=fl, topic=topic, parents=parents,
                          tree=tree, level=level, dkind=rng.choice(KINDS), author=rng.choice(AUTHORS))

    n = [0]

    def nid(prefix="D"):
        n[0] += 1
        return "%s%03d" % (prefix, n[0])

    tree_sizes = {0: int(n_total * 0.32), 1: int(n_total * 0.15), 2: int(n_total * 0.15)}
    tree_nodes = {}
    for t in (0, 1, 2):
        rid = "F%d" % t
        mk(rid, "finding", t, 0, [])
        levels = [[rid]]
        dmax = rng.choice([5, 6, 6]) if t == 0 else rng.choice([3, 4, 5])
        remaining = tree_sizes[t]
        for k in range(1, dmax + 1):
            size = min(remaining, rng.randint(3, 12)) if k < dmax else remaining
            size = min(size, remaining)
            lvl = []
            for _ in range(size):
                iid = nid()
                prev = levels[k - 1]
                ps = rng.sample(prev, min(len(prev), rng.choice([1, 1, 2])))
                if k >= 2 and rng.random() < 0.25:  # shared ancestor: also cite something from further up
                    older = [x for lv in levels[:k - 1] for x in lv]
                    extra = rng.choice(older)
                    if extra not in ps:
                        ps.append(extra)
                mk(iid, "decision", t, k, ps)
                lvl.append(iid)
            remaining -= size
            levels.append(lvl)
            tree_nodes[t] = tree_nodes.get(t, []) + lvl
            if remaining <= 0:
                break
    # cross-tree merge: a few decisions in trees 1/2 also cite a tree-0 decision (so they are tainted too)
    t0 = [i for i in tree_nodes[0]]
    for t in (1, 2):
        for iid in rng.sample(tree_nodes[t], max(1, len(tree_nodes[t]) // 12)):
            cand = rng.choice(t0)
            if items[cand]["level"] < items[iid]["level"] and cand not in items[iid]["parents"]:
                items[iid]["parents"].append(cand)
    # distractors: same files and topics as tree 0 but NOT derived from it
    t0_topics = [items[i]["topic"] for i in tree_nodes[0]]
    t0_files = sorted({f for i in tree_nodes[0] for f in items[i]["files"]})
    other = tree_nodes[1] + tree_nodes[2]
    while len(items) < n_total + 3:
        iid = nid()
        parents = [rng.choice(other)] if rng.random() < 0.3 else []
        mk(iid, "decision", 3, 0, parents,
           topic_pool=t0_topics if rng.random() < 0.85 else None,
           file_pool=t0_files if rng.random() < 0.85 else None)
    # random topological order
    indeg = {i: len([p for p in v["parents"]]) for i, v in items.items()}
    kids = {}
    for i, v in items.items():
        for p in v["parents"]:
            kids.setdefault(p, []).append(i)
    ready = [i for i, d in indeg.items() if d == 0]
    order = []
    while ready:
        j = rng.randrange(len(ready))
        ready[j], ready[-1] = ready[-1], ready[j]
        cur = ready.pop()
        order.append(cur)
        for c in kids.get(cur, []):
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    assert len(order) == len(items)
    superseded = set(rng.sample([i for i in order if items[i]["kind"] == "decision"], int(n_total * 0.08)))
    return [items[i] for i in order], kids, superseded


def descendants(kids, root):
    seen, stack = set(), [root]
    while stack:
        for c in kids.get(stack.pop(), []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def build_graph(ws, order, superseded, capture, seed):
    rng = random.Random(seed * 7 + 1)
    s = new_store(ws)
    t = 1000.0
    for it in order:
        t += 1
        if it["kind"] == "finding":
            provenance.add_finding(s, "alice", it["text"], "src-" + it["id"], finding_id=it["id"], now=t)
        else:
            based = [p for p in it["parents"] if rng.random() < capture]
            decisions.post_decision(s, it["author"], it["text"], artifacts=it["files"], based_on=based,
                                    kind=it["dkind"], decision_id=it["id"], now=t)
    replacements = {}
    for old in sorted(superseded):
        new = decisions.supersede_decision(s, "alice", old, "reworded: " + next(
            x["text"] for x in order if x["id"] == old), now=t + 1)
        replacements[old] = new["id"]
    return s, replacements


def render_notes(order, profile, seed, replacements, superseded):
    """Flat notes file: one line per item, '<id> | <files> | <text> | basis: <citations>'."""
    rng = random.Random(seed * 13 + zlib.crc32(profile.encode()) % 1000)
    pid, pq, _ = PROFILES[profile]
    by_id = {i["id"]: i for i in order}
    lines = []
    tree0 = {i["id"] for i in order if i["tree"] == 0}
    for it in order:
        refs = []
        for p in it["parents"]:
            r = rng.random()
            src = by_id[p]
            if r < pid:
                refs.append("based on %s" % p)
            elif r < pid + pq:
                refs.append('following "%s"' % src["text"])
            else:
                refs.append("follows up on the earlier work on %s" % src["topic"][1])
        body = "%s" % it["text"]
        if it["id"] in superseded:
            body += " [superseded]"
        if refs:
            body += " | basis: " + "; ".join(refs)
        elif profile == "id_noise" and it["tree"] == 3 and rng.random() < 0.3:
            body += " | note: independent of %s, unrelated" % rng.choice(sorted(tree0))
        lines.append((it["id"], " | ".join(it["files"]) + " | " + body))
    for old, new in replacements.items():
        lines.append(("R_" + old, " | ".join(by_id[old]["files"]) + " | reworded: " + by_id[old]["text"]))
    return lines


def grep_closure(lines, order, root, sweep_files=False):
    """Transitive reference-following with word-boundary id match and exact (case-insensitive) text match."""
    text_of = {i["id"]: i["text"].lower() for i in order}
    files_of = {i["id"]: i["files"] for i in order}
    found, queue = set(), [root]
    while queue:
        src = queue.pop()
        pat = re.compile(r"\b%s\b" % re.escape(src))
        if src not in text_of:
            continue
        t = text_of[src]
        for lid, body in lines:
            if lid == src or lid in found:
                continue
            if pat.search(body) or t in body.lower():
                found.add(lid)
                queue.append(lid)
    if sweep_files:
        fset = set(files_of[root])
        for x in found:
            fset.update(files_of.get(x, []))
        for lid, body in lines:
            if lid != root and lid not in found and any(f in body for f in fset):
                found.add(lid)
    return found


def run(n_scen):
    out = {"profiles": {}, "n_scenarios": n_scen}
    acc = {p: {"strict": [], "sweep": [], "t_strict": [], "t_sweep": []} for p in PROFILES}
    graph_rows, status_rows, orphan_rows, sens_rows = [], [], [], []
    for seed in range(1, n_scen + 1):
        order, kids, superseded = gen_structure(seed)
        truth = descendants(kids, "F0")
        truth_open = {i for i in truth if i not in superseded}
        for capture, rows, tag in ((1.0, graph_rows, "full"), (0.8, sens_rows, "capture80")):
            ws = "prov_blast_%s_%d" % (tag, seed)
            s, repl = build_graph(ws, order, superseded, capture, seed)
            try:
                t0 = time.perf_counter()
                res = provenance.retract(s, "F0", "alice", reason="synthetic")
                dt = (time.perf_counter() - t0) * 1000
                affected = {d["id"] for d in res["affected"]}
                p_, r_ = pr(affected, truth)
                rows.append(dict(seed=seed, precision=p_, recall=r_, ms=dt, truth=len(truth), found=len(affected)))
                if tag == "full":
                    tainted = {r[0] for r in s.rows("MATCH (d:Decision {status:'tainted'}) RETURN d.id", read_only=True)}
                    sup_kept = {r[0] for r in s.rows("MATCH (d:Decision {status:'superseded'}) RETURN d.id", read_only=True)}
                    status_rows.append(dict(
                        tainted_exact=tainted == truth_open,
                        superseded_untouched=superseded <= sup_kept,
                        false_taint=len(tainted - truth), missed_taint=len(truth_open - tainted)))
                    orph = [new for old, new in repl.items() if old in truth]
                    live_untainted = [n for n in orph if s.rows(
                        "MATCH (d:Decision {id:$i}) RETURN d.status", {"i": n}, read_only=True)[0][0] == "open"]
                    orphan_rows.append(dict(replacements_of_derived=len(orph), left_open=len(live_untainted)))
                    if seed == 1:
                        out["example_truth_size"] = len(truth)
                        out["example_graph_nodes"] = len(order) + len(repl)
            finally:
                s.drop()
        for prof in PROFILES:
            lines = render_notes(order, prof, seed, repl, superseded)
            for key, sweep in (("strict", False), ("sweep", True)):
                t0 = time.perf_counter()
                f = grep_closure(lines, order, "F0", sweep)
                dt = (time.perf_counter() - t0) * 1000
                heirs = {x for x in f if x.startswith("R_")}
                if key == "strict":
                    acc[prof].setdefault("heirs", []).append((len(heirs & {"R_" + o for o in repl if o in truth}), len([o for o in repl if o in truth])))
                p_, r_ = pr(f - heirs, truth)
                acc[prof][key].append((p_, r_))
                acc[prof]["t_" + key].append(dt)
    summ = lambda rows, k: mean(r[k] for r in rows)
    out["graph_full"] = dict(precision=summ(graph_rows, "precision"), recall=summ(graph_rows, "recall"),
                             median_ms=median(r["ms"] for r in graph_rows),
                             exact=sum(1 for r in graph_rows if r["precision"] == 1 and r["recall"] == 1),
                             truth_mean=mean(r["truth"] for r in graph_rows),
                             rows=graph_rows)
    out["graph_capture80"] = dict(precision=summ(sens_rows, "precision"), recall=summ(sens_rows, "recall"),
                                  exact=sum(1 for r in sens_rows if r["precision"] == 1 and r["recall"] == 1))
    out["status"] = dict(
        tainted_status_exact=sum(r["tainted_exact"] for r in status_rows),
        superseded_untouched=sum(r["superseded_untouched"] for r in status_rows),
        false_taint=sum(r["false_taint"] for r in status_rows), missed_taint=sum(r["missed_taint"] for r in status_rows))
    out["orphaned_replacements"] = dict(
        derived_superseded_replaced=sum(r["replacements_of_derived"] for r in orphan_rows),
        left_open_untainted=sum(r["left_open"] for r in orphan_rows))
    for prof, a in acc.items():
        out["profiles"][prof] = {}
        for key in ("strict", "sweep"):
            out["profiles"][prof][key] = dict(
                heirs_caught=sum(h[0] for h in a["heirs"]) if key == "strict" else None,
                heirs_total=sum(h[1] for h in a["heirs"]) if key == "strict" else None,
                precision=mean(x[0] for x in a[key]), recall=mean(x[1] for x in a[key]),
                exact=sum(1 for x in a[key] if x == (1.0, 1.0)), median_ms=median(a["t_" + key]))
    return out


def run_chain():
    """Chains longer than the BASED_ON traversal cap (8)."""
    rows = []
    for L in (4, 6, 8, 9, 10, 12, 20):
        s = new_store("prov_chain_%d" % L)
        try:
            provenance.add_finding(s, "a", "root fact", "x", finding_id="CF", now=1.0)
            prev = "CF"
            for i in range(1, L + 1):
                decisions.post_decision(s, "a", "step %d" % i, based_on=[prev], decision_id="C%d" % i, now=1.0 + i)
                prev = "C%d" % i
            res = provenance.retract(s, "CF", "a")
            st = {r[0]: r[1] for r in s.rows("MATCH (d:Decision) RETURN d.id, d.status", read_only=True)}
            tainted = sorted(int(k[1:]) for k, v in st.items() if v == "tainted")
            why_deepest = provenance.why(s, prev)
            rows.append(dict(length=L, tainted=len(tainted), expected=L, deepest_tainted=max(tainted) if tainted else 0,
                             still_open=sorted(int(k[1:]) for k, v in st.items() if v == "open")[:3],
                             why_from_tip_finding_found=bool(why_deepest["findings"]),
                             why_from_tip_decisions=len(why_deepest["decisions"])))
            # also: retraction of a mid-chain decision reaches 8 hops past it
        finally:
            s.drop()
    return rows


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    t = time.time()
    res = run(n)
    res["chain"] = run_chain()
    res["wall_s"] = time.time() - t
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "blast.json"), "w") as f:
        json.dump(res, f, indent=1)
    g = res["graph_full"]
    print("graph(full capture): P=%.3f R=%.3f exact=%d/%d median %.1f ms  truth~%.0f" % (
        g["precision"], g["recall"], g["exact"], n, g["median_ms"], g["truth_mean"]))
    c = res["graph_capture80"]
    print("graph(80%% edge capture): P=%.3f R=%.3f exact=%d/%d" % (c["precision"], c["recall"], c["exact"], n))
    for prof, d in res["profiles"].items():
        for k, v in d.items():
            if v.get("heirs_total") is not None:
                print("   replacements of derived decisions found by grep: %d/%d" % (v["heirs_caught"], v["heirs_total"]))
            print("%-10s %-6s P=%.3f R=%.3f exact=%d/%d %.2f ms" % (prof, k, v["precision"], v["recall"], v["exact"], n, v["median_ms"]))
    print(res["status"], res["orphaned_replacements"])
    for r in res["chain"]:
        print(r)
