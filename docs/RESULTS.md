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

---

# Round 2: plugin v2 and two held-out levels

Run: 2026-10-15, 17:30-17:59 IST. Same infrastructure and scorer. Plugin v2 = changes motivated by
the round-1 failure analysis (code tagged `round1-plugin-v1` for v1). Levels 6 and 7 were written
and their checkers validated against reference solutions *before* any v2 result existed, and v2
was not tuned on them. L1-L5 baseline numbers are reused from round 1.

## What changed in v2
1. Before an edit, show other sessions' recent interface/config/storage/rename changes to nearby
   or imported files (cross-file digest).
2. Duplicate requests: the session that started first proceeds; later ones are told to stand down.
3. Session-start briefings are suppressed unless they contain something substantive.
4. Importing the project's own package is no longer reported as a new dependency.

## Clash-free trials (out of 5)

| Level | Baseline (r1) | Plugin v1 (r1) | Plugin v2 (r2) | Failed checks per trial: base / v1 / v2 |
|---|---|---|---|---|
| L1 | 4 | 4 | 4 | 0.2 / 0.2 / 0.2 |
| L2 | 5 | 4 | 4 | 0.0 / 0.2 / 0.2 |
| L3 | 1 | 0 | 1 | 0.8 / 1.0 / 0.8 |
| L4 | 2 | 1 | 2 | 1.2 / 0.8 / 0.6 |
| L5 | 0 | 0 | 0 | 3.6 / 3.0 / 2.2 |
| **L1-L5** | **12/25** | **9/25** | **11/25** | |
| L6 (held-out) | 0 | n/a | 1 | 1.0 / n/a / 2.4 |
| L7 (held-out) | 5 | n/a | 4 | 0.0 / n/a / 0.2 |
| **L6+L7** | **5/10** | n/a | **5/10** | |

(L6/L7 baselines were run in round 2.)

## Statistics (exact tests; small samples)
- Clash-free, L1-L5: v2 vs baseline 11/25 vs 12/25, p = 1.00; v2 vs v1 11/25 vs 9/25, p = 0.77.
- Held-out L6+L7: 5/10 vs 5/10, p = 1.00.
- Failed checks per trial, L3-L5 pooled (15 trials each): baseline 1.87, v1 1.60, v2 1.20
  (v2 vs baseline permutation p = 0.29; v1 vs baseline p = 0.75).

## Reading
- **No demonstrated improvement in clash-free outcomes** from either plugin version, on the tuned
  levels or the held-out ones.
- **A weak, non-significant trend** toward fewer failed checks on the hardest levels
  (1.87 -> 1.60 -> 1.20 pooled), consistent with but not proof of a benefit. It would need more
  trials to confirm or dismiss.
- **No evidence of overall harm**, but see abstention below.

## Abstention (sessions that changed nothing)
Counting replies that say no files were changed:
- Round 1: baseline 7/90 (8%), plugin v1 9/90 (10%).
- Round 2: plugin v2 18/125 (14%); 12 of those are L5, where standing down is the *designed*
  behaviour for duplicate tickets. Outside L5, v2 abstained in 6/95 sessions (about 6%), similar to
  the baseline rates (about 7% outside L5).
- Qualitatively, when plugin-arm sessions did abstain they usually cited a live lease and
  described it as "the same ticket". In L6 two trials lost one session's entire work this way.

## Problems this round exposed (not yet fixed)
1. **Goal text shown to other sessions is the start of the prompt.** With a long shared preamble
   the distinguishing part of each ticket is cut off, so sessions cannot tell different tickets
   apart and may read a collision warning as "someone has my ticket".
2. **Held-out L6 has an under-specified ticket.** Ticket B says "use the project's stock module"
   without naming it, while ticket A creates `shop/inventory.py`. In 2 plugin trials B stopped for
   lack of a module it could not name; the baseline had the same ambiguity. L6 results are
   therefore weaker evidence than L7.
3. **Collision messages can read as an instruction to stop.** The wording "check what the other
   work is doing before overwriting it" invites abstention instead of careful merging.

## Honest summary
The mechanism works end to end and is cheap, but across two rounds and 100 plugin and baseline
trials the evidence does not show that it reduces collisions on these tasks. The most defensible
claims are about the mechanism and the measurement method, not about an outcome improvement.

## Limits
n = 5 per cell; one model; one fixture; tickets and scoring written by the same author; run-to-run
variance is large relative to the effects looked for; abstention was counted with a text pattern.


# Round 3: plugin v3 (fixes for the three problems round 2 exposed)

Run: 2026-10-17, 11:55-12:40 IST. Same infrastructure, scorer and model. Plugin v3 changes:
1. Goal text shown to other sessions keeps the start *and* the end of long prompts (stored up to
   600 characters instead of 200), so a shared preamble no longer hides the ticket.
2. Collision wording now tells the session to read the file as it is, make its change on top of the
   other work and not skip its task, and states that a live session on a file is not "the same
   ticket" unless a "same ticket" line says so.
3. L6 ticket B now names `shop/inventory.py`. **L6 is therefore no longer held out**: it was edited
   after seeing results. The L6 baseline was re-run on the new ticket.
L7 was untouched. Baseline numbers for L1-L5 and L7 are reused from earlier rounds.

## Clash-free trials (out of 5)

| Level | Baseline | Plugin v1 | Plugin v2 | **Plugin v3** |
|---|---|---|---|---|
| L1 | 4 | 4 | 4 | **5** |
| L2 | 5 | 4 | 4 | **3** |
| L3 | 1 | 0 | 1 | **2** |
| L4 | 2 | 1 | 2 | **4** |
| L5 | 0 | 0 | 0 | **0** |
| **L1-L5** | 12/25 | 9/25 | 11/25 | **14/25** |
| L6 (edited ticket; not held out) | 0 (re-run) | n/a | n/a | **2** |
| L7 (held out, unchanged) | 5 | n/a | 4 | **5** |

Failed checks per trial, L3-L5 pooled (15 trials each): baseline 1.87, v1 1.60, v2 1.20, **v3 0.87**.

## Statistics (exact / permutation tests)
- Clash-free, L1-L5: v3 vs baseline 14/25 vs 12/25, Fisher p = 0.78.
- L6: 2/5 vs 0/5, p = 0.44.
- Failed checks, L3-L5 pooled, v3 vs baseline: permutation test p = 0.045 one-sided.

## Reading
- **Clash-free rate: no significant difference.** The best v3 number (14/25) is still within noise
  of baseline (12/25).
- **Failed checks per trial fell in every round** (1.87, 1.60, 1.20, 0.87). The final comparison is
  nominally significant (p = 0.045), but this is the third round of tuning on the same tasks, with
  several metrics examined, so the p-value is optimistic. Treat it as suggestive, not confirmed.
- L5 (duplicate tickets) is still 0/5: failures there are duplicate and orphaned work, which v3 did
  not target.
- L2 got worse (3/5 vs 5/5 baseline); with n = 5 this may be noise, but it was not investigated.
- Not analysed this round: whether abstention decreased after the wording change.
- Plugin hook errors: 0 in 40 trials.

## Defensible claim
"Across three rounds the plugin reduced the number of failed checks per trial on collision-heavy
tasks (1.87 to 0.87, post-hoc p = 0.045) but did not significantly change how often a trial was
fully collision-free."

## Limits
Same as round 2, plus: three rounds of tuning on the same L1-L5 tasks (overfitting risk), L6 edited
after seeing results, no new fixture or model, n = 5 per cell.

