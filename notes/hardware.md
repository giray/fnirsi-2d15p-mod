# Hardware notes

Facts about the 2D15P hardware, with sources. Append dated bullets.

- FPGA: **EG4S20BG256** (Anlogic Eagle). Owns acquisition, signal processing and
  LCD drive. Not changeable from MCU firmware.
- MCU: **Synwit** Cortex-M part, markings lasered off; identified via the USB
  VID/strings it reports as a virtual COM device.
- DMM IC: markings lasered off; not identified.
- MCU↔FPGA interface (from the UA mod README, see `prior-art.md`): per-channel
  32-bit frequency readout (bit 31 = period vs pulse-count mode); per-channel
  config byte with a bandwidth-limit bit; frequency-counter mode threshold at
  2^22 Hz = 4,194,304 Hz.
- USB: mass storage (USB Sharing / bootloader) and an undocumented CDC/serial
  port. **No writes to the CDC port on a live unit** until understood.
- Flash source: firmware image is unencrypted, raw code plus resources
  (bitmap fonts etc.) — EEVblog teardown.

## Findings log (append-only)

- (none yet)

### 2026-10-05 — static analysis of 2D15P_V2.7.0.7_260826.bin (crc32 B43E8C2D)

- **Image is a two-part container**, not a flat MCU image:
  | file offset | size | content |
  |---|---|---|
  | `0x000000` | 0x1000 | header: two 32-byte names + `(off,size,end)` u32 triples at 0x20 and 0x4C, rest zero |
  | `0x001000` | 0x6A9C0 (436,672) | `APP_2D15P_V2.7_260826.bin` — MCU firmware |
  | `0x06C000` | 0xB9EE9 (761,577) | `FPGA_2D15P_v0.7(251118).bin` — FPGA bitstream (magic `CC 55 AA 33` after 0x20 of 0xFF; Anlogic EG4 format) |
  So **the upgrade also carries an FPGA bitstream** (v0.7, dated 2025-11-18); the MCU
  programs it (string `P:/Upgrade/FPGA.bin`). Editing the bitstream is out of scope,
  but note that an upgrade can change FPGA behaviour, not only MCU code.
- **MCU APP link base = 0x12000.** `MCU address = file offset + 0x11000`.
  Evidence: vector[1] (Reset) = 0x1230D and a Keil `Reset_Handler`
  (`ldr r0,=SystemInit; blx r0; ldr r0,=__main; bx r0`) sits at file 0x130C;
  SVC/PendSV/SysTick vectors (0x31C11/0x31361/0x324DD) all disassemble as real
  handlers under this base; settings strings are referenced from a pointer table
  only under this base. Flash below 0x12000 (72 KB) is presumably the recovery
  bootloader and is **not** in the upgrade image.
- Initial SP = 0x2000FB30 → SRAM at 0x20000000, ≥ 64 KB.
- **Core is ARMv8-M (Cortex-M33 class)**: PendSV uses `mrs r2, psplim` and
  `vstmdbeq` (FPU). Among Synwit parts this points at the SWM34S/SWM341 family.
- Software stack: **FreeRTOS** (SVC/PendSV/SysTick kernel handlers, `Tmr Svc`),
  **cm_backtrace** fault tracer (`addr2line -e %s%s -afpiC`, `.axf` → built with
  Keil MDK), file paths `app/main.c`, `DISPLAY/interface.c`, `BSP/bsp_sys.c`,
  a FAT-like `P:/` filesystem (`P:/Upgrade`, `P:/Screenshot file/%d.bmp`).
- Live USB identity in recovery/mass-storage mode (2026-10-05): `0416:5020`,
  Manufacturer "Synwit", Product "Mass Storage", full-speed (12 Mbit/s), one
  FAT16 volume of ~13 MB exposing the `P:/` filesystem. VID 0x0416 is the
  Winbond/Nuvoton vendor ID, which Synwit chips reuse.
- USB strings in the image: `Synwit`, `Mass Storage 1.00`, `USBC`. No "Virtual COM" string in
  the APP part — the CDC port seen on the live device may come from the
  bootloader region or be enumerated differently; still unresolved.
- Tools: `tools/fw_inspect.py` parses the header, carves parts, prints vectors
  and the address delta, greps strings, and dumps pointer tables.
  `tools/.venv` has capstone 5 for disassembly (`tools/.venv/bin/python`).

### 2026-10-05 — MCU software map (from Phase 1 static analysis)

MCU addresses; file offset = addr − 0x11000. Query with `tools/fw_xref.py`.

**Boot and tasks**
- `main` = 0x3FD24 (sets VTOR = 0x12000, calls a ROM routine at 0x11000431
  → there is a vendor ROM/bootloader API region at 0x11000000).
- System init = 0x32508 (creates queues/semaphores at 0x349A0.., tasks at
  0x34A54..). Settings/UI init = 0x36018 (reads config block at flash
  0x11000, fills the settings struct, sends hw-sync commands 1..0xA2).
- Tasks (xTaskCreate = 0x51564): 0x42990 UI draw (widget bitmap at
  0x200036E0/E1), 0x43FB8 input dispatch, 0x43F88 hardware sync
  (`0x14E68(cmd)`), 0x43F28 DMM UART TX, 0x439B8 DMM packet parser,
  0x457F0 USB mass storage / flash, 0x44170 display + key scan.
- Queues: `[0x2000324C]` 2-byte {type,id} input events; `[0x20003250]` 1-byte
  hw-sync commands; `[0x20003254]` 2-byte DMM UART commands; `[0x20003258]`
  DMM packet semaphore; `[0x2000325C]` touch semaphore.
- ISRs in use: IRQ8 0x37BC8 UART (DMM chip, RX buffer 0x2000343C..),
  IRQ24 0x13C30, IRQ38 0x1A3F0 touch controller (I2C, flags 0x2000BB1C..),
  IRQ39 0x1A53C rotary encoder (→ 0x20003424), IRQ73 0x3009C,
  IRQ77 0x38854 USB, IRQ88 0x14148.
- FreeRTOS: xQueueSend 0x50DC4, xQueueReceive 0x51164, semaphore take
  0x512E4, xQueueCreate 0x50BB8, vTaskDelay 0x4F9F4. Log/assert printf with
  file+line = 0x1240C (file names at 0x7ABFB "app/main.c" etc.).

**Settings/state struct @0x20000198** (partial; see re-plan.md for UI fields)
- +0x00/+0x01: saved from config block bytes 2/3 (scale/timebase indices).
- +0x2C: channel config nibbles (sent to FPGA), +0x2F run/stop, +0x30 run
  state, +0x3C2 trigger source/flags, +0x44 last FPGA status byte.
- +0x460 DMM function index, +0x470 DMM HOLD, +0xE24 DMM sub-state.
- +0xE28 language, +0xE33 page, +0xE34 menu panel, +0xE3C highlight bits.
- +0x138.., +0x1FE..: constant tables written by init (calibration/scale
  candidates) — **off limits**.

**Config block @ flash 0x11000** (4 KB sector between bootloader and APP)
- Written by 0x31DF0(magic) at power-off (long press raw key 0 → type-1 id
  32). Byte0 magic: 0x55 normal (boot page 2), 0xAA → boot page 4
  (unknown/self-test?), other → first-boot path (English, page 2).
  Bytes 2/3 → struct +0/+1; 0x11004.. → further settings (lang at +0x18 of
  the block → +0xE28). CRC16 poly 0x1021 used by the flash/file code.

**Keys**
- 22 raw key bits read from word 0x20003420 (filled from GPIO; ports at
  0x40040000 region are PORT config, GPIO data in 0x4000xxxx). Scan loop
  0x44ED0, debounce to 0x45/0x46 ticks, short/long tables 0x5535C/0x5537A.
- Raw→id (short): 0:14 2:20 3:10 4:12 5:3 6:6 **7:15 (DDS)** 8:9 9:2 10:7
  11:21 12:8 13:1 15:22 16:5 17:4 19:19 20:13 21:11. Long: 0→32 (save +
  power-off), 3→31. Knob rotate = ids 23/24.
- Type-1 handler table 0x55398 (ids 1..32). Known: 1 Measure panel,
  2 Trigger panel, 3 Cursor panel, 4 Auto, 5 Run/Stop (= HOLD on DMM page),
  9 Math panel, 10 Vertical panel, 11 → 0x49758, 13 → 0x2C9E0 (Level/run
  toggle), **15 DDS (0x2CA60)**, 19 → 0x2CAA0 (DMM function cycling?),
  31/32 long presses.

**DMM data path**
- DMM chip ↔ MCU over UART (IRQ8). RX packet lands at 0x2000343C.., parser
  task 0x439B8 reads BCD nibbles at 0x2000343D+2.., decodes with 0x407D4
  (39 cases = mode/range). Commands to the chip: queue [0x20003254] →
  task 0x43F28 → TX buffer 0x2000018B (bytes +2,+3, checksum +9).
  This is the hook for Goal 2 (REL at display time) and Goal 4 (forward
  readings to the PC).

### 2026-10-06 — Language/string system (static analysis, stock 2.7.0.7)

Full slot list with capacities and sharing: `firmware/work/lang_slots.json`
(130 slots, regenerate from scratch scripts if lost; work dir is gitignored).

**Language variable.** `u8 [0x20000198+0xE28]`: **1 = CN, 2 = EN** (not 0/1).
Settings handlers 0x47100 (→1) / 0x47128 (→2) (handler table 0x555A8/0x555AC);
first-run picker handlers 0x494D4 (→1, page 2) / 0x49584 (→2, page 2) (table
0x55654/0x55658), picker drawn by 0x2BA74 (widget struct 0x59FA0). Saved in the
config block (loaded at 0x3672C). Defaults are **CN**: factory reset
`0x31DF0(0)` writes `movw r0,#0x9201` @0x31F66 (byte @file 0x20F68 = lang) and
magic 0xAA (@0x32018) → next boot page 4 (probably the picker); blank config
block → 0x37A78 `movs r0,#1` @0x37A7E (file 0x26A7E).

**Lookup.** Almost all sites: `p = tbl[(lang-1)*N + i]`, e.g. 0x23724
`ldrb r0,[..,#0xe28]; add r0,r0,r0,lsl#1; add r0,0x5A070,r0,lsl#2; ldr r5,[r0,#-0xc]`.
Measurement table uses `(lang!=1)*15` (0x1F8D2). So values other than 1 act as EN
at some sites and index garbage at others: keep exactly two languages (1, 2).
- ROM `[2][N]` tables (CN half then EN half): 0x59FB0×3 trig mode, 0x59FC8×4,
  0x59FE8×2, 0x59FF8×6, 0x5A028×4, 0x5A048×3, 0x5A060×2, 0x5A070×3,
  0x5A088×13 top menu, 0x5A0F0×9 DDS waves, 0x5A138×4, 0x5A2C4×4 About,
  0x5A2E4×6 Settings, 0x5A314/31C/324/32C/334 ×1, 0x5A33C×17 DMM functions
  (1-based index +0x461), 0x5A440×2, 0x5A450×1, 0x5A4BC×15 measurements.
  Non-language tables in between: 0x5A158 units, 0x5A164 timebase, 0x5A1E0
  sample rates, 0x5A230 Stop/Run, 0x5A238.., 0x5A290 fn ptrs, 0x5A3C4 DMM
  tokens, 0x5A3E8 units, 0x5A534.. units.
- Code literal pairs `{CN,EN}` picked by `adr/addw + lang*4-4`: 0x1BE34,
  0x1BE3C (await trigger / auto measurement), 0x21720 (begin), 0x24828
  (Remove), 0x2739C, 0x273A4 (delete), 0x2A714 (USB-sharing msg), 0x2A9CC/D4/DC
  (Saved / Save failed / Saving...), 0x2B388 (low battery), 0x28780 (Signal
  Generator).
- `cmp lang,#1; moveq` pairs with inline strings in the code area (4-byte padded):
  0x274E6 Meas/测量, 0x2753E Save/保存 (0x28008/0x28000), 0x27762 Run/运行
  (0x7B5CF/0x28018), 0x277BC Menu/菜单 (0x28028/0x28020), 0x2968C OK/确认
  (0x2A408/0x2A400).
- **RAM tables** `[lang][2]` at 0x20000FF4 ON/OFF, 0x20001004 CH1/CH2,
  0x20001014 vec/dot, 0x20001024 OFF/20M, 0x20001034 AC/DC (toggle widget
  0x2C690). They live in the **compressed RW init image** (Keil
  `__decompress1` 0x121E4, region table 0x7C5CC: load 0x7C720 → 0x20000000,
  0x11E0 B; blob ends 0x7C9B9, APP ends 0x7C9C0). Changing these pointers means
  re-compressing; only in-place overwrite of their target strings is cheap
  (capacities incl. NUL: 开启 7, 关闭 7, 矢量 7, **点 4**, 交流 7, 直流 7).
- EN-only in both languages: status 0x27034 table (Trig'd/Auto/Ready/Arm/Roll/
  Stop/Wait, indexed by FPGA state +0x44), OFF (0x220E6), 15min/30min/1hour
  (0x23000..), HOLD (0x26B90), DDS, 50%, Min/2s..∞ (0x2480C). Language labels
  `中文` 0x7B9E9 (7 B) / `English` 0x7B4E7 are code-referenced by movw/movt at
  0x22820/0x22C04 (Settings) and 0x2BA98/0x2BAD2 (picker), shown in both
  languages. "2.bmpSaving..." = `sprintf("%d.bmp%s")` with the format inline at
  0x2A9E4 (9 B + 3 B padding, so "%d.bmp %s" fits).

**Rendering.** Strings are **UTF-8** (decoder 0x3FC44 → code points). Draw
routine 0x1984C(x,y,w,h, str, font, colour, flags): decodes into 0x80140000,
fetches glyph descriptors via `font->get_glyph_dsc` (blx [font]) into
0x80180000, word-wraps on spaces inside the box width. Width-measuring loops
(0x23754, 0x1AFB0, ...) are the same for both languages. **A code point with
no glyph ends the string** (`blx r6; cbz r0, done`), so unsupported letters
(ı ş ä ß) truncate, they do not show boxes. Fonts are LVGL-style objects at RAM
0x20001044 + n*0x30 (line heights 12/14/16/18/20/23), 4 bpp, one sparse cmap
with absolute code points. **All six fonts contain full ASCII 0x20–0x7E**
(plus Ω ℃ ℉ √ ∞ ∫ and PUA icons U+F014/F06A/F071/F08A/F091 in some fonts), so
ASCII in a CN slot renders with the normal Latin glyphs.
Language-dependent layout (CN value first):
- Top menu + its 13 touch maps (0x1AEB0 draw; 0x4C7B0, 0x4CAF0, 0x4CCC0,
  0x4CE90, 0x4D060, 0x4D3F0, 0x4D830, 0x4DD48, 0x4E214, 0x4E534, 0x4E7DC,
  0x4EDAC, 0x4EF88): item padding 0xE vs 0xC (`moveq #0xe` @0x1AF00, 0x1B000,
  and two per touch map, e.g. 0x4C7EE/0x4C810), gap 7 vs 5 (@0x1AF84). Wrap
  at x>0x188. (UA's 3-row menu changed row height 0x1A→0x12 @0x1AF28/0x1AF56/
  0x1B038, stride 0x20→0x14 @0x1B012 and per touch map.)
- Status-bar trigger mode 0x2C5B6: CN uses the 14 px font 0x20001074, EN the
  12 px 0x20001044 (`movw sb,#0x1074` @0x2C5D8, file 0x1B5DA; UA set it to 0x1044).
- DDS list text x-offset 0x1C vs 0x10: @0x2894C (file 0x1794C) and 0x4C342
  (file 0x3B342).
- Settings language radio: 0x21C54 (`cmp #1`), 0x22854 (`cmp #2`).
- `sprintf` target 0x200036B8 is **40 bytes** (next var 0x200036E0); used with
  "%s:%.2f%s" (measurement names), "< %s" (Back), "%d.bmp%s", "%s:V%d.%d.%d.%d"
  (version number), "%s:" (menu names). Keep those strings ≤ ~20 chars.

**Space.** String pool 0x7AC00–0x7C31C, merged by the linker (suffix sharing:
设置 is the tail of 恢复出厂设置, 占空比 of 正占空比, 'mA' of 直流电流 mA,
Hz of kHz, ...).
- CN segments referenced only from CN slots: **113 segments, 1348 B** (incl.
  NULs) + 测量 7 B + inline 保存/运行/菜单/确认 4×8 B. Use ownership per byte, not
  per pointer, before overwriting in place.
- Chinese cm_backtrace/debug printf strings (UART only): ~2012 B. Reusable
  only if we accept garbled fault logs.
- **CJK glyph bitmaps**: contiguous per font, no font-header change needed if
  left as dead glyph data: 0x5C325–0x5CA89 (1892), 0x5DDB7–0x60706 (10575),
  0x61F16–0x629AE (2712), 0x63DAE–0x63E81 (211), **0x6545C–0x6C249 (28141)**
  + 0x6C2B9–0x6C2D7, 0x6E8A2–0x702A6 (6660); total ≈ 50 KB. Icon U+F014 in
  the 20 px font sits at 0x6C249–0x6C2B9 and must be kept (UA 1.0 bug).
  Overwriting these only breaks CJK rendering, which nothing would draw once
  every CN slot holds ASCII (the label `中文` must be replaced too).
  UA instead rebuilt all six fonts compactly into 0x5C325–0x69D3F, which moved
  bitmap/glyph_dsc/cmap pointers and the per-font glyph cache (+0x28/+0x2C of
  each font object) in the RW image → blob grew → APP size in header
  0x6A9C0→0x6A9D0 (file 0x24). We should avoid that path.
- No proven-free padding in the APP: the 0x00/0xFF runs at 0x586xx–0x59Dxx,
  0x5B3xx–0x5B9xx, 0x71xxx–0x79xxx sit inside image/table data; 0x7C695–0x7C71F
  is the end of a ctype table (0x7C718 is referenced). 1600 B after APP end
  (file 0x6B9C0–0x6C000) would need an APP size change.
- Not in scope but noted: the APP has a SCPI-like command parser (0x44448:
  `*IDN?`, `CAL:ADC:PREP`, `CAL:ADC:CALC`, `CAL:BIAS:CALC`, `CAL:AMP:*`,
  `MEAS:CH`), most likely behind the CDC/serial port (not traced) — so that
  port probably accepts **calibration** commands; reinforces SAFETY rule 5. `MEAS:CH` is relevant to Goal 4.

### 2026-10-06 — fw_font.py and CN-layout patch set

- `tools/fw_font.py` (stdlib only): finds the Keil region table, unpacks the RW
  image, finds the font objects and parses their ROM descriptors. There are
  **8 fonts**, not 6: also lh 28 (15 glyphs, range 0xA..0x2109) and lh 117
  (24 glyphs: big digits). get_glyph_dsc 0x39044: `range_start <= cp <= cmap+4`
  (an inclusive end, not a length), then the glyph cache (dsc+0x14/+0x18), then
  a binary search of the u16 list. adv = glyph_dsc word >> 20, in whole pixels.
  The measuring loops only add up adv, with no letter spacing and no kerning.
  ofs_y is measured upward from the bottom of the line. `--runs` reproduces the
  CJK runs (total 50221 B; largest 0x6545C–0x6C249, 28141 B). Leftover
  aligned-word "pointers" into the runs are coincidences: instruction bytes, the
  __scatterload relative words at 0x121DC/0x121E0, and the constant 0x60000 at
  0x567E8.
- +0xE29 = screen brightness (slider 0..0x92, 0x471C0; PWM at 0x400461A4).
  Factory default `movw r0,#0x9201; strh.w r0,[sb,#0xe28]` sets lang=1 and
  brightness=0x92. +0xE2A is also defaulted to 0x92.
- `firmware/work/lang_layout.json`: 37 entries, **61 single-immediate changes**.
  The CN-only layout selects are, per menu builder (draw 0x1AEB0 plus 13 touch
  maps): padding 0xE→0xC (twice), width addend 0xC→0xA, gap 7→5. Also: status-bar
  trigger font 0x1074→0x1044, DDS x-offset 0x1C→0x10 (twice), and default
  language EN (0x31F66, 0x37A7E). I scanned systematically: every
  `ldrb [..,#0xe28]` and every later `cmp` on that register. All other uses
  index tables. Windows are unique in stock and don't overlap each other or
  dmm-first. fw_patch dry-run on stock is OK (output crc32 CD8C01BA).

### 2026-10-06 — USB personalities (observed, passive)
- Normal operation: CDC ACM **0416:50A1**, bcdDevice 3.00 → `/dev/ttyACM0`
  (kernel log). USB Sharing / recovery: mass storage **0416:5020**.
- The host's ModemManager grabs/releases ttyACM0 on every plug-in and logs
  "not supported by any plugin" (likely rejected before any AT probe, but not
  provable). `host/99-fnirsi-2d15p.rules` sets ID_MM_DEVICE_IGNORE, gives
  plugdev access (owner is not in dialout) and a `/dev/fnirsi-2d15p` symlink.
  Install it before anything opens the port.

### 2026-10-06 — USB CDC / SCPI interface (static analysis only; nothing was sent to the device)

**Two USB personalities.** Both descriptor sets live in the RW init image (RAM).
- **CDC** (normal operation):
  - Device descriptor 0x200000E0: class 02, **VID 0x0416, PID 0x50A1**, bcdDevice 0x0300.
  - Config 0x200000F2 (67 B): IF0 = CDC ACM with notify EP 0x81 (interrupt, 8 B); IF1 = data, bulk **EP 0x82 IN / EP 0x02 OUT**, 64 B each.
  - Strings: "Synwit" (0x20000139) and "USB Virtual COM" (0x20000147). No serial number.
- **MSC** (USB Sharing only):
  - Device descriptor 0x2000002B: **VID 0x0416, PID 0x5020**, bcdDevice 0x0100.
  - Config 0x2000003D: class 08/06/50, bulk 0x81 / 0x01.
  - Strings: "Synwit", "Mass Storage", serial "A0000080401150".
- **When each is active:**
  - The USB task 0x457F0 installs the CDC descriptors at start (0x45824..) and initialises USB (0x3825C). So **CDC is up whenever the APP runs and USB Sharing is off**, on every page.
  - 0x4BC1C (USB Sharing ON) sets page 7 and re-enumerates as MSC.
  - 0x45AB0 (exit sharing) sets page 2 and re-enumerates as CDC.
  - The recovery bootloader's MSC is not in the APP.
- **CDC class requests** (0x38B10): SET_LINE_CODING (0x20) only stores 7 B at 0x20000178, and GET_LINE_CODING (0x21) returns them. SET_CONTROL_LINE_STATE (0x22) only stores wValue at 0x20002F60. Nothing reads either value for any action. **No DTR/RTS action, no auto-command on connect.**
- The only producer for the TX ring is the reply code in the display task. So **the device never sends anything unprompted**; opening the port and listening is passive.

**Transport.**
- Port state struct at 0x20002D54 (`sb`):
  - TX ring +0x000..0xFF (write index +0x104, read index +0x102, count +0x100);
  - line buffer +0x106 (length +0x206; write index +0x20A, which wraps at 0x100);
  - EP2 OUT packet buffer +0x250 (count +0x290, flag +0x292);
  - TX staging +0x20E (length +0x24E).
- The ISR (IRQ77, 0x38854) fills the OUT packet buffer. The **display/key task 0x44170** copies it into the line buffer (0x443B0) and, **on the same loop pass**, NUL-terminates it and parses it (0x44422).
- There is **no line terminator handling**: one USB OUT transfer is one command. Exact commands are compared with `memcmp(buf, "CMD", strlen+1)` (0x13680 is memcmp), so **"CMD\r\n" does not match and gets "ERR"**. Prefix commands (MEAS:CH, CAL:AMP:PREP) ignore trailing bytes. Matching is case-sensitive. Max length 256 (indexes wrap).
- Replies go through the TX ring → EP2 IN (0x44238..0x4436C, up to 64 B per packet, `0x38708(2,…)`), with **no terminating newline**.
- Unknown command → "ERR". Page/state gates → "ERR1" (not page 2), "ERR2" (+0x2E busy), "ERR3" (+0x2D set / bad channel), "ERR4" (bad argument).
- The parser is skipped while page == 7 (0x44204).

**Command table** (all handlers are inside 0x44170; the type-5 input-event table is at 0x44158):

| Command | Match | Handler | Gate | Effect / reply | Class |
|---|---|---|---|---|---|
| `*IDN?` | exact | 0x444E4 | none | `FNIRSI 2D15P, NULL, V%d.%d.%d.%d` (version nibbles at +0xE2E) | **READ-ONLY** |
| `MEAS:CH1:` / `MEAS:CH2:` + `VRMS` / `VAVG` / `VPP` / `VMAX` / `VMIN` | prefix | 0x44824 → 0x4545C | page 2 (else ERR1) | `%.2f%s` scope measurement (float at struct +0x70+ch*0x34+k*4, unit from a table near 0x457A4) | **READ-ONLY** (scope only) |
| `CAL:ADC:PREP` | exact | 0x4453A | page 2, idle | posts input {5,0} → 0x50034: rewrites channel config (+0xA..+0x45) and sends FPGA cal commands 0x76..0xA2 | **CALIBRATION** |
| `CAL:ADC:CALC` | exact | 0x445B4 | page 2, idle | status 0x20002FED=0x7F, {5,1} → 0x5053C. Result arrives later as "SUCC" / "ERR%d" (0x44904/0x452FE); hw-sync 0x1739E/0x174C4 stores results (+0x3BD/+0x3C1) | **CALIBRATION** |
| `CAL:AMP:CALC` | exact | 0x446E4 | page 2, idle | {5,2} → 0x50690 | **CALIBRATION** |
| `CAL:AMP:PREP ` + `CH1, ` / `CH2, ` / `ALL, ` + `100mv` / `200mv` / `500mv` / `10v`… | prefix | 0x4475C → 0x45548 | page 2, idle | writes 0x20002FEE, {5,3} → 0x507E4 (channel config + FPGA cal commands) | **CALIBRATION** |
| `CAL:BIAS:CALC` | exact | 0x44656 | page 2, idle | {5,4} → `b.w 0x4B8D4` = starts the on-screen self-calibration (page 0xA, same as Menu → Calibration) | **CALIBRATION** |
| `CAL:BIAS:CALC?` | exact | 0x446C6 | none | busy → "1"; **on page 0xA it posts {5,5} → 0x48F60 (leaves the calibration page)**; else "0" | **CHANGES-SETTINGS** (not a pure query) |

- **Flash:** the only internal-flash writer in the APP is 0x31DF0 (ROM API 0x11000471/0x11000401/0x110004C1), which saves the settings struct, including the calibration-range fields, to the config block at 0x11000. It runs on power-off, low battery, factory reset and 0x46218.
- **So CAL changes become permanent** at the next save, even though the CAL handlers do not write flash themselves.

**DMM readings.**
- No command returns them. MEAS:CH is scope-only and returns ERR1 on the DMM page.
- The decoded reading is written by the DMM task (0x43B60..0x43C4C) into the settings struct (0x20000198 + offset):
  - **+0x464 float** (value in display units; already sign-applied);
  - +0x468 u8 decimals (drawn with `"%.<n>f"`);
  - **+0x469 u8 token**: if non-zero, the display shows `table 0x5A3C4[token-1]` instead of the number (1 AUTO, **2 ".OL" = overrange**, 3 " ", 4 CAL, 5 PAS, 6 Er1, 7 Er2, 8 Er3, 9 ErC);
  - **+0x46C u8 unit** → `0x5A3E8[unit]` (mV V Ω kΩ MΩ nH uH mH H nF uF mF F uA mA A ℃ ℉ Hz kHz MHz, …);
  - +0x460 function, +0x46A/+0x46E secondary "%d Hz" field, +0x470 HOLD.
  - Absolute addresses: value 0x200005FC, token 0x20000601, unit 0x20000604.
- Display: draw fn 0x269E4 (widget 0x10). It runs once per DMM packet, ending in `bl 0x142C8` at **0x43E88**.

**Proposed Goal-4 patch (design only; not written).** Stream one line per reading; the host never writes.
- **Hook:** at 0x43E88 change `bl 0x142C8` to `bl cave` (4 B, same length).
- **Cave** (Thumb, about 140–180 B):
  - push; `bl 0x142C8`;
  - if page byte (+0xE33) == 1 (optional): build the line in a stack buffer (~48 B), reusing the firmware's own `sprintf` 0x12424 / `snprintf` 0x12450 and the float→double helper 0x54D28 exactly like 0x269E4:
    - `snprintf(fmt,10,"%%.%df",dec)` then `sprintf(buf,fmt,val)`, or the token string;
    - then append `" " + unit + (HOLD?" H":"") + "\r\n"`;
  - then, between cpsid i / cpsie i, copy the bytes into the TX ring at 0x20002D54 (write index +0x104, count +0x100, drop if count would exceed 0xFF, the same rule as stock), and set [0x20002FE8]=1;
  - pop.
  - The display task (any page except 7) drains the ring to EP 0x82.
  - Unit strings are UTF-8 (Ω, ℃). Either emit an ASCII name table (≈60 B) or let the host decode UTF-8.
- **Cave location:** the tail of the 20 px CJK glyph run, 0x66000..0x6C249 (lang_build uses ~1.6 KB from 0x6545C). It is executable flash: the APP sits in the Code region, there is **no MPU/SAU setup anywhere** (no references to 0xE000ED90.. / 0xE000EDD0..), and no XN.
- **Must avoid:** dmm-first (0x3011C..0x3016F incl. the cave 0x30162), lang/layout.json and boot_fix (0x985E).
- **To check before writing it:**
  - the DMM task's stack size (xTaskCreate args near 0x34A54) for the ~64-byte frame;
  - that the DMM task is the only writer at that point. The TX ring is otherwise produced only by the display task, and ring count updates there run without a lock, hence the cpsid in the cave.
- **Alternative:** a new query (e.g. reuse the unknown-command branch 0x444D2) handled inside the display task. That avoids cross-task ring access but needs host writes.

**Safety verdict for SAFETY.md rule 5.**
- **Safe:**
  - opening/listening on the CDC port (any DTR/RTS/baud);
  - `*IDN?` sent with no CR/LF;
  - `MEAS:CH1:VRMS`-style queries (read-only, page 2 only).
- **Never send:**
  - any `CAL:*` command, **including `CAL:BIAS:CALC?`**;
  - any untested string beginning with "CAL:". Prefix matching means e.g. `CAL:AMP:PREP …` with extra bytes still runs.
- Sending garbage is otherwise answered with "ERR" and has no side effect.
