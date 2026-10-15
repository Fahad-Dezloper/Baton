# Evaluation results, round 1 (plugin v1)

Run: 2026-10-15, 16:35-17:17 IST. Harbor 0.24.0, local Docker sandboxes, one fresh container per
trial. 5 levels x 2 arms x 5 attempts = 50 trials, 150 sessions, cheap model, subscription token.
All sessions of a trial start at the same moment on one shared checkout. Scorer: `evals/clash/check.py`.

## Result

| Level | Sessions | Baseline clash-free | Plugin clash-free | Avg failed checks (baseline / plugin) | Warnings delivered |
|---|---|---|---|---|---|
| L1 easy | 2 | 4/5 | 4/5 | 0.2 / 0.2 | 4 |
| L2 medium | 2 | 5/5 | 4/5 | 0.0 / 0.2 | 3 |
| L3 hard | 3 | 1/5 | 0/5 | 0.8 / 1.0 | 4 |
| L4 very hard | 5 | 2/5 | 1/5 | 1.2 / 0.8 | 7 |
| L5 extreme | 6 | 0/5 | 0/5 | 3.6 / 3.0 | 26 (10 duplicate-request) |
| **All** | | **12/25** | **9/25** | | |

**The plugin did not improve outcomes in this round.** Overall 12/25 vs 9/25 (Fisher exact
two-sided p = 0.57); levels 3-5 only 3/15 vs 1/15 (p = 0.60); no single level differs. With 5 trials
per cell these numbers cannot distinguish "no effect" from a modest effect in either direction.
Average failed checks were lower for the plugin on L4 and L5, higher on L3; also within noise.

## What did work (mechanism)
- 0 hook errors and 0 failed jobs across 50 trials; hooks ran in ~50-130 ms.
- Warnings and briefings were delivered and the sessions acknowledged them (25 of 30 L5 replies,
  22 of 25 L4 replies mention a warning or coordination).
- Delivery is not the same as a better outcome, which is the point of this table.

## Why it did not help (hypotheses, from reading the hook logs; not yet tested)
1. **Simultaneous start.** All sessions begin together, so session-start briefings were nearly
   empty ("session X (no prompt yet)"): context spent, nothing learned.
2. **Same-file scope.** Warnings fire only when two sessions touch the same file. L3's failures are
   cross-file contract mismatches (the report module coded against fields another session had not
   added yet), which no warning mentions.
3. **Non-actionable duplicate warning.** For identical tickets (L5) the text said "coordinate
   before duplicating work", but a session has no way to coordinate; duplicate work persisted in 4/5.
4. **Noise.** Some derived decisions are false positives, e.g. importing the project's own package
   was reported as "added dependency: shop".
5. **Timing.** Decisions are recorded after the edit, so the earliest collisions occur before
   anything is recorded.

## Threats to validity
- n = 5 per cell; one model; one fixture; tickets written by me and designed to provoke clashes.
- L1 baseline was 4/5 here but 0 clashes in the earlier in-process baseline: run-to-run variance
  is real, so single runs are not evidence.
- Plugin hooks add latency and context, which can themselves change behaviour.
- Fixes motivated by this data and tested on the same levels would risk overfitting; a held-out
  set of new levels is needed before claiming an improvement.

Raw per-trial evidence: `evals/harbor/jobs/` (not committed; `evals/harbor/results/SUMMARY.md` is).
