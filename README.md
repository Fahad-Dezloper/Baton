# baton

Shared task, decision and handoff graph for parallel coding sessions, backed by FalkorDB.

Parallel sessions on one repository collide silently: one renames a module while another
imports it, two people pick different storage engines, three sessions implement the same
ticket. And when a session ends, the next one starts from zero.

baton keeps a small graph of **who is working on what, what has been decided, and what depends on
what**, so sessions can check before they act and pick up where the last one stopped.

> Status: core library done (Phase 1). Server and host integration are next. See [docs/PLAN.md](docs/PLAN.md) for the phased build and
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

## Host integration
Works with Claude Code through hooks plus an MCP server (Phase 3).

## License
To be decided.
