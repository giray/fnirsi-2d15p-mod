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
