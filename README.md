# baton

Shared task, decision and handoff graph for parallel coding sessions, built on **FalkorDB**.

**Hackathon:** WeMakeDevs x FalkorDB "Graph Hacks: Context for AI Agents". **Track 2: Agent Memory and Coordination.**

Parallel sessions on one repository collide silently: one changes a function signature while
another builds on the old one, two sessions pick different storage engines, three sessions
implement the same ticket. And when a session ends, the next one starts from zero.

baton keeps a graph of **who is working on what, what has been decided, and what each decision was
based on**. It installs as a Claude Code plugin (hooks + MCP server): sessions are warned before
they step on each other, decisions are captured from edits with no commands typed, and a handoff
is written when a session stops.

## Why the graph matters
Without FalkorDB there is nothing to ask. The product answers graph questions:
- *Who holds a live lease on a file I am about to edit?* (Task - TOUCHES -> Artifact)
- *What changed in files near or imported by this one?* (Decision - ABOUT -> Artifact)
- *What was this decision based on, and what breaks if that fact is wrong?* (variable-length
  BASED_ON traversals, used for both `why` and retraction)
- *Which tasks are ready, with all dependencies done?* (DEPENDS_ON)
- Claims are atomic because FalkorDB serializes writes per graph (verified with a race test and a
  negative control, [docs/SPIKES.md](docs/SPIKES.md)).

## Data model
One graph per workspace (`baton_<workspace>`), so one workspace cannot address another.

| Node | Key properties |
|---|---|
| `Actor` | id (session id), kind, started_at |
| `Task` | id, goal, goal_key, status (open/claimed/done/released), owner, lease_until, version |
| `Decision` | id, text, kind (interface/config/storage/rename/note/...), status (open/superseded/retracted/tainted), author |
| `Finding` | id, text, source, confidence, status |
| `Artifact` | path |
| `Handoff` | id, note |

| Relationship | Meaning |
|---|---|
| `(Task)-[:DEPENDS_ON]->(Task)` | ordering |
| `(Task)-[:TOUCHES]->(Artifact)` | a session's live footprint |
| `(Actor)-[:DECIDED]->(Decision)` | authorship |
| `(Decision)-[:ABOUT]->(Artifact)` | what a decision concerns |
| `(Decision)-[:BASED_ON]->(Decision \| Finding)` | provenance |
| `(Decision)-[:SUPERSEDES]->(Decision)` | replacement |
| `(Handoff)-[:INCLUDES]->(Task \| Decision \| Finding \| Artifact)` | session handoff packet |

## Key Cypher
All queries are named and parameterized in [`src/baton/graph/queries.py`](src/baton/graph/queries.py);
model output never becomes Cypher.

Atomic claim (at most one caller gets a row; expired leases can be taken over; dependencies must be done):
```cypher
MATCH (t:Task {id: $task_id})
WHERE t.status = 'open' OR (t.status = 'claimed' AND t.lease_until < $now)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task) WHERE d.status <> 'done'
WITH t, count(d) AS blockers WHERE blockers = 0
SET t.status = 'claimed', t.owner = $actor_id, t.lease_until = $lease_until, t.version = t.version + 1
RETURN t
```
Other sessions with a live lease on the files I am about to edit:
```cypher
MATCH (t:Task {status: 'claimed'})-[:TOUCHES]->(a:Artifact)
WHERE a.path IN $paths AND t.owner <> $actor_id AND t.lease_until >= $now
RETURN t, a.path
```
Recent changes by others to files near, or imported by, the one being edited:
```cypher
MATCH (d:Decision)-[:ABOUT]->(a:Artifact)
WHERE d.author <> $actor_id AND d.status IN ['open', 'tainted'] AND d.kind <> 'note'
  AND coalesce(d.updated_at, d.created_at) >= $since
  AND a.path <> $path AND (a.path STARTS WITH $prefix OR a.path IN $near)
RETURN d, a.path ORDER BY coalesce(d.updated_at, d.created_at) DESC LIMIT 20
```
Blast radius of a wrong fact (everything derived from it, transitively), used by `retract`:
```cypher
MATCH (root:Finding {id: $id})<-[:BASED_ON*1..8]-(d:Decision) RETURN DISTINCT d
```

## Try it in two minutes (no model, no API key)
```sh
docker compose up -d                                   # FalkorDB :6379, Browser :3000
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python demo/run_demo.py                      # scripted two-session scenario
```
The script drives the same hook handlers the plugin uses, with the same payload shapes, and prints
what each session would be told: recorded decisions, a cross-file warning, a same-file collision, a
next-day handoff briefing, and a retraction that taints derived decisions. Then open
http://localhost:3000, select graph `baton_demo` and run the queries in
[`demo/queries.cypher`](demo/queries.cypher) to see the graph.

## Use with Claude Code
```sh
claude --plugin-dir ./plugin         # hooks + tools, no commands to remember
```
Automatic: a session is briefed on other live sessions and the latest handoff; edits are checked
against other sessions' work; file changes and renames are recorded; interface, config and
dependency changes become decisions on their own (derived deterministically from the edit payload,
no model call); a handoff with the last test result is written when the session stops.

MCP tools (13): create_task, get_ready_tasks, claim_task, renew_lease, complete_task, release_task,
post_decision, check_conflicts, add_finding, why, retract, handoff_export, handoff_import.

Settings (`.baton.json` in the project, or environment): `policy` = `warn` (default) | `ask` |
`deny`; `enabled`; `lease_seconds`; `capture`. `BATON_DISABLED=1` turns it off. **Fails open:** if the
store is unreachable, hooks print nothing and never block the session. Hooks add roughly 50-130 ms.

Tests: `.venv/bin/python -B -m unittest discover -s tests -t .` (94 tests, run against a live FalkorDB v4.22.1; also passed on 6.0.2).

## Evaluation (honest summary)
Parallel Claude Code sessions (cheap model, 5 attempts per cell) are started at the same moment on one
shared checkout with overlapping tickets. A scripted checker scores whether the combined result is
collision-free. Harness, tasks and checkers: [`evals/`](evals); full write-up and caveats:
[docs/RESULTS.md](docs/RESULTS.md).

| | Baseline | Plugin v1 | Plugin v2 | Plugin v3 |
|---|---|---|---|---|
| Clash-free, L1-L5 (of 25) | 12 | 9 | 11 | 14 |
| Failed checks per trial, L3-L5 | 1.87 | 1.60 | 1.20 | 0.87 |

- The share of fully collision-free trials did **not** change significantly (14/25 vs 12/25, p = 0.78).
- Failed checks per trial fell each round (1.87 to 0.87; post-hoc p = 0.045 after three tuning rounds
  on the same tasks, so treat as suggestive).
- Duplicate-ticket tasks (L5) are not solved (0/5). One level got worse (L2, 3/5 vs 5/5).
- The mechanism itself is verified: real warnings reach real concurrent sessions with nothing typed,
  with zero hook errors in 40 v3 trials.

Limits: small samples, one model, one fixture project, tasks and scorer written by the same author,
three rounds of tuning on the same levels, one level edited after results were seen.

## Layout
```
src/baton/        core library, MCP server, hook entry points
plugin/           Claude Code plugin (manifest, hooks, MCP config)
demo/             scripted scenario and Browser queries
evals/clash/      collision tasks, fixture project and checker
evals/harbor/     containerised runner for the evaluation
docs/             plan, architecture, spikes, results
tests/            unit and integration tests
```

## AI assistance disclosure
This project was designed and built with substantial help from an AI coding assistant (Claude
Code), including code, tests, evaluation harness and documentation. The author directed the work and
reviewed the results; the evaluation numbers above come from runs recorded in this repository.
All data is synthetic (the `shop` fixture) or generated by the runs themselves.

## License
To be decided.
