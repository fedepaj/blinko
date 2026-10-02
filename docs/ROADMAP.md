# Status and roadmap

Status of October 2026. The measurements behind most of these decisions are
in [FINDINGS.md](FINDINGS.md); the wire format is in
[../core/docs/PROTOCOL.md](../core/docs/PROTOCOL.md).

## What works today

**Firmware.** An Arduino library for the Nano R4 (Renesas RA4M1) and a
portable Zephyr module, sharing the same C core and wire format. Both transmit
from a hardware timer; T and the packet repetition are run-time settings, and
so is the LED brightness on the Arduino library: a 240 kHz PWM on the LED
pins, gated by the chips. Both survive the death of the
application: a hard fault, an assert, `fatal()` or a watchdog reset ends in a
bit-banged loop that blinks the reason on the red LED with no interrupts and
no kernel, and persists it to flash so that every following boot repeats it
until the firmware clears it. The reason carries the program counter and the
link register (and the fault status register on the Arduino library); up to
three return addresses found on the stack follow it as a log line. The death
loop sends at a fixed conservative timing (T = 120 µs, every packet three
times), whatever the running configuration. On Zephyr the module can also take
over the standard logging macros, so existing firmware needs no change. Each
board announces a 16-bit identifier derived from its factory unique id.

**Receiver** (`core/`, identical on every platform). Blob segmentation, one
receiver per light, per-light profiles with matched column weights, three
decoding modes (luma, pilot-calibrated RGB unmixing, direct three-channel), an
exposure-aware maximum-likelihood packet detector (RLL(2,7) Viterbi with
smeared templates, clock PLL, cyclic decoding of repeated packets and
sync-free backward framing), fountain assembly guarded by two message CRCs
with leave-one-out recovery, cross-talk filtering between lights, and grouping
of the lights that belong to one board.

**Apps.** iOS and Android: live preview with a marker per light, console with
persistent history, filtering by source, board identifiers, recording and
in-app replay, a remote session over TCP to drive measurements from a
computer ([REMOTE.md](REMOTE.md), [RECORDINGS.md](RECORDINGS.md)). Android
adds RAW sensor capture (needed on phones whose ISP compresses highlights),
reduced 4×4 and decoded through the same multi-source path as everything
else, and a row time per capture mode.

**Tools.** `core/tools/`: a rolling-shutter simulator, a 2-D synthetic scene
generator, the test suite (phone-like conditions, repeated packets, the
transmitter and the assembler), a replay tool for recordings, a ground-truth
loss budget and two lab scripts (`codelab.py`, `v3lab.py`). `tools/board.py`
drives the boards over serial, `tools/flash_r4.py` flashes a chosen Nano R4
when several are connected, `tools/bench.py` runs live experiments (T ×
repetition × exposure) on both phones at once.

## Open

1. **A message generation number on the wire.** The packets do not say which
   version of a slot's text they belong to. A text identical to the one a slot
   already delivered is not delivered again, and a slot replaced faster than a
   receiver collects it is never seen (the two message CRCs keep mixtures of
   two texts out, they do not make the newer text arrive). A few bits of
   generation in the META would settle both; it is a protocol change.
2. **The chip interrupt's cost on the RA4M1.** It takes about 12 µs, which
   limits T to 45 µs and takes most of the CPU (about 60 % at T = 60 µs, 80 %
   at 45).
3. **The Zephyr port encodes packets inside its timer callback.** It does so
   right after a packet starts, so the delay falls in the packet's dark gap,
   but ticks are still lost there; the Arduino library does it in a
   lower-priority interrupt and loses none. The module as it stands is built
   for the Nano 33 BLE but has not been run on a board: its transmitter path,
   start-up and fault path need a pass on hardware.
4. **Stitching for lights smaller than a packet** is experimental and off by
   default: it works on the simulator from about 40 % of a packet per frame
   and has not decoded a packet on a phone.
5. **Segmentation rejects dim clean lights.** Its thresholds are absolute (a
   range of 20 counts, a peak of 48), so a light with sharp stripes and a low
   peak, a RAW capture at low ISO or a dimmed LED, is not seen at all.
6. **Android is tested on one phone** (Samsung S21 FE); Camera2 behaviour
   around manual exposure and RAW varies a lot between vendors.
7. **UNO R4 boards.** The Arduino library builds for the Nano R4 only: the
   UNO R4 variants do not define the LED pins it uses by default.
8. **UNO Q kiosk** (`unoq/`): the receiver on a board with a display and a CSI
   camera instead of a phone. Verified against recordings, untested on the
   hardware.
9. **Two boards in one frame.** There is no recording yet of two boards in
   one frame close enough to decode both, so the cross-talk filter and the
   same-board grouping are not covered by the recorded measurements.
10. **Parameters per phone.** T, repetition and brightness are set on the
    board by hand; the receiver knows the exposure, the row time, the blob
    height and the saturation, so the app could recommend them.

## Things we would like to try

- **Stitching below a third of a packet per frame.** Below about 40 % of a
  packet no frame shows a whole sync. Pieces can be chained to each other by
  correlation, but the period of the cycle cannot be pinned without an anchor.
  A second camera clock reference or a longer sync would do it. It is the
  far-light regime and it is hard.
- **Multi-level signalling.** With the LED brightness under PWM control, an ON
  run could carry one more bit in its level where the camera has the dynamic
  range (short exposure, no saturation). The receiver's templates would take
  the level as a hypothesis.
- **Dimming measured.** How much the PWM brightness recovers when the LED
  saturates the sensor, per distance, has not been measured with all three
  dies dimmed.

## Considered and not done

- **A 16-bit CRC per packet** would cost another 4 bits per packet; CRC-12 with
  a non-zero init plus the message CRCs and the assembler's leave-one-out
  recovery deliver no wrong message on the recordings and in the simulator.
- **A 16-bit payload per packet** would carry 60 % more data per row at the
  price of taller packets, which costs distance directly. Worth it only if a
  use case appears where the board can always be very close.
- **Scrambled block codes (64b/66b, 8b/10b)** give no run-length guarantee or a
  worse ratio of bits per minimum run than RLL(2,7), and need a long
  synchronous stream where a rolling shutter reads a few milliseconds at a time.
- **Modulating information onto the LED level** inside the chip timing: see
  multi-level signalling above.
