# Translation sources

Terminology research behind `lang/<code>.json` (2026-10-06): vendor manuals,
datasheets and technical references in each language, checked against the
draft wording. Each file lists the changes that were recommended, with
confidence and a source URL. Not every suggestion was applied: a few were
too wide for their on-screen box, or too uncertain. `lang/<code>.json` is the
authority.

Turkish also follows the TMMOB EMO Ankara article "Osiloskop Kullanimi"
(Onder Siser, Haber Bulteni 2024/2): Dusey, Tetikleme, Olcme.

**Turkish duty cycle** (owner-supplied research, 2026-10-06): EMO and academic
usage is "doluluk orani"; Turkish oscilloscope datasheets and bench usage keep
"Duty"/"Duty Cycle" in English. So the generator parameter (`dds.param.2`) is
"Doluluk" and the measurement readouts (`meas.4/5`) are "Duty+"/"Duty-".
"Doluluk Orani" was not used: it is ~20% wider than "Duty Cycle", and an
over-long label here pushed the generator keypad off-screen in the UA mod
(its v1.2 changelog).
