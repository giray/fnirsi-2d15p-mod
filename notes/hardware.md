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
