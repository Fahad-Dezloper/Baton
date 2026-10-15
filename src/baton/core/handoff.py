"""Bounded handoff export and import. Phase 1.8."""

MAX_SUMMARY_CHARS = 8000  # stay well under the host's injected-context cap


def export_handoff(store, task_id):
    raise NotImplementedError("Phase 1.8")


def import_handoff(store, actor_id, handoff_id):
    raise NotImplementedError("Phase 1.8")
