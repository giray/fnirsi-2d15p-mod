# tools/

- `fw_patch.py` — the only way to modify a firmware image. Verifies the input
  CRC32 (and optional size), applies same-length byte or padded-string
  replacements from a JSON patch set, reports the output CRC32.
  `python3 tools/fw_patch.py <stock.bin> <set.json> --dry-run` first, always.

- `fw_inspect.py` — read-only first look: parses the container header, lists
  the APP/FPGA parts with CRCs, prints the Cortex-M vector table and the
  file→address delta (+0x11000), `--grep` over ASCII strings with addresses,
  `--ptrs START END` to dump a pointer table as strings, `--carve DIR` to write
  the parts out. Standard library only.
- `fw_xref.py` — needs `.venv`. `--build` sweeps the APP part once into
  `firmware/work/xref.json` (literal/adr/movw-movt refs, BL call graph,
  function starts from prologues). Then `--to ADDR…` (who references),
  `--near LO HI`, `--callers FN`, `--func ADDR -n N` (disassemble, resolves
  pc-relative loads and strings), `--switch TBx_ADDR N` (decode tbb/tbh).
- `.venv/` — Python venv with capstone 5 for disassembly:
  `tools/.venv/bin/python`. Use `Cs(CS_ARCH_ARM, CS_MODE_THUMB|CS_MODE_MCLASS)`
  and remember address = file offset + 0x11000 for the APP part.

Planned, not written: `fw_disasm.py` (wrapper around the above for "disassemble
around address X") and `host/cdc_sniff.py`.
- `bps_apply.py` — apply a BPS patch (e.g. the UA mod) with patch/source/target CRC32 checks: `python3 tools/bps_apply.py stock.bin mod.bps out.bin`
