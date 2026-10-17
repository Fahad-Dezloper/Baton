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
git clone <repo-url> baton && cd baton
docker compose up -d && python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/baton doctor && .venv/bin/python demo/run_demo.py
```
Needs Docker, Python 3.10+. Then open http://localhost:3000, select graph `baton_demo` and run the
queries in [`demo/queries.cypher`](demo/queries.cypher). `baton doctor` checks the install and prints
the fix for anything missing; more in [docs/QUICKSTART.md](docs/QUICKSTART.md).

The demo script drives the same hook handlers the plugin uses, with the same payload shapes, and
prints what each session would be told: recorded decisions, a cross-file warning, a same-file
collision, a next-day handoff briefing, and a retraction that taints derived decisions.

## Use with Claude Code
```sh
claude --plugin-dir /path/to/baton/plugin     # use it in any project; hooks + tools, no commands to remember
```
Automatic: a session is briefed on other live sessions and the latest handoff; edits are checked
against other sessions' work; file changes and renames are recorded; interface, config and
dependency changes become decisions on their own (derived deterministically from the edit payload,
no model call); a handoff with the last test result is written when the session stops.

MCP tools (13): create_task, get_ready_tasks, claim_task, renew_lease, complete_task, release_task,
post_decision, check_conflicts, add_finding, why, retract, handoff_export, handoff_import.

Settings (`.baton.json` in the project, or environment): `policy` = `warn` (default) | `ask` |
`deny`; `enabled`; `lease_seconds`; `capture`. `BATON_DISABLED=1` turns it off. **Fails open:** if the
store is unreachable, hooks print nothing and never block the session. Each hook call takes roughly 0.1-0.15 s.

Tests: `.venv/bin/python -B -m unittest discover -s tests -t .` (124 tests, run against a live FalkorDB v4.22.1; also passed on 6.0.2).

## Evaluation (honest summary)
Parallel Claude Code sessions (cheap model) are started at the same moment on one shared checkout
with overlapping tickets. A scripted checker scores whether the combined result is collision-free.
Harness, tasks and checkers: [`evals/`](evals). Write-ups with all caveats:
[docs/RESULTS.md](docs/RESULTS.md) (rounds 1-3), [docs/RESULTS-HELDOUT.md](docs/RESULTS-HELDOUT.md),
[docs/RESULTS-PROVENANCE.md](docs/RESULTS-PROVENANCE.md).

**Collision avoidance.** Levels L1-L5 were tuned on over three rounds, so the fresh result is the
held-out set L8-L10 (written and validated before any run, success metrics stated in advance, plugin
unchanged, 7 attempts per cell):

| | Baseline | Plugin v3 |
|---|---|---|
| Held-out L8-L10, clean runs (of 21) | 15 | **20** |
| Held-out, failed checks per trial | 0.48 | **0.10** |
| Tuned L1-L5, clean runs (of 25) | 12 | 14 |

- Held-out difference: Fisher p = 0.093, failed checks p = 0.108. The pre-stated bar was p < 0.05, so
  **we do not claim an effect**; the direction is favourable and consistent across rounds.
- Known defect: a live-session warning can make a session defer too much. In two L2 trials a session
  saw another session's lease on `db.py`, chose not to edit it, and wrote code calling a function
  that never existed (baseline edited the file in 5/5). Duplicate-ticket tasks (L5) are not solved (0/5).
- Sessions that did nothing outside L5: baseline 0/160, plugin v3 1/94.

**Retraction and handoff** (deterministic, [`evals/provenance/`](evals/provenance)). Retracting a
finding tainted exactly its derived decisions on 25 generated graphs (precision and recall 1.0, ~3 ms).
Grep over a flat notes file matches that only when every note cites its source by id or verbatim
quote (recall 0.65 with mixed citations, 0 with paraphrased ones). The graph is only as good as the
recorded `based_on` links (recall 0.73 if 20% are missing). Handoffs keep tainted and interface
decisions first; beyond ~50 decisions most notes are dropped by the size budget.

The mechanism itself is verified: real warnings reach real concurrent sessions with nothing typed,
with zero hook errors across the evaluation trials.

Limits: small samples, one model, one fixture project, tasks and scorer written by the same author.

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

## Known limits
- Text from one session is shown to other sessions: secrets are redacted by pattern (best effort,
  not a guarantee) and text is flattened and clipped, but treat the shared graph as visible to every
  session in the workspace.
- Sessions in different project directories or git worktrees use separate graphs by default; set
  `BATON_WORKSPACE` to share one. MCP tools expect project-relative paths.
- No password or TLS for a remote FalkorDB yet.

## License
MIT, see [LICENSE](LICENSE).
