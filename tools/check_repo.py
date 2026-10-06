#!/usr/bin/env python3
"""Checks that need no firmware image (run in CI and before committing).

- every JSON file parses; patch sets are gated on the stock CRC and size
- lang/*.json: known ids, plain ASCII, in-place byte limits, sprintf limits
- no vendor material (.bin/.bps/.zip/.pdf) is tracked
Pixel widths, menu rows and the patched-image self-check need the stock image:
run tools/build_all.sh for those.
"""
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from lang_build import SPRINTF_LIMIT  # noqa: E402

errors = []


def err(msg):
    errors.append(msg)


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError as e:
        err(f'{path}: invalid JSON: {e}')


for path in glob.glob(os.path.join(ROOT, '**', '*.json'), recursive=True):
    if '/.venv/' in path or '/firmware/work/' in path:
        continue
    load(path)

for path in [os.path.join(ROOT, 'firmware', 'dmm-first.json'), os.path.join(ROOT, 'lang', 'layout.json')] + \
        glob.glob(os.path.join(ROOT, 'firmware', 'build', '*.json')):
    j = load(path) or {}
    if j.get('input_crc32') != 'B43E8C2D' or j.get('require_size') != 1203945:
        err(f'{path}: not gated on stock crc32 B43E8C2D / size 1203945')
    for i, p in enumerate(j.get('patches', [])):
        n = len(bytes.fromhex(p['replace'].replace(' ', '')))
        if 'find' in p and len(bytes.fromhex(p['find'].replace(' ', ''))) != n:
            err(f'{path}: patch {i} find/replace length differ')

slots = load(os.path.join(ROOT, 'lang', 'slots.json'))
by_id = {s['id']: s for s in slots['slots']}
known = set(by_id) | {x['id'] for x in slots['extra']}
caps = {s['id']: s['cn_inplace_capacity'] for s in slots['slots']
        if s['cn_site']['how'] != 'word' or s['kind'] == 'rw_data_table'}
caps = {k: v for k, v in caps.items() if by_id[k]['cn_site']['how'] != 'movw/t'}


def ascii_ok(t):
    return all(0x20 <= ord(c) <= 0x7E for c in t)


en = load(os.path.join(ROOT, 'lang', 'en.json'))
for k, v in en['strings'].items():
    if k not in known:
        err(f'lang/en.json: unknown id {k}')
    if not ascii_ok(v):
        err(f'lang/en.json: {k} not ASCII: {v!r}')
for path in sorted(glob.glob(os.path.join(ROOT, 'lang', '*.json'))):
    code = os.path.basename(path)[:-5]
    if code in ('slots', 'layout', 'en'):
        continue
    j = load(path)
    for k, e in j['strings'].items():
        t = e.get('text')
        if k not in known:
            err(f'{path}: unknown id {k}')
        if t is None:
            continue
        if not ascii_ok(t):
            err(f'{path}: {k} not ASCII: {t!r}')
        if k in caps and by_id[k]['cn_exclusive'] and caps[k] and len(t) + 1 > caps[k]:
            err(f'{path}: {k} {t!r} longer than {caps[k] - 1} chars (in-place slot)')
        for pre, lim in SPRINTF_LIMIT.items():
            if k.startswith(pre) and len(t) > lim:
                err(f'{path}: {k} {t!r} longer than {lim} chars (sprintf buffer)')
    if j['strings'].get('rw.onoff.1', {}).get('text') != j['strings'].get('rw.bw.0', {}).get('text'):
        err(f'{path}: rw.onoff.1 and rw.bw.0 share storage and must be identical')

tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True).stdout.split()
for f in tracked:
    if f.lower().endswith(('.bin', '.bps', '.ips', '.zip', '.pdf', '.bmp')):
        err(f'vendor/binary file tracked: {f}')

for e in errors:
    print('ERROR', e)
print(f'check_repo: {len(errors)} error(s)')
sys.exit(1 if errors else 0)
