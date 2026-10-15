#!/usr/bin/env bash
# Run the collision evaluation: every level, both arms, K attempts each, one trial at a time.
#
#   evals/harbor/run_eval.sh [K] ["L1 L2 L3 L4 L5"] ["baseline plugin"]
#
# Examples
#   evals/harbor/run_eval.sh                 # K=5, all levels, both arms (about 50 trials)
#   evals/harbor/run_eval.sh 3 "L2 L3"       # fewer attempts, two levels
#
# Safe to stop (Ctrl-C) and re-run: finished jobs are skipped.
# Uses your subscription token from .env.eval (no API key). Usage counts against your plan.
set -u
cd "$(dirname "$0")/../.."

K="${1:-5}"
LEVELS="${2:-L1 L2 L3 L4 L5}"
ARMS="${3:-baseline plugin}"
MODEL="${BATON_EVAL_MODEL:-anthropic/claude-haiku-5-5}"
HARBOR=".venv/bin/harbor"

[ -x "$HARBOR" ]            || { echo "missing $HARBOR (run: .venv/bin/pip install -e . harbor)"; exit 1; }
[ -f .env.eval ]            || { echo "missing .env.eval (see evals/harbor/README.md)"; exit 1; }
docker image inspect baton-eval:latest >/dev/null 2>&1 \
                            || { echo "missing image: docker build -t baton-eval:latest -f evals/harbor/image/Dockerfile ."; exit 1; }

export PYTHONPATH="evals/harbor/agent${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p evals/harbor/jobs

total=0; done_n=0; failed=0
for level in $LEVELS; do for arm in $ARMS; do total=$((total+1)); done; done
echo "evaluation: levels=[$LEVELS] arms=[$ARMS] attempts=$K  jobs=$total  model=$MODEL"
echo "started: $(date)"

for level in $LEVELS; do
  lvl="$(echo "$level" | tr 'A-Z' 'a-z')"
  for arm in $ARMS; do
    case "$arm" in
      baseline) agent="baton_eval.agent:BatonClashBaseline" ;;
      plugin)   agent="baton_eval.agent:BatonClashPlugin" ;;
      *) echo "unknown arm: $arm"; exit 1 ;;
    esac
    job="eval-${arm}-${lvl}-k${K}"
    done_n=$((done_n+1))
    if [ -f "evals/harbor/jobs/$job/result.json" ]; then
      echo "[$done_n/$total] skip $job (already finished)"
      continue
    fi
    echo "[$done_n/$total] $job  ($(date +%H:%M:%S))"
    "$HARBOR" run -p "evals/harbor/tasks/clash-$lvl" -a "$agent" -m "$MODEL" \
        --env-file .env.eval \
        -k "$K" -n 1 -o evals/harbor/jobs --job-name "$job" > "evals/harbor/jobs/$job.log" 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
      failed=$((failed+1)); echo "    job exited with code $rc (see evals/harbor/jobs/$job.log)"
    fi
    # one-line progress from the verifier files
    .venv/bin/python evals/harbor/summarize.py "evals/harbor/jobs/$job" --oneline 2>/dev/null
  done
done

echo "finished: $(date)   failed jobs: $failed"
echo
.venv/bin/python evals/harbor/summarize.py "evals/harbor/jobs/eval-*-k${K}"
