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
compresses highlights) and a row time per resolution.

**Tools.** `core/tools/`: a rolling-shutter simulator, a 2-D synthetic scene
generator, the test suite (phone-like conditions, repeated packets), a replay
tool for recordings, a ground-truth loss budget, a line-code bench
(`codelab.py`) and a Python reference of the v3 detector (`v3lab.py`).
`tools/board.py` drives the boards over serial, `tools/flash_r4.py` flashes a
chosen Nano R4 when several are connected, `tools/bench.py` runs live
experiments (chip × repeat × exposure) on both phones at once.

## Next

1. **CPU on Android.** The three RAW profiles of a frame are decoded one after
   the other and the phone's governor keeps the big cores slow under that load
   (10–29 fps). One decode thread per channel, or sustained-performance mode.
2. **Parameters per phone.** T and repetition are set on the board by hand
   today; the receiver knows the exposure, the row time and the blob height,
   so the app can recommend them (and the firmware could cycle through a few).
3. **Transmission modes in the library.** Today a board chooses RGB (three
   streams) or mono (one stream on every LED). Planned as further selectable
   modes, not replacements: **multi-level (PWM) signalling** for more bits per
   run where the camera has the dynamic range, and **stroboscopic stitching**,
   where the transmitter's packet period is chosen against the camera's frame
   period so that successive frames read successive parts of a long packet.
4. **Android on more devices.** Tested on the S21 FE only; Camera2 behaviour
   around manual exposure and RAW varies a lot between vendors.
5. **UNO Q kiosk** (`unoq/`): the receiver on a board with a display and a CSI
   camera instead of a phone. Written and verified against recordings, still to
   be brought up on the hardware.
6. **Merging lights that carry the same stream** is done from packet timing;
   the remaining case is two boards transmitting genuinely identical content.

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
