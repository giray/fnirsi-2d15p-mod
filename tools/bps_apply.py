#!/usr/bin/env python3
"""Apply a BPS patch (beat format, as made by Flips / Rom Patcher JS).

    python3 tools/bps_apply.py SOURCE.bin PATCH.bps OUTPUT.bin

Verifies the patch's own CRC32, the source CRC32 and the target CRC32 stored
in the patch; refuses to write anything if any of them mismatch.
"""
import sys
import zlib


def _num(p, i):
    data, shift = 0, 1
    while True:
        x = p[i]; i += 1
        data += (x & 0x7F) * shift
        if x & 0x80:
            return data, i
        shift <<= 7
        data += shift


def apply(src, patch):
    if patch[:4] != b'BPS1':
        raise ValueError('not a BPS1 patch')
    body, footer = patch[:-12], patch[-12:]
    s_crc, t_crc, p_crc = (int.from_bytes(footer[k:k + 4], 'little') for k in (0, 4, 8))
    if zlib.crc32(patch[:-4]) != p_crc:
        raise ValueError('patch file CRC mismatch (corrupt download?)')
    if zlib.crc32(src) != s_crc:
        raise ValueError(f'source CRC {zlib.crc32(src):08X} != expected {s_crc:08X}')
    i = 4
    s_size, i = _num(patch, i)
    t_size, i = _num(patch, i)
    meta_size, i = _num(patch, i)
    i += meta_size
    if len(src) != s_size:
        raise ValueError(f'source size {len(src)} != expected {s_size}')
    out = bytearray(t_size)
    o = s_rel = t_rel = 0
    while i < len(body):
        d, i = _num(patch, i)
        cmd, n = d & 3, (d >> 2) + 1
        if cmd == 0:                       # SourceRead
            out[o:o + n] = src[o:o + n]; o += n
        elif cmd == 1:                     # TargetRead
            out[o:o + n] = patch[i:i + n]; i += n; o += n
        else:
            off, i = _num(patch, i)
            off = (-1 if off & 1 else 1) * (off >> 1)
            if cmd == 2:                   # SourceCopy
                s_rel += off
                out[o:o + n] = src[s_rel:s_rel + n]; s_rel += n; o += n
            else:                          # TargetCopy (may overlap)
                t_rel += off
                for _ in range(n):
                    out[o] = out[t_rel]; o += 1; t_rel += 1
    if o != t_size:
        raise ValueError('output size mismatch')
    if zlib.crc32(out) != t_crc:
        raise ValueError(f'target CRC {zlib.crc32(out):08X} != expected {t_crc:08X}')
    return bytes(out), s_crc, t_crc


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src = open(sys.argv[1], 'rb').read()
    out, s_crc, t_crc = apply(src, open(sys.argv[2], 'rb').read())
    open(sys.argv[3], 'wb').write(out)
    print(f'source crc32={s_crc:08X} OK  ->  {sys.argv[3]} size={len(out)} crc32={t_crc:08X} OK')


if __name__ == '__main__':
    main()
