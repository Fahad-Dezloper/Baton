# Clash tests: do parallel agents collide?

A repeatable harness. Same fixture, same tickets, same checker; only the *arm* changes.
Arm `baseline` = no coordination. Arm `plugin` = run again once the graph plugin exists.

## Layout
```
fixture/        pristine "shop" Python package every level starts from
tasks.json      the tickets (and the prompt wrapper) given to each agent
check.py        scores a finished level:  python3 -B check.py <L1..L5> <dir>
setup_level.sh  creates runs/<arm>/<level> from the fixture + git snapshot
runs/<arm>/Lx   the working copies the agents edited
results/<arm>/  one JSON per level + BASELINE.md summary
```

## How to run an arm
1. `./setup_level.sh <arm> L1` ... `L5` (one working copy per level).
2. For each level, start its agents **at the same time**, each given the `wrapper` from
   `tasks.json` with `{DIR}` = that level's directory and `{TICKET}` = its ticket.
   Agents see only their own ticket (like separate sessions would).
3. When all agents have finished: `python3 -B check.py Lx runs/<arm>/Lx > results/<arm>/Lx.json`.

## Levels
| Level | Agents | What can clash |
|---|---|---|
| L1 Easy | 2 | two functions added to one file |
| L2 Medium | 2 | storage rewrite vs a feature that reads storage |
| L3 Hard | 3 | discount, tax and report must agree on unspecified internals |
| L4 Very hard | 5 | module rename + feature + tests + config change + logging |
| L5 Extreme | 6 | 3 identical tickets, a signature change, 2 contradictory requirements |

## Metrics
`clash_free` (bool) and `clash_count` = number of failed checks, with a typed list
(`lost_update`, `overwritten_work`, `contract_mismatch`, `broken_imports`, `stale_reference`,
`duplicate_work`, `orphaned_work`, `requirement_unmet_*`, ...).
**Note:** `clash_count` counts failed checks, not root causes: one root cause can fail several
checks (see L4). Compare arms on `clash_free` per level and on the list of root causes in BASELINE.md.

## Caveats (read before comparing arms)
- Checker v2. It was tightened twice *after* seeing baseline output because it missed overwritten
  work (L2, L5). All baseline numbers were re-scored with the final checker. Use the same
  `check.py` for every arm.
- One run per level. LLM agents are non-deterministic; a clean single run is not proof.
  Re-run each level several times per arm before claiming a difference.
- Agents are the same model/config in every arm; record it when you run the plugin arm.
- The checker runs agent-written code inside a cleaned temp copy.
- Agents that run tests in the shared checkout can leave data files behind; the checker deletes
  data files in its copy, so leftover state cannot fake persistence.
