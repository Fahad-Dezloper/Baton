"""Decisions and conflict checks. Phase 1.5 / 1.6."""


def post_decision(store, actor_id, text, artifacts=(), based_on=()):
    raise NotImplementedError("Phase 1.5")


def supersede_decision(store, actor_id, old_id, text):
    raise NotImplementedError("Phase 1.5")


def check_conflicts(store, actor_id, paths):
    """Return open decisions and live leases by others touching `paths`."""
    raise NotImplementedError("Phase 1.6")
