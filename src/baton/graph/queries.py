"""Named, parameterized Cypher. Callers never build Cypher from model output.

Verified against a live FalkorDB in the test suite (tests/); see docs/SPIKES.md for the race test.
"""

# Atomic lease claim. Writes serialize per graph, so at most one caller gets a row back.
# A task is claimable when it is open (or its lease expired) and every dependency is done.
CLAIM_TASK = """
MATCH (t:Task {id: $task_id})
WHERE t.status = 'open'
   OR (t.status = 'claimed' AND t.lease_until < $now)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task) WHERE d.status <> 'done'
WITH t, count(d) AS blockers
WHERE blockers = 0
SET t.status = 'claimed',
    t.owner = $actor_id,
    t.lease_until = $lease_until,
    t.version = t.version + 1
RETURN t
"""

RENEW_LEASE = """
MATCH (t:Task {id: $task_id, status: 'claimed', owner: $actor_id})
WHERE t.lease_until >= $now
SET t.lease_until = $lease_until, t.version = t.version + 1
RETURN t
"""

COMPLETE_TASK = """
MATCH (t:Task {id: $task_id, status: 'claimed', owner: $actor_id})
SET t.status = 'done', t.done_at = $now, t.version = t.version + 1
RETURN t
"""

RELEASE_TASK = """
MATCH (t:Task {id: $task_id, status: 'claimed', owner: $actor_id})
SET t.status = 'open', t.owner = '', t.lease_until = 0, t.version = t.version + 1
RETURN t
"""

GET_TASK = """
MATCH (t:Task {id: $task_id})
RETURN t
"""

TASK_BLOCKERS = """
MATCH (t:Task {id: $task_id})-[:DEPENDS_ON]->(d:Task)
WHERE d.status <> 'done'
RETURN d.id, d.goal, d.status
"""

# Tasks whose dependencies are all done.
READY_TASKS = """
MATCH (t:Task {status: 'open'})
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task) WHERE d.status <> 'done'
WITH t, count(d) AS blockers
WHERE blockers = 0
RETURN t
ORDER BY t.created_at
"""

# Open decisions by someone else about any of the given artifacts.
OPEN_DECISIONS_FOR_ARTIFACTS = """
MATCH (d:Decision)-[:ABOUT]->(a:Artifact)
WHERE a.path IN $paths AND d.status IN ['open', 'tainted'] AND d.author <> $actor_id
RETURN d, a.path
"""

# Live leases on tasks that touch any of the given artifacts, held by someone else.
LIVE_LEASES_FOR_ARTIFACTS = """
MATCH (t:Task {status: 'claimed'})-[:TOUCHES]->(a:Artifact)
WHERE a.path IN $paths AND t.owner <> $actor_id AND t.lease_until >= $now
RETURN t, a.path
"""

# Other unfinished tasks with the same normalized goal.
DUPLICATE_TASKS = """
MATCH (t:Task)
WHERE t.goal_key = $goal_key AND t.status IN ['open', 'claimed'] AND t.id <> $exclude_id
RETURN t
"""

# Everything derived (transitively) from a root, per root label.
BLAST_FROM_DECISION = """
MATCH (root:Decision {id: $id})<-[:BASED_ON*1..8]-(d:Decision)
RETURN DISTINCT d
"""

BLAST_FROM_FINDING = """
MATCH (root:Finding {id: $id})<-[:BASED_ON*1..8]-(d:Decision)
RETURN DISTINCT d
"""

# What a decision was based on (transitively), decisions and findings.
WHY_DECISIONS = """
MATCH (d:Decision {id: $id})-[:BASED_ON*1..8]->(s:Decision)
RETURN DISTINCT s
"""

WHY_FINDINGS = """
MATCH (d:Decision {id: $id})-[:BASED_ON*1..8]->(s:Finding)
RETURN DISTINCT s
"""

# Recent non-note decisions by others about files near the one being edited (same directory
# subtree) or explicitly related (imported). Excludes the file itself: same-file collisions are
# reported by the stricter queries above.
RECENT_CHANGES_NEARBY = """
MATCH (d:Decision)-[:ABOUT]->(a:Artifact)
WHERE d.author <> $actor_id AND d.status IN ['open', 'tainted'] AND d.kind <> 'note'
  AND coalesce(d.updated_at, d.created_at) >= $since
  AND a.path <> $path AND (a.path STARTS WITH $prefix OR a.path IN $near)
RETURN d, a.path
ORDER BY coalesce(d.updated_at, d.created_at) DESC
LIMIT 20
"""

ALL = {
    "RECENT_CHANGES_NEARBY": RECENT_CHANGES_NEARBY,
    "CLAIM_TASK": CLAIM_TASK,
    "RENEW_LEASE": RENEW_LEASE,
    "COMPLETE_TASK": COMPLETE_TASK,
    "RELEASE_TASK": RELEASE_TASK,
    "GET_TASK": GET_TASK,
    "TASK_BLOCKERS": TASK_BLOCKERS,
    "READY_TASKS": READY_TASKS,
    "OPEN_DECISIONS_FOR_ARTIFACTS": OPEN_DECISIONS_FOR_ARTIFACTS,
    "LIVE_LEASES_FOR_ARTIFACTS": LIVE_LEASES_FOR_ARTIFACTS,
    "DUPLICATE_TASKS": DUPLICATE_TASKS,
    "BLAST_FROM_DECISION": BLAST_FROM_DECISION,
    "BLAST_FROM_FINDING": BLAST_FROM_FINDING,
    "WHY_DECISIONS": WHY_DECISIONS,
    "WHY_FINDINGS": WHY_FINDINGS,
}
