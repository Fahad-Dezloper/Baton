# Harbor for the evaluation phase

Source: harborframework.com, docs.harborframework.com (task overview, run-a-job) and the project
README, read 2026-10-15. Harbor was **not installed or run** yet; everything below is from docs.

## What Harbor is
"A framework for running any agent with any model on any task in any sandbox in parallel."
From the Terminal-Bench team. Install: `uv tool install harbor` (or `pip install harbor`).
Agents include Claude Code, OpenHands, Codex CLI. Sandboxes: Docker (local default), Daytona,
Modal and others.

## Task format
```
my-task/
├── instruction.md      what the agent is told
├── task.toml           task configuration (fields not read yet)
├── environment/        Dockerfile (or docker-compose.yaml for multi-container)
├── solution/solve.sh   reference solution
└── tests/test.sh       verifier; writes /logs/verifier/reward.txt (number)
                         or /logs/verifier/reward.json (labelled, multi-dimensional)
```
Multi-step tasks use `steps/step-N/{instruction.md,tests/test.sh,...}`, run in order.

## Running
```
harbor run -p <task-or-dataset-dir> -a claude-code -m <model> -n <concurrent> -k <attempts>
```
`-n` concurrent trials, `-k` attempts per task, `-o` jobs dir, `-e` sandbox, `--ak k=v` agent
settings. Config is a `JobConfig` (`--print-config`, `<job>/config.json`).

## Fit with baton's evaluation
| Need | Harbor | Notes |
|---|---|---|
| Reproducible sandbox per trial | Yes | Docker image per task |
| Repeated runs for rates, not single runs | Yes (`-k`) | what the clash baseline is missing |
| Parallel trials | Yes (`-n`) | |
| Machine-readable score per trial | Yes (`reward.json`) | map each clash check to a key |
| Shareable, rerunnable by judges | Yes | strong for the submission |
| **Several agents concurrently in ONE checkout** | **Not native** | a trial is one agent |
| Injecting an MCP server / plugin into the agent | Unverified | not in the pages read |

The concurrency gap is the important one. Clashes only happen when sessions overlap in time.
Multi-step tasks run steps in sequence, so they do not reproduce a race.

## Proposed use (Phase 5.1 decision)
One trial = one **orchestrator** session inside the sandbox that launches N headless worker
sessions against the shared checkout (with or without baton enabled), waits for them, then the
verifier runs `evals/clash/check.py` and writes `reward.json`. Harbor then supplies repetition,
parallelism, isolation and reporting; baton's harness supplies the overlap.

Arms = two agent configurations of the same task (`baseline`, `plugin`).

## Open questions to settle before committing to this
1. Can Claude Code in a Harbor trial be given a plugin / MCP server config and extra files?
2. Can the orchestrator launch nested headless sessions inside the sandbox (auth, network)?
3. FalkorDB inside the sandbox: single image with the module, or a compose sidecar?
4. Cost: each trial runs 2-6 real sessions; budget `-k` accordingly.
5. `task.toml` timeouts and resource fields (not read).

## Fallback
If Harbor cannot host concurrent sessions, keep `evals/clash` as the runner and use a simple
repeat loop (same checker, same fixture). The headline numbers are the same; only portability
differs.
