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

## Choosing T

The board is configured by **T**, the shortest run of the line code (the
timer runs at T/3, one chip). Rules:

- the camera exposure should be `<= T`; the receiver still decodes up to
  about `2 T` with a growing penalty and gives up beyond `3 T`;
- a chip (`T/3`) should be at least ~1.5 rows, better 3 or more;
- a packet is 82 chips (`RS_PKT_CHIPS`), i.e. `82 · T / (3 · t_row)` rows
  tall. If this is taller than the blob, switch on **repetition** (`rep 2` or
  `rep 3` on the demo, `cfg.repeat`): the receiver reads one packet across
  two copies, and from any sync it also reads the packet before it, so a blob
  about one packet long still yields a packet per frame.

Examples. iPhone 14 (`t_row` 5.1 µs, exposure 15 µs, blob 500–600 rows): T =
45–60 µs, packets 400–530 rows, ~100 packets/s. Samsung S21 FE in RAW capture
(`t_row` 2.65 µs, exposure 57.5 µs, blob ~1600 rows of 3000): T = 90–120 µs
(exposure 0.5–0.65 T), packets 920–1230 rows, so `rep 2–3`; 15–26 packets/s
at 30 fps. In the firmware: `chip 90` and `rep 2` over the serial port, or
`cfg.chip_us = 90; cfg.repeat = 2` (the library clamps `chip_us` to ≥ 24 µs).

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
| row time `t_row` | **5.1 µs** (T = 60 µs → 3.9 rows per chip) |
| frame readout | ≈ 5.5 ms out of a 16.7 ms frame period (33 % coverage) |
| scan axis | rows of the native buffer (horizontal bands in landscape) |
| chosen T | **45–60 µs** (exposure 0.25–0.33 T; 25–33 kbit/s gross per channel) |
| packet height | 67 × 5.9 ≈ 395 rows |
| decoded packets | 33–38 pkt/s with the board at ~5 cm (blob ≈ 170 rows + halo); 50–120 pkt/s with the current receiver |
| chip in the bit-bang fault loop | ≈ 38 µs (7.6 rows/chip): the receiver adapts by itself |

With `T_chip = 100 µs` (the initial value) a packet would be ≈ 1300 rows tall,
more than the whole frame: nothing decodable. Calibration is therefore
essential for every new camera.

## Measured results (2026-10-01, Samsung S21 FE, back wide camera, Camera2)

| Quantity | Value |
|---|---|
| shortest exposure | **57.5 µs** (the camera reports it; the edges in the data show about 60–100 µs) |
| row time | 1080p **5.44 µs**, 4K 3.22 µs, RAW 4000×3000 **2.65 µs** (the strobe gave 2.83; the decoded packets' clock, which is what matters, gives 2.65) |
| frame readout | 1080p 6.0 ms, 4K 7.0 ms, RAW ~8 ms, of a 33 ms frame at 30 fps |
| capture | RAW_SENSOR (Bayer, black 64, white 1023): the YUV path hides saturation behind the ISP's highlight compression |
| chosen T / repeat | **90–120 µs, rep 2–3** → 15–26 packets/s |

The row time differs per resolution, so the Android app keeps one per
resolution (Settings, filled by the strobe calibration; defaults are these).
