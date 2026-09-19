# Findings

What was actually measured while building Blinko, with the numbers. Most of it
was surprising enough to change the design, and most of it applies to any
optical link that uses a consumer camera as the receiver.

Measurements come from an iPhone 14 (back wide camera), an Arduino Nano R4
(Renesas RA4M1) and an Arduino Nano 33 BLE (nRF52840), and from a corpus of
recorded sessions replayed through the same C receiver the apps use.

## The camera

| Quantity | Measured |
|---|---|
| Row time `t_row` | 5.1 µs |
| Shortest exposure | 19 µs at 60 fps, 15 µs at 120 fps |
| Frame readout | ≈ 5.5 ms of the 16.7 ms frame period at 60 fps |
| Scan axis | rows of the native sensor buffer |

Two consequences. First, the readout covers only a third of a 60 fps frame
period: between two readouts there is a gap of several milliseconds, about 90
chips, in which everything transmitted is lost. Nothing in the receiver can
recover it, which is why packets are short, self-contained and repeated rather
than being part of a stream. Second, a chip of 30 µs is about 6 rows, and a
67-chip packet about 400 rows: the defocused LED must cover at least that many
rows of the frame or no packet ever fits in one frame. This is the real limit
on distance, not brightness. At 30 cm the blob is around 60 rows and nothing
decodes, whatever the exposure.

**Exposure must be shorter than a chip.** The row integrates over the exposure
window, so an exposure of one chip halves the contrast of the stripes and an
exposure of two erases them. Phones that cannot go below 30 µs need a longer
chip on the board.

## Bright LEDs destroy their own signal, and the halo saves it

A LED close to the lens saturates the sensor. Once a row clips, the exposure
smear spreads the ON state into the following chip and the one-chip OFF gaps
disappear: in one fault recording the ON runs measured 36 to 94 rows against 6
for the OFF runs, which is information that no threshold can recover.

The fix turned out to be spatial rather than temporal. The clipped core of the
blob loses the gaps, but the **halo around it does not**: it is dimmer, it does
not clip, and it carries the same modulation. The receiver therefore weights
each column of the blob by the energy of its row-to-row differences, which is
high exactly where the stripes are and low in a flat clipped core, in the dark
surround and in noise-only columns. Steps into and out of clipping are excluded
from that energy so a clipping edge is not mistaken for a stripe.

Measured on the corpus, the single-ROI path went from 132 to 315 packets; a
saturated fault recording went from 3.5 to about 20 packets per second.

Whether the clipped columns should be dropped outright depends on the light: a
pulsed red fault LED saturates its core for long stretches, a colour LED clips
only briefly on white rows. No fixed rule worked for both, so the receiver
builds both variants of the profile and keeps the one the decoder turns into
more packets in that frame, re-checking every few frames.

## A colour LED is three LEDs in different places

The RGB LED of a Nano R4, seen defocused from a few centimetres, is not one
coloured disc: it is three discs, one per die, offset by about 40 % of their
diameter. The offset comes from the die pitch and the lens aperture, so it does
not shrink with distance.

When the pitch runs along the scan axis, the top rows of the blob see mostly
one die and the bottom rows another. The colour-calibration pilot block, which
lights the three dies in turn and expects one row to see all three, then never
locks: on one recording 15 pilot blocks were visible in the frames and not one
was recognised.

Two fixes. The pilot block was too tall in the first place (9 × 8 chips is 432
rows, more than the blob), so it is now 9 × 4 chips and is sent every 30 ms
instead of every 100. And when all three camera channels are modulated but no
calibration is valid, the receiver simply decodes the camera's own R, G and B
channels as the three streams: the crosstalk between LED primaries and camera
filters is moderate, and the packet CRC rejects what it corrupts. Corpus:
438 → 814 packets, with recordings that decoded nothing before reaching 8 to
50 packets per second.

## Light from one board lands on the other

With two boards in the frame, the stripes of a bright LED spread across the
**whole width** of the frame, not just its blob: lens flare plus row gain. A
track whose own light happens to be dark for a moment therefore decodes its
neighbour's packets inside its own rows, and attributes them to the wrong
board.

This is worse than losing a packet. A foreign packet that passes the packet CRC
enters the fountain system of the wrong slot and poisons it until the slot is
reset. The receiver now drops those copies before assembly, by two independent
signals: the same packet decoded at the same row by two tracks belongs to the
track whose blob owns that row, and a packet far dimmer than a neighbour's
typical amplitude, whose timing fits that neighbour's carousel, is that
neighbour's leak.

## Two lights of one board can be recognised from the packets alone

The packets of one carousel obey a relation: the seed difference of two packets
of the same slot equals their distance in packets (rows within a frame plus the
time between frames) times the number of channels, plus the channel difference,
modulo the control triplets. Two tracks whose packets satisfy that relation are
two lights of the same board, whether they overlap in the frame or sit far
apart. Over four seconds of a two-board recording the evidence for the correct
pair grew steadily while the evidence between the two different boards stayed
negative, so the apps can group the lights of a board and attribute every
message to one logical source.

## The fault loop has to be timed by deadline, not by delay

The first death loop wrote a chip, then called a microsecond delay. The work
per chip is not free, so a 30 µs chip became 84 µs on the Nano R4 and about
40 µs on the Nano 33: packets almost three times taller than the blob, and
nothing decoded from a board that was in fact transmitting correctly.

Timing by deadline fixes it: read a free-running counter and wait until the
next multiple, so the per-chip work is absorbed instead of added. The Nano R4
uses the DWT cycle counter, the Zephyr port polls its `counter` device as a
clock, and both needed no interrupts, which is the point of the exercise.
Verified live at 6.0 rows per chip on both boards.

## Fault airtime is a design choice

While the board is dead the carousel still rotates through the fault, the
status and the last log messages. Giving the fault slot more visits shortens
the time to read the crash reason: at weight 3 it takes about 85 % of the
packets, and the reason arrives **1.3 to 1.5 s after the fault**, measured from
the serial command that provokes it to the message on the phone. The last log
lines still follow a few seconds later, which is usually the context you want.

## Small receiver lessons

- **A CRC-8 per packet is not enough on its own.** One corrupted sync in 256
  passes the packet CRC, and a single bad row poisons a fountain system for
  good. The assembler keeps the raw rows and, when the message CRC fails,
  re-solves leaving one row out at a time until the message checks out. In a
  corruption test that recovered 55 messages and took slot resets from 488 down
  to 97, with no wrong message delivered.
- **Do not require both message CRCs to deliver.** A directly solved system is
  safe with one of them; requiring both meant that a pulsed fault LED, which
  rarely shows every control packet in a short window, often never delivered.
  Both are still required for the leave-one-out recovery, where many trials
  would make a single CRC-8 unsafe. Messages assembled from the corpus went
  from 11 to 19, all of them correct.
- **Knowing the timing helps less than expected.** The 8-chip sync fixes the
  chip length to about 2 %, which is 1.4 chips of drift by the end of a packet,
  so retrying a failed packet with the receiver's own chip clock and with the
  sync estimate stretched by ±3 % is worth a lot: corpus 814 → 1601 packets.
  Going further and decoding at predicted positions without a sync at all
  bought only another 1.5 %. A loss budget against ground truth in the
  simulator explains why: in clean conditions the decoder already gets 100 % of
  the packets that fit in the frame, and phase prediction only pays where
  saturation has destroyed the sync while leaving the bits alive. What is lost
  in practice is packets cut by the edge of the frame and packets whose bits
  are genuinely damaged, and neither is recoverable by better timing.

## Tooling lessons

- **Record, then replay.** Judging a receiver change by watching the live
  counters is hopeless: the numbers move with how you hold the phone. Recording
  raw frames with their timestamps and replaying them through the same C code
  turned every change into a measurement. Every number in this document comes
  from that loop.
- **Compression was not worth it.** LZ4 on camera frames gains about 1.4 × at
  roughly 15 ms per frame, which limited the recorder to 45 fps and made
  recordings unrepresentative of live behaviour. Writing raw frames from a
  background queue records at the full 119 fps with no dropped frames.
- **Watch the thermal state.** After an hour of 120 fps capture the phone
  reaches a "serious" thermal state and the frame rate drifts between 85 and
  110 fps. Comparing a measurement taken then with one taken on a cold phone is
  meaningless, so the apps report the thermal state with the statistics.
