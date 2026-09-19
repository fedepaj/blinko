# Status and roadmap

Status of September 2026. The measurements behind most of these decisions are
in [FINDINGS.md](FINDINGS.md); the wire format is in
[../core/docs/PROTOCOL.md](../core/docs/PROTOCOL.md).

## What works today

**Firmware.** An Arduino library for the Renesas RA4M1 boards and a portable
Zephyr module, sharing the same C core and wire format. Both transmit from a
hardware timer, and both survive the death of the application: a hard fault, an
assert, `fatal()` or a watchdog reset ends in a bit-banged loop that blinks the
reason on the red LED with no interrupts and no kernel, and persists it to
flash so the next boot can repeat it. The reason carries the program counter,
the link register, the fault status register and up to three return addresses
found on the stack. On Zephyr the module can also take over the standard
logging macros, so existing firmware needs no change. Each board announces a
16-bit identifier derived from its factory unique id.

**Receiver** (`core/`, identical on every platform). Blob segmentation, one
receiver per light, per-light profiles with matched column weights, three
decoding modes (luma, pilot-calibrated RGB unmixing, direct three-channel),
timing hypotheses and grid decoding in the packet decoder, fountain assembly
with leave-one-out recovery, cross-talk filtering between lights, and grouping
of the lights that belong to one board.

**Apps.** iOS and Android: live preview with a marker per light, console with
persistent history, filtering by source, board identifiers, recording and
in-app replay. The iOS app also exposes a remote session over TCP, used to
drive measurements from a computer.

**Tools** (`core/tools/`). A rolling-shutter simulator, a 2-D synthetic scene
generator, the test suite, a replay tool for recordings and a ground-truth loss
budget. `tools/board.py` drives both boards over serial.

## Next

1. **Android on more devices.** The app is tested on one phone; Camera2
   behaviour around manual exposure varies a lot between vendors.
2. **UNO Q kiosk** (`unoq/`): the receiver on a board with a display and a CSI
   camera instead of a phone. Written and verified against recordings, still to
   be brought up on the hardware: camera format, achievable exposure, CPU cost
   and the display.
3. **Merging lights that carry the same stream** is done from packet timing;
   the remaining case is two boards transmitting genuinely identical content.
4. **Distance.** The only real lever is a shorter chip, which needs a shorter
   exposure than most phones allow, or wide-angle optics. Worth measuring on a
   few more phones before changing anything.

## Considered and not done

- **A 16-bit CRC per packet** would cost 12 % of the throughput to protect
  against a failure mode that the assembler's leave-one-out recovery already
  handles at no cost on the wire.
- **A 16-bit payload per packet** would carry 60 % more data per row at the
  price of packets 24 % taller, which costs distance directly. Worth it only if
  a use case appears where the board can always be very close.
- **Dropping Manchester coding** (4B5B would shorten a packet by about 40 %)
  would take away what makes the decoder self-calibrating and tolerant to
  exposure smear.
- **PWM dimming** of bright LEDs, to avoid saturating the sensor, needs a
  carrier above 500 kHz so that the exposure does not see it, and the LED pins
  of the target boards are not all on suitable timer channels. The receiver now
  handles saturation well enough that this is not urgent.
- **An edge-based decoder** for saturated signals was implemented and measured
  worse than the classic path, including a failure mode where it produced
  all-zero packets that passed the CRC. It is still in the code, disabled
  (`use_edges = 0`).
