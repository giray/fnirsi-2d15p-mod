# FNIRSI 2D15P: multimeter-first firmware mod

[![check](https://github.com/giray/fnirsi-2d15p-mod/actions/workflows/check.yml/badge.svg)](https://github.com/giray/fnirsi-2d15p-mod/actions/workflows/check.yml)
**Project:** <https://github.com/giray/fnirsi-2d15p-mod>, with downloads on the
[Releases](https://github.com/giray/fnirsi-2d15p-mod/releases) page. Current
version: **mod 1.0**.

An unofficial modification of the **FNIRSI 2D15P** (100 MHz 2-channel scope +
True RMS multimeter + DDS generator) firmware for people who mainly use it as a
**multimeter**, with **corrected English** and an optional **Turkish, German or
Dutch** UI.

> **Firmware V2.7.0.7 only** (`2D15P_V2.7.0.7_260826.bin`, CRC32 `B43E8C2D`).
> Every patch checks this and refuses any other file. Not affiliated with
> FNIRSI. You flash this at your own risk; read [SAFETY.md](SAFETY.md).

| English | Turkish: DMM page |
|---|---|
| ![English settings with the 3-row menu](docs/screenshots/en-settings.png) | ![DMM page in Turkish](docs/screenshots/tr-dmm.png) |
| **German** | **Dutch** |
| ![German settings](docs/screenshots/de-settings.png) | ![Dutch math panel](docs/screenshots/nl-math.png) |
| **Turkish** | **Dutch** |
| ![Turkish horizontal panel](docs/screenshots/tr-horizontal.png) | ![Dutch settings](docs/screenshots/nl-settings.png) |

## What it changes

**Multimeter first** (`firmware/dmm-first.json`)
- Boots into the **multimeter** instead of the oscilloscope.
- The **DDS key** toggles scope ↔ multimeter. The signal generator stays
  available from the main menu.
- The **DDS key LED** is lit on the multimeter page (and, as before, whenever
  the generator output is on).
- The **Menu key** works on the multimeter page: it returns to the scope with
  the main menu open (stock ignores it there).

**Languages** (`lang/`)
- Corrected English, e.g. Level → Horizontal, Ramp → Triangle, Skew → Offset,
  Regarding → About, Auto Shut → Auto Off, On-off → Continuity,
  "2.bmpSaving..." → "2.bmp saving...", clearer USB and low-battery messages.
- **One secondary language replaces Chinese**: Turkish, German or Dutch (or
  none). Written in plain ASCII (`Turkce`, `Lautstaerke`) because the device
  fonts have no accented letters.
- **Three-row top menu**, so full labels fit without covering the submenu;
  the touch zones are moved to match.
- English is the default after a factory reset.
- **Settings → About** shows the mod version (`Version (mod 1.0):V2.7.0.7`),
  so you can always tell which build is installed.

Measurement, calibration and the FPGA are not touched.

## Variants

| Variant | Patch set | Result CRC32 |
|---|---|---|
| Multimeter-first only, stock languages | `firmware/dmm-first.json` | `3A36D9C7` |
| + English fixes, no second language | `firmware/build/dmm-first+en.json` | `0576CBF4` |
| + English fixes + Turkish | `firmware/build/dmm-first+tr.json` | `725F2B1B` |
| + English fixes + German | `firmware/build/dmm-first+de.json` | `1AB2F8B6` |
| + English fixes + Dutch | `firmware/build/dmm-first+nl.json` | `D54F66DE` |

## Install

1. Download the **official** V2.7.0.7 firmware from FNIRSI and unzip it. You
   need `2D15P_V2.7.0.7_260826.bin` (CRC32 `B43E8C2D`).
2. Make the modified file, either way:
   - **Browser, no install:** get the `.bps` for your variant from the
     [Releases](https://github.com/giray/fnirsi-2d15p-mod/releases) page, open
     [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/), pick the
     stock `.bin` as ROM and the `.bps` as patch, *Apply patch*.
   - **Python 3 (stdlib only):**
     ```bash
     mkdir -p out && python3 tools/fw_patch.py 2D15P_V2.7.0.7_260826.bin firmware/build/dmm-first+de.json -o out/2D15P_V2.7.0.7_260826.bin
     ```
3. Check the result's CRC32 against the table above, and make sure the file is
   named **exactly** `2D15P_V2.7.0.7_260826.bin`.
4. On the device: **Menu → USB Sharing (USB Drive) → ON**. Copy the file into
   the **`Upgrade file`** folder, `sync`/eject, then power-cycle. The updater
   runs and the file disappears.
5. For the second language: **Settings → Language**.

**Reverting:** flash the official file the same way. **If the device doesn't
boot:** power off, **hold the large knob and briefly press power**. The
recovery bootloader appears as a USB drive regardless of the main firmware;
copy the official file into `Upgrade file` and power-cycle. Try this once with
the stock file *before* flashing anything custom ([SAFETY.md](SAFETY.md)).

## Translations

Translations live in `lang/<code>.json`, one entry per UI string with the
English next to it. Corrections and new languages are welcome. See
[lang/README.md](lang/README.md) for the rules (ASCII only, length limits) and
how to build. The builder checks everything it can before writing anything:
ASCII, byte and pixel limits measured with the device's own fonts, and a
self-check of every string read in the patched image.

The Turkish, German and Dutch texts are first drafts. Fixes from native
speakers are very welcome, especially for the abbreviations.

## Contributing

- **Translations:** edit `lang/<code>.json` and open a pull request, or use the
  *Translation* issue template. New languages are welcome; see
  [lang/README.md](lang/README.md).
- **Bugs:** open an issue with the variant, the mod version from the About
  page and, ideally, a screenshot.
- **Firmware changes:** read [SAFETY.md](SAFETY.md) and the lab notebook in
  [notes/](notes/) first. Every change must be a same-length, CRC-gated patch
  and must not touch calibration data. CI (`tools/check_repo.py`) checks
  everything that can be checked without the firmware image;
  `tools/build_all.sh` checks the rest locally.

## How it works

The image is not encrypted. The MCU application is a Keil-built FreeRTOS
program for an ARMv8-M (Cortex-M33-class) Synwit MCU, linked at `0x12000`
(`MCU address = file offset + 0x11000`). All changes are **same-length byte
patches** applied by `tools/fw_patch.py`, which refuses to run unless the input
CRC32 matches the stock image.

- The secondary language uses the Chinese slot (language byte `1`). The new
  strings are stored in the bitmap area of the Chinese glyphs in the six UI
  fonts, which nothing draws any more. Slot pointers are redirected, and Chinese-mode layout
  constants are set to the English values.
- The UI/event model, key tables, LED driver, string tables, fonts and DMM data
  path are documented in [notes/](notes/), the lab notebook of this project.

| Tool | |
|---|---|
| `tools/fw_patch.py` | CRC-gated same-length patcher (stdlib) |
| `tools/lang_build.py` | build English + one language into a patch set ([lang/README.md](lang/README.md)) |
| `tools/build_all.sh` | rebuild every variant, make `.bps` release files and SHA256SUMS |
| `tools/fw_font.py` | read the device fonts: widths, CJK glyph area, `--render` previews |
| `tools/fw_inspect.py` | image header, parts, vectors, strings, pointer tables |
| `tools/fw_xref.py` | capstone cross-reference database and disassembly queries |
| `tools/bps_apply.py`, `tools/bps_make.py` | apply / create BPS patches |
| `tools/check_repo.py` | firmware-free checks run by CI |

Disassembly tools need `python3 -m venv tools/.venv && tools/.venv/bin/pip install capstone keystone-engine`;
everything else is plain Python 3.

## Not done (yet)

- **REL / probe zero for the DMM:** the stock firmware has no relative mode, so
  this needs new code.
- **DMM readings on a Linux PC:** the firmware has a SCPI-like parser
  (`*IDN?`, `MEAS:CH`, …) that is probably reachable over the USB serial port.
  It also has calibration commands, so we won't write to that port until it's
  understood from static analysis.
- Status-bar words (`Trig'd`, `Stop`, `Roll`, `HOLD`) are English in every
  language; they are not localized in the stock firmware either.
- Scope artefacts below ~4.19 MHz come from the FPGA and can't be fixed here.

## Credits

- [FNIRSI-2D15P-UA](https://github.com/Serhii-Povshednyi/FNIRSI-2D15P-UA) by
  Serhii Povshednyi: the first public mod of this firmware (Ukrainian UI and
  corrected English for V2.7.0.7). It proved the bootloader accepts modified
  images, and its README documents the MCU/FPGA split and the sub-4.19 MHz
  FPGA artefact. This project reuses:
  - most of its **English corrections** (wording, checked against the
    Chinese source strings);
  - its **three-row top-menu geometry** (row height 0x12, stride 0x14 in the
    draw routine and the 13 touch maps).

  None of its files or font data are included. If you want Ukrainian, use his
  mod; the two are separate builds and can't be combined.
- [Capstone](https://www.capstone-engine.org/) and
  [Keystone](https://www.keystone-engine.org/) for (dis)assembly,
  [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) for patching in
  the browser.

## Licence

The tools, notes and patch sets in this repository are **GPL-3.0** ([LICENSE](LICENSE)).

FNIRSI's firmware is **not** included and must be obtained from FNIRSI;
`.gitignore` keeps `.bin`/`.bps`/`.zip`/`.pdf` files out of the repository.
Patch sets contain only the new bytes, plus short instruction or pointer
context so each patch can be checked before it is applied. Vendor data being
overwritten (glyph bitmaps, Chinese strings) is checked by CRC32 instead of
being copied. The `.bps` release files contain only new bytes.
