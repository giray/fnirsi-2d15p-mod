#!/usr/bin/env python3
"""
Generate a language patch set for the FNIRSI 2D15P V2.7.0.7 (stock crc32 B43E8C2D).

English stays the primary language (slot 2) with the fixes from lang/en.json.
The secondary slot (1, stock: Chinese) gets lang/<code>.json; missing
translations fall back to the fixed English. All text must be plain ASCII:
the device stops drawing a string at the first code point its font lacks.

    python3 tools/lang_build.py STOCK.bin tr                 # -> firmware/build/dmm-first+tr.json
    python3 tools/lang_build.py STOCK.bin de --base none     # language only, no dmm-first patches
    python3 tools/lang_build.py STOCK.bin en                 # English in both slots, no Chinese
    python3 tools/lang_build.py STOCK.bin tr --image         # also write firmware/work/<name>/<stock name>.bin

New strings are packed into the CJK glyph bitmaps of the six fonts, which
nothing draws once every secondary-slot string is ASCII. Pointers are
repointed where the slot is a pointer word or a movw/movt pair; slots that are
only reachable in place (pc-relative addw strings, RW-image tables) are
overwritten within their capacity. The output is an ordinary tools/fw_patch.py
patch set, gated on the stock CRC, with the base set (dmm-first) merged in.
"""
import argparse
import json
import os
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

BASE = 0x11000            # MCU address = file offset + BASE
STOCK_CRC = 0xB43E8C2D
STOCK_NAME = '2D15P_V2.7.0.7_260826.bin'
APP_END = 0x7C9C0
# CJK glyph area kept free for new code (Goal 4 DMM streaming); strings never go here
CODE_RESERVED = [(0x66000, 0x6C249)]
HEAP_FIRST = 0x6545C
# sprintf target 0x200036B8 is 40 bytes; these ids are formatted into it
SPRINTF_LIMIT = {'meas.': 20, 'btn.back': 20, 'about.3': 20}
# fixed-width boxes: id prefix -> (font line height, max pixels, where)
MENU_MAX_ROWS = 3   # 3-row menu (lang/layout.json): rows at y=0x28/0x3C/0x50, divider at 0x68
PIXEL_LIMIT = {'trig.mode.': (12, 34, 'status-bar trigger mode box (0x2C5F6: x=0xDE w=0x22)')}


def die(msg):
    sys.exit(f'lang_build: {msg}')


def load_json(path):
    with open(path) as f:
        return json.load(f)


def h(addr):
    return int(addr, 16) if isinstance(addr, str) else addr


def check_ascii(sid, text, where):
    if text is None:
        return
    bad = [c for c in text if not (0x20 <= ord(c) <= 0x7E)]
    if bad:
        die(f'{where}: "{sid}" = {text!r} has non-ASCII {bad!r}; use plain ASCII (e.g. i for ı, ae for ä)')


# ---- Thumb-2 movw/movt -------------------------------------------------------

def _imm16(hw1, hw2):
    return ((hw1 & 0xF) << 12) | (((hw1 >> 10) & 1) << 11) | (((hw2 >> 12) & 7) << 8) | (hw2 & 0xFF)


def _enc(op_hw1, rd, imm):
    hw1 = op_hw1 | (((imm >> 11) & 1) << 10) | ((imm >> 12) & 0xF)
    hw2 = (((imm >> 8) & 7) << 12) | (rd << 8) | (imm & 0xFF)
    return hw1.to_bytes(2, 'little') + hw2.to_bytes(2, 'little')


def _hw(img, addr):
    o = addr - BASE
    return int.from_bytes(img[o:o + 2], 'little'), int.from_bytes(img[o + 2:o + 4], 'little')


def movw_movt_patches(img, at, old_target, new_target, note):
    """Re-point a movw Rd,#lo ... movt Rd,#hi pair (movt within 16 bytes after)."""
    hw1, hw2 = _hw(img, at)
    if hw1 & 0xFBF0 != 0xF240:
        die(f'0x{at:X}: expected movw, found {hw1:04X} {hw2:04X}')
    rd = (hw2 >> 8) & 0xF
    for a in range(at + 4, at + 20, 2):
        t1, t2 = _hw(img, a)
        if t1 & 0xFBF0 == 0xF2C0 and (t2 >> 8) & 0xF == rd:
            break
    else:
        die(f'0x{at:X}: no movt r{rd} follows the movw')
    old = (_imm16(t1, t2) << 16) | _imm16(hw1, hw2)
    if old != old_target:
        die(f'0x{at:X}: movw/movt loads 0x{old:X}, slot map says 0x{old_target:X}')
    return [patch(at, img, _enc(0xF240, rd, new_target & 0xFFFF), f'{note}: movw r{rd} lo -> 0x{new_target:X}'),
            patch(a, img, _enc(0xF2C0, rd, new_target >> 16), f'{note}: movt r{rd} hi')]


# ---- patches ------------------------------------------------------------------

def patch(addr, img, new, note, data=False):
    """data=True: the overwritten bytes are vendor data (glyph bitmaps, Chinese
    strings); verify them by CRC32 instead of copying them into the patch set."""
    o = addr - BASE
    old = bytes(img[o:o + len(new)])
    p = {'note': note, 'offset': f'0x{o:05X}'}
    if data:
        p['find_crc32'] = f'{zlib.crc32(old):08X}'
    else:
        p['find'] = old.hex(' ')
    p['replace'] = bytes(new).hex(' ')
    return p


def span(p):
    o = int(p['offset'], 16)
    return o, o + len(bytes.fromhex(p['replace'].replace(' ', '')))


class Heap:
    def __init__(self, runs):
        # the 20 px font's run first (where strings have always gone, keeps
        # released builds byte-identical), then the rest by size
        self.runs = [[a, b] for a, b in sorted(runs, key=lambda r: (r[0] != HEAP_FIRST, -(r[1] - r[0])))]
        self.placed = {}

    def put(self, text):
        if text in self.placed:
            return self.placed[text]
        need = len(text) + 1
        for r in self.runs:
            if r[1] - r[0] >= need:
                addr = r[0]
                r[0] += need
                self.placed[text] = addr
                return addr
        die(f'out of heap space for {text!r}')


def cjk_runs(img):
    try:
        import fw_font
        runs = []
        for a, b, *_ in fw_font.cjk_runs(img):
            for ra, rb in CODE_RESERVED:      # cut reserved ranges out of the run
                if a < rb and ra < b:
                    if a < ra:
                        runs.append((a, ra))
                    a = max(a, rb)
            if a < b:
                runs.append((a, b))
        return runs
    except ImportError:
        die('tools/fw_font.py not found (needed to locate the free CJK glyph area)')


def text_widths(img):
    try:
        import fw_font
    except ImportError:
        return None
    fonts = fw_font.load(img)
    return lambda px, s: fw_font.text_width(fonts[px], s)


def build(img, code, base_set):
    slots = load_json(os.path.join(ROOT, 'lang', 'slots.json'))
    en_fix = load_json(os.path.join(ROOT, 'lang', 'en.json'))['strings']
    sec = None if code == 'en' else load_json(os.path.join(ROOT, 'lang', f'{code}.json'))
    by_id = {s['id']: s for s in slots['slots']}
    extra = {x['id']: x for x in slots['extra']}
    for k, v in en_fix.items():
        if k not in by_id and k not in extra:
            die(f'lang/en.json: unknown id {k!r}')
        check_ascii(k, v, 'lang/en.json')

    english = {sid: en_fix.get(sid, s['en']) for sid, s in by_id.items()}
    mod_version = load_json(os.path.join(ROOT, 'lang', 'en.json')).get('mod_version')
    second, warn = {}, []
    if sec:
        for sid, e in sec['strings'].items():
            if sid not in by_id and sid not in extra:
                die(f'lang/{code}.json: unknown id {sid!r}')
            check_ascii(sid, e.get('text'), f'lang/{code}.json')
            if sid in english and e.get('en') != english[sid]:
                warn.append(f'{sid}: English changed to {english[sid]!r} (file has {e.get("en")!r}); re-check translation')
    for sid in by_id:
        t = sec['strings'].get(sid, {}).get('text') if sec else None
        second[sid] = t if t is not None else english[sid]
    if mod_version:   # About shows "<Version> (mod X.Y):V2.7.0.7" in both languages
        for d in (english, second):
            d['about.3'] = f"{d['about.3']} (mod {mod_version})"
    lang_name = (sec['strings'].get('lang.name', {}).get('text') if sec else None) or (sec['name'] if sec else 'English')
    check_ascii('lang.name', lang_name, 'language name')

    for sid in by_id:
        for pre, lim in SPRINTF_LIMIT.items():
            if sid.startswith(pre):
                for t in (english[sid], second[sid]):
                    if len(t) > lim:
                        die(f'{sid}: {t!r} longer than {lim} chars (formatted into a 40-byte sprintf buffer)')

    tw = text_widths(img)
    if tw is None:
        die('tools/fw_font.py is required for the pixel-width checks')
    for sid in by_id:
        for pre, (px, lim, where) in PIXEL_LIMIT.items():
            if sid.startswith(pre):
                for t in (english[sid], second[sid]):
                    if tw(px, t) > lim:
                        die(f'{sid}: {t!r} is {tw(px, t)} px wide, the {where} is {lim} px')

    for lang_texts in (english, second):
        rows = menu_rows(tw, [lang_texts[f'menu.{i}'] for i in range(13)])
        if len(rows) > MENU_MAX_ROWS:
            die(f'top menu needs {len(rows)} rows, only {MENU_MAX_ROWS} fit above the divider: '
                + ' / '.join(' '.join(r) for r in rows))

    heap = Heap(cjk_runs(img))
    out, skipped = [], []

    def inplace(addr, cap, text, sid, why):
        if cap is None:
            die(f'{sid}: no in-place capacity known for {why}')
        if len(text) + 1 > cap:
            die(f'{sid}: {text!r} needs {len(text) + 1} bytes, only {cap} available in place ({why})')
        data = text.encode() + b'\0' * (cap - len(text))
        out.append(patch(addr, img, data, f'{sid} [{why}] in place: {text!r}', data=True))

    inplace_owner = {}
    for sid, s in by_id.items():
        for slot, text, site, target, cap, excl in (
                (1, second[sid], s['cn_site'], s['cn_target'], s['cn_inplace_capacity'], s['cn_exclusive']),
                (2, english[sid], s['en_site'], s['en_target'], s['en_inplace_capacity'], None)):
            stock_text = s['en'] if slot == 2 else None
            if slot == 2 and text == stock_text:
                continue
            tag = f'{sid} slot{slot}'
            how = site['how']
            if s['kind'] in ('rom_table', 'code_pool_pair') and how == 'word':
                a = heap.put(text)
                out.append(patch(h(site['at']), img, a.to_bytes(4, 'little'), f'{tag} -> {text!r} @0x{a:X}'))
            elif how == 'movw/t':
                a = heap.put(text)
                out.extend(movw_movt_patches(img, h(site['at']), h(target), a, f'{tag} {text!r}'))
            else:   # pc-relative addw or RW-image table: in place only
                t_addr = h(target)
                if slot == 1 and not excl:
                    if text != s['en']:
                        skipped.append(f'{tag}: stock string is shared, kept as is (wanted {text!r})')
                    continue
                if slot == 2 and s['kind'] == 'rw_data_table':
                    die(f'{tag}: English RW-table strings cannot be changed')
                prev = inplace_owner.get(t_addr)
                if prev:
                    if prev[1] != text:
                        die(f'{tag}: shares its string with {prev[0]} but text differs ({text!r} vs {prev[1]!r})')
                    continue
                inplace_owner[t_addr] = (tag, text)
                inplace(t_addr, cap, text, tag, s['kind'])

    ln = extra['lang.name']
    a = heap.put(lang_name)
    for at in ln['sites']:
        out.extend(movw_movt_patches(img, h(at), h(ln['stock_target']), a, f'lang.name {lang_name!r}'))
    fb = extra['fmt.bmp']
    if fb['id'] in en_fix:
        inplace(h(fb['at']), fb['capacity'], en_fix[fb['id']], 'fmt.bmp', 'sprintf format')

    for text, addr in heap.placed.items():
        out.append(patch(addr, img, text.encode() + b'\0', f'heap string {text!r}', data=True))

    layout_path = os.path.join(ROOT, 'lang', 'layout.json')
    layout = load_json(layout_path)['patches'] if os.path.exists(layout_path) else []
    if not layout:
        warn.append('lang/layout.json missing: secondary language keeps the Chinese-mode layout constants')

    allp = list(base_set) + list(layout) + out
    spans = sorted((span(p) + (p['note'],) for p in allp))
    for (a0, a1, n0), (b0, b1, n1) in zip(spans, spans[1:]):
        if b0 < a1:
            die(f'overlapping patches: [{n0}] and [{n1}] at 0x{b0:X}')
    for p in out:
        o0, o1 = span(p)
        if not (0x1000 <= o0 and o1 <= APP_END - BASE):
            die(f'patch outside APP: {p["note"]}')
    return allp, english, second, lang_name, heap, warn, skipped


def menu_rows(tw, labels):
    """Row breaking of the top menu, as drawn by 0x1AEB0 with lang/layout.json
    applied: 14 px font, item = text + 10 px, gap 5 px, wrap when x > 0x188."""
    rows, x = [[]], 0xC
    for t in labels:
        w = tw(14, t)
        if x + w > 0x188 and rows[-1]:
            rows.append([])
            x = 0xC
        rows[-1].append(t)
        x += w + 0xA + 5
    return rows


def apply_in_memory(img, patches):
    data = bytearray(img)
    for p in patches:
        o0, o1 = span(p)
        cur = bytes(data[o0:o1])
        if (cur.hex(' ') != p['find']) if 'find' in p else (zlib.crc32(cur) != int(p['find_crc32'], 16)):
            die(f'self-check: find mismatch for [{p["note"]}]')
        data[o0:o1] = bytes.fromhex(p['replace'].replace(' ', ''))
    return bytes(data)


def verify(img, out_img, english, second, lang_name):
    """Resolve every slot in the patched image the way the firmware does."""
    slots = load_json(os.path.join(ROOT, 'lang', 'slots.json'))

    def cstr(addr):
        o = addr - BASE
        return out_img[o:out_img.index(b'\0', o)].decode('utf-8')

    def movw_movt(at):
        hw1, hw2 = _hw(out_img, at)
        rd = (hw2 >> 8) & 0xF
        for a in range(at + 4, at + 20, 2):
            t1, t2 = _hw(out_img, a)
            if t1 & 0xFBF0 == 0xF2C0 and (t2 >> 8) & 0xF == rd:
                return (_imm16(t1, t2) << 16) | _imm16(hw1, hw2)

    n = 0
    for s in slots['slots']:
        for want, site, target in ((second[s['id']], s['cn_site'], s['cn_target']),
                                   (english[s['id']], s['en_site'], s['en_target'])):
            if site['how'] == 'word':
                if s['kind'] == 'rw_data_table':
                    got = cstr(h(target))          # pointer itself unchanged (compressed RW image)
                else:
                    o = h(site['at']) - BASE
                    got = cstr(int.from_bytes(out_img[o:o + 4], 'little'))
            elif site['how'] == 'movw/t':
                got = cstr(movw_movt(h(site['at'])))
            else:
                got = cstr(h(target))
            if got != want and not (site is s['cn_site'] and not s['cn_exclusive'] and got == s['en']):
                die(f'self-check: {s["id"]} reads {got!r}, expected {want!r}')
            n += 1
    for at in slots['extra'][0]['sites']:
        if cstr(movw_movt(h(at))) != lang_name:
            die(f'self-check: language label at 0x{h(at):X} wrong')
    if any(0x80 <= c for s in slots['slots'] for c in cstr(h(s['cn_target'])).encode()
           if s['kind'] == 'rw_data_table' and s['cn_exclusive']):
        die('self-check: CJK text left in an RW table string')
    return n


def width_report(img, english, second):
    tw = text_widths(img)
    if not tw:
        return ['(tools/fw_font.py not available: no pixel-width check)']
    lines = []
    for sid in english:
        if second[sid] == english[sid]:
            continue
        we, ws = tw(16, english[sid]), tw(16, second[sid])
        if ws > we * 1.25 and ws - we > 12:
            lines.append(f'{sid:16} {ws:4d}px vs EN {we:4d}px  {second[sid]!r}')
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stock_bin')
    ap.add_argument('lang', help='secondary language code (lang/<code>.json), or "en" for English only')
    ap.add_argument('--base', default='firmware/dmm-first.json', help='patch set to merge in, or "none"')
    ap.add_argument('-o', '--out', help='output JSON (default firmware/build/<base>+<lang>.json)')
    ap.add_argument('--image', action='store_true', help='also build the image with tools/fw_patch.py')
    a = ap.parse_args()

    img = open(a.stock_bin, 'rb').read()
    if zlib.crc32(img) != STOCK_CRC:
        die(f'{a.stock_bin}: crc32 {zlib.crc32(img):08X}, need stock {STOCK_CRC:08X}')
    base_set, base_name = [], 'lang'
    if a.base != 'none':
        b = load_json(os.path.join(ROOT, a.base) if not os.path.isabs(a.base) else a.base)
        if int(b['input_crc32'], 16) != STOCK_CRC:
            die(f'{a.base} is not keyed to the stock image')
        base_set, base_name = b['patches'], os.path.splitext(os.path.basename(a.base))[0]

    allp, english, second, lang_name, heap, warn, skipped = build(img, a.lang, base_set)
    checked = verify(img, apply_in_memory(img, allp), english, second, lang_name)
    print(f'self-check: {checked} slot reads resolve to the intended text')
    name = f'{base_name}+{a.lang}'
    out = a.out or os.path.join(ROOT, 'firmware', 'build', f'{name}.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    doc = {'_comment': f'GENERATED by tools/lang_build.py ({a.lang}, base {a.base}). Do not edit; edit lang/*.json and rebuild.',
           'input_crc32': f'{STOCK_CRC:08X}', 'require_size': len(img), 'output_name': STOCK_NAME,
           'secondary_language': lang_name, 'patches': allp}
    with open(out, 'w') as f:
        json.dump(doc, f, indent=1, ensure_ascii=True)
        f.write('\n')
    used = sum(len(t) + 1 for t in heap.placed)
    print(f'{out}: {len(allp)} patches ({len(base_set)} base), {len(heap.placed)} strings / {used} B in the CJK area')
    print(f'secondary language: {lang_name}')
    for w in warn:
        print('WARN', w)
    for s in skipped:
        print('KEPT', s)
    for line in width_report(img, english, second):
        print('WIDE', line)
    if a.image:
        img_out = os.path.join(ROOT, 'firmware', 'work', name, STOCK_NAME)
        os.makedirs(os.path.dirname(img_out), exist_ok=True)
        r = subprocess.run([sys.executable, os.path.join(HERE, 'fw_patch.py'), a.stock_bin, out, '-o', img_out],
                           capture_output=True, text=True)
        if r.returncode:
            die('fw_patch failed:\n' + r.stdout + r.stderr)
        print(r.stdout.strip().splitlines()[-2])


if __name__ == '__main__':
    main()
