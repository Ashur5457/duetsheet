"""Tests for "Ask the agent to revise": /api/revise, /api/agent, wait, agent-status, annotations.
Usage: python tests/test_agent.py      (from the repository root)"""
import http.server, json, os, pathlib, shutil, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix='duetsheet-agent-'))
os.environ['DUETSHEET_RUN_DIR'] = str(TMP / 'run')   # before the import: RUN_DIR is read once
os.environ['DUETSHEET_HABITS_DIR'] = str(TMP / 'habits')
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
import duetsheet as D  # noqa: E402

fails = []


def ok(cond, what):
    print(('  ok   ' if cond else '  FAIL ') + what)
    if not cond:
        fails.append(what)


def cli(*args, **kw):
    return subprocess.Popen([sys.executable, str(REPO / 'duetsheet.py'), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', env=os.environ, **kw)


def run(*args):
    p = cli(*args)
    out, _ = p.communicate(timeout=60)
    return p.returncode, out


def main():
    try:
        root = TMP / 'demo'
        shutil.copytree(REPO / 'examples' / 'demo-project', root)
        proj = root
        rep = json.loads((proj / 'report.json').read_text(encoding='utf-8'))
        rep['annotations'] = {
            'a1': {'id': 'a1', 'no': 1, 'target': {'kind': 'point', 'blockId': 'b-fig1', 'rowId': 3}, 'tags': ['use-log-scale'], 'text': 'why so low?', 'status': 'open', 'createdAt': '2026-09-24T00:00:00.000Z'},
            'a2': {'id': 'a2', 'no': 2, 'target': {'kind': 'lasso', 'blockId': 'b-fig2', 'space': 'data', 'xKey': 'a', 'yKey': 'b', 'polygon': [[0, 0], [1, 1], [0, 1]],
                                                   'enclosed': list(range(1, 41))}, 'tags': ['how-computed'], 'text': 'cluster', 'status': 'open', 'from': 'view',
                   'createdAt': '2026-09-24T00:00:01.000Z'},   # a question asked while reading
            'a3': {'id': 'a3', 'no': 3, 'target': {'kind': 'block', 'blockId': 'b-intro'}, 'tags': [], 'text': 'done one', 'status': 'done', 'createdAt': '2026-09-24T00:00:02.000Z'}}
        rep['annotations']['a1']['thread'] = [{'by': 'claude', 'text': 'It is the random start.', 'at': 'x'}, {'by': 'user', 'text': 'Then say so in the caption.', 'at': 'y'}]
        rep.setdefault('style', {})['writing'] = {'rules': [{'text': 'Conclusion first.'}, {'text': 'Numbers with units.'}]}
        (proj / 'report.json').write_text(json.dumps(rep, ensure_ascii=False), encoding='utf-8')

        print('annotations')
        code, out = run('annotations', str(root))
        j = json.loads(out)
        ok(code == 0 and j['open'] == 2, 'two open annotations, the done one left out')
        a1, a2 = j['annotations']
        ok(a1['block']['id'] == 'b-fig1' and a1['dataset']['id'] == 'exp' and a1['targetRows'] == [{'dataset': 'exp', **r} for r in rep['datasets']['exp']['rows'] if r['id'] == 3], 'point: block, dataset and the row')
        ok(len(a2['targetRows']) == 30 and a2['targetRowsNote'] == '10 more rows not shown', 'lasso: 30 rows and a note')
        ok(a2['annotation'].get('from') == 'view' and a2['annotation']['tags'] == ['how-computed'], 'a question asked while reading keeps from and its question tag')
        ok('rows' not in json.dumps(a1['dataset']) or isinstance(a1['dataset']['rows'], int), 'dataset rows are a count, not the data')
        ok(len(out) < 20000, f'compact output ({len(out)} characters)')
        ok(a1['annotation']['thread'][-1]['text'] == 'Then say so in the caption.', 'the conversation comes with the annotation')
        ok(j['writingRules'] == ['Conclusion first.', 'Numbers with units.'], 'the confirmed writing rules come along')
        code, out = run('check', str(root))
        ok(code == 0, 'a report with a thread and writing rules checks OK')
        bad = json.loads((proj / 'report.json').read_text(encoding='utf-8'))
        bad['annotations']['a1']['thread'] = [{'by': 'robot', 'text': 'x'}]
        bad['style']['writing'] = {'rules': 'be brief'}
        (proj / 'report.json').write_text(json.dumps(bad), encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 1 and 'annotations.a1.thread must be' in out and 'style.writing must be' in out, 'a bad thread and bad rules are errors')
        (proj / 'report.json').write_text(json.dumps(rep, ensure_ascii=False), encoding='utf-8')

        print('several series and file requests')
        two = json.loads(json.dumps(rep))
        two['datasets']['exp2'] = {**two['datasets']['exp'], 'id': 'exp2', 'title': 'second'}
        c = two['blocks']['b-fig2']['chart']
        c['series'] = [{'dataset': c['dataset'], 'x': c['x'], 'y': c['y'], 'label': 'first'}, {'dataset': 'exp2', 'x': 'a', 'y': 'b', 'label': 'second'}]
        two['annotations']['a2']['target'].update(enclosed=[1, 2], enclosedBy={'exp': [1, 2], 'exp2': [5]})
        two['annotations']['a4'] = {'id': 'a4', 'no': 4, 'target': {'kind': 'block', 'blockId': 'b-fig2'}, 'tags': ['add-data-files'], 'text': 'one series per file',
                                    'files': ['data/cycle1-runs.csv', 'data/cycle2-runs.csv'], 'status': 'open', 'createdAt': '2026-09-24T00:00:03.000Z'}
        (proj / 'report.json').write_text(json.dumps(two, ensure_ascii=False), encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 0, 'a chart with two series and a file request checks OK')
        j2 = json.loads(run('annotations', str(root))[1])
        lasso = [x for x in j2['annotations'] if x['annotation']['id'] == 'a2'][0]
        ok([d['id'] for d in lasso['datasets']] == ['exp', 'exp2'] and [(r['dataset'], r['id']) for r in lasso['targetRows']] == [('exp', 1), ('exp', 2), ('exp2', 5)],
           'annotations: both datasets and the rows of each series')
        req = [x for x in j2['annotations'] if x['annotation']['id'] == 'a4'][0]
        ok(req['annotation']['files'] == ['data/cycle1-runs.csv', 'data/cycle2-runs.csv'] and req['annotation']['tags'] == ['add-data-files'], 'the file request comes with its files')
        c['series'][1]['y'] = 'nope'
        two['annotations']['a4']['files'] = ['../../outside.csv']
        (proj / 'report.json').write_text(json.dumps(two, ensure_ascii=False), encoding='utf-8')
        code, out = run('check', str(root))
        ok(code == 1 and 'chart.series[1].y "nope" is not a column' in out and 'annotations.a4.files: "../../outside.csv" is outside' in out, 'bad series column and outside file are errors')
        (proj / 'report.json').write_text(json.dumps(rep, ensure_ascii=False), encoding='utf-8')

        print('wait without a launcher')
        code, out = run('wait', str(root))
        ok(code == 3 and 'LAUNCHER NOT RUNNING' in out, 'exits 3 and says how to start it')

        print('launcher endpoints')
        D.Handler.root, D.Handler.token, D.Handler.prints = root, 'b' * 32, None
        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), D.Handler)
        D.Handler.port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        D.write_json(D.agent_file(proj, 'launcher.json'), {'at': D.now_iso(), 'pid': os.getpid()})   # what serve() does every 5 s
        base = f'http://127.0.0.1:{D.Handler.port}'
        H = {'X-Duetsheet-Token': 'b' * 32, 'Content-Type': 'application/json'}
        get = lambda p: json.loads(urllib.request.urlopen(urllib.request.Request(base + p, headers=H)).read())
        post = lambda p, body, h=H: json.loads(urllib.request.urlopen(urllib.request.Request(base + p, data=json.dumps(body).encode(), headers=h, method='POST')).read())
        st = get('/api/agent')
        ok(st == {'listening': False, 'request': None, 'status': None}, 'nobody listening, no request')
        info = get('/api/info')
        ok(info['root'] == str(root) and info['app'], 'info has the folder and the app path (for the copyable prompt)')
        for bad in ({'kind': 'rm -rf', 'open': 1}, {'kind': 'revise', 'open': 'x'}):
            try:
                post('/api/revise', bad)
                ok(False, f'refused {bad}')
            except urllib.error.HTTPError as e:
                ok(e.code == 400, f'refused {bad}')
        try:
            post('/api/revise', {'open': 1}, {'Content-Type': 'application/json'})
            ok(False, 'no token refused')
        except urllib.error.HTTPError as e:
            ok(e.code == 403, 'no token refused')

        print('personal habits and show in folder')
        ok(get('/api/personal') == {'profile': None, 'writing': None}, 'no personal habits yet')
        req = urllib.request.Request(base + '/api/personal', data=json.dumps({'profile': {'font': {'size': 7}}, 'writing': {'rules': [{'text': 'Conclusion first.'}]}}).encode(),
                                     headers=H, method='PUT')
        urllib.request.urlopen(req)
        p = get('/api/personal')
        ok(p['profile']['font']['size'] == 7 and p['writing']['rules'][0]['text'] == 'Conclusion first.' and (TMP / 'habits' / 'writing.json').is_file(),
           'saved to the personal folder and read back')
        for body, code_ in (({'path': '../../x'}, 403), ({'path': 'data/none.csv'}, 404), ({}, 400)):
            try:
                post('/api/reveal', body)
                ok(False, f'reveal {body}')
            except urllib.error.HTTPError as e:
                ok(e.code == code_, f'reveal {body} -> {e.code}')

        print('request before an agent listens: wait picks it up at once')
        st = post('/api/revise', {'kind': 'revise', 'open': 2})
        ok(st['request']['open'] == 2 and st['request']['kind'] == 'revise' and not st['listening'], 'request stored, nobody listening')
        t0 = time.time()
        code, out = run('wait', str(root))
        ok(code == 0 and 'REVISE REQUESTED: 2 open annotation(s)' in out and time.time() - t0 < 5, 'wait returns at once: ' + out.strip().splitlines()[-1][:80])

        print('agent-status')
        code, out = run('agent-status', str(root), 'working', '--note', 'reading 2 comments')
        st = get('/api/agent')
        ok(code == 0 and st['status']['state'] == 'working' and st['status']['note'] == 'reading 2 comments', 'working shown to the page')
        run('agent-status', str(root), 'done')
        ok(get('/api/agent')['status']['state'] == 'done', 'done shown to the page')
        code, out = run('agent-status', str(root), 'sleeping')
        ok(code == 1 and 'usage' in out, 'unknown state refused')

        print('an agent listening, then a new request')
        p = cli('wait', str(root))
        time.sleep(2)
        ok(get('/api/agent')['listening'], 'the page sees a listening agent')
        ok(p.poll() is None, 'wait keeps waiting while nothing is requested')
        st = post('/api/revise', {'kind': 'revise', 'open': 1})
        ok(st['status'] is None, 'the old status does not belong to the new request')
        out, _ = p.communicate(timeout=10)
        ok(p.returncode == 0 and 'REVISE REQUESTED: 1 open annotation(s)' in out, 'wait wakes up on the new request')
        time.sleep(0.2)
        ok(not get('/api/agent')['listening'], 'not listening once wait has returned')

        print('launcher stops while an agent waits')
        run('agent-status', str(root), 'done')
        p = cli('wait', str(root))
        time.sleep(1.5)
        D.write_json(D.agent_file(proj, 'launcher.json'), {'at': D.iso_ms((time.time() - 60) * 1000)})
        out, _ = p.communicate(timeout=10)
        ok(p.returncode == 3 and 'LAUNCHER STOPPED' in out, 'wait exits 3 when the launcher is gone')
        httpd.shutdown()

        print('init-agent')
        own = 'Mine: the section between `<!-- duetsheet:start -->` and `<!-- duetsheet:end -->` is managed.\n'
        (root / 'CLAUDE.md').write_text(own, encoding='utf-8')
        run('init-agent', str(root))
        run('init-agent', str(root))
        c, g = (root / 'CLAUDE.md').read_text(encoding='utf-8'), (root / 'AGENTS.md').read_text(encoding='utf-8')
        ok(c.startswith(own), 'own text that mentions the markers is kept')
        ok(c.count('\n' + D.MARK_START + '\n') == 1 and c.count('## Duetsheet report') == 1, 'one section after two runs')
        ok(g.count('## Duetsheet report') == 1 and 'wait' in g, 'AGENTS.md has the same section')

        print('files stay out of the project')
        ok(not (proj / 'agent').exists() and D.agent_file(proj, 'x').parent.parent == TMP / 'run', 'agent files under the run folder: ' + D.agent_file(proj, 'x').parent.name)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f'\n{len(fails)} failure(s)' if fails else '\nall passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
