#!/usr/bin/env python3
"""
Font inspector for the FNIRSI 2D15P MCU APP (stock V2.7.0.7). Plain python3, stdlib only.

Everything is derived from the image: the Keil scatter-load region table is located,
the compressed RW init image (__decompress1 LZ format) is unpacked, the six
LVGL-style font objects are found in it, and their ROM descriptors are parsed.

Device facts this relies on (see notes/hardware.md, 2026-10-06):
  font object (RAM, stride 0x30):  +0 get_glyph_dsc fn, +4 get_bitmap fn,
      +8 u16 line_height, +0xA s16 base_line, +0x10 -> dsc (inline at +0x14)
  dsc: +0 glyph_bitmap, +4 glyph_dsc[8 B], +8 cmaps, +0xC kern(0),
      +0x12 u16 bits (cmap_num:9, bpp:4 @bit9), +0x14/+0x18 glyph cache
  cmap (one, sparse): +0 u32 range_start, +4 u16 range_END (inclusive, compared as
      upper bound by 0x39044), +8 unicode_list (u16 absolute code points, sorted),
      +0x10 u16 count
  glyph_dsc: u32 (bitmap_index:20 | adv_w:12, integer px), u8 box_w, u8 box_h,
      s8 ofs_x, s8 ofs_y.  Bitmaps 4 bpp, packed continuously (ceil(w*h/2) bytes).
  Width measuring (0x23754, 0x1AFB0, draw 0x1984C): UTF-8 decode, stop at
  NUL/LF/CR or at the first code point without a glyph, sum adv_w. No letter
  spacing, no kerning.

API:
  fonts = load(image_bytes)            # {line_height: Font}
  f.has(cp), f.advance(cp), f.glyph(cp), text_width(f, s), visible_prefix(f, s)
  cjk_runs(image_bytes)                # [(start, end, font_lh)] MCU addresses, end exclusive
  render(f, s) -> (w, h, pixels 0..15)

CLI:
  fw_font.py IMAGE                       # summary of fonts
  fw_font.py IMAGE --width 16 "Some text"
  fw_font.py IMAGE --runs
  fw_font.py IMAGE --render 16 "text" out.pgm
"""
import sys, struct, argparse

APP_OFF, APP_BASE = 0x1000, 0x12000
DELTA = APP_BASE - APP_OFF            # MCU address = file offset + 0x11000
RAM = 0x20000000


def _app_size(img):
    # header: (off,size,end) triple at 0x20 for the APP part
    off, size = struct.unpack_from('<II', img, 0x20)
    if off != APP_OFF:
        raise ValueError('unexpected container header')
    return size


def _u32(img, addr):
    return struct.unpack_from('<I', img, addr - DELTA)[0]


def decompress1(img, src, size):
    """Keil armlink __decompress1 (stock copy at MCU 0x121E4)."""
    o = src - DELTA
    out = bytearray()
    while len(out) < size:
        t = img[o]; o += 1
        n = t & 7
        if n == 0:
            n = img[o]; o += 1
        m = t >> 4
        if m == 0:
            m = img[o]; o += 1
        for _ in range(n - 1):
            out.append(img[o]); o += 1
        if t & 8:
            back = img[o]; o += 1
            p = len(out) - back
            for _ in range(m + 2):
                out.append(out[p]); p += 1
        else:
            out.extend(b'\0' * m)
    return bytes(out[:size])


def region_table(img):
    """Find Keil Region$$Table entries (load, exec, size, handler) whose exec is RAM base."""
    size = _app_size(img)
    lo, hi = APP_BASE, APP_BASE + size
    for o in range(APP_OFF, APP_OFF + size - 16, 4):
        load, exe, sz, fn = struct.unpack_from('<IIII', img, o)
        if exe == RAM and lo <= load < hi and 0 < sz < 0x10000 and lo <= (fn & ~1) < hi:
            return o + DELTA, load, exe, sz, fn
    raise ValueError('scatter-load region table not found')


def rw_image(img):
    _, load, exe, sz, _ = region_table(img)
    return decompress1(img, load, sz)


class Font:
    def __init__(self, img, rw, obj):
        r = lambda a: struct.unpack_from('<I', rw, a - RAM)[0]
        self.obj = obj
        self.line_height, self.base_line = struct.unpack_from('<Hh', rw, obj + 8 - RAM)
        dsc = r(obj + 0x10)
        self.dsc = dsc
        self.bitmap, self.gdsc, self.cmaps = r(dsc), r(dsc + 4), r(dsc + 8)
        bits = struct.unpack_from('<H', rw, dsc + 0x12 - RAM)[0]
        self.bpp = (bits >> 9) & 0xF
        self.cache = (r(dsc + 0x14), r(dsc + 0x18))
        self.range_start = _u32(img, self.cmaps)
        self.range_end, = struct.unpack_from('<H', img, self.cmaps + 4 - DELTA)
        ulist = _u32(img, self.cmaps + 8)
        n, = struct.unpack_from('<H', img, self.cmaps + 0x10 - DELTA)
        self.codepoints = list(struct.unpack_from('<%dH' % n, img, ulist - DELTA))
        self.ulist = ulist
        self.glyphs = {}
        for i, cp in enumerate(self.codepoints):
            w0, bw, bh, ox, oy = struct.unpack_from('<IBBbb', img, self.gdsc + 8 * i - DELTA)
            idx = w0 & 0xFFFFF
            nbytes = (bw * bh * self.bpp + 7) // 8
            self.glyphs[cp] = dict(index=i, adv=w0 >> 20, box_w=bw, box_h=bh, ofs_x=ox, ofs_y=oy,
                                   start=self.bitmap + idx, end=self.bitmap + idx + nbytes)
        self._img = img

    def has(self, cp):
        # 0x39044: range check, then binary search of the unicode list
        return self.range_start <= cp <= self.range_end and cp in self.glyphs

    def advance(self, cp):
        return self.glyphs[cp]['adv'] if self.has(cp) else None

    def glyph(self, cp):
        return self.glyphs.get(cp) if self.has(cp) else None

    def bitmap_of(self, cp):
        g = self.glyph(cp)
        raw = self._img[g['start'] - DELTA:g['end'] - DELTA]
        px = []
        for b in raw:
            px += [b >> 4, b & 0xF]          # 4 bpp, high nibble first (LVGL)
        return px[:g['box_w'] * g['box_h']]

    def __repr__(self):
        return (f'Font(lh={self.line_height} obj=0x{self.obj:X} glyphs={len(self.glyphs)} '
                f'bitmap=0x{self.bitmap:X} gdsc=0x{self.gdsc:X} cmap=0x{self.cmaps:X} '
                f'range=0x{self.range_start:X}..0x{self.range_end:X})')


def find_font_objects(img, rw):
    size = _app_size(img)
    code = lambda v: v & 1 and APP_BASE <= (v & ~1) < APP_BASE + size
    objs = []
    for o in range(0, len(rw) - 0x30, 4):
        f0, f1 = struct.unpack_from('<II', rw, o)
        dsc = struct.unpack_from('<I', rw, o + 0x10)[0]
        if code(f0) and code(f1) and dsc == RAM + o + 0x14:
            objs.append(RAM + o)
    return objs


def load(img):
    rw = rw_image(img)
    fonts = {}
    for obj in find_font_objects(img, rw):
        f = Font(img, rw, obj)
        fonts[f.line_height] = f
    return fonts


def _utf8_codepoints(s):
    if isinstance(s, str):
        s = s.encode('utf-8')
    # mirrors 0x3FC44 for well-formed input
    return [ord(c) for c in s.decode('utf-8')]


def visible_prefix(font, s):
    """Code points the device will actually draw/measure (stops at NUL/LF/CR or a missing glyph)."""
    out = []
    for cp in _utf8_codepoints(s):
        if cp <= 0xD and (1 << cp) & 0x2401:
            break
        if not font.has(cp):
            break
        out.append(cp)
    return out


def text_width(font, s):
    return sum(font.advance(cp) for cp in visible_prefix(font, s))


def render(font, s):
    """Single-line preview. Returns (w, h, list of 0..15 pixel values row-major).
    Vertical placement follows LVGL (top = line_height - base_line - box_h - ofs_y); the canvas
    grows to include descenders that fall below line_height (the device's own clipping of
    those rows is not modelled)."""
    cps = visible_prefix(font, s)
    w = max(1, sum(font.advance(c) for c in cps))
    tops = [font.line_height - font.base_line - font.glyph(c)['box_h'] - font.glyph(c)['ofs_y'] for c in cps]
    y_min = min([0] + tops)
    y_max = max([font.line_height] + [t + font.glyph(c)['box_h'] for t, c in zip(tops, cps)])
    h = y_max - y_min
    px = [0] * (w * h)
    x = 0
    for cp, top in zip(cps, tops):
        g = font.glyph(cp)
        bm = font.bitmap_of(cp)
        for yy in range(g['box_h']):
            for xx in range(g['box_w']):
                X, Y = x + g['ofs_x'] + xx, top - y_min + yy
                if 0 <= X < w and 0 <= Y < h:
                    px[Y * w + X] = max(px[Y * w + X], bm[yy * g['box_w'] + xx])
        x += g['adv']
    return w, h, px


def is_cjk(cp):
    return cp >= 0x2E80 and not (0xE000 <= cp <= 0xF8FF)   # exclude PUA icons (U+F014 etc.)


def _references(img):
    """All absolute pointers into the APP found as aligned words (APP + RW image) or movw/movt pairs."""
    size = _app_size(img)
    lo, hi = APP_BASE, APP_BASE + size
    refs = set()
    for o in range(APP_OFF, APP_OFF + size - 3, 4):
        v = struct.unpack_from('<I', img, o)[0]
        if lo <= v < hi:
            refs.add((v, o + DELTA, 'word'))
    rw = rw_image(img)
    for o in range(0, len(rw) - 3, 4):
        v = struct.unpack_from('<I', rw, o)[0]
        if lo <= v < hi:
            refs.add((v, RAM + o, 'rw'))
    # Thumb-2 MOVW/MOVT (T3/T1): hw1 = 11110 i 10 0 1 0/1 0 0 imm4 ; hw2 = 0 imm3 Rd imm8
    def imm16(h1, h2):
        return ((h1 & 0xF) << 12) | (((h1 >> 10) & 1) << 11) | (((h2 >> 12) & 7) << 8) | (h2 & 0xFF)
    movw = {}
    for o in range(APP_OFF, APP_OFF + size - 3, 2):
        h1, h2 = struct.unpack_from('<HH', img, o)
        if h1 & 0xFBF0 == 0xF240 and not h2 & 0x8000:
            movw[(h2 >> 8) & 0xF] = (o, imm16(h1, h2))
        elif h1 & 0xFBF0 == 0xF2C0 and not h2 & 0x8000:
            rd = (h2 >> 8) & 0xF
            if rd in movw and o - movw[rd][0] < 48:
                v = (imm16(h1, h2) << 16) | movw[rd][1]
                if lo <= v < hi:
                    refs.add((v, movw[rd][0] + DELTA, 'movw/t'))
    return refs


def font_data_ranges(img, fonts):
    """[start,end) of each font's bitmap + glyph_dsc + cmap + unicode list (MCU addresses)."""
    out = []
    for f in fonts.values():
        out.append((f.bitmap, f.ulist + 2 * len(f.codepoints)))
    return out


def _looks_like_insn(img, addr):
    """Heuristic: the aligned word at addr is (part of) a 32-bit Thumb instruction."""
    o = addr - DELTA
    pre = lambda h: (h >> 11) in (0x1D, 0x1E, 0x1F)
    h1 = struct.unpack_from('<H', img, o)[0]
    h0 = struct.unpack_from('<H', img, o - 2)[0]
    h2 = struct.unpack_from('<H', img, o + 2)[0]
    return pre(h1) or (pre(h0) and not pre(h1))


def cjk_runs(img, fonts=None, warnings=None):
    """Byte ranges [start,end) (MCU addresses) holding only bitmaps of CJK glyphs
    (cp >= 0x2E80, PUA icons excluded), not overlapping any non-CJK glyph.
    Pointer check: any RW-image word or MOVW/MOVT pair landing inside a run is fatal.
    Aligned APP words landing inside a run are reported in `warnings` (list) unless they
    sit inside font data themselves; the linear word scan cannot tell literal pools from
    instruction bytes, so these are usually coincidences (check with fw_xref.py)."""
    fonts = fonts or load(img)
    refs = _references(img)
    fdata = font_data_ranges(img, fonts)
    in_fdata = lambda a: any(s <= a < e for s, e in fdata)
    rt = region_table(img)[0]
    # __scatterload keeps Region$$Table base/limit as offsets relative to its own literal
    # (0x121DC + 0x6A3F0 = 0x7C5CC); those words are not pointers.
    scatter_rel = lambda a, v: rt <= ((a & ~3) + v) & 0xFFFFFFFF <= rt + 0x40
    runs = []
    for lh, f in sorted(fonts.items()):
        spans = sorted((g['start'], g['end'], cp) for cp, g in f.glyphs.items() if g['end'] > g['start'])
        keep = [(s, e) for s, e, cp in spans if not is_cjk(cp)]
        cur = []
        for s, e, cp in spans:
            if not is_cjk(cp):
                continue
            if cur and cur[-1][1] == s:
                cur[-1][1] = e
            else:
                cur.append([s, e])
        for s, e in cur:
            if any(ks < e and s < ke for ks, ke in keep):
                raise AssertionError(f'non-CJK glyph inside run 0x{s:X}-0x{e:X}')
            for v, a, kind in refs:
                if not s <= v < e:
                    continue
                if kind in ('rw', 'movw/t'):
                    raise AssertionError(f'run 0x{s:X}-0x{e:X} referenced by {kind} 0x{a:X} -> 0x{v:X}')
                if (not in_fdata(a) and not _looks_like_insn(img, a) and not scatter_rel(a, v)
                        and warnings is not None):
                    warnings.append(f'aligned word 0x{a:X} = 0x{v:X} points into run 0x{s:X}-0x{e:X}')
            runs.append((s, e, lh))
    return runs


def _main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('image')
    ap.add_argument('--width', nargs=2, metavar=('LH', 'TEXT'))
    ap.add_argument('--runs', action='store_true')
    ap.add_argument('--render', nargs=3, metavar=('LH', 'TEXT', 'OUT_PGM'))
    a = ap.parse_args()
    img = open(a.image, 'rb').read()
    fonts = load(img)
    if a.width:
        f = fonts[int(a.width[0])]
        vis = visible_prefix(f, a.width[1])
        full = _utf8_codepoints(a.width[1])
        print(f'{text_width(f, a.width[1])} px  ({len(vis)}/{len(full)} chars drawn, lh {f.line_height})')
        if len(vis) < len(full):
            bad = full[len(vis)]
            print(f'WARNING: truncated at U+{bad:04X} {chr(bad)!r} (no glyph / terminator)')
    elif a.runs:
        warn = []
        runs = cjk_runs(img, fonts, warn)
        for s, e, lh in runs:
            print(f'0x{s:X}-0x{e:X}  {e - s:6d} B  font {lh}px  (file 0x{s - DELTA:X}-0x{e - DELTA:X})')
        big = max(runs, key=lambda r: r[1] - r[0])
        for w in warn:
            print('warning:', w)
        print(f'total {sum(e - s for s, e, _ in runs)} B; largest 0x{big[0]:X}-0x{big[1]:X} ({big[1] - big[0]} B)')
    elif a.render:
        f = fonts[int(a.render[0])]
        w, h, px = render(f, a.render[1])
        with open(a.render[2], 'wb') as fh:
            fh.write(b'P5\n%d %d\n15\n' % (w, h) + bytes(px))
        print(f'{a.render[2]}: {w}x{h}')
    else:
        for lh, f in sorted(fonts.items()):
            asc = sum(1 for c in range(0x20, 0x7F) if f.has(c))
            print(f, f'ascii {asc}/95, cjk {sum(1 for c in f.glyphs if is_cjk(c))}')


if __name__ == '__main__':
    _main()
