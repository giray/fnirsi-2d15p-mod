# Languages

The 2D15P firmware has exactly two UI language slots. Stock: slot 1 = Chinese,
slot 2 = English. This mod keeps **English as the primary language** (with the
text fixes in `en.json`) and puts **one secondary language** into slot 1,
replacing Chinese. Each secondary language is its own firmware build.

| File          | What                                                       |
|---------------|------------------------------------------------------------|
| `slots.json`  | Map of every localized string (stable ids, addresses). Derived from static analysis; don't edit by hand. |
| `en.json`     | English corrections (only the ids that change).            |
| `tr.json`, `de.json`, `nl.json` | Secondary languages.                     |
| `layout.json` | Byte patches that give slot 1 the English layout (menu spacing, fonts) instead of the Chinese one, and make English the factory default. |

## Rules for translations

- **Plain ASCII only** (space to `~`). The device stops drawing a string at the
  first character its fonts don't have, so `ş`, `ä`, `ı` would cut text off.
  Write `s`, `ae`, `i` instead. The builder refuses anything else.
- `"text": null` means "use the English text". Abbreviations such as NCV,
  Vrms, MIN: are usually best left as they are.
- `"en"` is the English reference. If the English changes later, the builder
  warns so the translation can be re-checked.
- Keep labels about as long as the English. The builder prints `WIDE` lines
  for strings that render much wider than the English (it measures with the
  device's own fonts). Long labels may wrap or overflow on screen.
- A few strings can only be overwritten in place and have hard limits
  (the builder stops with a clear message if one is too long):
  `bar.save`, `bar.run`, `bar.menu`, `dds.ok` max 7 characters;
  `rw.onoff.*`, `rw.disptype.0`, `rw.bw.0`, `rw.coupling.*` max 6;
  `rw.disptype.1` max 3. `rw.onoff.1` and `rw.bw.0` share storage and must be
  identical.
- `meas.*`, `btn.back` and `about.3` are formatted into a small buffer: max 20
  characters.
- `trig.mode.*` is also shown in the status bar in a 34 px wide box (12 px
  font), so it must stay within 34 px ("Normal" is 33). The builder measures
  this and stops if a label is too wide. That is why Turkish uses "Oto".
- The top menu (`menu.*`) has three rows. The builder simulates the
  firmware's row breaking and stops if the labels need a fourth row
  (`python3 tools/fw_font.py <stock.bin> --width 14 "Label"` gives a label's
  width in pixels).
- `about.3` ("Version") gets ` (mod X.Y)` appended from `mod_version` in
  `en.json`, so the About page shows which mod build is installed.
- `lang.name` is how the language appears in Settings and the first-boot
  language picker (next to "English").

## Adding a language

1. `cp lang/de.json lang/xx.json`, set `"code"`, `"name"`, and replace every
   `"text"` (or set it to `null`).
2. `python3 tools/lang_build.py firmware/stock/2D15P_V2.7.0.7_260826.bin xx --image`
3. Fix any errors, look at the `WIDE` list, flash, check the screens.

## Building

```bash
python3 tools/lang_build.py firmware/stock/2D15P_V2.7.0.7_260826.bin tr --image
#  -> firmware/build/dmm-first+tr.json   (patch set, stock-CRC gated, shareable)
#  -> firmware/work/dmm-first+tr/2D15P_V2.7.0.7_260826.bin
python3 tools/lang_build.py firmware/stock/2D15P_V2.7.0.7_260826.bin en   # English only
python3 tools/lang_build.py firmware/stock/2D15P_V2.7.0.7_260826.bin de --base none  # language only
```

`tools/build_all.sh` rebuilds every language plus the `.bps` release files.

The builder checks everything before writing: ASCII, lengths, no overlapping
patches, every patch inside the MCU part, and a self-check that resolves all
260 string reads in the patched image to the intended text.
