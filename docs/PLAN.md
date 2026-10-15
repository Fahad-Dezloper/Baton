# Build plan

Window: Oct 15 → Oct 18 (submissions close Oct 18, 11:59 PM IST). Work is done phase by phase;
each phase ends with an **exit check** that must pass before the next one starts.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

## Phase 0: Foundations and spikes (verify the unknowns)
Goal: replace assumptions with measured facts before building on them.

- [x] 0.1 FalkorDB runs locally via `docker compose up`; pin the image tag in `docker-compose.yml`
- [x] 0.2 Spike: N concurrent `claim` queries on one task; exactly one winner
- [x] 0.3 Spike: write serialization per graph, and whether writes to different graphs overlap
- [x] 0.4 (partly; see SPIKES.md) Spike: host hook behaviours on the installed version: injected context at session start,
      pre-tool `ask`/`deny`, subagent identity field, direct MCP tool hook, what a stop hook can read
- [x] 0.5 Decide transport: stdio vs HTTP for the server, and hook to core call path

Exit check: a written `docs/SPIKES.md` with results; every assumption in `ARCHITECTURE.md` marked
verified or changed. **Done**, with open items listed in SPIKES.md.

## Phase 1: Graph core (library, no network surface)
Goal: all coordination logic as plain, tested Python over FalkorDB.

- [x] 1.1 Idempotent schema bootstrap (indexes, constraints)
- [x] 1.2 Workspace → graph name mapping (one graph per tenant/workspace)
- [x] 1.3 Tasks: create, dependencies, ready frontier
- [x] 1.4 Leases: claim, renew, release, complete (atomic, versioned, expiry)
- [x] 1.5 Decisions: post, supersede, link to artifacts, open/closed status
- [x] 1.6 Conflict detection: overlapping artifacts, in-flight renames/config changes, duplicate tickets
- [x] 1.7 Provenance: findings, `why`, `retract` with blast radius
- [x] 1.8 Handoff: bounded export, import, size budget
- [x] 1.9 Integration tests against live FalkorDB (race test, tenant canary, retraction correctness)

Exit check: `python -m unittest` green against a live instance; race test shows one winner.
**Done**: 28 tests green on FalkorDB v4.22.1 and 6.0.2 (see SPIKES.md, Phase 1 results).

## Phase 2: MCP server
- [x] 2.1 Tool surface and input schemas (`claim_task`, `complete_task`, `get_ready_tasks`,
      `post_decision`, `check_conflicts`, `handoff_export`, `handoff_import`, `why`, `retract`)
- [x] 2.2 Caller identity (session / subagent id) on every call
- [x] 2.3 Error model: fail-open by default, explicit reasons
- [x] 2.4 Packaging and a smoke test over the real protocol

Exit check: a host session can call every tool end to end.
**Done**: 9 new tests incl. real stdio protocol with two server processes; a real host session
created, claimed, decided, checked conflicts and exported a handoff through the tools.

## Phase 3: Host integration (hooks + plugin)
- [ ] 3.1 Session start: register caller, inject a small handoff summary (size-capped, pointer to the rest)
- [ ] 3.2 Pre-edit: conflict check; default to warn/ask, never hard-block, fail open
- [ ] 3.3 Post-edit and stop: record touched artifacts and decisions
- [ ] 3.4 Handoff export on stop (not on session end; the budget there is small)
- [ ] 3.5 Plugin manifest bundling hooks + server; one-command install
- [ ] 3.6 Settings: warn vs block, timeouts, opt-out

Exit check: two real sessions on one repo; a conflict is surfaced with no manual command.

## Phase 4: Automatic capture
- [ ] 4.1 Defensive transcript reader (typed content blocks, async-written file)
- [ ] 4.2 Deterministic decision extraction first; optional model pass behind a flag
- [ ] 4.3 De-duplication and supersede detection

Exit check: decisions recorded without the user typing anything.

## Phase 5: Evaluation
- [ ] 5.0 Decide runner: Harbor vs the local harness (see docs/EVAL-HARBOR.md open questions)
- [ ] 5.1 Port the clash harness (`evals/clash`) and add a `plugin` arm runner
- [ ] 5.2 Repeat each level several times per arm; report rates, not single runs
- [ ] 5.3 Handoff benchmark: tokens and turns to resume vs pasting the transcript
- [ ] 5.4 Race test, tenant canary, retraction correctness
- [ ] 5.5 Results table and charts for the README

Exit check: a results table comparing `baseline` and `plugin` with run counts and caveats.

## Phase 6: Visibility and demo
- [ ] 6.1 Live graph view (FalkorDB Browser queries first; small viewer only if time remains)
- [ ] 6.2 Seeded, scripted two-session scenario with a fallback recording
- [ ] 6.3 Demo script and video

## Phase 7: Ship
- [ ] 7.1 README: install, schema, the key Cypher queries, eval table, limits
- [ ] 7.2 Deployment or full local setup instructions
- [ ] 7.3 Assistance disclosure and track entry
- [ ] 7.4 Blog post
- [ ] 7.5 Submission checklist; submit well before the deadline

## Cut order if behind
1. Live viewer beyond FalkorDB Browser
2. Model-based decision extraction (keep deterministic)
3. Duplicate-ticket detection (keep artifact-overlap conflicts)
4. Cross-workspace sharing (never planned; keep isolation)

Never cut: leases + race test, conflict check, handoff, retraction, baseline vs plugin numbers.

## Rules to keep in mind
- Main work happens during the event window; this scaffold only sets structure.
- Only public, synthetic or own data.
- Disclose assistance in the README.
