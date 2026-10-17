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
(to be filled in)
