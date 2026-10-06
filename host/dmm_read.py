#!/usr/bin/env python3
"""Show / log FNIRSI 2D15P multimeter readings on Linux.

Needs the mod's DMM streaming patch: while the multimeter page is shown and a
host has the USB serial port open, the device sends one line per reading:

    DMM,<function>,<value|OL|token>,<unit>,<hold 0/1>\\r\\n

    python3 host/dmm_read.py                 # live display
    python3 host/dmm_read.py --csv log.csv   # also append to a CSV file
    python3 host/dmm_read.py --raw           # print lines exactly as received
    python3 host/dmm_read.py --idn           # ask the device who it is, then exit

Standard library only. Listening is passive; the only thing this tool can send
is the read-only "*IDN?" query (with --idn). It never sends anything else, in
particular no "CAL:" command (see SAFETY.md).
Port: /dev/fnirsi-2d15p (from host/99-fnirsi-2d15p.rules), else the ttyACM*
whose USB id is 0416:50a1.
"""
import argparse
import csv
import glob
import os
import select
import sys
import termios
import time
from datetime import datetime

VID, PID = '0416', '50a1'
IDN_QUERY = b'*IDN?'          # exact bytes, no CR/LF: the device compares the whole transfer


def find_port():
    if os.path.exists('/dev/fnirsi-2d15p'):
        return '/dev/fnirsi-2d15p'
    for tty in sorted(glob.glob('/sys/class/tty/ttyACM*')):
        dev = os.path.realpath(os.path.join(tty, 'device'))
        for up in (dev, os.path.dirname(dev)):
            try:
                vid = open(os.path.join(up, 'idVendor')).read().strip()
                pid = open(os.path.join(up, 'idProduct')).read().strip()
            except OSError:
                continue
            if (vid, pid) == (VID, PID):
                return '/dev/' + os.path.basename(tty)
    return None


def open_port(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attr = termios.tcgetattr(fd)
    attr[0] = 0                                        # iflag: raw
    attr[1] = 0                                        # oflag: raw
    attr[2] = termios.CS8 | termios.CREAD | termios.CLOCAL | termios.HUPCL
    attr[3] = 0                                        # lflag: no echo, non-canonical
    attr[4] = attr[5] = termios.B115200                # ignored by CDC, set for tidiness
    termios.tcsetattr(fd, termios.TCSANOW, attr)
    termios.tcflush(fd, termios.TCIFLUSH)
    return fd                                          # open() raised DTR: the device starts streaming


def lines(fd, timeout=None):
    buf = b''
    deadline = time.monotonic() + timeout if timeout else None
    while True:
        wait = None if deadline is None else max(0, deadline - time.monotonic())
        r, _, _ = select.select([fd], [], [], wait)
        if not r:
            if buf:
                yield buf.decode('ascii', 'replace')
            return
        chunk = os.read(fd, 512)
        if not chunk:
            raise OSError('device disconnected')
        buf += chunk
        while b'\n' in buf:
            line, buf = buf.split(b'\n', 1)
            yield line.rstrip(b'\r').decode('ascii', 'replace')


def parse(line):
    p = line.split(',')
    if len(p) != 5 or p[0] != 'DMM':
        return None
    return {'function': p[1], 'value': p[2], 'unit': p[3], 'hold': p[4] == '1'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', help='serial device (default: auto)')
    ap.add_argument('--csv', help='append readings to this CSV file')
    ap.add_argument('--raw', action='store_true', help='print received lines unchanged')
    ap.add_argument('--idn', action='store_true', help='send *IDN? and print the reply')
    a = ap.parse_args()

    port = a.port or find_port()
    if not port:
        sys.exit('No FNIRSI 2D15P found (USB 0416:50a1). Is it on, with USB Sharing OFF?')
    fd = open_port(port)

    if a.idn:
        os.write(fd, IDN_QUERY)
        reply = b''
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.0:
            if select.select([fd], [], [], 0.2)[0]:
                reply += os.read(fd, 256)
        # streamed DMM lines may be mixed in; the IDN reply has no newline
        idn = [l for l in reply.decode('ascii', 'replace').split('\r\n') if l and not l.startswith('DMM,')]
        print(' '.join(idn) or '(no reply)')
        return

    out = None
    if a.csv:
        new = not os.path.exists(a.csv) or os.path.getsize(a.csv) == 0
        out_f = open(a.csv, 'a', newline='')
        out = csv.writer(out_f)
        if new:
            out.writerow(['time', 'function', 'value', 'unit', 'hold'])

    print(f'Listening on {port}. Show the multimeter page on the device. Ctrl-C to stop.', file=sys.stderr)
    try:
        for line in lines(fd):
            if a.raw:
                print(line, flush=True)
                continue
            r = parse(line)
            if not r:
                continue
            now = datetime.now()
            hold = '  HOLD' if r['hold'] else ''
            print(f"\r{now:%H:%M:%S}  {r['function']:<5} {r['value']:>10} {r['unit']:<5}{hold}   ",
                  end='', flush=True)
            if out:
                out.writerow([now.isoformat(timespec='milliseconds'), r['function'], r['value'], r['unit'],
                              int(r['hold'])])
                out_f.flush()
    except KeyboardInterrupt:
        print(file=sys.stderr)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
