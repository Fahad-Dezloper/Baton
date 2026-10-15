# Harbor evaluation: baseline vs baton

Each task is one "clash level": several Claude Code sessions start at the same moment against
one shared checkout in a sandbox, then a verifier checks whether the combined result collides.
Only the agent class differs between arms.

| Arm | Agent | What is enabled |
|---|---|---|
| baseline | `baton_eval.agent:BatonClashBaseline` | nothing (no coordination) |
| plugin | `baton_eval.agent:BatonClashPlugin` | baton hooks + tools |

## One-time setup
```sh
python3 -m venv .venv && .venv/bin/pip install -e . harbor
docker build -t baton-eval:latest -f evals/harbor/image/Dockerfile .
python3 evals/harbor/build_tasks.py            # (re)generate tasks from evals/clash/tasks.json
```

## Subscription auth (no API key, no per-token billing)
```sh
claude setup-token                                   # prints a long-lived token
echo 'CLAUDE_CODE_OAUTH_TOKEN=<token>' > .env.eval   # git-ignored
```

## Run
```sh
export PYTHONPATH=evals/harbor/agent
# infrastructure check, no model calls:
.venv/bin/harbor run -p evals/harbor/tasks/clash-l1 -a baton_eval.agent:BatonClashPlugin \
    -m anthropic/claude-haiku-5-5 --ae BATON_DRY_RUN=yes -n 1 -o evals/harbor/jobs
# real runs: 5 attempts of one level, one arm
.venv/bin/harbor run -p evals/harbor/tasks/clash-l4 -a baton_eval.agent:BatonClashPlugin \
    -m anthropic/claude-haiku-5-5 --env-file .env.eval -k 5 -n 1 -o evals/harbor/jobs
```
Rewards per trial (`verifier/reward.json`): `clash_free` (1/0), `checks_failed`,
`checks_passed_fraction`. Details of each failed check: `verifier/check.json`.

## Notes
- The checker is `evals/clash/check.py` (same one used for the baseline in evals/clash).
- Trials start from a pristine fixture each time (fresh container).
- `-n` is trials in parallel; sessions *within* a trial are always concurrent. Keep `-n 1` on a
  subscription plan to stay inside rate limits.

## Pitfall: scrubbed artifacts
Harbor replaces the *values* of sensitive-looking env keys (names containing KEY, TOKEN, AUTH, ...)
everywhere in saved trial files. A one-character value such as `CLAUDE_FORCE_OAUTH=1` turns every
`1` into `[REDACTED]` and corrupts reward.json. Do not pass such flags through `--ae`; the agent
already refuses API keys and requires the subscription token.
