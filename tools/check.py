#!/usr/bin/env python3
"""Check duetsheet.html before a commit.

1. Code, comments and docs are English: CJK, kana, Hangul and full-width characters may appear
   only inside the translation block (<script type="application/json" id="duetsheet-i18n">).
2. The translation block is valid JSON, every language has a "_name", and no translation
   changes the {placeholders} of its English source.
3. Every tr('...') string used in the code has an entry in the reference table (zh-Hant),
   so the "Download template" button offers it to translators.
4. Reports how complete each language is (missing sentences fall back to English).

Usage: python tools/check.py          (from the repository root)
Exit code 1 if any error is found.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'duetsheet.html')
OPEN = '<script type="application/json" id="duetsheet-i18n">'
REFERENCE = 'zh-Hant'
WIDE = re.compile('[\u3000-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]')
PH = re.compile(r'\{(\w+)\}')
TEXT_EXT = ('.html', '.md', '.txt', '.json', '.py', '.js', '.css', '.svg')

errors = []


def err(msg):
    errors.append(msg)
    print('ERROR', msg)


def english_of(key):
    return key.split('|', 1)[1] if re.match(r'^[a-z]+\|', key) else key


def placeholders(s):
    return sorted(set(PH.findall(s)))


src = open(HTML, encoding='utf-8').read()
a = src.find(OPEN)
if a < 0:
    sys.exit('ERROR translation block not found in duetsheet.html')
b = src.index('</script>', a)
block, outside = src[a + len(OPEN):b], src[:a] + src[b:]

# 1. wide characters outside the translation block, in every text file of the repository
for i, line in enumerate(outside.split('\n'), 1):
    if WIDE.search(line):
        err(f'duetsheet.html (outside the translation block), line ~{i}: {line.strip()[:80]}')
for dirpath, dirnames, files in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if not d.startswith('.')]
    for f in files:
        p = os.path.join(dirpath, f)
        if p == HTML or not f.endswith(TEXT_EXT):
            continue
        try:
            text = open(p, encoding='utf-8').read()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.split('\n'), 1):
            if WIDE.search(line):
                err(f'{os.path.relpath(p, ROOT)}, line {i}: non-English text outside the translation block')
                break

# 2. the translation block
try:
    tables = json.loads(block)
except ValueError as e:
    sys.exit(f'ERROR translation block is not valid JSON: {e}')
if REFERENCE not in tables:
    sys.exit(f'ERROR reference language {REFERENCE} missing from the translation block')
ref_keys = [k for k in tables[REFERENCE] if not k.startswith('_')]
for code, table in tables.items():
    if not isinstance(table.get('_name'), str) or not table['_name']:
        err(f'{code}: "_name" is missing')
    for k, v in table.items():
        if k.startswith('_'):
            continue
        if not isinstance(v, str):
            err(f'{code}: value for {k!r} is not a string')
        elif placeholders(v) != placeholders(english_of(k)):
            err(f'{code}: placeholders differ for {k!r}: {v!r}')
        if k not in tables[REFERENCE]:
            err(f'{code}: {k!r} is not in the reference table {REFERENCE}')

# 3. strings used in the code
used = set(json.loads('"' + m.replace('"', '\\"').replace("\\'", "'") + '"')
           for m in re.findall(r"\btr\('((?:[^'\\]|\\.)*)'", outside))
PROPER_NOUNS = set()
m = re.search(r"const TOOLS=\[(.*?)\];", outside)
if m:
    PROPER_NOUNS = set(re.findall(r"'([^']+)'", m.group(1))) - {'Other'}
for k in sorted(used - set(ref_keys) - PROPER_NOUNS):
    err(f'tr({k!r}) has no entry in {REFERENCE}; add it to every language (or at least {REFERENCE})')

# 4. completeness
print(f'{len(ref_keys)} sentences in the reference table ({REFERENCE})')
for code, table in tables.items():
    n = sum(1 for k in ref_keys if isinstance(table.get(k), str) and table[k].strip())
    print(f'  {code:8} {table.get("_name", "?")}: {n}/{len(ref_keys)}' + ('' if n == len(ref_keys) else f'  ({len(ref_keys) - n} fall back to English)'))

if errors:
    print(f'\n{len(errors)} error(s)')
    sys.exit(1)
print('OK')
