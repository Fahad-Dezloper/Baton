"""Spike 0.2: does the atomic claim query give exactly one winner under a real race?

Usage: .venv/bin/python spikes/race_claim.py [workers] [rounds]
Needs FalkorDB on localhost:6379 (docker compose up -d).
"""
import json
import os
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from falkordb import FalkorDB  # noqa: E402

from baton.graph.queries import CLAIM_TASK  # noqa: E402

GRAPH = "spike_race"
TASK_ID = "t1"

RESET = """
MERGE (t:Task {id: $id})
SET t.status = $status, t.owner = '', t.lease_until = $lease_until, t.version = 0
"""


def one_round(graphs, workers, status, lease_until, now):
    graphs[0].query(RESET, {"id": TASK_ID, "status": status, "lease_until": lease_until})
    barrier = threading.Barrier(workers)
    results = [None] * workers
    latencies = [0.0] * workers

    def work(i):
        g = graphs[i]
        barrier.wait()
        t0 = time.perf_counter()
        r = g.query(
            CLAIM_TASK,
            {"task_id": TASK_ID, "actor_id": "w%d" % i, "now": now, "lease_until": now + 300},
        )
        latencies[i] = (time.perf_counter() - t0) * 1000.0
        results[i] = len(r.result_set)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = graphs[0].ro_query(
        "MATCH (t:Task {id:$id}) RETURN t.owner, t.version, t.status", {"id": TASK_ID}
    ).result_set[0]
    return sum(results), latencies, final


def scenario(name, graphs, workers, rounds, status, lease_until, now):
    winners_per_round, all_lat, bad = [], [], []
    for r in range(rounds):
        winners, lat, final = one_round(graphs, workers, status, lease_until, now)
        winners_per_round.append(winners)
        all_lat.extend(lat)
        owner, version, st = final
        if winners != 1 or version != 1 or st != "claimed":
            bad.append({"round": r, "winners": winners, "final": final})
    dist = {}
    for w in winners_per_round:
        dist[w] = dist.get(w, 0) + 1
    return {
        "scenario": name,
        "workers": workers,
        "rounds": rounds,
        "winners_distribution": dist,
        "violations": len(bad),
        "violation_samples": bad[:3],
        "claim_latency_ms": {
            "p50": round(statistics.median(all_lat), 2),
            "p95": round(sorted(all_lat)[int(len(all_lat) * 0.95)], 2),
            "max": round(max(all_lat), 2),
        },
    }


def control_round(graphs, workers):
    """Deliberately NON-atomic claim (read, then write). Proves the harness can see races."""
    graphs[0].query(RESET, {"id": TASK_ID, "status": "open", "lease_until": 0})
    barrier = threading.Barrier(workers)
    won = [0] * workers

    def work(i):
        g = graphs[i]
        barrier.wait()
        st = g.ro_query("MATCH (t:Task {id:$id}) RETURN t.status", {"id": TASK_ID}).result_set[0][0]
        if st == "open":
            g.query(
                "MATCH (t:Task {id:$id}) SET t.status='claimed', t.owner=$a",
                {"id": TASK_ID, "a": "w%d" % i},
            )
            won[i] = 1

    ts = [threading.Thread(target=work, args=(i,)) for i in range(workers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return sum(won)


def control(graphs, workers, rounds):
    dist = {}
    for _ in range(rounds):
        w = control_round(graphs, workers)
        dist[w] = dist.get(w, 0) + 1
    return {
        "scenario": "NON-atomic control (read then write)",
        "workers": workers,
        "rounds": rounds,
        "winners_distribution": dist,
        "rounds_with_double_claim": sum(v for k, v in dist.items() if k > 1),
    }


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    conns = [FalkorDB(host="localhost", port=int(os.environ.get("BATON_FALKORDB_PORT", "6379"))) for _ in range(workers)]
    graphs = [c.select_graph(GRAPH) for c in conns]
    now = int(time.time())
    out = [
        scenario("fresh open task", graphs, workers, rounds, "open", 0, now),
        # expired lease takeover: claimed, lease_until in the past
        scenario("expired lease takeover", graphs, workers, rounds, "claimed", now - 10, now),
    ]
    # a live lease must NOT be claimable at all
    live_winners, _, final = one_round(graphs, workers, "claimed", now + 600, now)
    out.append({"scenario": "live lease (expect 0 winners)", "winners": live_winners, "final": final})
    out.append(control(graphs, workers, rounds))
    graphs[0].delete()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
