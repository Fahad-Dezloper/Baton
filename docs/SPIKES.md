# Phase 0 spike results

Run on 2026-10-15, macOS, Docker Desktop (4 CPUs), falkordb-py 1.8.0, Claude Code 2.1.299.
Raw outputs: `spikes/results/`. Scripts: `spikes/`.

## 0.1 Image and version
| Fact | Value |
|---|---|
| `falkordb/falkordb:latest` | same image id as `v4.22.1`; module version `42201` |
| `6.0.2` tag | exists (no `v` prefix); module version `60002` |
| Pinned in `docker-compose.yml` | `falkordb/falkordb:v4.22.1` |
| `THREAD_COUNT` | 4 (container sees 4 CPUs) |
| Module load args printed by `MODULE LIST` (4.22.1) | `MAX_QUEUED_QUERIES 25`, `TIMEOUT 1000`, `RESULTSET_SIZE 10000` |

Notes
- Earlier research said v6.0.x was the current line. `latest` actually serves 4.22.1. Both
  versions pass the claim test below.
- The load args above matter for load tests: a 25-deep queue and a 1 s timeout.
  Not yet confirmed whether they are enforced the same way in the running instance.

## 0.2 Atomic claim under a real race: VERIFIED
Script: `spikes/race_claim.py`; uses the `CLAIM_TASK` query from `src/baton/graph/queries.py`.

| Scenario (32 workers, 300 rounds each) | Result |
|---|---|
| Fresh open task | exactly 1 winner in 300/300 rounds, version always 1 |
| Expired lease takeover | exactly 1 winner in 300/300 rounds |
| Live (unexpired) lease | 0 winners |
| **Control**: non-atomic read-then-write | double claims in 300/300 rounds (up to 26 "winners") |

- p95 claim latency under 32-way contention: about 1.8 ms.
- On 6.0.2 (16 workers, 100 rounds): same results, including the control.
- The control matters: it shows the harness can detect a race, so the clean result is meaningful.

Caveats: threads in one client process, one server, no replicas, no network faults.

## 0.3 Concurrency model: MEASURED
Scripts: `spikes/write_scaling.py`, `spikes/read_stall.py`. (A first run with tiny writes finished
in 0.03 s and is not used; results below are from the heavier workload.)

| Measure | Result |
|---|---|
| 1 thread, 20k-node writes | 31 writes/s |
| 8 threads, **one** graph | 36 writes/s (about 1.2x: writes serialize) |
| 8 threads, **8 separate** graphs | 76 writes/s (about 2.1x over one graph; ceiling is THREAD_COUNT=4) |
| Read latency during a 1.5M-node write | p50 0.16-0.43 ms (idle baseline 0.2-0.5 ms) |
| Stalls | exactly one read stalled 230-630 ms per large write, 20-50% into the write |

Reading: readers are generally not blocked by a write, and writes to different graphs overlap.
The single mid-write stall is unexplained (cause not investigated). Coordination writes are
tiny, so it is unlikely to matter, but do not claim "readers are never blocked".

## 0.4 Host hooks on the installed version
Probe: `spikes/hooktest/` (a real nested headless session with logged hooks, cheap model, about
1.3 cents per run).

| Question | Result |
|---|---|
| Context injection at session start | VERIFIED: `additionalContext` reached the model |
| Pre-tool `deny` with reason | VERIFIED: tool did not run; model saw and repeated the reason |
| Fields on tool events | `session_id`, `transcript_path`, `cwd`, `tool_name`, `tool_input`, `tool_use_id`, `permission_mode`, `prompt_id`, `effort` |
| Subagent identity | VERIFIED: tool events inside a subagent carry `agent_id` and `agent_type`; the main session's do not. Same `session_id` for both |
| Subagent lifecycle events | `SubagentStart` and `SubagentStop` fire, the latter with `agent_transcript_path` |
| Stop event | has `last_assistant_message`, `transcript_path`, `stop_hook_active` |
| Session end | fires with `reason` |
| Tool name for subagents | `Agent` |

NOT verified yet
- `ask` decision (interactive only; headless sessions cannot prompt)
- the direct MCP tool hook type
- transcript file content shape (the file is not written with session persistence disabled)
- desktop, IDE and web behaviour; plugin install prompts

## 0.5 Decisions
1. **Core is a Python library.** Hooks run a `baton` CLI that calls the core directly.
   Measured cost of a cold hook process (start, connect, one write, one read): about 90 ms
   median, 116 ms max. No daemon until that proves too slow.
2. **Tools go through a stdio MCP server** (Phase 2), sharing the same core.
3. **Pin v4.22.1.** Re-run the integration suite on 6.0.2 in Phase 1.9 before claiming support.
4. **Actor identity = `session_id`, plus `agent_id` for subagents.**
5. **Policy default: warn/ask, deny is opt-in.** Open question: headless runs cannot answer `ask`,
   so the evaluation arm (Phase 5) must use context warnings or `deny` with a reason. Decide in 3.2.
6. **Evaluation arm runner** will launch parallel headless sessions in one checkout with the
   plugin enabled, so hooks (not in-process subagents) are what is being tested.

## Still open
- Transcript shape and decision extraction (Phase 4.1)
- Behaviour of `ask` interactively (Phase 3.2, manual check)
- Cause of the mid-write read stall (low priority)

## Phase 1 results (core library)
- 28 tests, all green on FalkorDB `v4.22.1` and `6.0.2`.
- Final `CLAIM_TASK` (includes the dependency check): exactly one winner in 400/400 rounds at
  32 workers; p95 about 1.9 ms; the non-atomic control double-claimed in 200/200 rounds.
- A test caught a real design flaw: recency-only truncation of a handoff dropped the one
  decision that carried provenance. Fixed by priority ranking (see ARCHITECTURE.md).
- Isolation canary: a fact in one workspace graph is invisible from another; hostile workspace
  names cannot escape the `baton_` prefix.
- Not covered yet: behaviour under network faults or replicas; very large graphs.

## Phase 3 results (host integration)
Identity finding (probe `spikes/identity/`): in a real session, both the hooks and the stdio MCP
server see `CLAUDE_CODE_SESSION_ID`, equal to the `session_id` hooks receive, and both see
`CLAUDE_PROJECT_DIR`. So one actor id and one workspace id are shared by hooks and tools with no
hand-off file. (`CLAUDE_PID` points at the *outer* process, so it is not used.)

Design that follows
- Every session (and subagent: `session/agent_id`) owns an implicit task whose lease is renewed on
  each edit and whose TOUCHES edges list the files changed. Other sessions see it as a live lease.
- Hooks: SessionStart (register + briefing), UserPromptSubmit (goal + duplicate check), PreToolUse
  (conflict check), PostToolUse (record edit / rename), Stop (idempotent handoff), SessionEnd (release).
- Policy default `warn` (injected context; works headless). `ask` and `deny` are opt-in via
  `.baton.json` or `BATON_POLICY`. `BATON_DISABLED=1` turns everything off. Every failure exits 0.

Evidence
- 55 tests green, run twice. Handlers are exercised against live FalkorDB; the CLI is exercised as a
  subprocess, including dead-store (fail open) and disabled modes.
- Real host run, two overlapping sessions, plugin loaded via `--plugin-dir`: B's start was briefed
  that A was working on `app.py`; B's pre-edit received "Possible collision on app.py ... last
  edit 1s ago"; B kept A's function and appended its own, citing the warning.
- Hook latency in the real host: about 60-130 ms per event.

Caveats (important)
- This is one demonstration, not a measurement. The host also has its own guard (a write to an
  existing file needs a prior read), so the run does not isolate baton's effect. Phase 5 does.
- MCP tools need user permission in a host; hooks do not. In the run, B could not record its change
  via the tool because the tool was not pre-approved. Automatic capture (Phase 4) should not depend
  on the model calling tools.
- A first attempt at the overlap test failed to overlap: the host refused a standalone `sleep`.
  Overlap was produced with real sustained work instead.
- Not verified: `ask` interactively, behaviour with compaction/resume, large repos, plugin install
  via a marketplace (only `--plugin-dir` tested).
