# Held-out evaluation (round 4): levels L8-L10, plugin v3 vs baseline

Status of this section: **written before any L8-L10 trial was run.** The levels, checkers and
metrics below were fixed first, validated against reference solutions and broken variants
(`tests/test_checkers.py`, class `HeldOutRound2Tests`), and committed. Results are appended below
the line "Results" only after the runs finish. Plugin code (`src/baton`, `plugin/`) is exactly
v3 as in the main branch; nothing in it was changed on this branch.

## Why this round exists
`docs/RESULTS.md` round 3 tuned the plugin on L1-L5 three times and edited L6 after seeing results.
The honest status there is "no significant clean-run difference; a post-hoc reduction in failed
checks". L8-L10 are new, were designed without looking at any plugin output, and are not edited
after results.

## The levels (fixture: the existing `shop` package, unchanged)
Three sessions per level, all started at the same moment on one shared checkout. Tickets name files
and functions explicitly.

| Level | Collision pattern | Tickets |
|---|---|---|
| L8 | One session renames a function that two other sessions' new code calls by its old name | A: rename `db.get_order` to `load_order` and update all callers. B: new `shop/audit.py` `order_total()` reading with `shop.db.get_order`. C: new `shop.api.order_exists()` reading with `db.get_order`. |
| L9 | A config key changes name and unit while two features read it | A: replace `CONFIG['timeout_seconds']` (30) with `CONFIG['timeout_ms']` (30000). B: `shop/client.py` `get_timeout()` in seconds, reading CONFIG each call. C: `shop/retry.py` `retry_budget_seconds()` = 3 x timeout in seconds, reading CONFIG each call. |
| L10 | Three sessions register entries in one shared registry file that may not exist yet | A, B, C each add one validator (`sku`, `qty`, `email`) to `VALIDATORS` in `shop/validators.py`, which also has `validate(kind, value)`; each ticket restates the full interface and says to create the file if missing. |

None of these is a duplicate of L1-L7: L4 renamed a module and changed config shape but with
different callers; L7 added four functions to one existing file. L8 puts new *callers* of a name that
is being removed, L9 changes a unit (silent wrong value, not an import error), and L10 is a
create-or-extend race on a file that does not exist at the start.

Checkers (`evals/clash/check.py`, functions `L8`, `L9`, `L10`) run behaviour in a clean copy and
also run the project's tests. Validation done before any trial: each accepts a reference solution,
rejects the pristine fixture, and rejects targeted broken variants (stale old name, unit mismatch,
cached config, lost registration, wrong predicate, missing dispatch, second registry, alias left
behind). 108 tests pass.

## Pre-stated metrics (fixed before results)
Primary (one number per arm, levels pooled and per level):
1. **Clean-run rate**: share of trials where every check passes (`clash_free`). Test: two-sided
   Fisher exact, plugin vs baseline, pooled over L8-L10 and per level (per-level tests are
   exploratory and uncorrected).
2. **Failed checks per trial**: mean of `checks_failed`. Test: two-sided permutation test on the
   trial-level counts, pooled over L8-L10.

Secondary: abstention rate (sessions that finished without changing any file), hook errors,
warnings delivered. Pre-stated reading rule: a claim of benefit requires the primary metric 1 *or*
2 to favour the plugin at two-sided p < 0.05 on this held-out set; otherwise the conclusion is "no
detectable effect", whatever the direction of the point estimate. Cells are not re-run to improve
numbers; only trials with an infrastructure failure (no verifier output) are re-run and reported as
such.

## Run plan
Both arms, K = 7 attempts per cell, 3 levels, 42 trials (126 sessions), same model (haiku),
subscription token, one trial at a time. Prefix `eval4`.

---
## Results
Run 2026-10-17, 13:20-13:45 IST, prefix `eval4`, 42 trials, 126 sessions, 0 infrastructure failures
(no trial was re-run), 0 plugin hook errors. Nothing was dropped or re-run.

| Level | Baseline clean | Plugin v3 clean | Failed checks / trial (base / plugin) | Fisher p (two-sided) |
|---|---|---|---|---|
| L8 rename vs old-name callers | 7/7 | 7/7 | 0.00 / 0.00 | 1.00 |
| L9 config key + unit change | 4/7 | 7/7 | 0.57 / 0.00 | 0.19 |
| L10 shared registry file | 4/7 | 6/7 | 0.86 / 0.29 | 0.56 |
| **Pooled** | **15/21 (71%)** | **20/21 (95%)** | **0.48 / 0.10** | **0.093** |

Failed checks per trial, pooled: permutation test (100k shuffles) two-sided p = 0.108.
Baseline failures were `contract_mismatch` x7 (L9: features read the removed `timeout_seconds`
key, KeyError; L10: registry/validator contract) and `lost_update` x3; plugin: one of each.

## Reading, by the pre-stated rule
- Neither primary metric reaches p < 0.05, so the pre-stated conclusion is **no detectable effect**.
- The direction favours the plugin on both metrics (95% vs 71% clean; 0.10 vs 0.48 failed checks),
  and on every level that had room (L8 is a ceiling: both arms 7/7, so it carries no information).
  With 21 trials per arm this is suggestive, not established: p = 0.09 and 0.11, three levels
  examined, one model, one fixture, tickets and checkers by one author.
- This is the first evidence not tuned on, and it points the same way as round 3's post-hoc
  failed-check reduction. It is consistent with a modest real benefit on config/registry-type
  collisions, but does not confirm it.
- Per-level tests are exploratory (uncorrected, n = 7).

## Abstention (sessions that changed no file)
Computed from session transcripts (`evals/harbor/abstention.py`): a session counts as writing if it
made a non-erroring Write/Edit/MultiEdit call or a Bash command that looks like a file mutation.
Heuristic; Bash false positives would undercount abstention.

| Data | Sessions abstaining outside L5 |
|---|---|
| Baseline L1-L4 (round 1) | 0/60 |
| Baseline L6, L7 (rounds 2-3) | 0/50 |
| Plugin v1 L1-L4 | 3/60 (5.0%) |
| Plugin v2 L1-L4, L6, L7 | 4/95 (4.2%) |
| Plugin v3 L1-L4, L6, L7 | 1/94 (1.1%; 1 transcript missing) |
| eval4 baseline L8-L10 | 0/63 |
| eval4 plugin v3 L8-L10 | 0/63 |

On L5 (duplicate tickets, standing down is designed) abstention is baseline 3/30, v1 10/30, v2 13/30,
v3 15/30. So v3's wording change did remove nearly all unwanted abstention outside L5 (the earlier
"about 6% vs 7%" text count overstated the baseline; transcripts show baseline 0%), and it is 0 in
the held-out set.

## The L2 regression (v3 3/5 vs baseline 5/5): a warning-induced mistake, not noise
Both failing trials (DKS5JaG, w938K6B) have the same cause: session B (CSV export) learned that
session A held a live lease on `shop/db.py` and that storage was being changed, and then chose not to
edit `db.py`. It wrote `shop/export.py` calling a `db.list_orders()` that nobody added, and its own
reply says so ("I did not touch db.py ... will fail until the other session adds it"). In all 5
baseline trials B edited `db.py` itself. The 3 clean v3 trials are ones where B did edit `db.py`.
Round 2 had one analogous failure (`all_orders`). So the lease message still induces deference to the
file's owner even after the v3 wording change; reported only, not fixed.

## Conclusion
On three fresh levels the plugin was clean in 20/21 trials against 15/21 for the baseline, but this
is not statistically significant (p = 0.09; failed checks p = 0.11), and one level was a ceiling.
The honest statement: **no significant difference; direction favourable, consistent with round 3's
post-hoc trend; unconfirmed.** Unwanted abstention outside L5 is now about 0-1%. A known cost
remains: lease-induced deference on shared files (L2), which a clean-run table on L8-L10 does not
exercise (each ticket there had an explicit target file). A confirmation would need roughly 40+
trials per arm on further new levels.

## Limits
n = 7 per cell; one model (haiku); one fixture; author wrote tickets and checkers (validated before
running, but L8 turned out too easy for both arms); only one session per level collides on any one
file, so L10 is the only same-file test; abstention is a heuristic.
