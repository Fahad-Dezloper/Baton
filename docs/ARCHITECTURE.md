# Architecture (draft)

Items marked **ASSUMED** are verified in Phase 0 before anything depends on them.

## Shape
```
host session(s) ──hooks──▶ baton CLI ─┐
        │                              ├──▶ baton core ──▶ FalkorDB (one graph per workspace)
        └──MCP tools──▶ baton server ──┘
```
Core is a plain library. The CLI (hooks) and the MCP server are thin shells over it.

## Graph model
Nodes
- `Actor {id, kind, started_at}`: a session or subagent
- `Task {id, goal, status, owner, lease_until, version, created_at}`
- `Decision {id, text, status, author, created_at}`
- `Finding {id, text, source, confidence, created_at}`
- `Artifact {path}`: a file, module or config surface
- `Handoff {id, summary, created_at}`

Relationships
- `(Task)-[:DEPENDS_ON]->(Task)`
- `(Task)-[:TOUCHES]->(Artifact)`
- `(Actor)-[:DECIDED]->(Decision)`
- `(Decision)-[:ABOUT]->(Artifact)`
- `(Decision)-[:BASED_ON]->(Decision|Finding)`
- `(Decision)-[:SUPERSEDES]->(Decision)`
- `(Handoff)-[:INCLUDES]->(Decision|Finding|Artifact|Task)`

Leases live on the `Task` node (`owner`, `lease_until`, `version`) so a claim is one atomic query.

## Key behaviours
- **Atomic claim**: a single `MATCH … WHERE … SET … RETURN` so writes serialized per graph give
  exactly one winner. **VERIFIED** in Phase 0.2 (see SPIKES.md).
- **Conflict check**: open decisions or live leases touching the same artifacts, authored by someone else.
- **Retraction**: reverse traversal over `BASED_ON` from a finding or decision.
- **Handoff**: bounded neighbourhood of a task (decisions, findings, artifacts, open questions), not a transcript.
- **Isolation**: workspace → graph name, chosen from authenticated context, never from model output.

## Failure policy
Fail open. If the graph is unreachable, the host session continues unaffected; coordination
features degrade to no-ops with a visible notice.

## Out of scope
General long-term memory recall, a hosted multi-user service, any UI beyond FalkorDB Browser
until Phase 6.
