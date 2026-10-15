# Baseline (no coordination), 2026-10-15

Same worker model in every arm (record it when running the plugin arm). One run per level.
Checker: check.py v2 (re-scored after two tightenings; see README).

| Level | Agents | Clash-free? | Failed checks | Root cause |
|---|---|---|---|---|
| L1 Easy | 2 | **Yes** | 0 | none; small disjoint edits to one file merged fine |
| L2 Medium | 2 | No | 1 | Agent B rewrote `db.py` (JSON) over Agent A's SQLite store; A's work silently replaced, orphan `orders.sqlite3` left. End state works. |
| L3 Hard | 3 | No | 1 | Report agent coded against discount/tax that did not exist yet and hard-coded zeros. Got `{subtotal 9000, discount 0, tax 0}`, expected `{10000, 1000, 720, 9720}`. |
| L4 Very hard | 5 | No | 5 | Two root causes: (1) config agent overwrote `config.py` and dropped the logging agent's `log_level` -> `KeyError` at import breaks api, cancel_order and the whole test suite; (2) tests agent still imports `db` after the rename. |
| L5 Extreme | 6 | No | 5 | Four agents wrote near-identical in-memory limiters in `api.py` (last write wins); the persistent limiter module is orphaned and uncalled; required `client_id` became optional; the two contradictory requirements (persist vs no disk I/O) are both unmet and nobody flagged the contradiction. |

## Summary
- 1 of 5 levels clash-free. Totals: 12 failed checks across 4 levels, from about 7 root causes.
- Pattern: the more agents touch the same files, the worse it gets. Failures are mostly
  **silent**: every agent reported "tests pass" or "NOTICED: none" for its own slice.
- Agents did sometimes notice a problem (L3 report agent, L4 config/rename/cancel agents) but
  had no channel to tell the others; they left it "out of scope".
- Honest limits: single run, same model throughout, tickets written by me, checker tightened
  after seeing output. The level structure is designed to produce clashes; L1 shows it does
  not always.

## What a coordination plugin should change (hypotheses to test, not results)
- L2/L5: warn before overwriting a file another session just changed (conflict check).
- L3: surface "interface not defined yet" and the other agents' pending decisions.
- L4: show that a rename/config change is in flight before others edit dependents.
- L5: detect identical in-flight tickets and contradictory requirements, and flag them.
