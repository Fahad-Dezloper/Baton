# baton

Shared task, decision and handoff graph for parallel coding sessions, backed by FalkorDB.

Parallel sessions on one repository collide silently: one renames a module while another
imports it, two people pick different storage engines, three sessions implement the same
ticket. And when a session ends, the next one starts from zero.

baton keeps a small graph of **who is working on what, what has been decided, and what depends on
what**, so sessions can check before they act and pick up where the last one stopped.

> Status: core, MCP server and host integration (hooks plugin) work. Automatic decision capture and the measured evaluation are next. See [docs/PLAN.md](docs/PLAN.md) for the phased build and
> [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the draft design.

## Layout
```
src/baton/        core library, MCP server, hook entry points
plugin/           host integration (manifest, hooks)  [Phase 3]
evals/clash/      reproducible collision tests: baseline vs plugin
docs/             plan and architecture
tests/            unit and integration tests
```

## Run FalkorDB locally
```sh
docker compose up -d      # server on :6379, browser UI on :3000
```

## Evaluation
`evals/clash` holds five levels of parallel-session tasks and a checker. Baseline (no coordination)
results are recorded in `evals/clash/results/baseline/BASELINE.md`. The same levels are re-run with
baton enabled in Phase 5.

## Try the MCP server
```sh
docker compose up -d
pip install -e .
BATON_WORKSPACE=demo baton-mcp      # stdio server
```
Tools: create_task, get_ready_tasks, claim_task, renew_lease, complete_task, release_task,
post_decision, check_conflicts, add_finding, why, retract, handoff_export, handoff_import.

## Use with Claude Code
```sh
docker compose up -d                 # FalkorDB
python3 -m venv .venv && .venv/bin/pip install -e .
claude --plugin-dir ./plugin         # hooks + tools, no commands to remember
```
What happens automatically: a session is briefed on other live sessions and the latest handoff,
edits are checked against other sessions' work, file changes and renames are recorded, and a
handoff is written when the session stops.

Settings (`.baton.json` in the project, or environment):
`policy` = `warn` (default, injects context) | `ask` | `deny`; `enabled`; `lease_seconds`.
`BATON_DISABLED=1` turns it off. If the store is unreachable, hooks do nothing.

## License
To be decided.
