# Status and roadmap

Status of September 2026. The measurements behind most of these decisions are
in [FINDINGS.md](FINDINGS.md); the wire format is in
[../core/docs/PROTOCOL.md](../core/docs/PROTOCOL.md).

## What works today

**Firmware.** An Arduino library for the Renesas RA4M1 boards and a portable
Zephyr module, sharing the same C core and wire format. Both transmit from a
hardware timer (chip length, packet repetition and, on the Arduino boards, the
LED brightness by PWM are run-time settings), and both survive the death of the
application: a hard fault, an
assert, `fatal()` or a watchdog reset ends in a bit-banged loop that blinks the
reason on the red LED with no interrupts and no kernel, and persists it to
flash so the next boot can repeat it. The reason carries the program counter,
the link register, the fault status register and up to three return addresses
found on the stack. The death loop sends at a fixed conservative timing
(T = 120 µs, every packet three times) that every phone tried could read,
whatever the running configuration. On Zephyr the module can also take over
the standard logging macros, so existing firmware needs no change. Each board
announces a 16-bit identifier derived from its factory unique id.

**Receiver** (`core/`, identical on every platform). Blob segmentation, one
receiver per light, per-light profiles with matched column weights, three
decoding modes (luma, pilot-calibrated RGB unmixing, direct three-channel), an
exposure-aware maximum-likelihood packet detector (RLL(2,7) Viterbi with
smeared templates, clock PLL, cyclic decoding of repeated packets and
sync-free backward framing), fountain assembly with leave-one-out recovery,
cross-talk filtering between lights, and grouping of the lights that belong to
one board.

**Apps.** iOS and Android: live preview with a marker per light, console with
persistent history, filtering by source, board identifiers, recording and
in-app replay, a remote session over TCP to drive measurements from a
computer. Android adds RAW sensor capture (needed on phones whose ISP
compresses highlights), processed at one pixel per 4x4 through the same
multi-source path as everything else, and a row time per resolution.

**Tools.** `core/tools/`: a rolling-shutter simulator, a 2-D synthetic scene
generator, the test suite (phone-like conditions, repeated packets), a replay
tool for recordings, a ground-truth loss budget, a line-code bench
(`codelab.py`) and a Python reference of the v3 detector (`v3lab.py`).
`tools/board.py` drives the boards over serial, `tools/flash_r4.py` flashes a
chosen Nano R4 when several are connected, `tools/bench.py` runs live
experiments (chip × repeat × exposure) on both phones at once.

## Next

1. **Android on more devices.** Tested on the S21 FE only; Camera2 behaviour
   around manual exposure and RAW varies a lot between vendors.
2. **Parameters per phone.** T, repetition and brightness are set on the board
   by hand today; the receiver knows the exposure, the row time, the blob
   height and the saturation, so the app can recommend them.
3. **UNO Q kiosk** (`unoq/`): the receiver on a board with a display and a CSI
   camera instead of a phone. Written and verified against recordings, still to
   be brought up on the hardware.
4. **Merging lights that carry the same stream** is done from packet timing;
   the remaining case is two boards transmitting genuinely identical content.

## Things we would like to try

- **Stitching below a third of a packet per frame.** The stitcher works from
  about 40 % of a packet per frame (simulated: 36-chip blobs give 14 packets in
  10 s, 42 chips 40). Below that no frame shows a whole sync, pieces can only be
  chained to each other by correlation (this works, 0.8–0.95 on real frames), but
  the period of the cycle cannot be pinned without an anchor: the correction
  from the chain's wrap overshoots. A second camera clock reference or a longer
  sync would do it. It is the far-light regime and it is hard.
- **Multi-level signalling.** With the LED brightness under PWM control, an ON
  run could carry one more bit in its level where the camera has the dynamic
  range (short exposure, no saturation). The receiver's templates would take
  the level as a hypothesis. Worth trying once the brightness control has been
  used for a while.

## Considered and not done

- **A 16-bit CRC per packet** would cost another 4 bits per packet; CRC-12 with
  a non-zero init plus the assembler's leave-one-out recovery holds the false
  message rate at zero on the corpus and in the simulator.
- **A 16-bit payload per packet** would carry 60 % more data per row at the
  price of taller packets, which costs distance directly. Worth it only if a
  use case appears where the board can always be very close.
- **Scrambled block codes (64b/66b, 8b/10b)** give no run-length guarantee or a
  worse ratio of bits per minimum run than RLL(2,7), and need a long
  synchronous stream where a rolling shutter reads a few milliseconds at a time.
- **PWM dimming inside the chip timing** exists now (`brightness`, a 240 kHz
  carrier on the LED pins, the chips switch the pin between the timer output
  and a dark GPIO). Measured at 1 cm on the iPhone it does not recover
  packets: 40 % brightness halves the clipped area but the halo the receiver
  reads fades first. It is a tool for the intermediate range. Modulating
  information onto the level is not done, see above.
