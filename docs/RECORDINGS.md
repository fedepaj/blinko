# Recordings (`.rsrec`)

A recording is a sequence of camera frames as the receiver sees them, with
their timestamps, in one file. Replayed through the same C receiver, on the
phone or on a computer, it turns a change to the receiver into a measurement
on real data.

Sources: `ios/Sources/Recorder.swift`, `android/…/Recorder.kt` (writers),
`core/tools/rsrec.py` (reader).

## File format

Everything is little-endian.

```
"RSREC001"                     8 bytes, magic
u32 headerLen
header                         headerLen bytes, a JSON object (UTF-8)
then, per frame, until the end of the file:
  "FRME"                       4 bytes
  f64 timestamp                seconds, on the camera's clock
  f32 gyro[3], f32 accel[3]    the motion sensors' last reading
  u32 rawSize                  bytes of the frame: width × height × 4
  u32 compSize                 bytes stored
  u8  codec                    0 = raw (compSize == rawSize), 1 = LZ4
  bytes                        compSize bytes
```

Both apps write **codec 0**. Codec 1 is LZ4 in the block framing of Apple's
Compression framework (`bv41` / `bv4-` blocks, `bv4$` at the end);
`rsrec.py` reads it when the `lz4` package is installed, the iOS app replays
it, and the Android app does not.

A reader stops at the first record that does not start with `FRME`. If a
write fails (disk full) the iOS app cuts the file back to the last whole
frame.

### Header

The same keys from both apps:

| Key | Meaning |
|---|---|
| `width`, `height` | size of the **stored** frames in pixels (after the column subsampling) |
| `columnStep` | every `columnStep`-th column of the source image is stored |
| `pixelFormat` | `"BGRA"` |
| `fps` | the camera's frame rate |
| `exposureUs` | exposure time in µs |
| `iso`, `lensPosition` | sensitivity and focus position |
| `camera` | camera name |
| `device` | iOS: the device model as the system names it (`iPhone`); Android: manufacturer and model |
| `axis` | scan axis selected in the app, `Rows` or `Columns` |
| `startedAt` | start time, ISO 8601 in UTC |
| `note` | free text: the note field of the app, or `note` of the remote `record` command |

The header does not carry the row time: a replay is told it separately
(`replay.py --row-us`).

### Frames

A frame is `height` rows of `width` pixels, 4 bytes per pixel in the order B,
G, R, A, with no padding. **Rows are kept at full resolution** because they are
the time axis; columns are subsampled, since a profile is an average across
columns.

| Source | Stored frame | A row is |
|---|---|---|
| iOS, 1920×1080 BGRA | every 4th column: 480×1080 | one sensor row (5.1 µs on an iPhone 14) |
| Android, 1080p or 4K (YUV or RGBA from the camera, converted to BGRA) | columns thinned to about 480 (`columnStep` 4 at 1080p, 8 at 4K): 480×1080, 480×2160 | one sensor row (5.44 µs at 1080p, 3.22 µs at 4K on a Samsung S21 FE) |
| Android, RAW | the reduced image the receiver decodes: one pixel per 2×2 Bayer block for every 4 sensor rows (R and B as they are, G the mean of Gr and Gb, scaled by the black and white levels so that a clipped pixel is 255), then every 4th of those columns. 4000×3000 becomes 500×750 | **4 sensor rows** (10.6 µs on a Samsung S21 FE) |

The timestamp is the camera's: seconds since boot on iOS, the sensor
timestamp on Android. Only differences matter; the replay tools subtract the
first frame's.

### Sizes

A stored frame is about 2 MB (480×1080×4), so a recording grows by about
250 MB per second on an iPhone at 120 fps and about 60 MB per second on
Android at 30 fps. The camera thread copies each frame into one of 24 pooled
buffers and a background thread writes it; when the writer falls behind,
frames are dropped and counted in the recording's summary line.

## Making a recording

**In the app.** Settings › Debug › *Recording mode* adds a Record button
(2 seconds) and a note field to the Live screen. Files are named
`rec-<yyyyMMdd-HHmmss>.rsrec` and are kept in `Documents/recordings` of the
app's container on iOS and in `recordings` of the app's files directory on
Android.

**From a computer**, through the remote session ([REMOTE.md](REMOTE.md)):

```sh
ios/tools/rslive.py record --seconds 2 --note "R4 rgb T=60" --out testdata              # iPhone
ios/tools/rslive.py --port 7778 record --seconds 3 --note "S21 RAW T=105 rep 3" --out testdata   # Android
```

The phone records (0.1 to 10 s on iOS, up to 30 s on Android), sends the file
and removes its own copy unless `--keep` is given. `tools/bench.py` records a
clip per measurement cell this way.

Getting at files kept on the phone: `rslive.py files`, then on Android
`rslive.py pull NAME` or Share in the Lab tab; on iOS
`ios/tools/pull_recordings.sh` copies them all to `ios/build/recordings`.

The iOS app does not decode while it records; the Android app does.

## Replaying

**On a computer**, with the core's replay tool:

```sh
.venv/bin/python core/tools/replay.py testdata/rec-….rsrec --multi --row-us 5.1
```

`--multi` runs the multi-source receiver, as the apps do; without it one
receiver decodes the whole frame's bright region. `--row-us` is the row time
of the recorded rows (5.1 for an iPhone 14; for a Samsung S21 FE 5.44 at
1080p, 3.22 at 4K and 10.6 for RAW recordings): with it the receiver gets the
recording's exposure in rows, without it the exposure is unknown to the
detector. The tool prints the messages as they complete and a line of metrics
per recording (frames, fps, distinct packets per second, frames with packets,
messages, RGB lock, pilots); `--json out.json` saves them, `--png N out.png`
extracts frame N, several files can be given at once.

From Python:

```python
from rsrec import Recording          # core/tools on the path
rec = Recording("rec.rsrec")
rec.header["exposureUs"], len(rec)
t, gyro, accel, bgra = rec.frame(0)  # bgra: numpy array (height, width, 4)
```

`tools/bench.py analyze DIR` replays every clip of a directory through both
receiver paths, and `make unoq-headless REC=rec.rsrec` runs the UNO Q kiosk on
a recording.

**On the phone.** Lab › *Replay a recording* lists the recordings kept on the
phone and runs one through the multi-source receiver; `rslive.py replay NAME`
starts the same from a computer. The messages appear in the console tagged
`replay` and live decoding pauses while it runs. The Android app replays raw
(codec 0) recordings only.
