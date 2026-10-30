const { execFileSync } = require('node:child_process')
console.log('RUNTIME_TOKEN_PRESENT=' + (process.env.ACTIONS_RUNTIME_TOKEN ? 'YES' : 'NO'))
console.log('RESULTS_URL_PRESENT=' + (process.env.ACTIONS_RESULTS_URL ? 'YES' : 'NO'))
execFileSync('bash', ['-c', process.env.INPUT_SCRIPT], { stdio: 'inherit', env: process.env })
