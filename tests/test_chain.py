"""Tests for the v0.6 data chain in duetsheet.py (check, step, fingerprints cache, /api/fingerprints).
Usage: python tests/test_chain.py      (from the repository root)"""
import json, os, pathlib, shutil, subprocess, sys, tempfile, threading, time, urllib.request, http.server

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
import duetsheet as D  # noqa: E402

PY = sys.executable
fails = []


def ok(cond, what):
    print(('  ok   ' if cond else '  FAIL ') + what)
    if not cond:
        fails.append(what)


def run(*args):
    r = subprocess.run([PY, str(REPO / 'duetsheet.py'), *args], capture_output=True, text=True, encoding='utf-8')
    return r.returncode, r.stdout + r.stderr


def make_project(tmp):
    root = tmp / 'experiment'
    (root / 'raw' / 'R1').mkdir(parents=True)
    for i in range(3):
        (root / 'raw' / 'R1' / f'ch{i}.csv').write_text(f'x,y\n1,{i}\n2,{i * 2}\n', encoding='utf-8')
    proj = root / 'duetsheet'
    (proj / 'scripts').mkdir(parents=True)
    (proj / 'derived_data').mkdir()
    (proj / 'scripts' / 'make_cells.py').write_text('print("cells")\n', encoding='utf-8')
    (proj / 'scripts' / 'summary.py').write_text('print("summary")\n', encoding='utf-8')
    (proj / 'derived_data' / 'cells.csv').write_text('id,ch,y\n1,0,0\n2,1,1\n3,2,2\n', encoding='utf-8')
    (proj / 'derived_data' / 'summary.csv').write_text('id,mean\n1,1\n', encoding='utf-8')
    fp = D.Fingerprints(proj)
    src = lambda p: {**fp.ref(p), 'importedAt': D.iso_ms(time.time() * 1000), 'parser': 'delimited'}
    rep = {'schema': 'duetsheet/0.5',
           'report': {'meta': {'title': 't', 'order': ['b1', 'b2']}},
           'blocks': {'b1': {'id': 'b1', 'type': 'chart', 'chart': {'kind': 'scatter', 'dataset': 'cells', 'x': 'ch', 'y': 'y'}},
                      'b2': {'id': 'b2', 'type': 'table', 'table': {'dataset': 'summary'}}},
           'datasets': {'cells': {'id': 'cells', 'columns': [{'key': 'id', 'label': 'id'}, {'key': 'ch', 'label': 'ch'}, {'key': 'y', 'label': 'y'}],
                                  'rows': [{'id': 1, 'ch': 0, 'y': 0}], 'source': src('derived_data/cells.csv')},
                        'summary': {'id': 'summary', 'columns': [{'key': 'id', 'label': 'id'}, {'key': 'mean', 'label': 'mean'}],
                                    'rows': [{'id': 1, 'mean': 1}], 'source': src('derived_data/summary.csv')}}}
    (proj / 'report.json').write_text(json.dumps(rep, indent=1), encoding='utf-8')
    return root, proj


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='duetsheet-chain-'))
    try:
        root, proj = make_project(tmp)
        print('0.5 report without steps')
        code, out = run('check', str(root))
        ok(code == 0 and 'OK' in out and 'Data chain' not in out, 'checks OK, no chain summary')

        print('step: record two steps')
        code, out = run('step', str(root), '--script', 'scripts/make_cells.py', '--in', '../raw/*/ch*.csv', '--out', 'derived_data/cells.csv',
                        '--command', 'python scripts/make_cells.py', '--param', 'limit=3', '--param', 'mode=fast')
        ok(code == 0 and 'Recorded step "s-make-cells"' in out, 'records s-make-cells: ' + out.strip().splitlines()[-1])
        code, out = run('step', str(root), '--script', 'scripts/summary.py', '--in', 'derived_data/cells.csv', '--out', 'derived_data/summary.csv')
        ok(code == 0, 'records s-summary')
        rep = json.loads((proj / 'report.json').read_text(encoding='utf-8'))
        s = rep['steps']['s-make-cells']
        ok(rep['schema'] == D.SCHEMA, 'schema raised to ' + D.SCHEMA)
        ok([r['path'] for r in s['inputs']] == ['../raw/R1/ch0.csv', '../raw/R1/ch1.csv', '../raw/R1/ch2.csv'], 'inputs are relative, sorted, / separated')
        ok(s['params'] == {'limit': 3, 'mode': 'fast'}, 'params parsed (numbers as numbers)')
        ok(all(len(r['sha256']) == 64 and r['size'] and r['modified'] for r in s['inputs'] + s['outputs'] + [s['script']]), 'every file has sha256, size, modified')

        print('check: all up to date')
        code, out = run('check', str(root))
        ok(code == 0 and '2 step(s), 2 derived file(s), 3 raw file(s), 2 script(s); all up to date' in out, 'summary line')
        ok('Read ' not in out, 'nothing re-read (size and date match)')

        print('a raw file changes')
        time.sleep(0.05)
        (root / 'raw' / 'R1' / 'ch1.csv').write_text('x,y\n1,9\n', encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 0, 'stale is a warning, not an error')
        ok('step "s-make-cells" needs rerunning: input ../raw/R1/ch1.csv changed' in out, 'direct step is stale')
        ok('step "s-summary" needs rerunning: input derived_data/cells.csv comes from step "s-make-cells"' in out, 'staleness goes downstream to the next step')
        ok('datasets.cells: derived_data/cells.csv comes from step "s-make-cells", which needs rerunning. Used by b1' in out, 'dataset and block named')
        ok('datasets.summary:' in out and 'Used by b2' in out, 'downstream dataset named')
        ok('2 step(s) need rerunning' in out, 'summary counts 2 stale steps')

        print('fingerprint cache')
        code, out = run('check', str(root))
        ok('Read ' not in out, 'second check reads nothing (cache hit): ' + ' | '.join(l for l in out.splitlines() if 'Read' in l))
        cache = json.loads((proj / 'cache' / 'fingerprints.json').read_text(encoding='utf-8'))
        ok('../raw/R1/ch1.csv' in cache, 'cache file has the changed raw file')
        p0 = root / 'raw' / 'R1' / 'ch0.csv'
        os.utime(p0, (time.time() + 60, time.time() + 60))  # touched a minute later, same bytes
        code, out = run('check', str(root))
        ok('Read 1 file(s)' in out and 'ch0.csv changed' not in out, 'a touched file is re-read once and is still the same')
        code, out = run('check', str(root), '--deep')
        ok('Read ' in out and 'Read 1 ' not in out, '--deep re-reads everything')

        print('rerun recorded')
        code, out = run('step', str(root), '--script', 'scripts/make_cells.py', '--in', '../raw/*/ch*.csv', '--out', 'derived_data/cells.csv')
        ok('Replaced step "s-make-cells"' in out, 'same id replaces the record')
        code, out = run('check', str(root))
        ok('needs rerunning' not in out and 'all up to date' in out, 'rerun with the same output bytes: the whole chain is fresh again')

        print('input patterns: new raw files')
        rep = json.loads((proj / 'report.json').read_text(encoding='utf-8'))
        ok(rep['steps']['s-make-cells']['inputPatterns'] == ['../raw/*/ch*.csv'] and rep['steps']['s-summary']['inputPatterns'] == ['derived_data/cells.csv'],
           'step keeps the --in patterns')
        (root / 'raw' / 'R2').mkdir()
        (root / 'raw' / 'R2' / 'ch0.csv').write_text('x,y\n1,1\n', encoding='utf-8')
        (root / 'raw' / 'R2' / 'notes.txt').write_text('not data', encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 0 and 'step "s-make-cells" needs rerunning: 1 new file(s) match its input patterns (../raw/R2/ch0.csv)' in out, 'a new matching file makes the step stale')
        ok('s-summary" needs rerunning' in out and '1 new raw file(s) not used yet' in out, 'downstream stale, summary counts the new file')
        code, out = run('step', str(root), '--script', 'scripts/make_cells.py', '--in', '../raw/*/ch*.csv', '--out', 'derived_data/cells.csv')
        code, out = run('check', str(root))
        ok('new file' not in out and 'all up to date' in out, 're-recording with the new file clears it')
        rep = json.loads((proj / 'report.json').read_text(encoding='utf-8'))
        rep['steps']['s-summary']['inputPatterns'] = ['../../*.csv']
        (proj / 'report.json').write_text(json.dumps(rep), encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 1 and 'input pattern "../../*.csv" is outside the folder "experiment"' in out, 'a pattern outside the folder is an ERROR')
        rep['steps']['s-summary']['inputPatterns'] = ['derived_data/cells.csv']
        (proj / 'report.json').write_text(json.dumps(rep), encoding='utf-8')

        print('derived file edited by hand')
        (proj / 'derived_data' / 'summary.csv').write_text('id,mean\n1,2\n', encoding='utf-8')
        code, out = run('check', str(root))
        ok('output derived_data/summary.csv changed after the step was recorded' in out, 'output change reported')
        ok('datasets.summary: derived_data/summary.csv changed since it was imported' in out, 'dataset import stale')

        print('missing and outside')
        (root / 'raw' / 'R1' / 'ch2.csv').unlink()
        code, out = run('check', str(root))
        ok('input ../raw/R1/ch2.csv is missing' in out, 'missing input reported')
        rep = json.loads((proj / 'report.json').read_text(encoding='utf-8'))
        rep['steps']['s-summary']['inputs'].append({'path': '../../elsewhere.csv', 'sha256': '0' * 64})
        (proj / 'report.json').write_text(json.dumps(rep), encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 1 and 'input "../../elsewhere.csv" is outside the folder "experiment"' in out, 'outside path is an ERROR')
        rep['steps']['s-summary']['inputs'][-1]['path'] = 'C:/data/x.csv'
        (proj / 'report.json').write_text(json.dumps(rep), encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 1 and '"C:/data/x.csv" is outside' in out, 'absolute path is an ERROR')
        rep['steps']['s-summary']['inputs'].pop()
        rep['datasets']['cells']['source']['path'] = '../../x.csv'
        (proj / 'report.json').write_text(json.dumps(rep), encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 1 and 'datasets.cells.source.path "../../x.csv" is outside' in out, 'dataset source outside is an ERROR')

        print('step errors')
        code, out = run('step', str(root), '--in', '../nothing/*.csv', '--out', 'derived_data/cells.csv')
        ok(code == 1 and 'matches no file' in out, 'pattern without files')
        (tmp / 'outside.csv').write_text('x', encoding='utf-8')
        code, out = run('step', str(root), '--in', '../../outside.csv', '--out', 'derived_data/cells.csv')
        ok(code == 1 and 'outside the folder' in out, 'input outside the folder refused')

        print('/api/fingerprints')
        root2, proj2 = make_project(tmp / 'b')
        fp = D.Fingerprints(proj2)
        good = fp.ref('../raw/R1/ch0.csv')
        D.Handler.root, D.Handler.token, D.Handler.prints = root2, 'a' * 32, None
        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), D.Handler)
        D.Handler.port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        body = {'files': [good, {**good, 'sha256': '1' * 64, 'size': 1}, {'path': '../raw/none.csv'}, {'path': '../../x'}, {'path': 'derived_data/cells.csv'}]}
        req = urllib.request.Request(f'http://127.0.0.1:{D.Handler.port}/api/fingerprints', data=json.dumps(body).encode(),
                                     headers={'X-Duetsheet-Token': 'a' * 32, 'Content-Type': 'application/json'}, method='POST')
        res = json.loads(urllib.request.urlopen(req).read())
        ok([r['state'] for r in res] == ['same', 'changed', 'missing', 'outside', 'unknown'], 'states: ' + ', '.join(r['state'] for r in res))
        ok(res[4].get('sha256') and len(res[4]['sha256']) == 64, 'unknown file gets its sha256 back')
        req2 = urllib.request.Request(req.full_url, data=req.data, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            urllib.request.urlopen(req2)
            ok(False, 'no token refused')
        except urllib.error.HTTPError as e:
            ok(e.code == 403, 'no token refused')
        httpd.shutdown()

        print('existing reports')
        code, out = run('check', str(REPO / 'examples' / 'demo-project'))
        ok(code == 0, 'demo-project checks OK: ' + out.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'\n{len(fails)} failure(s)' if fails else '\nall passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
