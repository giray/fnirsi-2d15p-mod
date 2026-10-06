# Prior art

## The UA mod (most important)

- Repo: `Serhii-Povshednyi/FNIRSI-2D15P-UA` on GitHub.
- An **unofficial patch for firmware V2.7.0.7** that adds a Ukrainian UI language
  and corrects English strings. Distributed as a **BPS patch** applied to the
  official `.bin` (so it redistributes only the diff, not FNIRSI's code).
- Target file: `2D15P_V2.7.0.7_260826.bin`, **stock CRC32 `B43E8C2D`**.
  Patched result CRC32 `4D482107`. The patch checks the source checksum and
  refuses other versions.
- Apply with **Rom Patcher JS** (browser, `marcrobledo.com/RomPatcher.js/`) or
  Floating IPS (Flips). Output must be renamed back to the exact stock name.
- Flash path it documents: Menu → USB Sharing → ON, device mounts as USB disk,
  copy file into `Upgrade file` folder, power-cycle. Revert by flashing the
  official file the same way. Recovery bootloader: hold large knob + briefly
  press power.

### Why this repo matters to us

It proves our goals are the *kind* of thing that's been done:
- It edits **UI strings, fonts, and menu layout** — same class of change as
  "boot into DMM" and "relabel/remap a button".
- The README documents the **MCU↔FPGA split** precisely:
  - frequency readout comes from FPGA as a 32-bit value per channel, bit 31
    selects period-measurement vs pulse-counting mode;
  - the bandwidth-limit switch is **one bit per channel in a channel config byte**
    sent to the FPGA;
  - the MCU reads the FPGA frequency counter only to display F and for automatic
    trigger-source selection — it does **not** change signal processing from it.
- It confirms the sub-4.19 MHz artefact is an **FPGA** issue (threshold is
  exactly 2^22 Hz = 4,194,304 Hz, the FPGA frequency-counter mode switch) and
  therefore **not fixable from MCU firmware**. Don't attempt it.

### Action

- Contact the author via the repo's Issues tab. He has already located string
  tables, font tables, and part of the MCU↔FPGA interface for 2.7.0.7 — exactly
  the map we need for "boot screen", "button remap", and "surface REL".
- Ask specifically: where is the **default/startup mode** selected; where is the
  **physical button → action** mapping; does stock DMM have a **relative/REL**
  mode and where is it invoked.

## Other

- No official FNIRSI PC application exists for the 2D15P. (FNIRSI ships a
  "USB Meter Tool" PC app for its *USB testers* — different product line,
  different protocol; not applicable here.)
- PC-side features the 2D15P officially has are only: **screenshot export** (BMP,
  ~470×272, via USB mass storage after enabling USB Sharing) and **firmware
  update** (copy `.bin` to `Upgrade file`). Both already work on Linux with no
  vendor software. There is no raw waveform/sample export.

## 2026-10-06 — UA mod 1.2 stacked with our patches

- Cloned the repo to `firmware/work/ua-repo/` (BPS `2D15P_V2.7.0.7_UA-mod-1.2.bps`,
  README says result crc32 `3DD5A6F0`; the older 4D482107 above was v1.0).
- `tools/bps_apply.py` (new, stdlib) verifies patch/source/target CRCs:
  stock B43E8C2D → `firmware/work/ua/…bin` 3DD5A6F0 OK.
- Diff vs stock: 98 runs, 53,227 bytes, all in APP (FPGA untouched). Header
  change is only the APP part size 0x6A9C0 → 0x6A9D0 (no header CRC).
  Code edits are small (0x1AF28…0x2C5DA touch maps/menu layout, 0x4C81E…
  0x4F01A one-byte layout tweaks); bulk is fonts (0x5C325–0x69D3F) and
  strings (0x7ACC0–0x7C9C3). **No overlap** with any dmm-first patch, and
  none inside the functions we patch or call (0x300B4, 0x2CA60, 0x36018 init,
  page setters).
- English fixes cannot cleanly be split from the Ukrainian work (string
  tables, fonts and menu layout change together), so we take the whole mod:
  Chinese is replaced by Ukrainian; English stays selectable and is the saved
  setting on this unit.
- `firmware/ua-dmm-first.json` = dmm-first's 4 patches gated on 3DD5A6F0.
  (Deleted 2026-10-06 — UA base shelved.)
- 2026-10-06: **Owner does not want Ukrainian** (so the full UA stack,
  `ua-dmm-first.json`, is shelved). English-only fixes, keeping Chinese, need
  our own patch set. UA's English fixes are mostly **pointer redirects** in the
  CN/EN tables (24 EN slots, 0x5A014–0x5A504, e.g. Level→Horizontal,
  Ramp→Triangle, Skew→Offset, Regarding→About, Auto Shut→Auto Off,
  On-off→Continuity, Peri→Period, A-on/A-off→All On/All Off, Set→Settings,
  USB Sharing→USB Drive, Afterglow→Persistence), new text placed in space UA
  freed by deleting CJK glyphs (0x6990A..). Without that space we must pack new
  strings into slack from shortened stock strings (Native information,
  name:100M…, USB-sharing and low-battery messages ≈ 60 B) or find other free
  space. Longer labels may need UA's 3-row menu layout change to fit; the
  remaining ~5 fixes are code-referenced strings (e.g. "2.bmpSaving...").
- 2026-10-06: Repo published (public) at github.com/giray/fnirsi-2d15p-mod,
  release v1.0 (pre-release, BPS files). Thank-you/credit note sent to the UA
  author: github.com/Serhii-Povshednyi/FNIRSI-2D15P-UA/issues/1 (reused: English
  corrections, 3-row menu constants; shared: status-bar box width, sprintf
  buffer size, glyph-miss truncation, SCPI parser).
