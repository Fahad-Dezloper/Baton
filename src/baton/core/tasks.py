"""Tasks and leases. Phase 1.3 / 1.4."""


def create_task(store, goal, depends_on=(), touches=()):
    raise NotImplementedError("Phase 1.3")


def ready_tasks(store):
    raise NotImplementedError("Phase 1.3")


def claim_task(store, task_id, actor_id, lease_seconds=300):
    raise NotImplementedError("Phase 1.4")


def renew_lease(store, task_id, actor_id, lease_seconds=300):
    raise NotImplementedError("Phase 1.4")


def complete_task(store, task_id, actor_id):
    raise NotImplementedError("Phase 1.4")


def release_task(store, task_id, actor_id):
    raise NotImplementedError("Phase 1.4")
