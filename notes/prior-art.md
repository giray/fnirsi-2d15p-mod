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
