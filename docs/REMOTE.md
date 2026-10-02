# Remote session

Both apps run a small TCP server through which a computer drives them: read
and change settings, sample statistics and messages, grab a frame, record,
replay. It is how measurements are scripted (`tools/bench.py`) and how
recordings get from the phone to the computer. The client is
`ios/tools/rslive.py`, for both apps, as a command and as a Python class
(`RSLive`).

Sources: `ios/Sources/RemoteServer.swift` and `SessionModel.swift`,
`android/…/RemoteServer.kt` and `Session.kt`.

## Connecting

The server is switched by **Settings › Debug › Remote session (TCP port
7777)**, on by default in both apps. It listens on the phone's **localhost
only**, which is where a USB forward arrives:

| | iOS | Android |
|---|---|---|
| USB forward | `pymobiledevice3 usbmux forward 7777 7777` (`make usb-forward`) | `adb forward tcp:7778 tcp:7777` (`make android-forward`) |
| client | `ios/tools/rslive.py …` (`make live ARGS=…`) | `ios/tools/rslive.py --port 7778 …` (`make live-android ARGS=…`) |

Over Wi-Fi: turn on **Allow Wi-Fi (LAN) connections** in the same section (off
by default; both switches are remembered), read the address shown there, and
give it to the client: `rslive.py --host 192.168.1.23 --port 7777 …`.

**Security.** The server has no authentication, and its commands change the
camera settings and delete recordings. On localhost only the computer at the
other end of the USB cable reaches it. With LAN connections allowed, anyone on
the network can drive the app: leave that off outside a network you trust.

## Framing

The same in both directions:

```
u32 length (big-endian) | u8 kind | payload (length bytes)
```

`kind` 0 is a JSON object in UTF-8, `kind` 1 is binary. A binary frame is
always announced by the JSON message that precedes it, which says what it is
and how long. A client sends only JSON commands, `{"cmd": "<name>", …}`; a
frame longer than 1 MB from a client closes the connection. The apps answer
with JSON objects that carry a `type`; a failed command is answered with
`{"type": "error", "msg": "<why>"}`.

Several clients may be connected. A reply goes to the client that asked;
broadcasts go to all of them.

## Commands

| Command | Fields | Reply |
|---|---|---|
| `get` | | `{"type": "settings", "settings": {…}}`: the settings and what the camera offers (below) |
| `set` | `key`, `value` | the same `settings` reply with the new state, or an `error`. On Android a change of camera or resolution reopens the camera and the reply comes 1.5 s later |
| `stats` | | one `stats` message (below) |
| `messages` | | `{"type": "messages", "messages": [{t, slot, level, level_name, text, source}, …]}`, oldest first: the console's history |
| `reset` | | clears the console and re-initialises the receiver; `{"type": "ok", "cmd": "reset"}` |
| `frame` | `step` (iOS only, default 2: keep every `step`-th column) | `{"type": "frame", "w", "h", "step", "format", "t"}` followed by a binary frame (below) |
| `record` | `seconds` (default 2), `note`, `send` (default true), `keep` (default true) | `{"type": "recording", "state": "started", "seconds", "note"}` at once; `{"type": "recording", "state": "done", "file", "summary"}` when it ends; then, with `send`, `{"type": "file", "name", "size"}` followed by the file as a binary frame. With `keep` false the file is removed from the phone once sent |
| `files` | | `{"type": "files", "files": [{name, size}, …]}`: the recordings kept on the phone |
| `pull` | `name` | Android only: `{"type": "file", "name", "size"}` followed by the file as a binary frame |
| `replay` | `name` | `{"type": "replay", "state": "started", "name"}`; the replay's messages are broadcast as `message`s and its end as a `replay` message (below) |
| `delete` | `names` (a list) or `name` | `{"type": "ok", "cmd": "delete", "removed": <count>}` |

A recording is named by its plain file name, as `files` lists it.

`record` is refused while a recording is running, and on iOS while a replay
is running; `replay` is refused while a replay is running, and on iOS while a
recording is. On iOS the app does not decode while it records and live
decoding pauses during a replay; on Android decoding continues while
recording and pauses during a replay.

### The `frame` reply

| `format` | Binary payload |
|---|---|
| `BGRA` | `w × h` pixels of 4 bytes (B, G, R, A), rows at full resolution, columns subsampled by `step`. On iOS the camera frame with every `step`-th column; on Android the image the receiver decodes (about 480 columns, whatever the capture format; in RAW the mosaic reduced 4×4) |
| `PROFILES` | Android, RAW capture with the strobe calibration mode on: `w` = 3 and the payload is three per-row profiles (R, G, B) of `h` 32-bit floats each |

`t` is the frame's timestamp in seconds on the camera's clock. Android answers
`error` "no frame" if no frame arrives within 3 s.

### `set` keys

| Key | iOS | Android |
|---|---|---|
| `fps` | one of `frame_rates` | one of `frame_rates`, or 0 for the fastest |
| `exposure` | 0..1 on a log scale from the sensor's shortest exposure (0) to 1/250 s (1) | the same |
| `exposure_us` | — | exposure in µs (1..10⁶), clamped to the sensor's range |
| `iso` | 0..1 of the sensor's range | the same |
| `lensPosition` | 0..1, 1 = far focus | 0..1, 1 = infinity |
| `zoom` | zoom factor | 1..`max_zoom` |
| `minContrast` | the decoder's minimum contrast (8-bit counts) | the same, 0..255 |
| `multiSource` | true / false | true / false |
| `axis` | `rows` / `columns` | `rows` / `columns` |
| `camera` | `Wide` / `Ultra` / `Front` | `Wide` / `Ultra` / `Front`, or a camera id from `cameras` |
| `resolution` | — | `1080p` / `4K` / `RAW`, among the camera's `resolutions` |
| `labMode` | — | strobe calibration mode, true / false |
| `strobeHz` | — | strobe frequency for the calibration, 1..10⁶ |
| `rowUs` | — | row time in µs (0.1..1000) of the image the receiver decodes, for the capture mode in use |
| `recordingEnabled` | — | the Record button in the Live tab, true / false |
| `note` | text stored in the header of the next recordings | the same |

A number must be finite. Android also checks the range and refuses a frame
rate or a resolution the camera does not offer; iOS checks `fps` against
`frame_rates`. An unknown key is an `error`.

### The `settings` object

Both apps: `camera`, `fps`, `exposure`, `iso`, `lensPosition`, `zoom`, `axis`,
`minContrast`, `multiSource`, `remoteEnabled`, the LAN switch (`remoteLAN` on
iOS, `remoteLan` on Android), `camera_name`, `frame_rates`, `min_exposure_us`,
`iso_range` (`[min, max]`), `max_zoom`.

Android adds: `resolution`, `resolutions`, `labMode`, `strobeHz`, `rowUs`,
`note`, `cameras` (a list of `"<id>: <description>"`), `exposure_us`, `format`
(what the camera delivers), `device`.

## Broadcast messages

Sent to every connected client without being asked for.

**`stats`**, every 200 ms while a client is connected (and as the reply to the
`stats` command):

| Field | Meaning |
|---|---|
| `t` | wall-clock time, seconds since 1970 |
| `fps` | frames processed per second |
| `pkt_per_s` | distinct packets per second |
| `packets`, `messages` | totals since the receiver was last reset |
| `rows_per_chip` | the clock of the decoded packets |
| `mode` | decoding mode: `mono` / `luma`, `RGB`, `direct` (on iOS with several lights, the modes joined by `/`) |
| `pilots`, `cond` | pilot blocks recognised, condition of the colour matrix |
| `contrast`, `peak`, `sat`, `roi` | of the whole-frame profile: range, brightest pixel, fraction of rows that clip, bright region on the cross axis |
| `syncs`, `crc_fail` | sync candidates and failed detector runs of the last frame |
| `last_packet_age` | seconds since the last packet |
| `exposure_us`, `iso`, `cam_fps`, `width`, `height` | what the camera is doing |
| `still`, `motion` | whether the phone is held still, and the motion level |
| `recording` | a recording is running |
| `thermal` | iOS: `nominal`, `fair`, `serious`, `critical`. Android always reports `nominal` |
| `tracks` | one object per light: `id`, `group` (logical source), `board` (the id the board announces, when seen), `x`, `y`, `radius` (fractions of the frame), `mode`, `packets`, `messages`, `pilots` |
| Android only | `stitched`, `exposure_actual_us` (what the sensor reports per frame), `readout_ms`, and `lab` (`period_rows`, `strength`, `row_time_us`, `readout_ms`, `count`) once a strobe calibration has run |

**`message`**, for every decoded message: `t`, `slot`, `level`, `level_name`,
`text`, `source` (the logical source, 0 for the single-receiver path). On iOS
a message decoded by a replay carries `"replay": true`.

**`replay`**, when a replay ends: `state` (`done`; on iOS `failed` when the
recording could not be read) and `summary`, the line the app shows.

## Limits

| | iOS | Android |
|---|---|---|
| frame a client may send | 1 MB | 1 MB |
| `record` duration | 0.1 to 10 s, refused outside | brought into 0.1 to 30 s |
| size of a recording | about 250 MB per second at 120 fps | about 60 MB per second at 30 fps |
| file transfer | the length field is 32 bits: a file over 4 GB is not sent and stays on the phone | the same length field |

## The client

```sh
rslive.py [--host H] [--port P] get | stats | reset | messages
rslive.py watch [--seconds N]                 # stats once a second, messages as they arrive
rslive.py set KEY VALUE
rslive.py frame OUT.png [--step 2]            # PROFILES replies are saved as .npy and plotted
rslive.py record [--seconds 2] [--note TEXT] [--out DIR] [--keep]
rslive.py files | pull NAME [--out DIR] | replay NAME | delete NAME… | delete --all
```

`record` asks for the file to be sent and, unless `--keep` is given, removed
from the phone. As a library:

```python
from rslive import RSLive
with RSLive(port=7778) as s:
    s.set("exposure_us", 60)
    path, summary = s.record(2, "S21 R4 T=105 rep 3", "testdata")
    print(s.stats()["pkt_per_s"])
```
