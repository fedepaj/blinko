# Rolling-shutter calibration

The decoder is self-calibrating (it measures the rows-per-chip from the sync
of every packet), but to pick `T_chip` and to know how many bits fit in a
frame it is worth measuring the camera's **row time** `t_row` once, with the
method from Joan Charmant's article.

## Procedure

1. Flash `arduino/libraries/Blinko/examples/StrobeCalibration` (a square wave on every LED, 2000 Hz
   by default; `arduino/build.sh StrobeCalibration upload`, or `make calib` inside
   `arduino/`), or just send `strobe 2000` to the demo over the serial port.
   The calibration sketch also accepts `f <hz>` on its own serial port.
2. In the app open **Lab**, turn on *Strobe calibration mode* and set the same
   frequency in *Strobe frequency (Hz)*.
3. Bring the phone close to the LED (1–3 cm) until the defocused blob fills
   the profile.
4. Read the *Measurement* section:
   - **Band period** `P` (scan lines per strobe period)
   - **Row time** `t_row = 1 / (f_strobe · P)`
   - **Frame readout** `t_row · H` (H = profile length, i.e. the frame height)
   - **Min chip (4 rows)** and **Packet height**, the two numbers that decide
     `T_chip`
   - **Peak strength**, for the chosen axis and for the other one: if the
     bands are on the other axis (a sensor that reads out the other way round)
     the app offers *Bands are on the other axis → switch*.

The *Camera* section below shows what the capture is actually doing: format,
frame rate, exposure and its minimum, ISO, lens position and the ROI used.

## Choosing `T_chip`

- you need `T_chip >= 4 · t_row` (at least 4 scan lines per chip);
- the exposure must be `<= T_chip` (better `<= T_chip/2`);
- a packet is 67 chips (`RS_PKT_CHIPS`, protocol v2), so it is
  `67 · T_chip / t_row` scan lines tall: this must stay **below the height of
  the blob**, otherwise no packet ever fits whole in one frame.

Example: `t_row = 10 µs`, a blob 700 rows tall. `T_chip = 100 µs` gives packets
670 rows tall — it technically fits but almost never lands entirely inside the
blob (~0.04 complete packets per frame). `T_chip = 60 µs` gives 402 rows, so
about 0.7 packets per frame. In the firmware: `chip 60` over the serial port,
or `cfg.chip_us = 60` (the library clamps `chip_us` to a minimum of 15 µs).

## Checking the data signal

In **Live**, with the demo running:

- the profile chart under the preview shows the bands, with the decoded
  packets highlighted (orange/green/blue per channel, red for a FAULT packet);
- each tracked light gets a marker ring in the camera preview, labelled with
  its last message;
- the stats bar reports `fps`, `pkt/s`, `rows/chip`, `contrast`, `mode`,
  `peak`, `pilots` and `msgs`; `rows/chip` fills in as soon as valid packets
  arrive;
- messages appear under the chart and in the **Console** tab, tagged by source
  and slot, with haptic feedback.

If `contrast` is high but no packets arrive: the exposure is too long (blurred
chips), or the blob is shorter than the packet (move closer or lower `chip`),
or the scan axis is wrong (check it in Lab).

## When the LED saturates the sensor

A very bright LED very close to the camera clips the sensor: `peak` sits at
255, `contrast` is high, and the middle of the blob is a flat white disc where
the 1-chip OFF gaps have disappeared. The halo around that core still carries
them.

The receiver already compensates. Profiles weight each column by its
row-to-row variance and ignore steps into or out of clipping; columns that
clip on two or more rows are dropped outright as long as at least 8 unclipped
columns remain (`core/rs_frame.c`, `RS_SAT_LEVEL 250`, `RS_SAT_MIN_COLS 8`).
In the multi-source path the two hypotheses (with and without the clipped
core) are both evaluated and the better-decoding one is kept, per frame
(`core/rs_multi.c`).

Still, it is better not to saturate in the first place:

- move back slightly, until the core of the blob stops clipping — the blob
  stays defocused and the gaps come back;
- or lengthen the chip, `chip 45`, so that even the dimmer halo gets enough
  scan lines per chip;
- keep the exposure at the sensor minimum and do not raise the ISO;
- for a pulsed fault LED, saturation is expected (the death loop drives the
  red LED hard): rely on the halo and give it a longer chip.

## Measured results (2026-09-15, iPhone 14, back wide camera, 1920×1080 @ 60 fps)

| Quantity | Value |
|---|---|
| minimum exposure | **19 µs** at 60 fps (**15 µs** at 120 fps), ISO min 34 |
| row time `t_row` | **5.1 µs** (30 µs/chip → 5.9 rows/chip) |
| frame readout | ≈ 5.5 ms out of a 16.7 ms frame period (33 % coverage) |
| scan axis | rows of the native buffer (horizontal bands in landscape) |
| chosen `T_chip` | **30 µs** (exposure = 0.63 chip; 16.6 kbit/s gross) |
| packet height | 67 × 5.9 ≈ 395 rows |
| decoded packets | 33–38 pkt/s with the board at ~5 cm (blob ≈ 170 rows + halo); 50–120 pkt/s with the current receiver |
| chip in the bit-bang fault loop | ≈ 38 µs (7.6 rows/chip): the receiver adapts by itself |

With `T_chip = 100 µs` (the initial value) a packet would be ≈ 1300 rows tall,
more than the whole frame: nothing decodable. Calibration is therefore
essential for every new camera.
