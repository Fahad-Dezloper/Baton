# Provenance and handoff: deterministic benchmarks

Why this exists: `docs/RESULTS.md` did not show an outcome gain from collision warnings. These benchmarks
test two other features with generated ground truth, so the answer does not depend on model behaviour.
Everything is in `evals/provenance/`; raw numbers are in `evals/provenance/results/*.json`.
All numbers below are as measured on the first run; the generators were not tuned afterwards. (One checker
bug in the optional LLM test was fixed after its outputs existed, see C.)

Reproduce (FalkorDB on localhost:6379; graphs are named `prov_*` and dropped afterwards):

```
PYTHONPATH=src python -B evals/provenance/bench_blast.py 25
PYTHONPATH=src python -B evals/provenance/bench_handoff.py
PYTHONPATH=src python -B evals/provenance/llm_resume.py <scratch_dir>      # optional, uses `claude -p`
```

## A. Retraction / blast radius

Setup: 25 seeded scenarios, each ~203 items (3 root findings, 200 decisions). Retracted root `F0` has a
derivation tree of ~66 decisions on average, depth 5-6, branching, shared ancestors (a node also citing an
older ancestor), and cross-tree merges. About 38% of decisions are distractors: same files and topics as the
`F0` tree but not derived from it. 8% of decisions are superseded. The oracle is the generated derivation DAG.
Baton side: decisions posted with `post_decision(based_on=...)`, then `provenance.retract` on the live graph.

Alternative (no graph): a flat notes file, one line per item, each note citing its sources. Two searchers,
both transitive (they follow every hit and search for its dependents):
- **grep-refs**: word-boundary match on the source id, or exact case-insensitive match of the source text.
- **grep-refs + same-file sweep**: grep-refs, then also flag every note mentioning a file touched by anything found.

How notes cite sources is the variable. Profiles (id / quoted text / paraphrase): `ids` 100/0/0, `quotes`
0/100/0, `mixed` 50/25/25, `paraphrase` 0/0/100 (no id and no verbatim text, only reworded topic), and
`id_noise` (as `ids`, plus 30% of distractors mention a tainted id in passing: "independent of D012").

| Method (n=25) | Precision | Recall | Exact matches | Median time |
|---|---|---|---|---|
| **baton graph, every edge recorded** | 1.000 | 1.000 | 25/25 | 2.7 ms |
| baton graph, only 80% of edges recorded | 1.000 | 0.728 | 0/25 | - |
| grep-refs, `ids` | 0.998 | 1.000 | 23/25 | 8.2 ms |
| grep-refs, `quotes` | 0.998 | 1.000 | 23/25 | 11.4 ms |
| grep-refs, `mixed` | 0.997 | 0.654 | 0/25 | 7.1 ms |
| grep-refs, `paraphrase` | 0.000 (finds nothing) | 0.000 | 0/25 | 0.2 ms |
| grep-refs, `id_noise` | 0.801 | 1.000 | 0/25 | 9.8 ms |
| + file sweep, `ids` / `quotes` | 0.325 | 1.000 | 0/25 | 8-11 ms |
| + file sweep, `mixed` | 0.330 | 0.984 | 0/25 | 7.1 ms |
| + file sweep, `paraphrase` | 0.337 | 0.087 | 0/25 | 0.3 ms |

Reading it honestly:
- **Where grep matches the graph:** when every note cites its source by id or verbatim text, transitive grep
  reaches recall 1.000 and precision 0.998 (the 2 inexact scenarios: three notes with identical generic text
  to a tainted decision, a text-collision false positive). Depth up to 6 is no problem for it. Both are
  milliseconds. In that regime the graph's advantage is only the exact result and that it needs no
  discipline in how notes are written.
- **Where it breaks:** paraphrased references (recall 0 in the `paraphrase` profile, 0.654 in `mixed`), and
  ids mentioned in passing (precision 0.801). The file sweep recovers recall in `mixed` (0.984) but at
  precision about 0.33, i.e. two of three flagged decisions are innocent.
- **The graph's own weakness is capture, not search.** It is exact only for edges that were recorded. With a
  random 20% of `based_on` edges missing, mean recall drops to 0.728 (errors compound along chains) with
  precision still 1.0. This benchmark does not measure how often real sessions record `based_on`; that is
  the open question for the feature.
- Status handling: in all 25 runs the set of decisions with status `tainted` was exactly the derived decisions
  that were open; superseded descendants stayed `superseded` (no false or missed taints).
- **Unscored design gap:** `supersede_decision` creates a replacement with no `BASED_ON` edge. In the 25
  scenarios 119 superseded decisions derived from `F0` had replacements; all 119 replacements remain `open`
  and untainted after the retraction. (Verbatim-quoting notes would have caught them; paraphrased ones not.)
  Whether a replacement inherits taint is a product decision, so it is reported, not changed.

### Depth cap (`BASED_ON*1..8` in `graph/queries.py`)

A linear chain finding -> C1 -> ... -> CL, then retract the finding:

| Chain length | 4 | 6 | 8 | 9 | 10 | 12 | 20 |
|---|---|---|---|---|---|---|---|
| Decisions tainted | 4 | 6 | 8 | 8 | 8 | 8 | 8 |
| Left open (wrongly) | 0 | 0 | 0 | 1 | 2 | 4 | 12 |

Beyond 8 hops the traversal stops silently: retraction reports success and the deepest decisions stay
`open`. The same cap applies to `why`: from the tip of a 9+ chain the root finding is not returned. A
decision reachable by a shorter alternative path is still caught. Generated trees above stayed within 6 levels
so the main table is unaffected. Not changed here (query constants are out of scope); raising the bound or
iterating until no new nodes appear is a small follow-up.

## B. Handoff fidelity

Setup: a scripted session writes a task goal, touches 6 or 30 files, posts N decisions (15% `interface`, 10%
`config`/`storage`, rest `note`; ~12% based on a finding that is later retracted so they become tainted),
exports its handoff with an unfinished-task note and a last-test result, then a different session's
`sessions.briefing` is rendered. Ground truth items are found by unique token in the briefing text. Variants:
short (about 60 chars) vs long (about 400 chars) decision text, and resuming immediately vs 36 h later
(past the 24 h "recent decisions" window). 3 seeds each.

Fixed regardless of N: note retained 72/72 runs, last-test result 72/72, touched file paths 100% (even at 30
files), briefing under the 6000-char cap in every run.

Decisions are dropped by two budgets: 25 items at export and a 3000-char handoff section at import. Share of
the session's decisions present in the briefing (all classes), by N:

| N | short text | long text |
|---|---|---|
| 10 | 100% | 85% (after fix) |
| 50 | 50% | 16% |
| 200 | 12% | 4% |

Tainted decisions specifically (after the fix): short text 100% / 100% / 90% for N = 10/50/200 (the shortfall
at 200 is because 22+ tainted per run plus the 3000-char cap); long text 100% / 93% / 32%.

**Defect found and fixed.** `export_handoff` selects decisions in priority order (tainted, then non-note, then
notes) but `import_handoff` re-sorted them by recency. The briefing renders the imported packet and cuts the
tail at 3000 chars, so an older tainted or interface decision was dropped before newer notes. Failing test:
`tests/test_provenance_handoff.py::test_import_keeps_priority_order_under_truncation` (the tainted decision
was absent from the rendered handoff). Fix (`core/handoff.py`): sort by the same priority, then recency.
Measured before / after on the benchmark:

| Scenario (long text) | Tainted kept, before | after | Runs with a priority inversion, before | after |
|---|---|---|---|---|
| N=10, resumed 36 h later | 15/16 overall | 16/16 | 4/12 | 0/12 |
| N=50 | 50/90 | 84/90 | 12/12 | 0/12 |
| N=200 | 86/306 | 99/306 | 4/12 | 0/12 |

(An inversion = a lower-priority decision is in the briefing while a higher-priority one is dropped.) Short
texts were unaffected (0 inversions before and after). Raw before-fix data: `results/handoff_before_fix.json`.

**What remains, by design or not yet addressed:**
- At N >= 50 most open decisions are not in the briefing (cap of 25 items / 3000 chars). The briefing drops
  oldest notes last-priority first, which is sensible, but "open decisions" recall is 12% at N=200 with short
  text. Whether that matters depends on whether a resuming session needs the notes.
- Only decisions about files the session *touched* are exported; a decision about an untouched file is never in
  the handoff (not measured here).
- At 200 decisions with long text, 68% of tainted decisions are still dropped (budget, not ordering).

## C. LLM resume test (optional)

8 runs of `claude -p --model claude-haiku-5-5` in a tiny repo with a stubbed `migrate_rollback()`. The needed
fact (rollback must copy rows into table `_orders_bak`) exists only in the briefing. Checker (deterministic):
file parses, stub implemented, `_orders_bak` present.

| Arm | Pass |
|---|---|
| prompt only | 0/4 (all implemented the stub, none used `_orders_bak`) |
| prompt + baton briefing | 4/4 |

Caveats: small n; the test is close to tautological (a model that is given a fact uses it), so it shows the
briefing text transfers a hidden requirement, not that real sessions need or benefit from it. The first run's
checker had a bug (`py_compile` to `os.devnull` reported a syntax failure); the outputs were re-scored with
`ast.parse` without new model calls (`llm_resume.py <dir> recheck`). Rows are in `results/llm_resume.json`.

## Threats to validity
- Synthetic graphs written by the benchmark author; the shapes (depth <= 6, 200 items) are plausible, not
  measured from real use. The notes-file baseline is a model of how a team writes notes, not a measured team.
- Reference-style mix is an input assumption; the table shows the full range so the reader can pick.
- The graph result assumes `based_on` was recorded. 80% capture is one sensitivity point, not an estimate.
- Timing is a local single-node FalkorDB; it says nothing about large graphs.
