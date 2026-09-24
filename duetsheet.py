#!/usr/bin/env python3
"""Duetsheet launcher: open a report for a data folder in the browser, with no folder picker.

    python duetsheet.py [FOLDER]            start Duetsheet for FOLDER (default: the current folder)
    python duetsheet.py check [FOLDER]      check the report in FOLDER and exit (exit code 1 on errors)
                                            (--deep: re-read every file instead of trusting size and date)
    python duetsheet.py step FOLDER --script S --in PATTERN --out PATTERN
                                            record a computation step: which script turned which files into which
    python duetsheet.py annotations FOLDER  print the open annotations with what they point at (compact JSON for agents)
    python duetsheet.py wait FOLDER         for an agent: wait until the user clicks "Ask the agent to revise", then exit
    python duetsheet.py agent-status FOLDER working|done|failed [--note TEXT]
                                            for an agent: tell the page what it is doing
    python duetsheet.py install-skill       install the /duetsheet skill for Claude Code
    python duetsheet.py shortcut [FOLDER]   put a shortcut on the desktop that starts Duetsheet for FOLDER
    python duetsheet.py init-agent [FOLDER] add a marked section to AGENTS.md and CLAUDE.md in FOLDER that points any agent to Duetsheet

Where the report lives:
  - If FOLDER contains report.json, FOLDER is the project folder (raw data in FOLDER/data/).
  - Otherwise the report goes into FOLDER/duetsheet/ and FOLDER itself is the raw data folder.
    Raw data files are only read, never written.
  - Raw data stays outside duetsheet/ but inside FOLDER. Files computed from it (derived data, the scripts
    that compute them) go into FOLDER/duetsheet/derived_data/ and FOLDER/duetsheet/scripts/.

The launcher serves duetsheet.html on 127.0.0.1 and lets that page read and write the project
folder. Every request needs a random token that is only given to the browser window it opens.
Problems the page reports are printed here and appended to errors.log in the project folder,
so an agent running this command sees them.

Python 3.8 or later, standard library only.
"""
import argparse, base64, datetime, glob, hashlib, hmac, http.server, json, mimetypes, os, pathlib, posixpath, re, secrets, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.parse, webbrowser

VERSION = '0.6.0'
SCHEMA = 'duetsheet/0.6'
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


def atomic_write(path, data):
    """Write bytes through a temporary file and a rename, retrying while a sync client holds the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + secrets.token_hex(4) + '.duetsheet-tmp')
    tmp.write_bytes(data)
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                tmp.unlink()
                raise
            time.sleep(0.2 * (attempt + 1))


# ---------------------------------------------------------------- fingerprints
# A file is known by its path (relative to the folder of report.json) and the SHA-256 of its bytes.
# Raw data can be large (hundreds of files of tens of MB, often in a OneDrive folder, where reading a file
# may download it), so a file is only read when its size or modification time differs from what was
# recorded. Hashes computed that way are kept in cache/fingerprints.json; deleting it is harmless.

CACHE_FILE = ('cache', 'fingerprints.json')
MTIME_SLACK_MS = 2000   # copies and sync clients may move the modification time a little


def iso_ms(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def ms_of(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace('Z', '+00:00')).timestamp() * 1000
    except ValueError:
        return None


def norm(rel):
    return posixpath.normpath(str(rel).replace('\\', '/'))


def inside(root, project, rel):
    """True when rel (relative to the folder of report.json) stays inside the folder the user opened."""
    if not isinstance(rel, str) or not rel or re.match(r'^([A-Za-z]:|[\\/])', rel):
        return False
    try:
        (project / norm(rel)).resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


class Fingerprints:
    def __init__(self, project):
        self.project, self.file = project, project.joinpath(*CACHE_FILE)
        self.lock, self.dirty, self.hashed = threading.Lock(), False, 0
        try:
            self.cache = json.loads(self.file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.cache = {}
        if not isinstance(self.cache, dict):
            self.cache = {}

    def sha256(self, rel, st, force=False):
        mtime = st.st_mtime_ns // 1_000_000
        with self.lock:
            c = self.cache.get(rel)
        if not force and isinstance(c, dict) and c.get('size') == st.st_size and c.get('mtime') == mtime:
            return c.get('sha256')
        h = hashlib.sha256()
        with open(self.project / rel, 'rb') as fh:
            for b in iter(lambda: fh.read(1 << 20), b''):
                h.update(b)
        with self.lock:
            self.cache[rel] = {'size': st.st_size, 'mtime': mtime, 'sha256': h.hexdigest()}
            self.dirty = True
            self.hashed += 1
        return h.hexdigest()

    def ref(self, rel):
        """A file reference for a file that exists: {path, sha256, size, modified}."""
        rel = norm(rel)
        st = (self.project / rel).stat()
        return {'path': rel, 'sha256': self.sha256(rel, st), 'size': st.st_size, 'modified': iso_ms(st.st_mtime_ns // 1_000_000)}

    def status(self, ref, deep=False):
        """Compare a file reference {path, sha256, size?, modified?} with the file on disk.
        state: same | changed | missing | unknown (nothing recorded to compare with)."""
        rel = norm(ref.get('path'))
        out = {'path': ref.get('path'), 'state': 'missing'}
        try:
            st = (self.project / rel).stat()
        except OSError:
            return out
        if not (self.project / rel).is_file():
            return out
        out.update(size=st.st_size, modified=iso_ms(st.st_mtime_ns // 1_000_000))
        want, rec = ref.get('sha256'), ms_of(ref['modified']) if ref.get('modified') else None
        if not deep and want and ref.get('size') == st.st_size and rec is not None and abs(rec - st.st_mtime_ns / 1e6) <= MTIME_SLACK_MS:
            out.update(state='same', sha256=want)
            return out
        out['sha256'] = sha = self.sha256(rel, st, force=deep)
        out['state'] = 'unknown' if not want else 'same' if sha == want else 'changed'
        return out

    def save(self):
        with self.lock:
            if not self.dirty:
                return
            data, self.dirty = json.dumps(self.cache, indent=0, sort_keys=True), False
        try:
            atomic_write(self.file, data.encode('utf-8'))
        except OSError:
            pass


# ---------------------------------------------------------------- the data chain
# steps/{id} records one computation: a script turned input files into output files. A dataset imported
# from a step's output can be followed back, step by step, to the raw files no step produced.
# A step needs rerunning when its script or an input changed, or when an input comes from a step that
# needs rerunning; everything computed from it (outputs, datasets, charts and tables) is then out of date.

def match_patterns(root, project, patterns):
    """Files that match a step's inputPatterns now (paths relative to the folder of report.json), inside root only."""
    found = set()
    for pat in patterns if isinstance(patterns, list) else []:
        if not isinstance(pat, str) or not pat or re.match(r'^([A-Za-z]:|[\\/])', pat):
            continue
        for h in glob.glob(os.path.join(str(project), pat), recursive=True):
            rel = norm(os.path.relpath(h, project))
            if os.path.isfile(h) and inside(root, project, rel):
                found.add(rel)
    return found


def step_files(step):
    """(role, ref) for every file a step names."""
    if isinstance(step.get('script'), dict):
        yield 'script', step['script']
    for role in ('inputs', 'outputs'):
        for r in step.get(role) or []:
            yield role[:-1], r


def check_chain(project, root, rep, deep):
    """Return (errors, warnings, notes) about steps and dataset sources."""
    errors, warnings, notes = [], [], []
    steps = rep.get('steps') or {}
    datasets = rep.get('datasets') if isinstance(rep.get('datasets'), dict) else {}
    blocks = rep.get('blocks') if isinstance(rep.get('blocks'), dict) else {}
    if not isinstance(steps, dict):
        return ['"steps" must be an object keyed by step id'], [], []
    fp, seen = Fingerprints(project), {}

    def state(ref):
        key = (norm(ref.get('path')), ref.get('sha256'), ref.get('size'), ref.get('modified'))
        if key not in seen:
            try:
                seen[key] = fp.status(ref, deep)
            except OSError as e:
                seen[key] = {'state': 'missing', 'error': str(e)}
        return seen[key]['state']

    good = {}
    for key, s in steps.items():
        where = f'steps.{key}'
        if not isinstance(s, dict):
            errors.append(f'{where} must be an object')
            continue
        if s.get('id') != key:
            errors.append(f'{where}.id must be "{key}"')
        if not isinstance(s.get('outputs'), list) or not s['outputs']:
            errors.append(f'{where}.outputs must list the files the step wrote')
        if not isinstance(s.get('inputs', []), list):
            errors.append(f'{where}.inputs must be a list')
            continue
        ok = True
        for role, r in step_files(s):
            if not isinstance(r, dict) or not isinstance(r.get('path'), str) or not r['path']:
                errors.append(f'{where}: every {role} needs a "path"')
                ok = False
            elif not inside(root, project, r['path']):
                errors.append(f'{where}: {role} "{r["path"]}" is outside the folder "{root.name}". Raw data must be inside "{root.name}" '
                              f'(outside duetsheet/), and paths are relative to the folder of report.json')
                ok = False
            elif not re.fullmatch(r'[0-9a-f]{64}', str(r.get('sha256', ''))):
                warnings.append(f'{where}: {role} "{r["path"]}" has no sha256, so changes to it cannot be seen')
        pats = s.get('inputPatterns', [])
        if not isinstance(pats, list) or not all(isinstance(p, str) and p for p in pats):
            errors.append(f'{where}.inputPatterns must be a list of file patterns')
            ok = False
        else:
            for p in pats:   # the fixed part of a pattern must stay inside the folder
                fixed = re.split(r'[*?\[]', p)[0].rsplit('/', 1)[0] or '.'
                if re.match(r'^([A-Za-z]:|[\\/])', p) or not inside(root, project, fixed):
                    errors.append(f'{where}: input pattern "{p}" is outside the folder "{root.name}"')
                    ok = False
        if ok and isinstance(s.get('outputs'), list):
            good[key] = s

    # which step made each file: the latest one that lists it as an output
    made_by = {}
    for key, s in sorted(good.items(), key=lambda kv: str(kv[1].get('at', ''))):
        for r in s.get('outputs') or []:
            made_by[norm(r['path'])] = key

    # files that match a step's input patterns but are not among its recorded inputs: new data to compute with
    new_inputs = {key: sorted(match_patterns(root, project, s.get('inputPatterns')) - {norm(r['path']) for r in s.get('inputs') or []})
                  for key, s in good.items() if s.get('inputPatterns')}
    reasons, stale = {}, {}

    def is_stale(key, trail=()):
        if key in stale:
            return stale[key]
        if key in trail:   # a loop; reported once below
            return False
        s, why = good[key], []
        new = new_inputs.get(key) or []
        if new:
            why.append(f'{len(new)} new file(s) match its input patterns ({", ".join(new[:3])}{" ..." if len(new) > 3 else ""})')
        for role, r in step_files(s):
            st = state(r)
            if st == 'missing':
                why.append(f'{role} {r["path"]} is missing')
            elif st == 'changed':
                why.append(f'{role} {r["path"]} changed' + (' after the step was recorded' if role == 'output' else ''))
        for r in s.get('inputs') or []:
            up = made_by.get(norm(r['path']))
            if up and up != key and is_stale(up, trail + (key,)):
                why.append(f'input {r["path"]} comes from step "{up}", which needs rerunning')
        reasons[key], stale[key] = why, bool(why)
        return stale[key]

    for key in good:
        is_stale(key)

    uses = {}   # dataset id -> block ids
    for bid, b in blocks.items():
        if isinstance(b, dict):
            spec = b.get(b.get('type')) if b.get('type') in ('chart', 'table') else None
            if isinstance(spec, dict) and spec.get('dataset'):
                uses.setdefault(spec['dataset'], []).append(bid)

    stale_ds = {}
    for key, ds in datasets.items():
        src = ds.get('source') if isinstance(ds, dict) else None
        if not isinstance(src, dict) or not src.get('path'):
            continue
        where = f'datasets.{key}'
        if not inside(root, project, src['path']):
            errors.append(f'{where}.source.path "{src["path"]}" is outside the folder "{root.name}"; '
                          f'put the file inside "{root.name}" (paths are relative to the folder of report.json)')
            continue
        st = state(src)
        up = made_by.get(norm(src['path']))
        if st == 'missing':
            warnings.append(f'{where}.source.path "{src["path"]}" does not exist (paths are relative to the folder of report.json)')
        elif st == 'changed':
            stale_ds[key] = f'{src["path"]} changed since it was imported (sha256 differs); import it again'
        elif up and stale.get(up):
            stale_ds[key] = f'{src["path"]} comes from step "{up}", which needs rerunning'

    def short(items, n=3):
        items = list(items)
        return ', '.join(items[:n]) + (f' and {len(items) - n} more' if len(items) > n else '')

    for key in good:
        if stale[key]:
            outs = [r['path'] for r in good[key].get('outputs') or []]
            ds = [d for d, x in datasets.items() if isinstance(x, dict) and isinstance(x.get('source'), dict)
                  and norm(x['source'].get('path', '')) in {norm(o) for o in outs}]
            warnings.append(f'step "{key}" needs rerunning: {short(reasons[key])}. It wrote {short(outs)}'
                            + (f', imported as dataset {short(ds)}' if ds else ''))
    for key, why in stale_ds.items():
        warnings.append(f'datasets.{key}: {why}' + (f'. Used by {short(uses[key])}' if uses.get(key) else ''))

    if good:
        made = set(made_by)
        raw = {norm(r['path']) for s in good.values() for r in s.get('inputs') or []} - made
        scripts = {norm(s['script']['path']) for s in good.values() if isinstance(s.get('script'), dict)}
        n_stale = sum(stale.values())
        n_new = len({p for v in new_inputs.values() for p in v})
        notes.append(f'Data chain: {len(good)} step(s), {len(made)} derived file(s), {len(raw)} raw file(s), {len(scripts)} script(s); '
                     + (f'{n_stale} step(s) need rerunning' if n_stale else 'all up to date')
                     + (f'; {n_new} new raw file(s) not used yet' if n_new else ''))
    if fp.hashed:
        notes.append(f'Read {fp.hashed} file(s) to compute fingerprints (kept in {"/".join(CACHE_FILE)} for next time)')
    fp.save()
    return errors, warnings, notes


# ---------------------------------------------------------------- checking a report

STYLE_FIELDS = {'font.family', 'font.size', 'font.label', 'marker', 'line', 'ticks', 'frame', 'grid', 'palette',
                'figure.preset', 'chartDefaults.kind', 'chartDefaults.logY'}


def check_report(project, root=None, deep=False):
    """Return (errors, warnings, notes) for project/report.json, as lists of strings.
    root is the folder the user opens (the parent of duetsheet/, or project itself)."""
    errors, warnings, notes = [], [], []
    root = root or project
    path = project / 'report.json'
    if not path.is_file():
        return [f'{path} does not exist'], [], []
    raw = path.read_bytes()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return ['report.json is UTF-16; save it as UTF-8'], [], []
    if raw[:3] == b'\xef\xbb\xbf':
        warnings.append('report.json starts with a byte order mark (BOM); write plain UTF-8')
        raw = raw[3:]
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        return [f'report.json is not UTF-8: {e}'], warnings, notes

    def no_constants(name):
        raise ValueError(f'{name} is not valid JSON; write null instead (Python: json.dump(..., allow_nan=False))')
    try:
        rep = json.loads(text, parse_constant=no_constants)
    except json.JSONDecodeError as e:
        return [f'report.json line {e.lineno}, column {e.colno}: {e.msg}'], warnings, notes
    except ValueError as e:
        # find where the constant is, for the message
        for i, line in enumerate(text.splitlines(), 1):
            for tok in ('-Infinity', 'Infinity', 'NaN'):
                col = line.find(tok)
                if col >= 0 and line[:col].count('"') % 2 == 0:
                    return [f'report.json line {i}, column {col + 1}: {e}'], warnings, notes
        return [f'report.json: {e}'], warnings, notes

    if not isinstance(rep, dict):
        return ['report.json must be a JSON object'], warnings, notes
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
    e, w, n = check_chain(project, root, rep, deep)
    return errors + e, warnings + w, notes + n


def run_check(root, deep=False):
    project, _ = project_of(root)
    errors, warnings, notes = check_report(project, root, deep)
    for n in notes:
        say(n)
    for w in warnings:
        say('WARNING', w)
    for e in errors:
        say('ERROR', e)
    if not errors:
        say('OK', project / 'report.json', f'({len(warnings)} warning(s))' if warnings else '')
    return 1 if errors else 0


# ---------------------------------------------------------------- the page asks the agent to act
# The page's "Ask the agent to revise" button reaches an agent (Claude Code, Codex, ...) through small files in
# ~/.duetsheet/run/<folder name>-<hash of the project path>/ (outside the project, so a sync client such as OneDrive
# does not upload a file every few seconds), so any agent that can run a command in the background can answer:
#   launcher.json  written every few seconds by the running launcher (so waiting agents notice when it stops)
#   request.json   the latest request from the page: {id, kind, open, at}. It carries no text, only a kind from KINDS.
#   listening.json written every few seconds while an agent runs "duetsheet.py wait"
#   status.json    what the agent reported with "duetsheet.py agent-status": {request, state, at, note}
# A request is only a notice; the agent reads the annotations from report.json and treats them as feedback.

RUN_DIR = pathlib.Path(os.environ.get('DUETSHEET_RUN_DIR') or pathlib.Path.home() / '.duetsheet' / 'run')
KINDS = ('revise',)
STATES = ('working', 'done', 'failed')
FRESH_S = 15          # an agent is listening when listening.json is younger than this
LAUNCHER_STALE_S = 30


def agent_file(project, name):
    p = project.resolve()
    key = hashlib.sha1(str(p).lower().encode('utf-8')).hexdigest()[:12]
    label = re.sub(r'[^\w.-]+', '_', (p.parent.name if p.name == SUBDIR else p.name))[:40]
    return RUN_DIR / f'{label}-{key}' / name


def read_json(path):
    try:
        v = json.loads(path.read_text(encoding='utf-8'))
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path, obj):
    atomic_write(path, (json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8'))


def now_iso():
    return iso_ms(time.time() * 1000)


def age_s(obj):
    t = ms_of(obj.get('at')) if obj else None
    return (time.time() * 1000 - t) / 1000 if t is not None else float('inf')


def agent_state(project):
    """What the page shows next to the button."""
    req, st = read_json(agent_file(project, 'request.json')), read_json(agent_file(project, 'status.json'))
    return {'listening': age_s(read_json(agent_file(project, 'listening.json'))) < FRESH_S, 'request': req,
            'status': st if st and req and st.get('request') == req.get('id') else None}


def pending_request(project):
    """The latest request, if no agent has started on it yet."""
    req, st = read_json(agent_file(project, 'request.json')), read_json(agent_file(project, 'status.json'))
    if req and not (st and st.get('request') == req.get('id') and st.get('state') in STATES):
        return req
    return None


def wait_for_request(root):
    """For an agent: return when the user asks for something (exit 0), or when the launcher stops (exit 3).
    Meant to run in the background; each line it prints is something the agent should act on."""
    project, _ = project_of(root)
    if age_s(read_json(agent_file(project, 'launcher.json'))) > LAUNCHER_STALE_S:
        say('LAUNCHER NOT RUNNING: start it first:', f'python "{HERE / "duetsheet.py"}" "{root}"')
        return 3
    beat = 0
    try:
        while True:
            if time.time() - beat >= 5:
                write_json(agent_file(project, 'listening.json'), {'at': now_iso(), 'pid': os.getpid()})
                beat = time.time()
            req = pending_request(project)
            if req:
                say(f'{req.get("kind", "revise").upper()} REQUESTED: {req.get("open", 0)} open annotation(s) (request {req.get("id")}).',
                    'Report progress with agent-status, then run wait again.')
                return 0
            if age_s(read_json(agent_file(project, 'launcher.json'))) > LAUNCHER_STALE_S:
                say('LAUNCHER STOPPED: Duetsheet is no longer running for', root)
                return 3
            time.sleep(1)
    except KeyboardInterrupt:
        return 130
    finally:
        try:
            agent_file(project, 'listening.json').unlink()
        except OSError:
            pass


def set_agent_status(root, state, note):
    project, _ = project_of(root)
    req = read_json(agent_file(project, 'request.json'))
    write_json(agent_file(project, 'status.json'), {'request': req.get('id') if req else None, 'state': state, 'at': now_iso(), 'note': note})
    say('Status:', state, f'({note})' if note else '')
    return 0


def open_annotations(root):
    """The open annotations with the block, settings and data rows they point at, as compact JSON.
    A report can be megabytes of data rows; this is what an agent needs to read to revise it."""
    project, _ = project_of(root)
    try:
        rep = json.loads((project / 'report.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as err:
        say('ERROR', 'cannot read report.json:', err)
        return 1
    blocks, datasets = rep.get('blocks') or {}, rep.get('datasets') or {}
    rounds, changes = (rep.get('rounds') or {}).values(), (rep.get('changes') or {}).values()
    last = max((r.get('at', '') for r in rounds if isinstance(r, dict)), default='')
    out = []
    for a in sorted((a for a in (rep.get('annotations') or {}).values() if isinstance(a, dict) and a.get('status') != 'done'),
                    key=lambda a: a.get('no', 0)):
        t = a.get('target') or {}
        b = blocks.get(t.get('blockId')) or {}
        blk = {k: v for k, v in b.items() if k not in ('createdAt', 'updatedAt')}
        if isinstance(blk.get('image'), dict):   # no image data in the output
            blk['image'] = {k: v for k, v in blk['image'].items() if k != 'src'}
        spec = b.get(b.get('type')) if b.get('type') in ('chart', 'table') else None
        ds = datasets.get(spec.get('dataset')) if isinstance(spec, dict) else None
        item = {'annotation': a, 'block': blk}
        if isinstance(ds, dict):
            item['dataset'] = {'id': ds.get('id'), 'title': ds.get('title'), 'columns': ds.get('columns'),
                               'rows': len(ds.get('rows') or []), 'source': (ds.get('source') or {}).get('path')}
            ids = [t['rowId']] if 'rowId' in t else t.get('enclosed') or []
            if ids:
                want = set(ids)
                rows = [r for r in ds.get('rows') or [] if isinstance(r, dict) and r.get('id') in want]
                item['targetRows'] = rows[:30]
                if len(rows) > 30:
                    item['targetRowsNote'] = f'{len(rows) - 30} more rows not shown'
        out.append(item)
    print(json.dumps({'report': (rep.get('report') or {}).get('meta', {}).get('title'), 'file': str(project / 'report.json'),
                      'open': len(out), 'lastRoundAt': last or None,
                      'userChangesAfterLastRound': sum(1 for c in changes if isinstance(c, dict) and c.get('by') == 'user' and c.get('at', '') > last),
                      'annotations': out}, ensure_ascii=False, indent=1))
    return 0


# ---------------------------------------------------------------- the server

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'Duetsheet/' + VERSION
    root = None       # the folder the user opened
    token = ''
    port = 0
    prints = None     # Fingerprints of the project folder, shared by all requests

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
            return self.send(200, json.dumps({'name': self.root.name, 'version': VERSION, 'layout': 'data-folder' if project != self.root else 'project-folder',
                                              'root': str(self.root), 'app': str(stable_app(False))}), 'application/json')
        if path == '/api/agent':
            project, _ = project_of(self.root)
            return self.send(200, json.dumps(agent_state(project)), 'application/json')
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
        if path == '/api/fingerprints':   # {files: [file reference]} -> the state of each file now (see Fingerprints.status)
            try:
                files = json.loads(body.decode('utf-8'))['files']
                assert isinstance(files, list)
            except Exception:
                return self.send(400, 'expected {"files": [{"path": ...}]}')
            project, _ = project_of(self.root)
            if Handler.prints is None or Handler.prints.project != project:
                Handler.prints = Fingerprints(project)
            out = []
            for ref in files[:20000]:
                if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
                    out.append({'state': 'missing'})
                elif not inside(self.root, project, ref['path']):
                    out.append({'path': ref['path'], 'state': 'outside'})
                else:
                    try:
                        out.append(Handler.prints.status(ref))
                    except OSError as err:
                        out.append({'path': ref['path'], 'state': 'missing', 'error': str(err)})
            Handler.prints.save()
            return self.send(200, json.dumps(out), 'application/json')
        if path == '/api/revise':   # the page's "Ask the agent to revise": only a kind and a count are taken from the page
            try:
                req = json.loads(body.decode('utf-8'))
                kind, n = req.get('kind', 'revise'), int(req.get('open', 0))
                assert kind in KINDS and 0 <= n < 100000
            except Exception:
                return self.send(400, 'expected {"kind": "revise", "open": <number>}')
            project, _ = project_of(self.root)
            write_json(agent_file(project, 'request.json'), {'id': 'q' + secrets.token_hex(6), 'kind': kind, 'open': n, 'at': now_iso()})
            say(f'{kind.upper()} REQUESTED: {n} open annotation(s)')
            return self.send(200, json.dumps(agent_state(project)), 'application/json')
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


class Server(http.server.ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR lets a second launcher bind a port another one already uses, and requests then go to
    # either of them. Take the port exclusively there, so a busy port is skipped and the next one is used.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serve(root, port, open_browser):
    project, data = project_of(root)
    if not PAGE.is_file():
        say('ERROR', f'{PAGE} not found; keep duetsheet.py next to duetsheet.html')
        return 1
    try:
        stable_app(False)  # keep ~/.duetsheet/app (used by shortcuts) as new as this plugin version
    except OSError as err:
        say('WARNING', 'could not update', STABLE, err)
    if (project / 'report.json').is_file():
        run_check(root)
    else:
        say('No report yet. The page will create', project / 'report.json')
    token = secrets.token_hex(16)
    httpd = None
    for p in ([port] if port else range(8765, 8790)):
        try:
            httpd = Server(('127.0.0.1', p), Handler)
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

    stop = threading.Event()

    def heartbeat():   # lets "duetsheet.py wait" notice when the launcher stops
        while not stop.is_set():
            try:
                write_json(agent_file(project, 'launcher.json'), {'at': now_iso(), 'pid': os.getpid(), 'port': Handler.port})
            except OSError:
                pass
            stop.wait(5)
    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        say('stopped')
    finally:
        stop.set()
        try:
            agent_file(project, 'launcher.json').unlink()
        except OSError:
            pass
    return 0


# ---------------------------------------------------------------- recording a computation step

def record_step(root, a):
    """Add (or replace) steps/<id> in report.json with fingerprints of the script, inputs and outputs.
    Patterns are relative to the folder of report.json, for example ../Data/*.xlsx or derived_data/cells.csv."""
    project, _ = project_of(root)
    path = project / 'report.json'
    if not path.is_file():
        say('ERROR', f'{path} does not exist; write the report (or start Duetsheet once) before recording steps')
        return 1
    fp = Fingerprints(project)

    def expand(patterns, what):
        out = []
        for pat in patterns:
            hits = sorted(h for h in glob.glob(os.path.join(str(project), pat), recursive=True) if os.path.isfile(h))
            if not hits:
                raise ValueError(f'{what} "{pat}" matches no file (patterns are relative to {project})')
            for h in hits:
                rel = norm(os.path.relpath(h, project))
                if not inside(root, project, rel):
                    raise ValueError(f'{what} "{rel}" is outside the folder "{root.name}"; put it inside "{root.name}" first')
                if rel not in [r['path'] for r in out]:
                    out.append(fp.ref(rel))
        return out

    try:
        script = expand([a.script], '--script')[0] if a.script else None
        inputs, outputs = expand(a.inputs, '--in'), expand(a.outputs, '--out')
    except (ValueError, OSError) as err:
        say('ERROR', err)
        return 1
    if not outputs:
        say('ERROR', 'name the files the step wrote with --out')
        return 1
    params = {}
    for p in a.param:
        k, _, v = p.partition('=')
        try:
            params[k] = json.loads(v)
        except ValueError:
            params[k] = v
    stem = pathlib.PurePosixPath((script or outputs[0])['path']).stem
    sid = a.id or 's-' + (re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-') or 'step')
    step = {'id': sid, 'script': script, 'command': a.command, 'params': params, 'inputs': inputs, 'outputs': outputs,
            'inputPatterns': [norm(p) if not re.search(r'[*?\[]', p) else p.replace('\\', '/') for p in a.inputs],
            'at': iso_ms(time.time() * 1000), 'by': a.by, 'note': a.note}
    try:
        rep = json.loads(path.read_text(encoding='utf-8-sig'))   # read fresh: the page may have saved since
        steps = rep.setdefault('steps', {})
        replaced = sid in steps
        steps[sid] = step
        rep['schema'] = SCHEMA
        atomic_write(path, (json.dumps(rep, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8'))
    except (OSError, ValueError) as err:
        say('ERROR', 'could not update report.json:', err)
        return 1
    fp.save()
    total = len(inputs) + len(outputs) + bool(script)
    say('Replaced' if replaced else 'Recorded', f'step "{sid}":', f'{len(inputs)} input(s) -> {len(outputs)} output(s)',
        '' if fp.hashed == total else f'({fp.hashed} of {total} file(s) read; the other fingerprints were already known)')
    return 0


# ---------------------------------------------------------------- the Claude Code skill

def install_skill(target):
    src = HERE / 'skills' / 'duetsheet' / 'SKILL.md'
    if not src.is_file():
        say('ERROR', f'{src} not found')
        return 1
    dest = pathlib.Path(target).expanduser() / 'duetsheet'
    dest.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding='utf-8').replace('${CLAUDE_PLUGIN_ROOT}', str(HERE))
    (dest / 'SKILL.md').write_text(text, encoding='utf-8')
    say('Installed', dest / 'SKILL.md')
    say('In Claude Code, type /duetsheet (in a new session) to start.')
    return 0


# ---------------------------------------------------------------- a stable place for shortcuts and pointers

APP_FILES = ('duetsheet.py', 'duetsheet.html', 'AGENTS.md', 'schema/report.schema.json')
STABLE = pathlib.Path.home() / '.duetsheet' / 'app'


def from_plugin_cache():
    parts = [p.lower() for p in HERE.parts]
    return 'plugins' in parts and 'cache' in parts


def stable_app(create):
    """The folder that shortcuts and AGENTS.md pointers should name. A Claude Code plugin lives in a cache folder
    that changes with every update, so from there Duetsheet copies itself to ~/.duetsheet/app and names that."""
    if not from_plugin_cache():
        return HERE
    if create or STABLE.is_dir():
        for f in APP_FILES:
            (STABLE / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HERE / f, STABLE / f)
    return STABLE


# ---------------------------------------------------------------- a pointer for other agents

MARK_START, MARK_END = '<!-- duetsheet:start -->', '<!-- duetsheet:end -->'


def init_agent(root):
    app, (project, _) = stable_app(True), project_of(root)
    py = f'"{sys.executable}"' if ' ' in sys.executable else sys.executable
    block = '\n'.join([
        MARK_START,
        '## Duetsheet report',
        '',
        'This folder is reviewed with Duetsheet: the user reads and annotates the report in the browser while you write and revise it.',
        '',
        f'- Read the full rules before you change anything: `{app / "AGENTS.md"}`',
        f'- The report: `{project / "report.json"}`. Raw data files are only read, never changed.',
        f'- Raw data stays inside "{root.name}", outside `duetsheet/`. Files computed from it go into `duetsheet/derived_data/`,'
        ' the scripts into `duetsheet/scripts/`; record every script run with `duetsheet.py step`.',
        f'- Check after every write: `{py} "{app / "duetsheet.py"}" check "{root}"`',
        f'- Start it for the user (keep it running in the background): `{py} "{app / "duetsheet.py"}" "{root}"`',
        f'- Then listen for the page\'s "Ask the agent to revise" button (also in the background): `{py} "{app / "duetsheet.py"}" wait "{root}"`;'
        ' see "Answer the Ask the agent to revise button" in AGENTS.md.',
        MARK_END, ''])
    # The same section in AGENTS.md (Codex, Copilot, Cursor and others) and CLAUDE.md (Claude Code). Only the part between
    # the markers is Duetsheet's: running this again replaces it, and everything else in the files is kept as it is.
    # A marker counts only on a line of its own, so text that merely mentions it is never replaced.
    section = re.compile('^' + re.escape(MARK_START) + r'[ \t]*$.*?^' + re.escape(MARK_END) + r'[ \t]*$', re.M | re.S)
    for name in ('AGENTS.md', 'CLAUDE.md'):
        f = root / name
        old = f.read_text(encoding='utf-8-sig') if f.is_file() else ''
        m = section.search(old)
        if m:
            new = old[:m.start()] + block.rstrip('\n') + old[m.end():]
        else:
            new = (old.rstrip('\n') + '\n\n' if old.strip() else '') + block
        f.write_text(new, encoding='utf-8')
        say('Updated' if old else 'Created', f)
    say('Agents that read AGENTS.md or CLAUDE.md (Claude Code, Codex, Copilot, Cursor and others) now know how to use Duetsheet here.')
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
    name, py, script = shortcut_name(root), sys.executable, stable_app(True) / 'duetsheet.py'
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
    ap.add_argument('args', nargs='*', help='[check | step | annotations | wait | agent-status | install-skill | shortcut | init-agent] [FOLDER]')
    ap.add_argument('--note', default='', help='step, agent-status: a short note')
    ap.add_argument('--port', type=int, default=0, help='port (default: first free port from 8765)')
    ap.add_argument('--no-browser', action='store_true', help='do not open a browser window')
    ap.add_argument('--deep', action='store_true', help='check: re-read every file instead of trusting size and date')
    ap.add_argument('--skills-dir', default='~/.claude/skills', help='where install-skill puts the skill')
    ap.add_argument('--to', default='', help='where shortcut puts the shortcut (default: the desktop)')
    st = ap.add_argument_group('step', 'record a computation step (paths and patterns relative to the folder of report.json)')
    st.add_argument('--script', default='', help='the script that was run, for example scripts/make_cells.py')
    st.add_argument('--in', dest='inputs', action='append', default=[], metavar='PATTERN', help='files it read (repeatable; * and ** allowed)')
    st.add_argument('--out', dest='outputs', action='append', default=[], metavar='PATTERN', help='files it wrote (repeatable)')
    st.add_argument('--command', default='', help='the command line that was run')
    st.add_argument('--param', action='append', default=[], metavar='KEY=VALUE', help='a parameter of the run (repeatable)')
    st.add_argument('--id', default='', help='step id (default: s-<script name>; an existing step with this id is replaced)')
    st.add_argument('--by', default='claude', choices=('claude', 'user'), help='who ran it (claude stands for any agent)')
    ap.add_argument('--version', action='version', version=VERSION)
    a = ap.parse_args(argv)
    cmds = ('check', 'step', 'annotations', 'wait', 'agent-status', 'install-skill', 'shortcut', 'init-agent', 'serve')
    cmd = a.args[0] if a.args and a.args[0] in cmds else 'serve'
    rest = a.args[1:] if a.args and a.args[0] == cmd else a.args
    if cmd == 'install-skill':
        return install_skill(a.skills_dir)
    state = None
    if cmd == 'agent-status':
        if not rest or rest[-1] not in STATES:
            say('ERROR', 'usage: duetsheet.py agent-status FOLDER working|done|failed [--note TEXT]')
            return 1
        rest, state = rest[:-1], rest[-1]
    root = pathlib.Path(rest[0] if rest else os.getcwd()).expanduser().resolve()
    if not root.is_dir():
        say('ERROR', f'{root} is not a folder')
        return 1
    if cmd == 'check':
        return run_check(root, a.deep)
    if cmd == 'step':
        return record_step(root, a)
    if cmd == 'annotations':
        return open_annotations(root)
    if cmd == 'wait':
        return wait_for_request(root)
    if cmd == 'agent-status':
        return set_agent_status(root, state, a.note)
    if cmd == 'shortcut':
        return make_shortcut(root, a.to)
    if cmd == 'init-agent':
        return init_agent(root)
    return serve(root, a.port, not a.no_browser)


if __name__ == '__main__':
    sys.exit(main())
