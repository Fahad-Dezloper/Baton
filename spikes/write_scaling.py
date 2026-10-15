"""Spike 0.3: how do writes and reads behave across threads and graphs?

A) N threads write to ONE graph           -> expect serialized
B) N threads write to N SEPARATE graphs   -> do they overlap?
C) reads while a long write runs (same graph) -> are readers blocked?

Usage: .venv/bin/python spikes/write_scaling.py [threads] [writes_per_thread]
"""
import json
import statistics
import sys
import threading
import time

from falkordb import FalkorDB

HEAVY = "UNWIND range(1, $n) AS i CREATE (:N {v: i, k: $k})"


def timed_writes(graphs, per_thread, n):
    barrier = threading.Barrier(len(graphs))

    def work(idx):
        g = graphs[idx]
        barrier.wait()
        for j in range(per_thread):
            g.query(HEAVY, {"n": n, "k": "%d-%d" % (idx, j)})

    ts = [threading.Thread(target=work, args=(i,)) for i in range(len(graphs))]
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return time.perf_counter() - t0


def main():
    threads = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    per = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 300  # nodes per write
    big = int(sys.argv[4]) if len(sys.argv) > 4 else 400000
    conns = [FalkorDB(host="localhost", port=6379) for _ in range(threads)]
    cfg = conns[0].connection.execute_command("GRAPH.CONFIG", "GET", "THREAD_COUNT")
    out = {"threads": threads, "writes_per_thread": per, "nodes_per_write": n, "thread_count_config": cfg}

    # baseline: single thread, single graph
    solo = conns[0].select_graph("w_solo")
    solo_t = timed_writes([solo], per, n)
    out["single_thread_seconds"] = round(solo_t, 3)

    # A) one shared graph
    shared = [c.select_graph("w_shared") for c in conns]
    a = timed_writes(shared, per, n)
    # B) separate graphs
    separate = [c.select_graph("w_sep_%d" % i) for i, c in enumerate(conns)]
    b = timed_writes(separate, per, n)
    total = threads * per
    out["A_one_graph_seconds"] = round(a, 3)
    out["A_writes_per_sec"] = round(total / a, 1)
    out["B_separate_graphs_seconds"] = round(b, 3)
    out["B_writes_per_sec"] = round(total / b, 1)
    out["single_thread_writes_per_sec"] = round(per / solo_t, 1)
    out["B_over_A_speedup"] = round(a / b, 2)

    # C) read latency during a long write on the same graph
    g_w = conns[0].select_graph("w_read")
    g_w.query("UNWIND range(1, 100) AS i CREATE (:R {v: i})")
    reader = conns[1].select_graph("w_read")
    base = []
    for _ in range(50):
        t0 = time.perf_counter()
        reader.ro_query("MATCH (r:R) RETURN count(r)")
        base.append((time.perf_counter() - t0) * 1000.0)

    during = []
    write_ms = {}
    stop = threading.Event()

    def long_write():
        t0 = time.perf_counter()
        g_w.query("UNWIND range(1, %d) AS i CREATE (:Big {v: i})" % big + "")
        write_ms["ms"] = (time.perf_counter() - t0) * 1000.0
        stop.set()

    wt = threading.Thread(target=long_write)
    wt.start()
    time.sleep(0.05)
    while not stop.is_set():
        t0 = time.perf_counter()
        reader.ro_query("MATCH (r:R) RETURN count(r)")
        during.append((time.perf_counter() - t0) * 1000.0)
    wt.join()
    out["C_long_write_ms"] = round(write_ms.get("ms", 0), 1)
    out["C_read_baseline_ms_p50"] = round(statistics.median(base), 2)
    out["C_reads_during_write_count"] = len(during)
    if during:
        out["C_read_during_write_ms_p50"] = round(statistics.median(during), 2)
        out["C_read_during_write_ms_max"] = round(max(during), 2)

    for name in ["w_solo", "w_shared", "w_read"] + ["w_sep_%d" % i for i in range(threads)]:
        try:
            conns[0].select_graph(name).delete()
        except Exception:
            pass
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
