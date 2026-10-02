<img src="assets/logo/icon-rounded.png" alt="Blinko" width="110" align="right">

# Blinko

**Read a microcontroller's logs with a phone camera, through its LEDs.**

The board blinks its on-board LEDs; you point a phone at it and the messages
appear on the screen. No cable, no radio, no pairing, no extra hardware: the
LED that is already on the board is the transmitter, the camera that is already
in your pocket is the receiver.

It also works when the board is dead. A hard fault, a failed assert or a
watchdog reset ends in a handler that needs no interrupts, no kernel and no
drivers: it blinks the reason on the red LED until you press reset, and writes
it to flash so that every following boot repeats it until the firmware clears
it. A board that cannot talk on serial any more can still tell you *why* it
stopped.

## How it works

A CMOS camera does not expose the whole sensor at once: it exposes one row
after another, top to bottom. A LED blinking much faster than the frame rate is
therefore seen at a different instant by every row, and one frame comes out
striped. **The vertical axis of the image is a time axis**, at about 5 µs per
row on a modern phone, which is 200 kHz of sampling with no special hardware.

Blinko puts a small packet in those stripes:

```
 board                                   phone
 ┌────────────────────────┐              ┌──────────────────────────────┐
 │ Blinko.info("boot ok") │              │ camera, shortest exposure    │
 │   └ message slots      │   blinking   │   └ rows → brightness profile│
 │     └ fountain coding  │ ~~~~~~~~~~>  │     └ sync → chip clock      │
 │       └ RLL(2,7) code  │    light     │       └ fit → packets (CRC)  │
 │         └ timer → LEDs │              │         └ packets → message  │
 └────────────────────────┘              └──────────────────────────────┘
```

The board is configured with one time, **T**: the shortest run of light or
dark the line code produces (60 µs by default; the timer runs at T/3, one
chip). Each packet is 82 chips, 1.64 ms at T = 60 µs, and carries one byte of
the message. The receiver does not threshold the stripes: it fits chip
templates that include the camera's exposure smear, so it keeps decoding when
the exposure is long enough to round the shortest runs off, up to an exposure
of T. Packets are **fountain-coded**: the receiver rebuilds a message from
*any* sufficient subset of packets, so it does not matter which ones a given
frame happened to catch, and there is no retransmission protocol to run in a
fault handler. A colour LED sends three independent streams at once, one per
die, and the receiver separates them by measuring the camera's colour response
from pilot blocks the transmitter inserts periodically.

Measured with a Nano R4 a few centimetres from the camera, sending three
streams: an iPhone 14 at 120 fps decodes **about 470 distinct packets per
second** at the default T = 60 µs with one copy of each packet (about 240 at
T = 45 µs); a Samsung S21 FE at 30 fps in RAW capture decodes about 40 with
T = 105 µs and each packet sent three times. The reason for a crash reaches
the phone in one or two seconds.

The idea of measuring a rolling shutter with a blinking LED comes from Joan
Charmant's article
[Measuring rolling shutter with a strobing LED](https://joancharmant.com/blog/measuring-rolling-shutter-with-a-strobing-led/).

## What you need

- A board with at least one LED you can drive from a timer. Supported today:
  the **Arduino Nano R4** (Renesas RA4M1) through the Arduino library, and
  boards supported by **Zephyr** whose devicetree provides `led0` and a
  `counter` device, through the Zephyr module (tested on the Arduino Nano 33
  BLE).
- A phone: **iOS 17+** or **Android 9+** (API 28). The camera must allow a
  manual exposure shorter than the board's T; the shorter the better.
- Nothing else. A colour LED triples the throughput but is not required.

## Quick start

```sh
git clone --recursive https://github.com/fedepaj/blinko
cd blinko
make setup                # submodules + python venv (.venv)
make test                 # core test suite on the simulator

make fw-upload            # Arduino demo on a connected Nano R4
make ios-install          # iOS app on a paired iPhone (see ios/README.md for signing)
make android              # Android APK in android/build/
```

Open the board's serial port at 115200 and type `info hello`. Point the phone
at the board from a few centimetres, with the LED filling a good part of the
frame, and the message appears in the app's console.

Try the fault path too: `hf` provokes a real hard fault, or short **D2 to D3**
on the demo board. The red LED starts pulsing and the app shows the reason,
for example `HF p=0000437a l=00004b4f c=8200`, with the program counter, the
link register and the fault status register.

## Using it in your own firmware

Arduino:

```cpp
#include <Blinko.h>

void setup() {
  Blinko.begin();                       // T = 60 µs, RGB + built-in LED; the death loop always uses T = 120 µs, 3 copies
  Blinko.info("boot ok fw=%s", VERSION);
  Blinko.checkpoint("init-sensors");    // reported if a watchdog reset follows
  if (!sensor.begin()) Blinko.fatal(3, "sensor init");   // never returns: blinks the reason
}

void loop() {
  static uint32_t last;
  if (millis() - last >= 5000) {        // a status that changes faster than a phone reads it is never seen
    last = millis();
    Blinko.status("up=%lus rst=%s", millis() / 1000, Blinko.resetCause());
  }
}
```

Zephyr, where the module can also take over the standard logging macros
(`CONFIG_BLINKO_LOG_BACKEND=y`) so existing code needs no change at all:

```c
LOG_WRN("battery low: %d mV", mv);    /* goes out on the LEDs as well */
blinko_status("up=%us", k_uptime_get() / 1000);
k_oops();                             /* the fatal hook blinks the reason forever */
```

## The apps

The iOS and Android apps do the same job: manual exposure at the sensor
minimum, focus at infinity so the LED becomes a large blob, and the shared C
receiver on every frame. They show a live preview with a marker on each light
they are tracking, a console of decoded messages with the level and the source,
and the board identifier each board announces.

Some of what they do is less obvious:

- **Several boards at once.** The frame is segmented, each light gets its own
  receiver, and messages are attributed to the light that sent them. Two LEDs
  of the same board are recognised as one source and joined on screen.
- **Recordings.** A recording captures the frames the receiver sees with
  their timestamps, so a change to the receiver can be measured on real data
  instead of being judged by eye. The same recordings replay inside the app
  and through the Python tools in `core/tools/`. Format and workflow:
  [`docs/RECORDINGS.md`](docs/RECORDINGS.md).
- **Remote session** (Settings › Debug in both apps). The app runs a TCP
  server on port 7777 through which a computer reads live statistics, grabs
  frames, changes settings, records and replays. It listens on the phone's
  localhost by default, which is where a USB forward arrives
  (`make usb-forward` for the iPhone, `make android-forward` for Android); a
  separate setting, *Allow Wi-Fi (LAN) connections*, opens it to the network.
  `ios/tools/rslive.py` is the client for both apps, and it is also importable
  as a library for scripted measurements. Protocol:
  [`docs/REMOTE.md`](docs/REMOTE.md).

## Repository layout

Each component is an independent repository, included here as a submodule.
`core/` is shared by all of them and appears again as a submodule inside each,
so every component can be cloned and built on its own.

| Path | Repository | Contents |
|---|---|---|
| `core/` | [blinko-core](https://github.com/fedepaj/blinko-core) | protocol, transmitter, decoder, assembler, receiver, multi-source tracking, in portable C99, with the simulator, the tests and the replay tools in Python |
| `arduino/` | [blinko-arduino](https://github.com/fedepaj/blinko-arduino) | Arduino library `Blinko` for the Nano R4 and its example sketches |
| `zephyr-module/` | [blinko-zephyr](https://github.com/fedepaj/blinko-zephyr) | Zephyr module, log backend, fatal hook, sample with a USB shell |
| `ios/` | [blinko-ios](https://github.com/fedepaj/blinko-ios) | iPhone app (SwiftUI, AVFoundation) and the remote-session client `tools/rslive.py` |
| `android/` | [blinko-android](https://github.com/fedepaj/blinko-android) | Android app (Kotlin, Camera2, NDK) |
| `unoq/` | [blinko-unoq](https://github.com/fedepaj/blinko-unoq) | receiver kiosk for the Arduino UNO Q with a display and a CSI camera |
| `tools/` | this repository | scripts that drive the boards and the phones from a computer (below) |
| `docs/` | this repository | calibration, remote session, recordings, findings, roadmap |

After changing the core: commit in `core/`, run `make sync-core`, then commit
the submodule pointer (and, in `arduino/`, the refreshed library copy) in each
component. `make sync-core` (`tools/sync_core.sh`) points every component's
`core/` submodule at the root `core/` HEAD. It requires every submodule to be
initialised, refuses a `core/` with uncommitted changes to tracked files (only
commits travel), stops at the first component that cannot be synced, and
copies the transmitter sources into `arduino/libraries/Blinko/src/core/`. It
warns when a component's `core/` has local changes of its own and when the
core commit is not in `origin/main` yet: push `core` before pushing the
component pointers.

## Tools

`make setup` creates `.venv` with what the scripts need: numpy, pillow,
matplotlib and lz4 for the core tools, pyserial for the boards,
pymobiledevice3 for the iPhone's USB forward, west and pyelftools for the
Zephyr build. The scripts in `tools/` find the boards through `ioreg` and
Arduino's `dfu-util`, so they run on macOS only.

| Script | Use |
|---|---|
| `tools/board.py <board> <command>` | send a command to a board's serial shell and print the reply. `<board>` is `r4` (Nano R4 demo sketch), `n33` (Nano 33 BLE Zephyr shell), a `/dev/cu.usbmodem…` port, or, between identical boards, `r4:<usb serial>` (any part of the serial that only one board has). `r4a`/`r4b` (by port order) and `r4@<port suffix>` exist too, but port names swap when a board reboots; the serial does not. `tools/board.py list` prints every port with its board and USB serial |
| `tools/flash_r4.py` | flash one Nano R4 when several are connected: `--board <name as above>` or `--port <port>` touches the board into DFU mode and flashes the DFU device with that board's USB serial; `--serial <usb serial>` flashes a board that is already in DFU mode; `--bin` picks the image (default: the built `BlinkoDemo`). `arduino/build.sh … upload` calls it by itself when it sees more than one Nano R4 and `PORT` is set |
| `tools/bench.py` | live experiments over the remote sessions of the phones: `matrix` (T sweep), `repeat` (T × copies), `exposure` (exposure × T), each sampling the packet yield and recording a clip per cell, and `analyze DIR` (replay of every clip). The phones' ports and the boards' serials are the `PHONES` table at the top of the script. Every setting sent to a board is checked against its reply, and the boards get their T back at the end |
| `tools/sync_core.sh` | `make sync-core`, see above |
| `ios/tools/rslive.py` | remote-session client for both apps (`make live ARGS=…`, `make live-android ARGS=…`) |
| `core/tools/` | simulator, tests, replay of recordings: see [`core/README.md`](core/README.md) |

## Documentation

- [`core/docs/PROTOCOL.md`](core/docs/PROTOCOL.md) — the wire format and the
  receiver pipeline, in enough detail to write another implementation; units
  and limits.
- [`docs/CALIBRATION.md`](docs/CALIBRATION.md) — how to measure a camera's row
  time and choose T for it.
- [`docs/REMOTE.md`](docs/REMOTE.md) — the remote-session protocol of the two
  apps.
- [`docs/RECORDINGS.md`](docs/RECORDINGS.md) — the `.rsrec` recording format,
  how to make recordings and replay them.
- [`docs/FINDINGS.md`](docs/FINDINGS.md) — what the cameras, the LEDs and the
  link do, measured, and what the design does about it. The useful part for
  anyone doing optical links with consumer cameras.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — status and what is open.

## Limits worth knowing

- **Distance.** The defocused LED must cover at least a packet's height in
  the frame: `82 · T / (3 · t_row)` rows, about 320 at the default T on a
  5.1 µs-row sensor, a third of a 1080-row frame. That is a few centimetres
  with a phone's main camera; with a blob shorter than a packet the yield
  collapses, and further away nothing decodes. A shorter T makes the packet
  shorter (down to 45 µs on the Nano R4) at the price of exposure margin;
  sending each packet two or three times (`rep 2`) lets the receiver read a
  packet across two copies when the blob is about one packet tall.
- **Exposure.** The exposure must stay below T, the shortest run of the code.
  A phone that cannot go below about 60 µs needs a longer T on the board
  (90–120 µs).
- **Android.** The phone tested runs its manual-exposure Camera2 sessions at
  30 fps, so it sees only its readout time (6–8 ms) out of every 33 ms; the
  Android app offers RAW capture, which avoids the ISP's highlight
  compression, and packet repetition on the board is what makes a 30 fps
  phone work.
- **Very bright LEDs** saturate the sensor and lose the shortest runs in
  their core; the receiver recovers them from the halo around the blob. Moving
  back a little is the fix; the board can also dim its LEDs (`bright 40`, a
  PWM on the LED pins).
- **Messages** are short: 31 bytes, up to 41 characters of ordinary log text;
  a longer line is split into several. A text identical to the one a slot
  already delivered is not shown again, and a status that changes faster than
  about once a second is not received.
- This is a **one-way, line-of-sight, short-range** link of a few kbit/s. It is
  meant for logs and post-mortems, not for bulk data.

## Licence

MIT, see [LICENSE](LICENSE). Contributions and bug reports are welcome.
