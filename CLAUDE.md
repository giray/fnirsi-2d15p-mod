# FNIRSI 2D15P — firmware customisation project

A project to reverse-engineer and modify the firmware of a **FNIRSI 2D15P**
(3-in-1: 100 MHz 2-ch oscilloscope + True RMS multimeter + 10 MHz DDS
generator) to better suit how the owner actually uses it. There is no vendor
PC software and no official SDK; everything here is done by editing the stock
firmware image.

## What the owner wants (priority order)

The multimeter is the primary instrument; the scope is secondary; the signal
generator is barely used. The firmware changes we are working toward, in order:

1. **Boot into the multimeter.** The device should power on showing the DMM
   function, not the oscilloscope.
2. **Probe zeroing / relative (REL) for the DMM.** A quick way to null out lead
   resistance and offsets — ideally a one-touch "zero" the way bench meters do
   with REL. If stock firmware already has a REL/relative mode, the goal may
   reduce to *surfacing* it (fewer taps, or a dedicated button) rather than
   writing it from scratch.
3. **Remap the physical DDS button to the multimeter.** The generator is the
   least-used function; its dedicated button is better spent switching to the
   DMM.
4. **Display on Linux** While the Osciloscope display capture is not possible
   displaying multimeter measurements on a Linux PC is to be explored

Anything beyond these is out of scope unless the owner asks.

## Current state of knowledge (verified; sources in `notes/`)

- The firmware image is **not encrypted**. It contains raw firmware plus
  resources (bitmap fonts etc.) — confirmed by a teardown author on EEVblog.
- The device has a **bootloader recovery**: power off, hold the large knob,
  briefly press power. The bootloader presents as a USB mass-storage volume
  regardless of the main firmware, so a bad flash is recoverable. This is our
  safety net — confirm it works on the owner's unit BEFORE flashing anything
  custom.
- Normal flashing: enable **Menu → USB Sharing**, the device mounts as USB
  mass storage, copy the `.bin` into the **`Upgrade file`** folder, power-cycle.
  Up- and down-grade both work.
- A community member (Serhii Povshednyi, GitHub `Serhii-Povshednyi/FNIRSI-2D15P-UA`)
  has already produced a **working modified image** for firmware **V2.7.0.7**
  (a BPS patch adding a language + fixing UI strings). This proves the
  bootloader accepts third-party-modified images, and it maps out useful
  internals. He is the most valuable external contact. See `notes/prior-art.md`.
- Hardware: FPGA **EG4S20BG256**, MCU is a **Synwit** Cortex-M part (markings
  lasered off; identified via the USB VID/strings it reports as a virtual COM
  device), DMM IC also lasered off. Much processing (incl. LCD drive) happens
  in the **FPGA**, which the MCU firmware cannot change.
- The MCU reads a frequency counter from the FPGA and sends it config bits
  (bandwidth-limit bit per channel; frequency-counter mode bit). Signal
  processing proper lives in the FPGA.
- Firmware versions seen in the wild: 1.2.0.6, 1.3.0.7, 1.4.0.7, 2.0.0.7,
  2.6.0.7, **2.7.0.7** (latest as of this writing). The known-good mod targets
  **2.7.0.7** specifically (`2D15P_V2.7.0.7_260826.bin`, stock CRC32 `B43E8C2D`).
  **We have this exact image** in `firmware/stock/` (read-only, logged in
  `notes/flashing.md`), plus the official manual `2D15P_Manual_New_ZH_EN.pdf`
  in the project root.
- **Image layout (verified 2026-10-05):** 4 KB header, MCU APP at file 0x1000
  (436,672 B), FPGA bitstream at file 0x6C000 to the end. The APP is linked at
  **0x12000** so `MCU address = file offset + 0x11000`. Core is ARMv8-M
  (Cortex-M33 class), FreeRTOS, built with Keil. Details in `notes/hardware.md`.
- **Phase 1 done (2026-10-05): Goals 1 and 3 are a 3-entry patch set,
  `firmware/dmm-first.json`** (boot page constant + two instructions in the
  DDS key handler). Derivation and the UI/event architecture map are in
  `notes/re-plan.md` under "Phase 1 results". Not yet flashed.
- **Stock DMM has no REL/relative mode** (manual §3.3 and firmware strings both
  confirm; it has HOLD and MIN/MAX only). Goal 2 therefore means adding one,
  not surfacing one. Entering the DMM is Menu → multimeter.

## Feasibility, honestly

- Goals 1–3 are **MCU-firmware / UI changes** (default screen on boot, button
  mapping, surfacing an existing mode). These are the kind of change the UA mod
  already demonstrates, so they are plausible — *if* stock firmware already
  contains the behaviours and we are mostly re-routing to them.
- Writing a brand-new REL/zeroing algorithm from scratch is harder and may
  touch measurement code we don't fully understand. First establish whether
  stock DMM already has a relative mode (check the manual and the live device).
- What is **not** achievable from the MCU side: anything the FPGA owns
  (acquisition, the known sub-4.19 MHz scope artefacts). Don't promise scope
  behaviour fixes.

## Repo layout (as of 2026-10-05)

Not a git repository (yet). Layout:

```
CLAUDE.md                   this brief (read every session)
SAFETY.md                   flashing procedure + pre-flash checklist (authoritative)
README.md                   overview
notes/prior-art.md          the UA mod and what it proves (lab notebook)
notes/re-plan.md            phased RE plan with append-only findings log
notes/hardware.md           hardware facts + findings log
notes/flashing.md           stock-image CRCs, recovery round-trip status, flash log
tools/fw_patch.py           CRC-gated, same-length byte/string patcher (the only way to modify an image)
tools/fw_inspect.py         header/parts/vectors/strings/pointer-table inspector, --carve
tools/fw_xref.py            capstone xref db (firmware/work/xref.json): --to/--func/--switch/--callers
firmware/dmm-first.json     the Goal 1+3 patch set (file offsets = MCU addr - 0x11000)
tools/.venv/                venv with capstone 5 (use tools/.venv/bin/python for disassembly)
tools/README.md             tool list
firmware/patches.example.json   patch-set template (example offsets, not real)
firmware/stock/             owner-supplied official .bin, chmod 444 (empty until then)
firmware/work/              scratch / patched outputs
firmware/.gitignore         ignores *.bin/*.bps/*.ips if git is ever initialised
host/                       Linux host helpers (empty; cdc_sniff.py planned)
```

Still referenced in `README.md` / `notes/re-plan.md` but **not written**:
`tools/fw_disasm.py`, `host/cdc_sniff.py`. No `arm-none-eabi-*` toolchain is
on PATH. If a task needs one of these, create it (or ask the owner to install
it) rather than assuming it works.

## Commands

```bash
# Dry run: verify input CRC32/size and every find-pattern, write nothing
python3 tools/fw_patch.py firmware/stock/<stock.bin> firmware/<set>.json --dry-run

# Apply: writes to output_name from the JSON (or -o PATH), prints output CRC32
python3 tools/fw_patch.py firmware/stock/<stock.bin> firmware/<set>.json [-o firmware/work/out.bin]

# First look: header, parts, vectors, link base, CRC; grep strings; dump pointer tables
python3 tools/fw_inspect.py firmware/stock/<stock.bin>
python3 tools/fw_inspect.py firmware/stock/<stock.bin> --grep 'volt|dds|language'
python3 tools/fw_inspect.py firmware/stock/<stock.bin> --ptrs 0x5A0BC 0x5A0F0
python3 tools/fw_inspect.py firmware/stock/<stock.bin> --carve firmware/work   # APP + FPGA parts

# Disassemble (capstone lives in the venv; Thumb, M-class, address = file + 0x11000)
tools/.venv/bin/python -c "from capstone import *; ..."
```

`tools/fw_patch.py` and `tools/fw_inspect.py` are plain Python 3 standard
library. There are no tests, no build, no lint. The patch JSON format is documented in the script's docstring:
optional `input_crc32` / `require_size` gates, `output_name` (must be the
exact stock filename), and a `patches` list of either hex `find`/`replace`
pairs (equal length enforced) or ASCII `find_str`/`replace_str` with
`max_len`/`pad` to keep the field width. Every patch is verified against the
file content before any byte is changed, so a mismatch aborts the whole set.

## How to work in this repo

- **Read `notes/` first** every session: `prior-art.md`, `re-plan.md`,
  `hardware.md`, `flashing.md`. Append findings as dated bullets under the
  "Findings log" / "Flash log" headings; don't rewrite history.
- **Firmware files are user-supplied.** The owner downloads the official `.bin`
  from FNIRSI into `firmware/stock/`; we cannot redistribute it. Keep it
  read-only (`chmod 444`). Patched outputs go in `firmware/work/`. Never place
  a vendor `.bin` under version control (`firmware/.gitignore` covers this).
- **Every change to a firmware image goes through `tools/fw_patch.py`**, which
  verifies the input CRC32, enforces same-length byte patches, and reports the
  output CRC32. Do not hand-edit a `.bin` with a hex editor and flash it;
  record the change as a patch entry so it is repeatable and reversible.
- Distributing a mod should follow the UA precedent: ship a diff (BPS patch or
  a `fw_patch.py` JSON) keyed to the stock CRC, never the patched image.

## Safety rules — do not deviate

See `SAFETY.md` for the full list. The non-negotiables:

1. **Never flash a custom image until bootloader recovery is confirmed working**
   on this specific unit. (Confirmed 2026-10-05, see `notes/flashing.md`; the
   unit runs 2.7.0.7. Re-confirm if the unit or the bootloader ever changes.)
2. **Keep a pristine copy** of every stock `.bin` in `firmware/stock/`, read-only.
   Always be able to return to stock.
3. **Match the firmware version exactly.** Offsets are version-specific. A patch
   built for 2.7.0.7 must refuse to apply to anything else (the CRC gate does
   this). Never bypass a CRC/size check to force a patch onto a different version.
4. **Do not touch calibration data.** The DMM/scope calibration may live in
   flash and may be unrecoverable if overwritten. When in doubt, leave a region
   alone and ask.
5. **Do not write to the undocumented USB CDC/serial port on a live unit** until
   we understand it from static analysis — factory ports sometimes accept
   calibration/debug writes.
6. Always `sync` and unmount the upgrade volume before power-cycling, so the
   write is actually complete.

## Verification before any flash

Walk the checklist in `SAFETY.md` → "Pre-flash checklist" out loud with the
owner. If any item is unchecked, stop.
