#!/usr/bin/env python3
"""
First-look inspector for FNIRSI 2D15P firmware images (container format).

  python3 tools/fw_inspect.py firmware/stock/<file>.bin            # header, parts, vectors, crc
  python3 tools/fw_inspect.py <file>.bin --grep 'volt|dds|language' # strings (file offset + MCU address)
  python3 tools/fw_inspect.py <file>.bin --carve firmware/work      # write APP/FPGA parts out
  python3 tools/fw_inspect.py <file>.bin --ptrs 0x5a0c0 0x5a320     # dump a region as string pointers

Container layout (verified on V2.7.0.7, see notes/hardware.md):
  0x000  char name[32]  "APP_2D15P_V2.7_260826.bin"
  0x020  u32 app_off, app_size, app_end     (0x1000, 0x6A9C0, 0x6B9BF)
  0x02C  char name[32]  "FPGA_2D15P_v0.7(251118).bin"
  0x04C  u32 fpga_off, fpga_size, fpga_end  (0x6C000, 0xB9EE9, 0x125EE8)
The APP part is a Cortex-M (ARMv8-M) image linked at APP_BASE; MCU address =
file offset + (APP_BASE - app_off). Standard library only (no capstone needed).
"""
import sys, re, struct, zlib, argparse, pathlib

APP_BASE = 0x12000   # verified: vector[1] = 0x1230D, Reset_Handler at file 0x130C

def parse_header(d):
    parts = []
    for name_off, tbl_off in ((0x00, 0x20), (0x2C, 0x4C)):
        name = d[name_off:name_off+32].split(b'\0')[0].decode('ascii', 'replace')
        off, size, end = struct.unpack_from('<III', d, tbl_off)
        parts.append(dict(name=name, off=off, size=size, end=end, ok=(off+size-1 == end and end < len(d))))
    return parts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bin')
    ap.add_argument('--grep', help='case-insensitive regex over ASCII strings (min 4)')
    ap.add_argument('--min', type=int, default=4)
    ap.add_argument('--carve', metavar='DIR', help='write APP and FPGA parts into DIR')
    ap.add_argument('--ptrs', nargs=2, metavar=('START_ADDR', 'END_ADDR'),
                    help='dump MCU address range as u32 string pointers')
    a = ap.parse_args()
    d = open(a.bin, 'rb').read()
    print(f'file  : {a.bin}  size={len(d)} (0x{len(d):X})  crc32={zlib.crc32(d)&0xffffffff:08X}')
    parts = parse_header(d)
    for p in parts:
        print(f'part  : {p["name"]:32s} off=0x{p["off"]:06X} size=0x{p["size"]:06X} end=0x{p["end"]:06X} '
              f'crc32={zlib.crc32(d[p["off"]:p["off"]+p["size"]])&0xffffffff:08X} {"OK" if p["ok"] else "BAD"}')
    app = parts[0]
    delta = APP_BASE - app['off']
    sp, *vec = struct.unpack_from('<16I', d, app['off'])
    names = ['Reset','NMI','HardFault','MemManage','BusFault','UsageFault','','','','','SVC','DebugMon','','PendSV','SysTick']
    print(f'vectors: SP=0x{sp:08X}  ' + '  '.join(f'{n}=0x{v:X}' for n, v in zip(names, vec) if n))
    print(f'addr  : MCU address = file offset + 0x{delta:X}   (APP linked at 0x{APP_BASE:X})')

    if a.carve:
        out = pathlib.Path(a.carve); out.mkdir(parents=True, exist_ok=True)
        for p in parts:
            fn = out / p['name']
            fn.write_bytes(d[p['off']:p['off']+p['size']])
            print(f'carved: {fn}  ({p["size"]} bytes)')

    if a.grep:
        rx = re.compile(a.grep, re.I)
        for m in re.finditer(rb'[\x20-\x7e]{%d,}' % a.min, d):
            s = m.group().decode('ascii')
            if rx.search(s):
                fo = m.start()
                addr = f'0x{fo+delta:06X}' if app['off'] <= fo < app['off']+app['size'] else '   --   '
                print(f'  file 0x{fo:06X}  addr {addr}  {s}')

    if a.ptrs:
        s, e = (int(x, 0) for x in a.ptrs)
        for addr in range(s, e, 4):
            fo = addr - delta
            v = struct.unpack_from('<I', d, fo)[0]
            txt = ''
            if app['off'] <= v - delta < app['off']+app['size']:
                raw = d[v-delta:v-delta+48].split(b'\0')[0]
                try: txt = raw.decode('utf-8')
                except UnicodeDecodeError: txt = repr(raw)
            print(f'  0x{addr:06X}: 0x{v:08X}  {txt}')

if __name__ == '__main__':
    main()
