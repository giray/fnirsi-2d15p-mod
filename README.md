# FNIRSI 2D15P firmware customisation

Workspace for tailoring the FNIRSI 2D15P's firmware to a multimeter-first
workflow. No vendor PC software exists for this device; all changes are made by
editing the stock firmware image and reflashing via the device's built-in
updater.

**Goals (priority order):** (1) boot into the multimeter, (2) one-touch DMM probe
zero / REL, (3) remap the DDS button to the multimeter, (4) show DMM readings
on a Linux PC. Full detail in `CLAUDE.md`.

## Status (2026-10-05)

| item | state |
|---|---|
| Target firmware | V2.7.0.7 (`2D15P_V2.7.0.7_260826.bin`, stock crc32 `B43E8C2D`) |
| Recovery bootloader | confirmed working on the owner's unit |
| Goal 1 (boot to DMM) + Goal 3 (DDS key → DMM) | **patch set ready**, `firmware/dmm-first.json`, not yet flashed |
| Goal 2 (REL) | stock has no REL; needs new code, not started |
| Goal 4 (Linux display) | DMM UART packet parser located in firmware; not started |

The reverse-engineering map (page/event model, key tables, DMM data path) is in
`notes/re-plan.md`; image layout and MCU facts in `notes/hardware.md`.

## Start here

1. Read `CLAUDE.md` (goals, known facts, how to work here) and `SAFETY.md`
   (do not flash without this).
2. Read `notes/` — the lab notebook. `prior-art.md` is the highest-value file:
   someone has already modded this exact firmware and mapped internals.
3. Owner: put the official firmware `.bin` in `firmware/stock/` and `chmod 444`
   it. It is gitignored and never redistributed. The official manual PDF goes
   in the project root (also gitignored).
4. Tools: `python3 -m venv tools/.venv && tools/.venv/bin/pip install capstone`
   (only `fw_xref.py` needs it; the patcher and inspector are stdlib-only).

## Layout

```
CLAUDE.md                 project brief + rules (read every session)
SAFETY.md                 flashing safety + pre-flash checklist
README.md                 this file
LICENSE                   GPL-3.0 (our code and notes only; see below)
notes/                    lab notebook: prior-art, hardware, flashing, re-plan
tools/fw_patch.py         CRC-gated same-length patcher (the only way images get modified)
tools/fw_inspect.py       container header, parts, vectors, strings, pointer tables, --carve
tools/fw_xref.py          capstone cross-reference database + disassembly queries
firmware/dmm-first.json   Goal 1+3 patch set
firmware/patches.example.json   patch-set template
firmware/stock/           untouched official .bin (gitignored, read-only)
firmware/work/            scratch / patched outputs / xref.json (gitignored)
host/                     Linux host helpers (planned: udev rule, read-only CDC sniffer)
```

## Quick commands

```
# first look at an image
python3 tools/fw_inspect.py firmware/stock/<file>.bin --grep 'volt|dds|language'

# disassemble around an offset
python3 tools/fw_disasm.py firmware/stock/<file>.bin 0x100 --len 0x80

# apply a patch set (dry run first; verifies CRC, writes nothing)
python3 tools/fw_patch.py firmware/stock/<file>.bin firmware/<set>.json --dry-run

# cross-references (needs tools/.venv with capstone)
tools/.venv/bin/python tools/fw_xref.py firmware/stock/<file>.bin --build
tools/.venv/bin/python tools/fw_xref.py firmware/stock/<file>.bin --func 0x2CA60 -n 40
```

Addresses in the notes are MCU addresses; `file offset = address − 0x11000`
for the APP part.

## Licence and what is (not) in this repo

Everything written here (tools, notes, patch-set JSON) is **GPL-3.0**, see
`LICENSE`. FNIRSI's firmware, manual and the derived patched images are
**not** included and must not be committed; `.gitignore` enforces this. A
patch set only describes byte differences keyed to the stock CRC32, the same
approach as the community UA mod. Modifying your own device is at your own
risk; read `SAFETY.md`.

## Reality check

Goals 1–3 are MCU UI/logic changes and are plausible (the prior-art mod does the
same class of edits). The scope's acquisition quirks live in the FPGA and are
**not** fixable from this firmware — not a goal here. Don't trust rise-time or
overshoot below ~4.19 MHz on this scope regardless.
