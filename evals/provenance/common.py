"""Shared helpers for the provenance benchmarks."""

import os
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from baton.graph.client import Store  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def new_store(name: str) -> Store:
    assert name.startswith("prov_"), "benchmark workspaces must start with prov_"
    s = Store(name)
    s.drop()  # only ever our own prov_ graph
    s.bootstrap()
    return s


def pr(found, truth):
    found, truth = set(found), set(truth)
    tp = len(found & truth)
    precision = tp / len(found) if found else (1.0 if not truth else 0.0)
    recall = tp / len(truth) if truth else 1.0
    return precision, recall


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs):
    return statistics.median(list(xs))
