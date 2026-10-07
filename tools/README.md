# tools/

All tools are plain Python 3 (standard library) unless noted. Addresses are MCU
addresses; for the APP part `file offset = address - 0x11000`.

**Building and patching**
- `fw_patch.py`: the only way a firmware image gets modified. It verifies the
  input CRC32 (and optional size), applies same-length patches from a JSON patch
  set and reports the output CRC32. Each patch is checked before it is written,
  either by its literal `find` bytes (code, pointers) or by `find_crc32` (vendor
  data we overwrite but don't redistribute). Always run `--dry-run` first:
  `python3 tools/fw_patch.py <stock.bin> <set.json> --dry-run`
- `lang_build.py`: builds English (with the fixes) plus one secondary language
  from `lang/*.json` into a stock-CRC-gated patch set, merging
  `firmware/dmm-first.json`, `lang/layout.json`, `firmware/dmm-stream.json`
  (Goal 4) and `firmware/dmm-rel.json` (Goal 2), so every build is a complete
  mod image. It checks ASCII, byte limits, pixel limits and menu rows, and
  self-checks the patched image. See `lang/README.md`.
- `build_all.sh`: rebuilds every variant (`firmware/build/*.json`, images in
  `firmware/work/`) plus the no-language base (dmm-first + stream + rel), makes
  the `.bps` release files and `SHA256SUMS` in `firmware/work/release/`.
- `bps_make.py` / `bps_apply.py`: create / apply BPS patches (the format used
  by Rom Patcher JS and Flips), with source/target/patch CRC32 checks.
- `check_repo.py`: firmware-free sanity checks run by CI (JSON valid, patch sets
  CRC/size-gated, translations ASCII and within limits, no vendor binaries
  tracked). Run it before committing.

The firmware features themselves are hand-written patch sets:
`firmware/dmm-first.json` (Goals 1+3), `firmware/dmm-stream.json` (Goal 4) and
`firmware/dmm-rel.json` (Goal 2). Their Thumb code lives in the dead CJK glyph
area and is verified with the unicorn harness `firmware/work/scratch/emu.py`.

**Analysis**
- `fw_inspect.py`: first look at an image. Parses the container header, lists
  the APP/FPGA parts with CRCs, prints the vector table, `--grep` over strings,
  `--ptrs START END` to dump a pointer table, `--carve DIR` to write the parts out.
- `fw_font.py`: reads the device fonts out of the image (via the compressed
  RW data): glyph lookup, `text_width` exactly as the firmware measures,
  `cjk_runs` (the Chinese glyph bitmaps reused for new strings), `--render LH
  "text" out.pgm` previews.
- `fw_xref.py` (needs the venv): `--build` sweeps the APP part once into
  `firmware/work/xref.json`. Then use `--to ADDR…`, `--near LO HI`,
  `--callers FN`, `--func ADDR -n N` (disassembly with pc-relative loads and
  strings resolved), `--switch TBx_ADDR N`.

**Venv** (only for disassembly/assembly):
`python3 -m venv tools/.venv && tools/.venv/bin/pip install capstone keystone-engine`.
Use `Cs(CS_ARCH_ARM, CS_MODE_THUMB|CS_MODE_MCLASS)`. Keystone mis-encodes
Thumb-2 *conditional* wide branches (`bne.w` etc.), so hand-encode those and
always check new code by disassembling it with capstone.

Host side: `host/dmm_read.py` reads/logs the Goal-4 DMM stream over USB (live
view or CSV); it can also send the read-only `*IDN?` query and nothing else.
`host/99-fnirsi-2d15p.rules` keeps ModemManager off the port and adds
`/dev/fnirsi-2d15p`.
