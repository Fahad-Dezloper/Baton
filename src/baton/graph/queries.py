"""Named, parameterized Cypher. Callers never build Cypher from model output.

Every query here is a SKETCH until Phase 0/1 verifies it against a live FalkorDB.
"""

# Atomic lease claim. Writes serialize per graph, so at most one caller gets a row back.
CLAIM_TASK = """
MATCH (t:Task {id: $task_id})
WHERE t.status = 'open'
   OR (t.status = 'claimed' AND t.lease_until < $now)
SET t.status = 'claimed',
    t.owner = $actor_id,
    t.lease_until = $lease_until,
    t.version = t.version + 1
RETURN t
"""

# Tasks whose dependencies are all done.
READY_TASKS = """
MATCH (t:Task {status: 'open'})
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task) WHERE d.status <> 'done'
WITH t, count(d) AS blockers
WHERE blockers = 0
RETURN t
"""

# Open decisions by someone else about any of the given artifacts.
OPEN_DECISIONS_FOR_ARTIFACTS = """
MATCH (d:Decision {status: 'open'})-[:ABOUT]->(a:Artifact)
WHERE a.path IN $paths AND d.author <> $actor_id
RETURN d, a
"""

# Live leases on tasks that touch any of the given artifacts, held by someone else.
LIVE_LEASES_FOR_ARTIFACTS = """
MATCH (t:Task {status: 'claimed'})-[:TOUCHES]->(a:Artifact)
WHERE a.path IN $paths AND t.owner <> $actor_id AND t.lease_until >= $now
RETURN t, a
"""

# Everything derived from a finding or decision.
BLAST_RADIUS = """
MATCH (root {id: $id})<-[:BASED_ON*1..6]-(d:Decision)
RETURN DISTINCT d
"""

# What a decision was based on.
WHY = """
MATCH (d:Decision {id: $id})-[:BASED_ON*1..6]->(src)
RETURN DISTINCT src
"""

ALL = {
    "CLAIM_TASK": CLAIM_TASK,
    "READY_TASKS": READY_TASKS,
    "OPEN_DECISIONS_FOR_ARTIFACTS": OPEN_DECISIONS_FOR_ARTIFACTS,
    "LIVE_LEASES_FOR_ARTIFACTS": LIVE_LEASES_FOR_ARTIFACTS,
    "BLAST_RADIUS": BLAST_RADIUS,
    "WHY": WHY,
}
