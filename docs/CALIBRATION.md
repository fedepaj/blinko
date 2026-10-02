# Rolling-shutter calibration

The decoder is self-calibrating (it measures the rows per chip from the sync
of every packet), but to pick T for a camera and to know how tall a packet is
in its frames it is worth measuring the camera's **row time** `t_row` once,
with the method from Joan Charmant's article. The apps also keep the measured
row time and give it to the receiver, which needs it to express the exposure
in rows.

Units: **T** is the shortest run of the line code and the value a board is
configured with (`chip`, `chip_us`); a **chip** is T/3, the board's timer
period. The full glossary is in `core/docs/PROTOCOL.md`.

## Procedure

1. Flash `arduino/libraries/Blinko/examples/StrobeCalibration` (a square wave
   on every LED, 2000 Hz by default; `arduino/build.sh StrobeCalibration
   upload`, or `make calib` inside `arduino/`), or just send `strobe 2000` to
   the demo over the serial port (`strobe 0` returns to data). The calibration
   sketch accepts `f <hz>` on its own serial port.
2. In the app open **Lab**, turn on *Strobe calibration mode* and set the same
   frequency in *Strobe frequency (Hz)*.
3. Bring the phone close to the LED (1–3 cm) until the defocused blob fills
   the profile.
4. Read the *Measurement* section:
   - **Band period** `P` (rows per strobe period)
   - **Peak strength**: how clear the bands are. On iOS the other axis is
     shown next to it, and when the bands are there (a sensor that reads out
     the other way round) the app offers *Bands are on the other axis →
     switch*; on Android tap the profile in Live to switch the axis.
   - **Row time** `t_row = 1 / (f_strobe · P)`
   - **Frame readout** `t_row · H` (H = profile length, i.e. the frame height)
   - the shortest timing the camera resolves: **Min T (1.5 rows/chip)** on
     iOS, `4.5 · t_row`; **Min chip (4 rows)** on Android, `4 · t_row` (a chip
     of four rows; T is three times that)
   - **Packet height @T=60 µs**: `82 · 20 µs / t_row` rows.

The *Camera* section below shows what the capture is actually doing: format,
frame rate, exposure and its minimum, ISO, lens position and the ROI used.

A measurement with a row time between 2 and 30 µs and a peak strength above
0.3 is stored and used from then on (iOS: one value; Android: one per capture
mode, because the row time changes with the resolution). In Android's RAW
capture the Lab measures the sensor's rows and the app stores four times that,
the row time of the reduced image the receiver decodes.

## Choosing T

The board is configured by **T** (the timer runs at T/3, one chip). Rules:

- the camera exposure must stay below T: the receiver drops what it would
  have to fit with an exposure over 3 chips. Half of T or less is comfortable;
- a chip (`T/3`) should be at least 1.5 rows, better 3 or more;
- a packet is 82 chips (`RS_PKT_CHIPS`), i.e. `82 · T / (3 · t_row)` rows
  tall. If this is about the height of the blob, switch on **repetition**
  (`rep 2` or `rep 3` on the demo, `cfg.repeat`): the receiver reads one
  packet across two copies, and from any sync it also reads the packet before
  it, so a blob about one packet tall still yields a packet per frame;
- the Arduino library runs T down to 45 µs on the Nano R4
  (`BLINKO_MIN_CHIP_US`) and brings a shorter request up to that.

Examples. iPhone 14 (`t_row` 5.1 µs, exposure 15 µs): T = 60 µs, packets 322
rows (241 at T = 45 µs), one copy. Samsung S21 FE in RAW capture (`t_row`
2.65 µs, exposure 57.5 µs): T = 90–120 µs (exposure 0.5–0.65 T), packets
930–1240 sensor rows of 3000, so `rep 2` or `rep 3`. In the firmware:
`chip 105` and `rep 3` over the serial port, or
`cfg.chip_us = 105; cfg.repeat = 3`.

## Checking the data signal

In **Live**, with the demo running:

- the profile chart under the preview shows the bands; when a single receiver
  decodes the whole frame (multi-source off) the decoded packets are
  highlighted on it (orange/green/blue per channel, red for a FAULT packet);
- each tracked light gets a marker ring in the camera preview, labelled with
  its last message;
- the stats bar reports `fps`, `pkt/s`, `rows/chip`, `contrast`, `mode`,
  `peak`, `pilots` and `msgs`; `rows/chip` fills in as soon as valid packets
  arrive, and `pkt/s` counts distinct packets;
- messages appear under the chart and in the **Console** tab, tagged by source
  and slot.

If `contrast` is high but no packets arrive: the exposure is too long for T
(raise `chip`), or the blob is shorter than the packet (move closer, lower
`chip` or add `rep 2`), or the scan axis is wrong (check it in Lab).

## When the LED saturates the sensor

A very bright LED very close to the camera clips the sensor: `peak` sits at
255, `contrast` is high, and the middle of the blob is a flat white disc where
the shortest dark runs have disappeared. The halo around that core still
carries them.

The receiver compensates. Profiles weight each column by its row-to-row
variation and ignore steps into or out of clipping; columns that clip on two
or more rows can be dropped outright as long as at least 8 unclipped columns
remain (`core/rs_frame.c`, `RS_SAT_LEVEL 250`, `RS_SAT_MIN_COLS 8`). When
something in a blob clips, the multi-source receiver builds both profiles
(with and without the clipped core) and keeps the one that decodes more
packets, checking again every few frames (`core/rs_multi.c`).

Still, it is better not to saturate in the first place:

- move back slightly, until the core of the blob stops clipping — the blob
  stays defocused and the dark runs come back;
- or lower the LED brightness on the board (`bright 40`,
  `cfg.brightness`);
- or use a longer T (`chip 90`), so that the dark runs are longer and even
  the dimmer halo gets enough rows per chip;
- keep the exposure at the sensor minimum and do not raise the ISO;
- for a pulsed fault LED, saturation is expected (the death loop drives the
  red LED at full brightness): rely on the halo. The death loop sends at
  T = 120 µs with three copies of every packet, whatever the running
  configuration.

## Camera parameters

The two phones the project is measured on, back wide camera.

| Quantity | iPhone 14 (1920×1080, BGRA) | Samsung S21 FE (Camera2) |
|---|---|---|
| row time `t_row` | 5.1 µs | 1080p 5.44 µs; 4K 3.22 µs; RAW 4000×3000 2.65 µs per sensor row, 10.6 µs per row of the reduced image the receiver decodes |
| shortest exposure | 19 µs at 60 fps, 15 µs at 120 fps | 57.5 µs as the camera reports it; the edges in the data show 76–100 µs |
| frame rate with manual exposure | 120 fps | 30 fps |
| frame readout | about 5.5 ms (of 8.3 ms at 120 fps, 16.7 ms at 60 fps) | 1080p 6.0 ms, 4K 7.0 ms, RAW about 8 ms, of 33 ms |
| scan axis | rows of the native buffer (horizontal bands in landscape) | rows |
| capture | BGRA | RAW (`RAW_SENSOR`, black 64, white 1023): the YUV path hides saturation behind the ISP's highlight compression |
| usable T | 45–60 µs (exposure 0.25–0.33 T; 3–4 rows per chip) | 90–120 µs (exposure 0.5–0.65 T) |
| packet height | 241–322 rows | 930–1240 sensor rows |
| repetition | 1 | 2–3 |
| distinct packets per second, Nano R4 a few cm away, three streams | about 470 at T = 60 µs, about 240 at T = 45 µs | about 40 at T = 105 µs with 3 copies, about 22 with one |

On the Samsung in RAW the strobe calibration reads 2.83 µs per row where the
clock of the decoded packets gives 2.65 µs. The packets' clock is the figure
to trust: row time = (T/3) ÷ `rows/chip`.
