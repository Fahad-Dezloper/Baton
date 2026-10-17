# Token and time cost of the plugin

Measured from the recorded trials (Harbor `result.json` and session transcripts). Script:
`evals/harbor/usage.py`. 56 trials per arm over ten collision levels, one cheap model, five or seven
sessions per trial running in parallel. Costs are list-price estimates; a subscription is not billed
per token but its usage is still consumed.

## Result

| Per trial (56 trials each) | Baseline | v3 + MCP tools | v4 + MCP (leaner text) | **Hooks only** |
|---|---|---|---|---|
| Clean runs | 32/56 | 41/56 | 40/56 | **41/56** |
| Output tokens | 7,638 | 9,100 (1.19x) | 8,353 (1.09x) | **7,755 (1.02x)** |
| Cache-read tokens | 343,000 | 470,000 (1.37x) | 420,000 (1.22x) | **343,000 (1.00x)** |
| Turns | 26.1 | 32.1 (1.23x) | 29.3 (1.12x) | **26.0 (0.99x)** |
| Estimated cost | $0.0104 | $0.0136 (1.31x) | $0.0123 (1.19x) | **$0.0108 (1.04x)** |
| Estimated cost per clean run | $0.0181 | $0.0186 | $0.0173 | **$0.0147** |
| Failed checks per trial, L3-L5 | 1.87 | 0.87 | 0.87 | **0.93** |

Hooks-only matches baseline on tokens and turns, keeps the outcome gain of v3 (41/56 vs 32/56,
Fisher p = 0.11, not significant), and is about 19% cheaper per collision-free result.

Per-session duration (from each worker's own timer, levels 1-7): baseline 18.6 s, v3 22.8 s (1.23x),
v4 19.1 s (1.03x), hooks-only 19.6 s (1.06x). Whole-trial wall time is not used because the plugin
arms also start and stop a FalkorDB server inside the timed window, which is test scaffolding.

## Where the overhead came from
- The injected warnings are small: about 800 tokens per trial (median message 620 characters).
- The MCP tool definitions are small too (the first model call is about 450 tokens larger), because
  tools load on demand.
- The cost was redundant tool use. Across 125 sessions with the MCP tools loaded, models called
  `check_conflicts` 105 times and `post_decision` 84 times, plus a tool lookup before the first call.
  The hooks already check before every edit and record changes automatically, and the v3 warning even
  told the model to log changes by hand. Each manual call adds turns, and every turn re-reads the whole
  conversation (cache-read tokens).
- v4 removed the instruction and marked the tools "rarely needed": manual `post_decision` calls fell
  from 0.67 to 0.20 per session, but models still made 0.64 `check_conflicts` calls per session.
- Hooks-only removes the tools from the session entirely. The MCP server stays available as an optional
  add-on (`claude mcp add baton -- .../plugin/bin/baton-mcp`).

## Side effect: fewer deference mistakes
With the tools loaded, a session that saw another session's live lease sometimes decided not to edit the
file at all (L2: 3/5 vs 5/5 for baseline). Hooks-only restored L2 to 5/5 and L3 went from 2/5 to 5/5.
Single levels at n = 5 are noisy, so this is a lead, not a finding.

## Honest limits
- Plugin arms were tuned over several rounds; v4 and hooks-only were chosen after seeing earlier results.
- Rounds 1-3 and the v3/v4 columns measured the plugin with MCP tools; the hooks-only column is the
  product as now shipped.
- Rework needed after a collision is not counted in the token numbers, which favours the plugin.
- Hook latency is about 0.1 s per call (roughly 8 calls per session); not a significant part of the time.
