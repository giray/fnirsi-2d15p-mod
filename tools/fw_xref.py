#!/usr/bin/env python3
"""
Cross-reference helper for the 2D15P MCU APP part (Thumb-2, linked at 0x12000).
Run with tools/.venv/bin/python (needs capstone).

  fw_xref.py <image.bin> --build                   # linear sweep -> firmware/work/xref.json
  fw_xref.py <image.bin> --to 0x7B640 [0x...]      # who references these addresses (literal/adr/movw-movt/bl)
  fw_xref.py <image.bin> --func 0x21199 [-n 60]    # disassemble from an address (resolving pc-relative loads)
  fw_xref.py <image.bin> --callers 0x21199         # BL call sites of a function
  fw_xref.py <image.bin> --writes 0x2000xxxx       # instructions that store to an absolute address (via literal base)

Addresses are MCU addresses (file offset + 0x11000). Linear sweep is approximate
around literal pools; verify with --func before trusting a boundary.
"""
import sys, json, struct, argparse, pathlib, bisect
from capstone import *
from capstone.arm import *

APP_OFF, APP_BASE, APP_SIZE = 0x1000, 0x12000, 0x6A9C0
DELTA = APP_BASE - APP_OFF
DB = pathlib.Path('firmware/work/xref.json')

def load(path):
    d = open(path, 'rb').read()
    return d, d[APP_OFF:APP_OFF+APP_SIZE]

def u32(app, addr):
    o = addr - APP_BASE
    return struct.unpack_from('<I', app, o)[0] if 0 <= o <= len(app)-4 else None

def md():
    m = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS); m.detail = True; m.skipdata = True
    return m

def sweep(app):
    m = md(); refs = []; calls = []; movw = {}
    for ins in m.disasm(app, APP_BASE):
        if ins.id == 0: continue
        ops = ins.operands
        if ins.mnemonic.startswith('ldr') and len(ops) == 2 and ops[1].type == ARM_OP_MEM and ops[1].mem.base == ARM_REG_PC:
            target = ((ins.address + 4) & ~3) + ops[1].mem.disp
            v = u32(app, target)
            if v is not None: refs.append((ins.address, v, 'lit'))
        elif ins.mnemonic == 'adr':
            refs.append((ins.address, ((ins.address + 4) & ~3) + ops[1].imm, 'adr'))
        elif ins.mnemonic == 'movw':
            movw[ops[0].reg] = (ins.address, ops[1].imm)
        elif ins.mnemonic == 'movt' and ops[0].reg in movw:
            a, lo = movw.pop(ops[0].reg); refs.append((a, (ops[1].imm << 16) | lo, 'movw/t'))
        elif ins.mnemonic in ('bl', 'blx') and ops and ops[0].type == ARM_OP_IMM:
            calls.append((ins.address, ops[0].imm))
    return refs, calls

def build(path):
    d, app = load(path)
    refs, calls = sweep(app)
    funcs = set(t for _, t in calls)
    # add push {..., lr} prologues (Thumb16 0xB5xx, Thumb32 stmdb sp!,{...,lr} = E92D 4xxx) as function starts
    for i in range(0, len(app)-3, 2):
        if app[i+1] == 0xB5 or (app[i] == 0x2D and app[i+1] == 0xE9 and (app[i+3] & 0x40)):
            funcs.add(APP_BASE + i)
    funcs = sorted(funcs)
    DB.parent.mkdir(parents=True, exist_ok=True)
    json.dump({'refs': refs, 'calls': calls, 'funcs': funcs}, open(DB, 'w'))
    print(f'{len(refs)} refs, {len(calls)} calls, {len(funcs)} BL-target functions -> {DB}')

def owner(funcs, addr):
    i = bisect.bisect_right(funcs, addr) - 1
    return funcs[i] if i >= 0 else None

def disasm(app, addr, n):
    m = md(); start = addr & ~1
    for ins in list(m.disasm(app[start-APP_BASE:start-APP_BASE+n*4], start))[:n]:
        extra = ''
        for op in ins.operands:
            if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC:
                v = u32(app, ((ins.address + 4) & ~3) + op.mem.disp)
                if v is not None:
                    extra = f'  ; =0x{v:X}'
                    if APP_BASE <= v < APP_BASE+APP_SIZE:
                        raw = app[v-APP_BASE:v-APP_BASE+40].split(b'\0')[0]
                        if raw and all(0x20 <= b < 0x7f or b >= 0x80 for b in raw):
                            try: extra += '  "' + raw.decode('utf-8') + '"'
                            except UnicodeDecodeError: pass
        print(f'  {ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}{extra}')
        if ins.mnemonic == 'pop' and 'pc' in ins.op_str or ins.mnemonic == 'bx' and ins.op_str == 'lr':
            if n > 0: print('  --- (return)')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bin'); ap.add_argument('--build', action='store_true')
    ap.add_argument('--to', nargs='+'); ap.add_argument('--func'); ap.add_argument('-n', type=int, default=60)
    ap.add_argument('--switch', nargs=2, metavar=('TBx_ADDR','N'), help='decode a tbb/tbh jump table: case -> target, first insns')
    ap.add_argument('--callers'); ap.add_argument('--near', nargs=2, metavar=('LO','HI'), help='refs into an address range')
    a = ap.parse_args()
    if a.build: return build(a.bin)
    d, app = load(a.bin)
    db = json.load(open(DB)); funcs = db['funcs']
    if a.to:
        for t in a.to:
            t = int(t, 0); print(f'refs to 0x{t:X}:')
            for at, v, k in db['refs']:
                if v == t: print(f'  0x{at:X} ({k})  in func 0x{owner(funcs, at) or 0:X}')
    if a.near:
        lo, hi = (int(x, 0) for x in a.near)
        for at, v, k in db['refs']:
            if lo <= v < hi: print(f'  0x{at:X} ({k}) -> 0x{v:X}  in func 0x{owner(funcs, at) or 0:X}')
    if a.callers:
        t = int(a.callers, 0)
        for at, v in db['calls']:
            if v == t: print(f'  bl from 0x{at:X}  in func 0x{owner(funcs, at) or 0:X}')
    if a.switch:
        at, n = int(a.switch[0], 0), int(a.switch[1], 0)
        m = md(); ins = next(m.disasm(app[at-APP_BASE:at-APP_BASE+4], at))
        half = ins.mnemonic == 'tbh'; tbl = at + 4
        seen = {}
        for i in range(n + 1):
            off = struct.unpack_from('<H' if half else '<B', app, tbl - APP_BASE + i * (2 if half else 1))[0]
            tgt = tbl + off * 2
            seen.setdefault(tgt, []).append(i)
        for tgt, cases in sorted(seen.items()):
            print(f'cases {cases} -> 0x{tgt:X}')
            disasm(app, tgt, a.n)
    if a.func:
        disasm(app, int(a.func, 0), a.n)

if __name__ == '__main__':
    main()
