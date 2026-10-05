#!/usr/bin/env python3
"""
Safe byte-patcher for FNIRSI 2D15P firmware images.

Reads a JSON patch set, verifies the INPUT crc32 before touching anything,
applies byte/string replacements at exact offsets, writes a new file, and
reports the OUTPUT crc32 (and size) so you can confirm nothing drifted.

Patch file format (patches.json):
{
  "input_crc32": "B43E8C2D",            # optional but recommended: refuse if source differs
  "require_size": 1234567,               # optional: refuse if source size differs
  "output_name": "2D15P_V2.7.0.7_260826.bin",  # FNIRSI needs the exact stock name on the upgrade volume
  "patches": [
    {"note": "example: replace 4 bytes at 0x1234",
     "offset": "0x1234", "find": "01 02 03 04", "replace": "05 06 07 08"},
    {"note": "string swap (ASCII)",
     "offset": "0x5000", "find_str": "Ramp", "replace_str": "Triangle",
     "pad": " ", "max_len": 8}   # pad/truncate replacement to exactly the old field width
  ]
}
"""
import sys, json, zlib, argparse

def hexbytes(s): return bytes.fromhex(s.replace(' ', ''))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_bin')
    ap.add_argument('patches_json')
    ap.add_argument('-o', '--output', help='override output path')
    ap.add_argument('--dry-run', action='store_true', help='verify + report, write nothing')
    a = ap.parse_args()

    data = bytearray(open(a.input_bin, 'rb').read())
    in_crc = zlib.crc32(data) & 0xffffffff
    spec = json.load(open(a.patches_json))

    print(f'input : {a.input_bin}  size={len(data)} (0x{len(data):X})  crc32={in_crc:08X}')

    want_crc = spec.get('input_crc32')
    if want_crc and int(want_crc, 16) != in_crc:
        sys.exit(f'ABORT: input crc32 {in_crc:08X} != expected {int(want_crc,16):08X}. '
                 f'Wrong firmware version or already modified.')
    want_size = spec.get('require_size')
    if want_size and want_size != len(data):
        sys.exit(f'ABORT: input size {len(data)} != expected {want_size}.')

    for i, p in enumerate(spec['patches']):
        off = int(p['offset'], 0)
        if 'find_str' in p:
            old = p['find_str'].encode('ascii')
            newtxt = p['replace_str']
            width = p.get('max_len', len(old))
            pad = p.get('pad', '\x00')
            if len(newtxt) > width:
                sys.exit(f'patch {i} ({p.get("note","")}): replacement "{newtxt}" longer than field width {width}')
            new = (newtxt + pad * (width - len(newtxt))).encode('ascii')
            found = bytes(data[off:off+len(old)])
            if found != old:
                sys.exit(f'patch {i} ({p.get("note","")}): FIND mismatch at 0x{off:X}: '
                         f'file has {found!r}, expected {old!r}')
            data[off:off+width] = new
        else:
            old = hexbytes(p['find']); new = hexbytes(p['replace'])
            if len(old) != len(new):
                sys.exit(f'patch {i}: find/replace length differ ({len(old)} vs {len(new)}); '
                         f'same-length only to keep offsets stable')
            found = bytes(data[off:off+len(old)])
            if found != old:
                sys.exit(f'patch {i} ({p.get("note","")}): FIND mismatch at 0x{off:X}: '
                         f'file has {found.hex()}, expected {old.hex()}')
            data[off:off+len(new)] = new
        print(f'patch {i:2d} @0x{off:06X}: OK  {p.get("note","")}')

    out_crc = zlib.crc32(data) & 0xffffffff
    out = a.output or spec.get('output_name') or (a.input_bin + '.patched')
    print(f'output: {out}  size={len(data)} (0x{len(data):X})  crc32={out_crc:08X}')
    if a.dry_run:
        print('dry-run: nothing written')
        return
    open(out, 'wb').write(data)
    print('written. Copy this file (keep the exact name) into the "Upgrade file" volume.')

if __name__ == '__main__':
    main()
