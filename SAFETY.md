# SAFETY — read before flashing anything

Modifying firmware on a sealed instrument carries a real risk of bricking it or
silently corrupting its calibration. This file is the standing procedure.

## The one rule that matters most

**Confirm bootloader recovery works on THIS unit before you flash any custom
image.** The 2D15P has a recovery bootloader: power off, hold the large knob,
briefly press the power button; it appears as a USB mass-storage volume
regardless of the state of the main firmware. Before trusting it with a custom
build, practise the full recovery once with the *stock* image:

1. On stock firmware, note the version (About screen).
2. Enter the recovery bootloader as above; confirm it mounts as a USB volume.
3. Copy the **stock** `.bin` into `Upgrade file`, `sync`, unmount, power-cycle.
4. Confirm it boots and shows the same version.

Only after this round-trip succeeds should any modified image be flashed.

## Non-negotiables

- **Pristine stock kept, always.** The untouched official `.bin` lives in
  `firmware/stock/` and should be made read-only (`chmod 444`). Every session
  must be able to return to exactly-stock.
- **Exact version match.** Flash offsets are specific to one firmware version.
  `tools/fw_patch.py` refuses to apply a patch set whose declared `input_crc32`
  (and optional size) does not match the source file. **Never remove or weaken
  that gate** to force a patch onto a different version — on the wrong firmware
  the device may not boot.
- **Keep the stock filename.** FNIRSI's updater expects the exact stock name on
  the upgrade volume (e.g. `2D15P_V2.7.0.7_260826.bin`). If the browser/tool
  renames the output, rename it back before copying.
- **Same-length patches only** for byte edits, so nothing downstream shifts.
  `fw_patch.py` enforces this.
- **Calibration is sacred.** Do not write to any region that might hold DMM or
  scope calibration. If a byte range's purpose is unknown, treat it as off-limits
  and ask before touching it. Calibration loss may be permanent.
- **No writes to the USB CDC/serial port on a live unit** until its command set
  is understood from static analysis. Reading (passive) is fine; writing is not.
- **Flush before power-cycle.** `sync` and unmount the upgrade volume every time,
  or the write may be truncated.

## Pre-flash checklist (run every time, out loud)

- [ ] Bootloader recovery has been confirmed working on this unit (round-trip
      with stock done at least once).
- [ ] A pristine stock `.bin` for this exact version is in `firmware/stock/`,
      read-only, CRC32 recorded in `notes/flashing.md`.
- [ ] The patch set declares the correct `input_crc32` and it matches the source.
- [ ] `fw_patch.py --dry-run` passed with every patch reporting OK.
- [ ] The output `.bin` has the exact stock filename.
- [ ] Battery is at least ~50% (a dying battery mid-flash is a bricking risk).
- [ ] Owner understands this specific change and agrees to flash it.
- [ ] A plan to verify the change after boot is written down (what screen /
      behaviour to check).

## If a flash goes wrong

1. Don't panic or repeatedly power-cycle. Enter recovery (hold knob + power).
2. Copy the **stock** `.bin` into `Upgrade file`, `sync`, unmount, power-cycle.
3. If recovery doesn't mount, try a different cable/port and a charged battery.
4. Record exactly what was flashed and what happened in `notes/flashing.md`
   before trying anything else.
