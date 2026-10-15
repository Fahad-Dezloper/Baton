"""Findings, why-traces and retraction. Phase 1.7."""


def add_finding(store, actor_id, text, source):
    raise NotImplementedError("Phase 1.7")


def why(store, decision_id):
    raise NotImplementedError("Phase 1.7")


def retract(store, item_id):
    """Mark an item wrong and return everything derived from it."""
    raise NotImplementedError("Phase 1.7")
