"""Spike 0.3b: where do slow reads occur relative to a long write on the same graph?

Usage: .venv/bin/python spikes/read_stall.py [repeats] [nodes]
"""
import json
import statistics
import sys
import threading
import time

from falkordb import FalkorDB


def once(nodes):
    wc = FalkorDB(host="localhost", port=6379)
    rc = FalkorDB(host="localhost", port=6379)
    w = wc.select_graph("stall")
    r = rc.select_graph("stall")
    w.query("UNWIND range(1, 100) AS i CREATE (:R {v: i})")
    samples = []  # (t_since_write_start_ms, latency_ms)
    done = threading.Event()
    box = {}

    def long_write():
        box["t0"] = time.perf_counter()
        w.query("UNWIND range(1, %d) AS i CREATE (:Big {v: i})" % nodes)
        box["t1"] = time.perf_counter()
        done.set()

    th = threading.Thread(target=long_write)
    th.start()
    while "t0" not in box:
        time.sleep(0.001)
    while not done.is_set():
        s = time.perf_counter()
        r.ro_query("MATCH (x:R) RETURN count(x)")
        e = time.perf_counter()
        samples.append(((s - box["t0"]) * 1000.0, (e - s) * 1000.0))
    th.join()
    wc.select_graph("stall").delete()
    write_ms = (box["t1"] - box["t0"]) * 1000.0
    lat = sorted(x[1] for x in samples)
    slow = [(round(t, 1), round(l, 1)) for t, l in samples if l > 20]
    return {
        "write_ms": round(write_ms, 1),
        "reads": len(samples),
        "p50_ms": round(statistics.median(lat), 2),
        "p99_ms": round(lat[int(len(lat) * 0.99)], 2),
        "max_ms": round(lat[-1], 1),
        "slow_reads_over_20ms": slow,
        "slow_read_positions_pct_of_write": [round(100 * t / write_ms) for t, _ in slow],
    }


def main():
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    nodes = int(sys.argv[2]) if len(sys.argv) > 2 else 1500000
    print(json.dumps([once(nodes) for _ in range(repeats)], indent=2))


if __name__ == "__main__":
    main()
