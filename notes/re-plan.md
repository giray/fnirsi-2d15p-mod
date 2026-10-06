# Reverse-engineering plan

Lab notebook for turning the three goals into firmware edits. Append dated
findings; don't delete history.

## Phase 0 — groundwork (do before any patching)

- [x] Owner downloads official firmware for their version into `firmware/stock/`,
      `chmod 444` it, record name + crc32/sha256 in `notes/flashing.md`. (2026-10-05)
- [x] Confirm **bootloader recovery** round-trip with the stock image
      (`SAFETY.md`). Done 2026-10-05 as the 2.6.0.7 → 2.7.0.7 upgrade through
      recovery; unit now on 2.7.0.7. See `notes/flashing.md`.
- [x] Decide target version: **2.7.0.7**, CRC matches the UA mod exactly. (2026-10-05)
- [x] `python3 tools/fw_inspect.py firmware/stock/<file>.bin` — vector table,
      container layout, link base 0x12000 recorded in `notes/hardware.md`. (2026-10-05)
- [x] String tables located: raw strings at file 0x69C00–0x6B800 (addr
      0x7AC00–0x7C800), CN/EN pointer tables at addr 0x59FB0–0x5A530. (2026-10-05)

## Phase 1 — understand the UI/state model

Load the carved MCU image in Ghidra (Cortex-M little-endian; initial SP + reset
vector from `fw_inspect`). The string table is the way in — cross-reference from
labels back to the code that draws/handles each mode.

Questions to answer and write up here:
- [x] Where is the **power-on default mode** chosen? Constant `movs r3,#2` at
      0x3668E in init 0x36018, keyed on the config-block magic. (2026-10-05)
- [x] How are the **physical buttons / knobs** dispatched? Key scan 0x44ED0 →
      raw→id tables 0x5535C/0x5537A → type-1 events → handler table 0x55398.
      DDS key = id 15 → 0x2CA60. (2026-10-05)
- [x] Does stock DMM have a **REL** mode? No (manual + strings). HOLD exists
      (Run key on DMM page, flag +0x470). (2026-10-05)

## Phase 2 — the three changes

### Goal 1: boot into the multimeter
- [x] Designed: single-byte change at file 0x2568E (`firmware/dmm-first.json`).
      Boot page is always the constant (not "last used"). (2026-10-05)
- [x] Flashed and verified on the unit (2026-10-06, `notes/flashing.md`).

### Goal 3: remap DDS button → multimeter  (do before Goal 2; it's simpler)
- [x] Designed: two instructions in the DDS key handler 0x2CA60 (file 0x1BA70,
      0x1BA7E). DDS key toggles scope ↔ DMM; generator stays on the Menu
      popup. The key has no on-screen label to relabel. (2026-10-05)
- [x] Flashed and verified on the unit (2026-10-06, `notes/flashing.md`).

### Goal 2: DMM probe zero / REL
- Stock has no REL → this is the build-it path. Proposed minimal design
  (needs owner sign-off): on a chosen key (candidate: long-press raw key 3,
  id 31 → 0x14DC0, which already only acts on the DMM page), capture the
  current decoded reading into a free struct slot and subtract it at display
  time in the DMM reading widget (0x12, draw fn 0x26B99). Measurement code
  and the calibration tables stay untouched. Requires a code cave for ~40
  bytes of new Thumb code; candidates: unused tail of the APP part
  (0x6B9B0.. is zero padding to 0x6B9C0 — too small) or a dead function.
  Not started.

## Phase 3 — build, verify, flash

- Encode each change as an entry in a patch set JSON (see
  `firmware/patches.example.json`).
- `python3 tools/fw_patch.py firmware/stock/<file>.bin firmware/<set>.json
  --dry-run` — every patch must report OK and the input CRC must match.
- Walk `SAFETY.md` → Pre-flash checklist with the owner.
- Flash, verify the specific behaviour, log it in `notes/flashing.md`.

### Goal 4: DMM readings on Linux
- The MCU already has the decoded reading (DMM task 0x439B8 → 0x407D4). The
  cheapest host path is to emit it over the existing USB CDC port, but that
  port's firmware side has not been located yet (no "Virtual COM" string in
  the APP; may be in the bootloader ROM region). Alternative: screenshot
  polling via USB Sharing (official, slow). Not started.

## Optional side-quest — the CDC/serial port

Separate from the three goals. Static-analysis only until understood:
- Carve MCU image, find the "USB Virtual COM" descriptor string, follow xrefs to
  the bulk-OUT (EP 0x02) receive handler; look for a command parser.
- Passive read on the live port is fine (`host/cdc_sniff.py`). **No writes** to
  the live port until the command set is known — it may be a calibration channel.

## Findings log (append-only)

- (none yet)

- 2026-10-05: Phase 0 complete. Recovery confirmed, unit on 2.7.0.7.
  Stock image on hand, CRC matches UA mod, read-only, logged in `notes/flashing.md`.
  Image layout and link base in `notes/hardware.md`.
- 2026-10-05: **Manual check — stock DMM has NO relative/REL mode.** The manual
  (`2D15P_Manual_New_ZH_EN.pdf`, §3.3) lists only range display, HOLD,
  Max/Min, and a trend curve. The firmware string table agrees: no
  "REL"/"Relative"/"Zero"/相对/清零 in either language; DMM strings are
  DC/AC Voltage, Resistance, On-off, Diode, Inductance, Capacitance, DC/AC
  Current mA/A, Temperature, Frequency, NCV, LIVE, Automatic, built in self
  testing, MIN:/MAX:, HOLD. So **Goal 2 is the "build it" path**, not
  "surface it". Cheapest honest version: a REL that subtracts a stored reading
  at display time (reuse HOLD's capture path), leaving measurement/calibration
  code untouched. Needs owner sign-off before design.
- 2026-10-05: **Entering the DMM takes Menu → multimeter** (manual §3.3.1); the
  mode switch (scope/DMM/DDS) has no text label in the string table, so it is
  icon-driven. Goal 3 (DDS button → DMM) therefore saves real taps.
- 2026-10-05: Leads found in the APP (MCU addresses):
  - Localized string tables (paired CN then EN pointer arrays) 0x59FB0–0x5A530.
    Main Menu list = Level, Vertical, Trigger, Display, Measure, Cursor, Math,
    X-Y, Picture, Calibration, USB Sharing, Key Test, Set (13 items,
    0x5A0BC–0x5A0EC EN). Settings list = Language, Volume, Brightness,
    Auto Shut, Regarding, Factory Rst (0x5A2FC–0x5A310).
  - **13 code pointers at 0x5A290–0x5A2C0** (0x21199 … 0x21959) directly before
    the "Native information" strings — same count as the 13 main-menu items →
    probable **menu handler dispatch table**. Candidate for Goal 3 (repoint an
    entry) and for locating the mode-switch code.
  - 27 structs of stride 0x10 at 0x59E0C–0x59FAC, each with a Thumb code
    pointer (0x26409 … 0x2BA75): probable UI page/handler table (page init
    functions). Walk these to find the DMM page and the DDS page.
  - "Signal Generator" string referenced from code at 0x28784 — the DDS page
    draw routine is near there; good anchor for the DDS button path.
  - Manual §2.2 lists the physical keys: Cursor, Display, Measure, Save, Math,
    50%, Trigger, Run, DDS, CH1/CH2, Menu, Single, Auto, plus 3 knobs. "Key
    Test" menu item exists → there is a key-scan routine that names every key;
    use it to find the key→action switch.

### 2026-10-05 — Phase 1 results (static analysis, nothing flashed yet)

All addresses are MCU addresses; file offset = addr − 0x11000. Tools:
`tools/fw_xref.py` (build once with `--build`, then `--to/--func/--switch/--callers/--near`).

**Architecture of the UI (enough to do Goals 1 and 3):**
- Global settings/state struct at **0x20000198** (≥0xE60 bytes). Key fields:
  `+0xE33` = **current page** (1=DMM, 2=scope, 3=DDS, 4=unknown/boot-only,
  5=menu popup overlay, 6..10 = sub-screens; bit7 = hidden flag),
  `+0xE34` = open menu panel index (1..13 → table at 0x5A290),
  `+0xE28` = language (0 CN, 1 EN), `+0xE24` = DMM sub-state, `+0x470` = DMM HOLD,
  `+0x30` = run state, `+0x460` = DMM function index (0..7), `+0xE3C` = highlight bits.
- Page redraw: `0x1A7F8` reads +0xE33 and invalidates widgets via `0x13C84(id)`;
  widget table at 0x59D30 (16-byte {x,y / w,h / flags / draw_fn}, ids 0..0x27).
  DMM widgets 0x0C..0x15 (0x0D = DMM function label, 0x11 = HOLD box,
  0x12 = reading area); DDS widgets 0x19..0x1E.
- Page setters (each: `strb #N,[+0xE33]; bl 0x1A7F8; …; b.w 0x300B4`):
  **0x49924 = enter DMM (page 1)**, **0x49880 = enter DDS (page 3)**,
  0x472D0 = enter scope (page 2), 0x4BD9C = page 5 popup, …
- Events: 2-byte {type,id} queue `[0x2000324C]` → input task (0x43FB8..):
  type 1 = **physical key / knob** → table 0x55398[id−1] (ids 1..32);
  type 2 = **touch widget** → table 0x55418[id] (id 0x11 = DDS button,
  0x12 = DMM button of the popup); type 5 → 6-entry table at 0x44158.
  1-byte queue `[0x20003250]` → hardware-sync task → `0x14E68(cmd)`.
- Key scan: display/input task 0x44170, loop at 0x44ED0: 22 GPIO bits from
  `[0x20003420]` word, debounce counter per key, **raw→id table at 0x5535C**
  (short press) and **0x5537A** (long press, only bit0→32 = save+power-off,
  bit3→31). Raw bit 7 → id 15 = DDS key. Knob rotation via ISR 0x1A53C →
  byte 0x20003424 (0x17/0x18) → posted as type 1 by 0x44FB0.
- **DDS key handler = 0x2CA60** (type-1 id 15): page 5 → toggle popup bit;
  page 3 → `b.w 0x472D0` (back to scope); page ≠ 2 → return; page 2 →
  `b.w 0x49880` (enter DDS).
- Boot page: init `0x36018` reads a 4-byte word at flash **0x11000** (config
  block saved by `0x31DF0(0x55)` on power-off): low byte 0x55 → page 2,
  0xAA → page 4, anything else (blank) → first-boot path (page 2, English).
  The page constant is `movs r3,#2` at **0x3668E**. After that, init calls
  0x14B30, 0x14184, 0x300B4 and sends hw cmd 9, all of which branch on the
  page byte and handle page 1, so changing the constant should give a
  consistent DMM boot. Verified 0x14B30 only toggles bit 7 of the page byte.
- DMM data path (for Goal 4 later): UART ISR 0x37BC8 fills 0x2000343C.. and
  gives semaphore [0x20003258]; **DMM task 0x439B8** parses BCD nibbles and
  decodes mode/range in `0x407D4` (39-case switch). Commands to the DMM chip go
  through queue [0x20003254] → task 0x43F28 → UART TX buffer 0x2000018B.
- Run key on the DMM page (type-1 id 5 → 0x2DBE8) toggles **HOLD** (+0x470).
  Long-press raw key 3 (id 31 → 0x14DC0) acts only on the DMM page when
  +0xE24==1 — unexplored; may be range-related. Worth a look for Goal 2.
- 0x36018 also writes a large table of constants at +0x1FE.. and +0x138..;
  looks like calibration/scale defaults. **Do not touch.**

**Patch set `firmware/dmm-first.json`** (dry-run OK; output crc32 `043ECC1A`):
1. Goal 1 — file 0x2568E: `02 23`→`01 23` (`movs r3,#1`): boot page = DMM.
2. Goal 3 — file 0x1BA70: `03 28`→`01 28` (`cmp r0,#1`): DDS key on the DMM
   page goes back to the scope.
3. Goal 3 — file 0x1BA7E: `b.w 0x49880`→`b.w 0x49924`: DDS key on the scope
   page enters the DMM. The DDS remains reachable via Menu popup (touch id 0x11).
Net behaviour: power-on → DMM; DDS key toggles scope ↔ DMM; the generator is
only reachable from the Menu popup. Three same-length edits, 4 bytes differ.
Built to `firmware/work/dmm-first/2D15P_V2.7.0.7_260826.bin`. **Not flashed.**

**Verification plan after flashing** (write results in `notes/flashing.md`):
- Power on → DMM screen appears directly, reading updates, HOLD works.
- Press DDS key → scope; press again → DMM. Menu → generator still opens DDS.
- Power off/on → still boots to DMM (config save path unaffected).
- Language still correct (config block untouched). Screenshot still works.

- 2026-10-06: **dmm-first flashed and verified** (boot→DMM, DDS key scope↔DMM,
  generator via Menu, About 2.7.0.7). Owner notes: physical Menu key does
  nothing on DMM page (stock behaviour too; touch "< Back" needed); DDS key LED
  is off on DMM/scope pages.
- 2026-10-06: **Front-panel LEDs.** 16-bit word `0x2000341A` is shifted out to a
  serial register by `0x31C34` (GPIO 0x40041000 bits 4/5/8). Low byte = analog
  front-end config (written by 0x138C8 from struct +0x2C). High byte = LEDs,
  **active-low**, rebuilt on page change by `0x300B4` (sets 0xFF00, then clears):
  0x200/0x400 channel LEDs (+0xA, +0x3C2), **0x800 = lit iff generator output
  on (+0x450, toggled 0↔1 by 0x48038 which also sends hw cmd 0x16)** — believed
  to be the DDS key LED (owner to confirm), 0x1000/0x2000 = Run/Stop green/red
  (page 1: HOLD +0x470, page 2: run +0x2F, page 3: output +0x450), 0x8000 forced
  off, 0x100 cleared only on USB/page-7 screens (0x45AB0, 0x4BC1C).
- 2026-10-06: Patch 3 (Goal 3c) added to `firmware/dmm-first.json`: rewrote
  0x3011C..0x3016F (end of 0x300B4; no other refs into the range) so 0x800 is
  lit when page==1 OR +0x450==1; Run/Stop logic preserved (all three pages
  now select via carry, equivalent for 0/1 flags). Assembled with keystone
  (installed in tools/.venv), verified by capstone round-trip. New output
  crc32 `E826ED29` → `firmware/work/dmm-first-led/`. Not flashed.
- 2026-10-06: **dmm-first-led flashed** (E826ED29). Owner: DDS LED stays lit on
  scope page too. Analysis: both page setters tail-call 0x300B4, so on page 2
  the LED = generator output (+0x450). +0x450 is restored from the config block
  at boot (init 0x3688E) and factory default is 1 (0x31FA8 `strh 0x0101`), and
  the owner had pressed Run on the generator page during the LED test → output
  most likely still on. To verify: generator page → Run off → scope page LED off.
- 2026-10-06: **Menu key = type-1 id 13 (raw bit 20), handler 0x2C9E0.**
  Earlier label "Level/run toggle" was wrong. Page 2: toggles +0xE34 0↔1 (main
  menu panel) then 0x4BEB8 redraw; page 5 (key test): toggles +0xE3C bit 0x800;
  page 6: toggles +0x30 1/2 (picture viewer); **page 1 (DMM): ignored.**
  Raw bit 0 → id 14 (power, short press = bx lr). Only branch to 0x472D0
  (enter scope) is the DDS handler; other page-2 writers: 0x37A7A, 0x45ADC,
  0x48E28, 0x48F74, 0x493B4, 0x494E8, 0x49584 (second handler table
  0x555E0–0x55658, users in 0x428CC/0x2CAA0/0x473C4). DMM "< Back" touch
  handler not yet identified.
- 2026-10-06: Owner: DMM "< Back" goes to the scope; wants Menu key on DMM =
  go to scope + open main menu. **Patches 4+5 (Goal 3d)**: hook 0x2C9F6
  `cmp r0,#2; bne.w 0x30162` → cave in the freed tail of 0x300B4 (needs patch 3):
  page 1 → `bl 0x472D0` (enter scope) + `bl 0x470D8` (touch id 1 handler:
  +0xE34=1, redraw = main menu, same as scope Menu key); else `pop {r7,pc}`.
  Build crc32 `3A36D9C7` → `firmware/work/dmm-first-menu/`.
  Flashed + verified 2026-10-06.
- **Tooling gotcha:** keystone mis-encodes Thumb-2 *conditional* wide branches
  (`bne.w` at 0x2C9F8 came out targeting 0x5CB5E). bl/b.w/short branches were
  fine. Always round-trip through capstone; conditional .w branches are
  hand-encoded (T3) for now.
