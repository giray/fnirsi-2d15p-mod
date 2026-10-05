# Flashing log

Record every stock image and every flash here (append-only, dated).

## Stock images on hand

| date | filename | size | crc32 | sha256 | source |
|---|---|---|---|---|---|
| 2026-10-05 | `2D15P_V2.7.0.7_260826.bin` | 1203945 (0x125EE9) | `B43E8C2D` | `f35ff1a06f6b295d22b8982c58bb6fc8a02228ff8927e32790f21219e11433ae` | FNIRSI `2D15P_Firmware_V2.7.0.7.zip` (release 2026-08-26), kept alongside, both chmod 444 |

- 2026-10-05: CRC32 matches the UA mod's stated stock CRC exactly, so
  `notes/prior-art.md` offsets/findings for 2.7.0.7 apply to this image.
- Vendor README says Windows only for the upgrade path; the UA mod and the
  EEVblog reports confirm plain USB mass storage works from Linux.

## Bootloader recovery round-trip

- Unit's installed firmware on 2026-10-05 before our work: **V2.6.0.7**.
  Upgraded the same day to 2.7.0.7 (see Tier 2 below).
- [x] 2026-10-05 **Tier 1: recovery bootloader mounts.** Power off, hold large
      knob, brief power press → enumerates as USB mass storage
      (`idVendor=0416 idProduct=5020`, Manufacturer "Synwit", Product
      "Mass Storage", serial redacted), auto-mounted by udisks at
      `/run/media/$USER/4E21-0000`: FAT16, label-less, UUID `4E21-0000`,
      ~12.9 MB free, folders `Screenshot file`, `Screenshot simple file`,
      `Upgrade file` (empty), plus Windows-created `System Volume Information`.
      Same layout as the normal USB Sharing volume. dmesg showed two
      `device descriptor read/64, error -71` retries before enumerating; harmless.
      Unmounted, power-cycled, booted normally.
- [x] 2026-10-05 **Tier 2: flash through recovery works.** Official
      2.6.0.7 → 2.7.0.7 upgrade done via the recovery volume: copied
      `2D15P_V2.7.0.7_260826.bin` into `Upgrade file`, `sync`, unmount,
      power-cycle; updater ran and the unit now runs **V2.7.0.7**. Recovery
      path is confirmed usable for writes on this unit.
      Note: not a same-version round-trip (no 2.6.0.7 image on hand), so the
      "return to stock" baseline is now 2.7.0.7. Fetch the 2.6.0.7 image from
      FNIRSI if a downgrade path is ever wanted.

**Bootloader recovery: CONFIRMED on this unit (2026-10-05).** `SAFETY.md`
checklist item 1 can be ticked. Unit firmware: V2.7.0.7 = our stock image.

## Pending: dmm-first (Goals 1+3)

- Patch set `firmware/dmm-first.json`, built 2026-10-05 to
  `firmware/work/dmm-first/2D15P_V2.7.0.7_260826.bin`, crc32 `043ECC1A`,
  4 bytes differ from stock. Verification plan in `notes/re-plan.md`.
- [ ] Pre-flash checklist walked with owner (SAFETY.md)
- [ ] Flashed; result logged below

## Flash log

- 2026-10-05 — stock `2D15P_V2.7.0.7_260826.bin` (crc32 B43E8C2D) via recovery
  bootloader, from 2.6.0.7. Result: boots, About shows 2.7.0.7. Purpose:
  confirm recovery write path + align with prior-art target version.
