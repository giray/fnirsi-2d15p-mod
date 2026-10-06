#!/usr/bin/env python3
"""Make a BPS patch (beat format, as read by Rom Patcher JS / Flips).

    python3 tools/bps_make.py SOURCE.bin TARGET.bin OUT.bps

The patch holds only SourceRead commands (copy unchanged bytes from the
user's own stock file) and TargetRead commands carrying our new bytes, so no
vendor data is redistributed. Same-size images only (all our patches are).
The result is verified by applying it with tools/bps_apply.py.
"""
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bps_apply  # noqa: E402


def _num(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def make(src, dst, meta=b''):
    if len(src) != len(dst):
        raise ValueError('source and target differ in size')
    p = bytearray(b'BPS1' + _num(len(src)) + _num(len(dst)) + _num(len(meta)) + meta)
    i, n = 0, len(dst)
    while i < n:
        j = i
        if src[i] == dst[i]:
            while j < n and src[j] == dst[j]:
                j += 1
            p += _num(((j - i - 1) << 2) | 0)              # SourceRead
        else:
            # a changed run absorbs short equal gaps (cheaper than a new command)
            while j < n and (src[j] != dst[j] or dst[j:j + 4] != src[j:j + 4]):
                j += 1
            p += _num(((j - i - 1) << 2) | 1) + dst[i:j]   # TargetRead
        i = j
    p += zlib.crc32(src).to_bytes(4, 'little') + zlib.crc32(dst).to_bytes(4, 'little')
    p += zlib.crc32(p).to_bytes(4, 'little')
    return bytes(p)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src = open(sys.argv[1], 'rb').read()
    dst = open(sys.argv[2], 'rb').read()
    patch = make(src, dst)
    if bps_apply.apply(src, patch)[0] != dst:
        sys.exit('round-trip check failed, nothing written')
    open(sys.argv[3], 'wb').write(patch)
    print(f'{sys.argv[3]}: {len(patch)} B, source crc32 {zlib.crc32(src):08X} -> target {zlib.crc32(dst):08X} (round-trip OK)')


if __name__ == '__main__':
    main()
