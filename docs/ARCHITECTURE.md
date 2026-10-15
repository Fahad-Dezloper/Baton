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

## Identity and workspace (Phase 2)
- **Workspace** comes from `BATON_WORKSPACE`, else a hash of the server's working directory. It is
  never a tool argument, so a model cannot address another workspace.
- **Actor** is `BATON_ACTOR` or a random per-process id. Each host session launches its own server
  process, so sessions are distinct actors. Subagents share their parent's process; an optional
  `actor` label qualifies the id (`parent/label`) and is display-only.
- Tool results are plain dicts: `ok`, or `ok:false` with `error` (`not_found`, `invalid`) or
  `degraded:true` + `baton_unavailable` when the store cannot be reached. Connect and query
  timeouts are short (2 s / 5 s) so a tool call cannot hang a session.

## Conventions fixed in Phase 1
- Statuses: task `open|claimed|done`; decision/finding `open|superseded|retracted|tainted`.
- A decision's `kind` is one of `note|rename|interface|config|storage|other`.
- Retraction marks the root `retracted` and every transitive dependent decision `tainted`.
- Conflicts reported: open/tainted decisions by others, live leases by others on the same artifact,
  and duplicate tickets (same normalized goal, unfinished, other owner).
- Handoff export is bounded by item count and characters. When truncating it keeps tainted
  decisions first, then non-note kinds, then newest. (Pure recency dropped important older
  decisions in testing.)

## Failure policy
Fail open. If the graph is unreachable, the host session continues unaffected; coordination
features degrade to no-ops with a visible notice.

## Out of scope
General long-term memory recall, a hosted multi-user service, any UI beyond FalkorDB Browser
until Phase 6.
