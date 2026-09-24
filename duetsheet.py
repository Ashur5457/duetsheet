#!/usr/bin/env python3
"""Duetsheet launcher: open a report for a data folder in the browser, with no folder picker.

    python duetsheet.py [FOLDER]            start Duetsheet for FOLDER (default: the current folder)
    python duetsheet.py check [FOLDER]      check the report in FOLDER and exit (exit code 1 on errors)
    python duetsheet.py install-skill       install the /duetsheet skill for Claude Code
    python duetsheet.py shortcut [FOLDER]   put a shortcut on the desktop that starts Duetsheet for FOLDER

Where the report lives:
  - If FOLDER contains report.json, FOLDER is the project folder (raw data in FOLDER/data/).
  - Otherwise the report goes into FOLDER/duetsheet/ and FOLDER itself is the raw data folder.
    Raw data files are only read, never written.

The launcher serves duetsheet.html on 127.0.0.1 and lets that page read and write the project
folder. Every request needs a random token that is only given to the browser window it opens.
Problems the page reports are printed here and appended to errors.log in the project folder,
so an agent running this command sees them.

Python 3.8 or later, standard library only.
"""
import argparse, base64, hashlib, hmac, http.server, json, mimetypes, os, pathlib, re, secrets, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, webbrowser

VERSION = '0.5.0'
HERE = pathlib.Path(__file__).resolve().parent
PAGE = HERE / 'duetsheet.html'
SUBDIR = 'duetsheet'
OWN = ('report.json', 'errors.log', 'assets', 'exports', 'habits', 'lang')   # what Duetsheet may write in the project folder
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', SUBDIR}

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def say(*parts):
    print('[duetsheet]', *parts, flush=True)


def project_of(root):
    """(project folder, raw data folder) for a folder the user opened."""
    if (root / 'report.json').is_file():
        return root, root / 'data'
    return root / SUBDIR, root


# ---------------------------------------------------------------- checking a report

STYLE_FIELDS = {'font.family', 'font.size', 'font.label', 'marker', 'line', 'ticks', 'frame', 'grid', 'palette',
                'figure.preset', 'chartDefaults.kind', 'chartDefaults.logY'}


def check_report(project):
    """Return (errors, warnings) for project/report.json, as lists of strings."""
    errors, warnings = [], []
    path = project / 'report.json'
    if not path.is_file():
        return [f'{path} does not exist'], []
    raw = path.read_bytes()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return ['report.json is UTF-16; save it as UTF-8'], []
    if raw[:3] == b'\xef\xbb\xbf':
        warnings.append('report.json starts with a byte order mark (BOM); write plain UTF-8')
        raw = raw[3:]
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        return [f'report.json is not UTF-8: {e}'], warnings

    def no_constants(name):
        raise ValueError(f'{name} is not valid JSON; write null instead (Python: json.dump(..., allow_nan=False))')
    try:
        rep = json.loads(text, parse_constant=no_constants)
    except json.JSONDecodeError as e:
        return [f'report.json line {e.lineno}, column {e.colno}: {e.msg}'], warnings
    except ValueError as e:
        # find where the constant is, for the message
        for i, line in enumerate(text.splitlines(), 1):
            for tok in ('-Infinity', 'Infinity', 'NaN'):
                col = line.find(tok)
                if col >= 0 and line[:col].count('"') % 2 == 0:
                    return [f'report.json line {i}, column {col + 1}: {e}'], warnings
        return [f'report.json: {e}'], warnings

    if not isinstance(rep, dict):
        return ['report.json must be a JSON object'], warnings
    meta = (rep.get('report') or {}).get('meta') if isinstance(rep.get('report'), dict) else None
    if not isinstance(meta, dict):
        errors.append('report.meta is missing: report.json needs {"report": {"meta": {"title": ..., "order": [...]}}}')
        meta = {}
    blocks = rep.get('blocks') or {}
    datasets = rep.get('datasets') or {}
    for name in ('blocks', 'datasets', 'annotations', 'changes', 'rounds', 'examples'):
        if name in rep and not isinstance(rep[name], dict):
            errors.append(f'"{name}" must be an object keyed by document id')
    if not isinstance(blocks, dict):
        blocks = {}
    if not isinstance(datasets, dict):
        datasets = {}

    order = meta.get('order', [])
    if not isinstance(order, list):
        errors.append('report.meta.order must be a list of block ids')
        order = []
    for bid in order:
        if bid not in blocks:
            warnings.append(f'report.meta.order lists "{bid}", which is not in blocks')

    for key, ds in datasets.items():
        where = f'datasets.{key}'
        if not isinstance(ds, dict):
            errors.append(f'{where} must be an object')
            continue
        cols = ds.get('columns')
        rows = ds.get('rows')
        if not isinstance(cols, list) or not all(isinstance(c, dict) and 'key' in c for c in cols):
            errors.append(f'{where}.columns must be a list of {{"key", "label"}}')
            cols = []
        if not isinstance(rows, list):
            errors.append(f'{where}.rows must be a list')
            rows = []
        ids = [r.get('id') if isinstance(r, dict) else None for r in rows]
        if any(not isinstance(i, (int, float)) or isinstance(i, bool) for i in ids):
            errors.append(f'{where}: every row needs a numeric "id"')
        elif len(set(ids)) != len(ids):
            errors.append(f'{where}: row ids must be unique')
        src = ds.get('source')
        if isinstance(src, dict) and src.get('path'):
            f = (project / src['path']).resolve()
            if not f.is_file():
                warnings.append(f'{where}.source.path "{src["path"]}" does not exist (paths are relative to the folder of report.json)')
            elif src.get('sha256') and hashlib.sha256(f.read_bytes()).hexdigest() != src['sha256']:
                warnings.append(f'{where}: {src["path"]} changed since it was imported (sha256 differs)')

    colkeys = {k: {c.get('key') for c in (d.get('columns') or []) if isinstance(c, dict)} for k, d in datasets.items() if isinstance(d, dict)}
    for key, b in blocks.items():
        where = f'blocks.{key}'
        if not isinstance(b, dict):
            errors.append(f'{where} must be an object')
            continue
        if b.get('id') != key:
            errors.append(f'{where}.id must be "{key}"')
        t = b.get('type')
        if t not in ('text', 'chart', 'table', 'image', 'outline'):
            errors.append(f'{where}.type must be text, chart, table, image or outline')
            continue
        if b.get('breakBefore', 'auto') not in ('auto', 'page', 'avoid', 'beside'):
            errors.append(f'{where}.breakBefore must be auto, page, avoid or beside')
        if t in ('chart', 'table'):
            spec = b.get(t)
            if not isinstance(spec, dict):
                errors.append(f'{where}.{t} is missing')
                continue
            ds = spec.get('dataset')
            if ds not in datasets:
                errors.append(f'{where}.{t}.dataset "{ds}" is not in datasets')
                continue
            for f in (('x', 'y', 'color') if t == 'chart' else ('sortBy',)):
                v = spec.get(f)
                if v is not None and v not in colkeys.get(ds, set()):
                    errors.append(f'{where}.{t}.{f} "{v}" is not a column of dataset "{ds}"')
        if t == 'image':
            im = b.get('image')
            if not isinstance(im, dict):
                errors.append(f'{where}.image is missing')
            elif im.get('asset'):
                if not any((project / 'assets').glob(im['asset'] + '.*')):
                    warnings.append(f'{where}: no file assets/{im["asset"]}.* in the project folder')
            elif not str(im.get('src', '')).startswith('data:image/'):
                errors.append(f'{where}.image needs "asset" or a data:image/ "src"')

    for key, a in (rep.get('annotations') or {}).items():
        if not isinstance(a, dict):
            continue
        if a.get('status') not in ('open', 'done'):
            errors.append(f'annotations.{key}.status must be open or done')
        bid = (a.get('target') or {}).get('blockId')
        if bid and bid not in blocks:
            warnings.append(f'annotations.{key} points at block "{bid}", which no longer exists')
    for key, c in (rep.get('changes') or {}).items():
        if isinstance(c, dict) and c.get('by') not in ('user', 'claude'):
            errors.append(f'changes.{key}.by must be user or claude')
    prop = (rep.get('style') or {}).get('proposal') if isinstance(rep.get('style'), dict) else None
    if isinstance(prop, dict):
        for i, r in enumerate(prop.get('rows') or []):
            if not isinstance(r, dict) or r.get('field') not in STYLE_FIELDS:
                warnings.append(f'style.proposal.rows[{i}] has an unknown field and will be ignored')
    return errors, warnings


def run_check(root):
    project, _ = project_of(root)
    errors, warnings = check_report(project)
    for w in warnings:
        say('WARNING', w)
    for e in errors:
        say('ERROR', e)
    if not errors:
        say('OK', project / 'report.json', f'({len(warnings)} warning(s))' if warnings else '')
    return 1 if errors else 0


# ---------------------------------------------------------------- the server

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'Duetsheet/' + VERSION
    root = None       # the folder the user opened
    token = ''
    port = 0

    def log_message(self, *a):
        pass

    # -- helpers
    def send(self, code, body=b'', ctype='text/plain; charset=utf-8', headers=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def allowed(self):
        host = self.headers.get('Host', '')
        if host not in (f'127.0.0.1:{self.port}', f'localhost:{self.port}'):
            self.send(403, 'bad host')
            return False
        return True

    def authorised(self):
        if not hmac.compare_digest(self.headers.get('X-Duetsheet-Token', ''), self.token):
            self.send(403, 'missing or wrong token')
            return False
        return True

    def target(self):
        """Resolve /fs/<path> inside the opened folder. Returns (path, is_dir) or None."""
        rel = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path[len('/fs/'):])
        is_dir = rel.endswith('/') or rel == ''
        parts = [p for p in rel.split('/') if p]
        if any(p in ('.', '..') or '\\' in p or ':' in p for p in parts):
            self.send(400, 'bad path')
            return None
        p = self.root.joinpath(*parts) if parts else self.root
        try:
            p.resolve().relative_to(self.root.resolve())
        except ValueError:
            self.send(400, 'outside the folder')
            return None
        return p, is_dir

    def writable(self, p):
        project, _ = project_of(self.root)
        try:
            rel = p.resolve().relative_to(project.resolve())
        except ValueError:
            return p.resolve() == project.resolve()
        return not rel.parts or rel.parts[0] in OWN

    @staticmethod
    def mtime(p):
        return str(p.stat().st_mtime_ns // 1_000_000)

    # -- methods
    def do_GET(self):
        if not self.allowed():
            return
        path = urllib.parse.urlsplit(self.path).path
        if path in ('/', '/index.html', '/duetsheet.html'):
            return self.send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
        if not self.authorised():
            return
        if path == '/api/info':
            project, data = project_of(self.root)
            return self.send(200, json.dumps({'name': self.root.name, 'version': VERSION, 'layout': 'data-folder' if project != self.root else 'project-folder'}), 'application/json')
        if path.startswith('/fs/'):
            t = self.target()
            if not t:
                return
            p, is_dir = t
            if is_dir:
                if not p.is_dir():
                    return self.send(404, 'not found')
                items = []
                for c in sorted(p.iterdir(), key=lambda c: c.name):
                    if c.name.startswith('.') or c.name.endswith('.duetsheet-tmp'):
                        continue
                    st = c.stat()
                    items.append({'name': c.name, 'kind': 'directory' if c.is_dir() else 'file', 'size': st.st_size, 'mtime': st.st_mtime_ns // 1_000_000})
                return self.send(200, json.dumps(items), 'application/json')
            if not p.is_file():
                return self.send(404, 'not found')
            return self.send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or 'application/octet-stream', {'X-Mtime': self.mtime(p)})
        self.send(404, 'not found')

    def do_HEAD(self):
        if not self.allowed() or not self.authorised():
            return
        if not urllib.parse.urlsplit(self.path).path.startswith('/fs/'):
            return self.send(404)
        t = self.target()
        if not t:
            return
        p, is_dir = t
        ok = p.is_dir() if is_dir else p.is_file()
        self.send(200 if ok else 404, b'', headers={'X-Mtime': self.mtime(p)} if ok else None)

    def do_POST(self):
        if not self.allowed() or not self.authorised():
            return
        path = urllib.parse.urlsplit(self.path).path
        body = self.rfile.read(int(self.headers.get('Content-Length', 0) or 0))
        if path == '/api/log':
            try:
                e = json.loads(body.decode('utf-8'))
            except Exception:
                return self.send(400, 'bad log entry')
            level = str(e.get('level', 'error')).upper()
            msg, detail = str(e.get('msg', '')), str(e.get('detail', ''))
            say(level, msg + (' | ' + detail.replace('\n', ' | ') if detail else ''))
            project, _ = project_of(self.root)
            try:
                project.mkdir(parents=True, exist_ok=True)
                with open(project / 'errors.log', 'a', encoding='utf-8') as f:
                    f.write(f'{e.get("t") or time.strftime("%Y-%m-%dT%H:%M:%S")} {level} {msg}\n' + ''.join('    ' + l + '\n' for l in detail.splitlines()))
            except OSError:
                pass
            return self.send(204)
        if path.startswith('/fs/'):   # create a folder
            t = self.target()
            if not t:
                return
            p, _ = t
            if not self.writable(p):
                return self.send(403, 'Duetsheet only writes in its own project folder')
            p.mkdir(parents=True, exist_ok=True)
            return self.send(200)
        self.send(404, 'not found')

    def do_PUT(self):
        if not self.allowed() or not self.authorised():
            return
        if not urllib.parse.urlsplit(self.path).path.startswith('/fs/'):
            return self.send(404)
        t = self.target()
        if not t:
            return
        p, is_dir = t
        if is_dir or not self.writable(p):
            return self.send(403, 'Duetsheet only writes in its own project folder')
        body = self.rfile.read(int(self.headers.get('Content-Length', 0) or 0))
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + '.' + secrets.token_hex(4) + '.duetsheet-tmp')
        tmp.write_bytes(body)
        for attempt in range(5):   # a sync client (OneDrive, Dropbox) may hold the file for a moment
            try:
                os.replace(tmp, p)
                return self.send(200, b'', headers={'X-Mtime': self.mtime(p)})
            except PermissionError as e:
                err = e
                time.sleep(0.2 * (attempt + 1))
        try:
            tmp.unlink()
        except OSError:
            pass
        self.send(503, f'the file is locked by another program: {err}')


def serve(root, port, open_browser):
    project, data = project_of(root)
    if not PAGE.is_file():
        say('ERROR', f'{PAGE} not found; keep duetsheet.py next to duetsheet.html')
        return 1
    if (project / 'report.json').is_file():
        run_check(root)
    else:
        say('No report yet. The page will create', project / 'report.json')
    token = secrets.token_hex(16)
    httpd = None
    for p in ([port] if port else range(8765, 8790)):
        try:
            httpd = http.server.ThreadingHTTPServer(('127.0.0.1', p), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        say('ERROR', 'no free port between 8765 and 8789; use --port')
        return 1
    Handler.root, Handler.token, Handler.port = root, token, httpd.server_address[1]
    url = f'http://127.0.0.1:{Handler.port}/#token={token}'
    say('Duetsheet', VERSION, 'for', root)
    say('Report:', project / 'report.json')
    say('Raw data (read only):', data)
    say('Open:', url)
    say('Problems reported by the page are printed here and saved in', project / 'errors.log')
    say('Stop with Ctrl+C.')
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        say('stopped')
    return 0


# ---------------------------------------------------------------- the Claude Code skill

def install_skill(target):
    src = HERE / 'skills' / 'duetsheet' / 'SKILL.md'
    if not src.is_file():
        say('ERROR', f'{src} not found')
        return 1
    dest = pathlib.Path(target).expanduser() / 'duetsheet'
    dest.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding='utf-8').replace('{{DUETSHEET_DIR}}', str(HERE))
    (dest / 'SKILL.md').write_text(text, encoding='utf-8')
    say('Installed', dest / 'SKILL.md')
    say('In Claude Code, type /duetsheet (in a new session) to start.')
    return 0


# ---------------------------------------------------------------- a desktop shortcut

def desktop_dir():
    if os.name == 'nt':
        try:  # the real desktop, also when OneDrive has moved it
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and buf.value:
                return pathlib.Path(buf.value)
        except Exception:
            pass
    d = pathlib.Path.home() / 'Desktop'
    return d if d.is_dir() else pathlib.Path.home()


def shortcut_name(root):
    project, _ = project_of(root)
    title = ''
    try:
        title = json.loads((project / 'report.json').read_text(encoding='utf-8-sig'))['report']['meta']['title']
    except Exception:
        pass
    name = str(title or (root.parent.name if root.name == SUBDIR else root.name)).strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', name).strip()[:60] or 'report'
    return 'Duetsheet - ' + name


def make_shortcut(root, target):
    dest = pathlib.Path(target).expanduser() if target else desktop_dir()
    dest.mkdir(parents=True, exist_ok=True)
    name, py, script = shortcut_name(root), sys.executable, HERE / 'duetsheet.py'
    if os.name == 'nt':
        # The .lnk is made in a temporary folder and then moved: Windows may keep PowerShell from writing to the
        # desktop (controlled folder access) while still letting Python do it. WScript.Shell only creates the file:
        # it stores paths in the ANSI code page, so the paths are set through Shell.Application, which keeps Unicode.
        link = dest / (name + '.lnk')
        tmp = pathlib.Path(tempfile.mkdtemp(prefix='duetsheet-')) / 'shortcut.lnk'
        q = lambda v: "'" + str(v).replace("'", "''") + "'"
        args = f'"{script}" "{root}"'
        ps = (f'$w=(New-Object -ComObject WScript.Shell).CreateShortcut({q(tmp)});$w.TargetPath={q(os.environ.get("COMSPEC", "cmd.exe"))};$w.Save();'
              f'$s=(New-Object -ComObject Shell.Application).NameSpace({q(tmp.parent)}).ParseName({q(tmp.name)}).GetLink;'
              f'$s.Path={q(py)};$s.Arguments={q(args)};$s.WorkingDirectory={q(root)};'
              f'$s.Description={q("Start Duetsheet for " + root.name)};$s.Save()')
        enc = base64.b64encode(ps.encode('utf-16-le')).decode('ascii')
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand', enc], capture_output=True, text=True, errors='replace')
        try:
            if r.returncode or not tmp.is_file():
                raise OSError(re.sub(r'<[^>]+>', ' ', r.stderr or r.stdout).strip()[-400:])
            shutil.move(str(tmp), str(link))
        except OSError as err:
            say('ERROR', 'could not create the shortcut:', err)
            return 1
        finally:
            shutil.rmtree(tmp.parent, ignore_errors=True)
    else:
        link = dest / (name + ('.command' if sys.platform == 'darwin' else '.sh'))
        sh = lambda v: "'" + str(v).replace("'", "'\\''") + "'"
        link.write_text(f'#!/bin/sh\nexec {sh(py)} {sh(script)} {sh(root)}\n', encoding='utf-8')
        link.chmod(0o755)
    say('Created', link)
    say('Double-click it to open the report; keep the window that opens while you use it.')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='Duetsheet launcher', formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('args', nargs='*', help='[check | install-skill | shortcut] [FOLDER]')
    ap.add_argument('--port', type=int, default=0, help='port (default: first free port from 8765)')
    ap.add_argument('--no-browser', action='store_true', help='do not open a browser window')
    ap.add_argument('--skills-dir', default='~/.claude/skills', help='where install-skill puts the skill')
    ap.add_argument('--to', default='', help='where shortcut puts the shortcut (default: the desktop)')
    ap.add_argument('--version', action='version', version=VERSION)
    a = ap.parse_args(argv)
    cmd = a.args[0] if a.args and a.args[0] in ('check', 'install-skill', 'shortcut', 'serve') else 'serve'
    rest = a.args[1:] if a.args and a.args[0] == cmd else a.args
    if cmd == 'install-skill':
        return install_skill(a.skills_dir)
    root = pathlib.Path(rest[0] if rest else os.getcwd()).expanduser().resolve()
    if not root.is_dir():
        say('ERROR', f'{root} is not a folder')
        return 1
    if cmd == 'check':
        return run_check(root)
    if cmd == 'shortcut':
        return make_shortcut(root, a.to)
    return serve(root, a.port, not a.no_browser)


if __name__ == '__main__':
    sys.exit(main())
