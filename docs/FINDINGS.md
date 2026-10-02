# Findings

What the cameras, the LEDs and the link do, with the numbers, and what the
design does about each. Most of it applies to any optical link that uses a
consumer camera as the receiver.

Measurements come from an iPhone 14 and a Samsung S21 FE (back wide cameras),
an Arduino Nano R4 (Renesas RA4M1) and an Arduino Nano 33 BLE (nRF52840), and
from recorded sessions replayed through the same C receiver the apps use.
Where recorded packets are counted as true or wrong, they are checked against
the texts the boards were sending. Units (T, chip, rows) are defined in
`core/docs/PROTOCOL.md`.

## The camera

| Quantity | iPhone 14 |
|---|---|
| Row time `t_row` | 5.1 µs |
| Shortest exposure | 19 µs at 60 fps, 15 µs at 120 fps |
| Frame readout | about 5.5 ms of the 16.7 ms frame period at 60 fps |
| Scan axis | rows of the native sensor buffer |

**The readout covers only part of the frame period**: a third at 60 fps.
Between two readouts there is a gap of several milliseconds, several packets
long, in which everything transmitted is lost, and nothing in the receiver can
recover it. So packets are short, self-contained and fountain-coded instead of
being part of a stream.

**A packet must fit in the blob.** At T = 60 µs a chip is about 4 rows and an
82-chip packet (1.64 ms) about 320 rows: the defocused LED must cover at least
that many rows of the frame. This is the real limit on distance, not
brightness. At 30 cm the blob is around 60 rows and nothing decodes, whatever
the exposure. With the phone moved back until the blob is about 270 rows (0.8
packets) a 1.5 s recording holds a few tens of distinct packets, against about
700 with the board a few centimetres away. So the board can send each packet
twice or three times, and the receiver reads a packet across two copies.

**Exposure is a box filter.** A row integrates the LED over the exposure E, so
a step becomes a ramp E rows long and a run of length T keeps
`sinc(πE/2T)` of its amplitude: 64 % at E = T, 30 % at 1.5 T, nothing at 2 T.
The receiver fits templates that model the smear instead of thresholding the
profile, and drops what it would have to fit with an exposure over 3 chips
(E = T), where no run reaches full amplitude and the templates go flat. Phones
whose shortest exposure is long (57 µs on the Samsung S21 FE) therefore need
T ≥ 90 µs.

**Throughput.** With a Nano R4 a few centimetres from the lens, three streams
at T = 60 µs and one copy per packet, the iPhone at 120 fps decodes about 470
distinct packets per second (702 in a 1.5 s recording). At T = 45 µs it
decodes about 240.

## A second camera: the Samsung S21 FE

The Samsung (Camera2, Android 16) differs from the iPhone in every number
that matters.

| Quantity | iPhone 14 | Samsung S21 FE |
|---|---|---|
| shortest exposure | 15 µs | 57.5 µs |
| frame rate with manual exposure | 120 fps | 30 fps (the high-speed sessions refuse manual exposure) |
| readout per frame | 5.5 ms of 8.3 | 6–8 ms of 33 |
| row time | 5.1 µs | 5.44 µs at 1080p, 3.22 at 4K, 2.65 in RAW 4000×3000 |
| time the LED blob covers | about 2.8 ms | 1.3–1.9 ms at a few cm, 4.5 ms at 1 cm |

What follows from each:

- **Exposure 57.5 µs** is almost the whole of T at the default 60 µs, and
  nothing decodes; with T = 90–120 µs it is 0.5–0.65 T and decodes. The camera
  also reports less than it does: with 57.5 µs set, the edges in the data are
  76–100 µs long. When the reported exposure gives no valid packet the
  detector tries 1.4× and 2× of it.
- **A packet longer than the blob.** At T = 90–120 µs a packet lasts
  2.5–3.3 ms against a 1.3–1.9 ms window at a few centimetres: it never fits
  whole. Packet repetition on the board, with the receiver's cyclic decoding
  (the tail of a cut packet read from its previous copy) and backward decoding
  (the packet before a sync), is what makes the phone work; T alone does not.
  Without the cyclic decoding the recordings of this phone lose 30 % of their
  packets and deliver one message instead of seven.
- **The ISP hides saturation.** In YUV the luma tops out around 238 with
  highlights compressed, so clipped stripes look like modulation with the dark
  runs gone. RAW capture (`RAW_SENSOR`, black 64, white 1023) shows the
  clipping, and the receiver can then give the clipped columns no weight and
  read the halo.
- **Gr and Gb pixels differ in sensitivity** under a narrow-band LED: a green
  profile taken row by row has a period-2 zigzag. The strobe calibration takes
  green from the Gr rows only; the image the receiver decodes averages Gr and
  Gb inside each block.
- **The strobe calibration can be off by 7 %** on this sensor (2.83 against
  2.65 µs per row in RAW); the clock the decoded packets report is the truth,
  and it is what the exposure in rows should be derived from.
- **CPU.** The governor keeps the phone's big cores at 0.7–0.85 GHz under this
  bursty load, and the frame rate swings. The signal needs no more than about
  4 rows per chip, so the app reduces the RAW mosaic to one row per four
  sensor rows before the receiver (3.3 rows per chip at T = 105 µs) and asks
  the system for sustained-performance mode.

With T = 105 µs and three copies of every packet the phone decodes about 23
distinct packets per second in RAW capture (70 in a 3 s recording).

## Bright LEDs destroy their own signal, and the halo saves it

A LED close to the lens saturates the sensor. Once a row clips, the exposure
smear spreads the ON state into the following chips and the short OFF runs
shrink or disappear: in one recording of a saturating fault LED the ON runs
measure 36 to 94 rows against 6 for the OFF runs, which is information that
no threshold can recover.

The remedy is spatial, not temporal. The clipped core of the blob loses the
dark runs, but the **halo around it does not**: it is dimmer, it does not
clip, and it carries the same modulation. The receiver therefore weights each
column of the blob by the energy of its row-to-row differences, which is high
exactly where the stripes are and low in a flat clipped core, in the dark
surround and in noise-only columns. Steps into and out of clipping are excluded
from that energy so a clipping edge is not mistaken for a stripe. The
close-range iPhone recordings behind the figures in this document have
33–46 % of their rows clipping.

Whether the clipped columns should be dropped outright depends on the light: a
pulsed red fault LED saturates its core for long stretches, a colour LED clips
only briefly on white rows. No fixed rule works for both, so when something in
the blob clips the receiver builds both variants of the profile and keeps the
one the decoder turns into more packets in that frame, checking again every
few frames. When nothing clips the two variants are the same profile and the
comparison is skipped: made anyway, it costs a tenth of the receiver's time
over the recordings of both phones, and a third on the Samsung's.

The opposite case is not handled: a dim, clean light is rejected by the
segmentation, which asks for absolute levels (a range of 20 counts in the
frame, a blob peak of 48). On the Samsung in RAW a dimmed LED gives sharp
stripes with a peak of 15 of 255, and the frame comes out empty.

## A colour LED is three LEDs in different places

The RGB LED of a Nano R4, seen defocused from a few centimetres, is not one
coloured disc: it is three discs, one per die, offset by about 40 % of their
diameter. The offset comes from the die pitch and the lens aperture, so it does
not shrink with distance.

When the pitch runs along the scan axis, the top rows of the blob see mostly
one die and the bottom rows another. The colour-calibration pilot block, which
lights the three dies in turn and expects one stretch of rows to see all
three, then may never lock: on one recording 15 pilot blocks are visible in
the frames and not one can be recognised.

The design answers in three ways. The pilot block is short (9 × 4 chips, about
140 rows at T = 60 µs on a 5.1 µs-row sensor) so that it fits inside the blob,
and frequent (every 30 ms on average). Its cadence is jittered: a block starts
at a packet boundary, so a fixed cadence is a whole number of packets, and
that can sit within 2 % of a phone's frame period (32.8 ms at T = 105 µs
against 33.3 ms at 30 fps); the block then drifts a few rows per frame and
spends tens of consecutive frames outside the blob. And when all three camera
channels are modulated but no calibration is valid, the receiver decodes the
camera's own R, G and B channels as the three streams: the cross-talk between
LED primaries and camera filters is moderate, and the packet CRC rejects what
it corrupts.

## Light from one board lands on the other

With two boards in the frame, the stripes of a bright LED spread across the
**whole width** of the frame, not just its blob: lens flare plus row gain. A
track whose own light happens to be dark for a moment therefore decodes its
neighbour's packets inside its own rows, and attributes them to the wrong
board.

This is worse than losing a packet. A foreign packet that passes the packet CRC
enters the fountain system of the wrong slot and poisons it until the slot is
reset. The receiver drops those copies before assembly, by independent
signals: the same packet decoded at the same row by two tracks belongs to the
track whose blob owns that row; a packet in rows that belong to another
light's blob is that light's; and a packet far dimmer than a neighbour's
typical amplitude, whose timing fits that neighbour's carousel, is that
neighbour's leak.

## Two lights of one board can be recognised from the packets alone

The packets of one carousel obey a relation: the seed difference of two packets
of the same slot equals their distance in packets (rows within a frame plus the
time between frames) times the number of channels, plus the channel difference,
modulo the control triplets. Two tracks whose packets satisfy that relation are
two lights of the same board, whether they overlap in the frame or sit far
apart. Over four seconds of a two-board recording the evidence for the correct
pair grows steadily while the evidence between the two different boards stays
negative, so the apps can group the lights of a board and attribute every
message to one logical source. The distance between packets of different
frames needs the sensor's row time; without it only packets of the same frame
are compared.

## Chip timing on a small microcontroller

**The fault loop has to be timed by deadline, not by delay.** A loop that
writes a chip and then calls a microsecond delay adds the work per chip to the
period: a 30 µs chip comes out at 84 µs on the Nano R4 and at about 40 µs on
the Nano 33 BLE, packets up to almost three times taller than intended, and
nothing decodes from a board that is in fact transmitting correctly. The death
loops therefore read a free-running counter and wait until the next multiple,
so the per-chip work is absorbed instead of added. The Nano R4 uses the DWT
cycle counter, the Zephyr port polls its `counter` device as a clock, and
neither needs interrupts, which is the point of the exercise.

**Encoding packets inside the chip interrupt stretches every packet.**
Choosing and encoding the next three packets takes about 120 µs on the RA4M1,
six chip periods at T = 60 µs. Done inside the chip interrupt at the packet
boundary, it loses 8 % of the chip interrupts and makes every packet 89 chips
long instead of 82. The next packets are therefore encoded outside it, in a
context the chip interrupt preempts (PendSV in the Arduino library), into a
second buffer that the chip path swaps in at the boundary. For the same reason
the chip interrupt writes the pins first, with the chips computed in the
previous tick, and only then computes the next ones: the time from the timer
to the LEDs is constant. Packing a new message's text also takes several chip
periods, so it is done with the interrupt running and only a short copy is
masked.

**The chip interrupt itself costs about 12 µs** on the RA4M1. The board keeps
its tick rate and answers on serial down to T = 39 µs and stops answering at
36; the library's floor is T = 45 µs, where the interrupt takes about 80 % of
the CPU (about 60 % at T = 60 µs).

**Dimming by PWM needs each LED pin's timer output.** The lit level is a
240 kHz PWM on the LED pin (a 15 µs exposure sees 3–4 periods; at 1 MHz the
timer has too few counts and the LED stays dark), and the chips switch the pin
between the timer output and a dark GPIO, one register write per chip. On the
Nano R4 the LED pins sit on GPT channels: red 5A, green 6B, blue 6A, builtin
4B. Green and blue are the two outputs of one timer, and two pins on one timer
channel must share one timer object: a second, separate PWM object on that
channel leaves it misconfigured and both LEDs dark, which shows as a board
that sends on red only (camera peaks R 255, G 36, B 49: two streams of three
gone, and the pilots unrecognisable). The chip timer, in turn, has to run on
a channel none of the LED pins uses.

## Fault airtime is a design choice

While the board is dead the carousel still rotates through the fault, the
status and the last log messages. Giving the fault slot more visits shortens
the time to read the crash reason: at weight 3 it takes about three quarters
of the packets (74–79 % with a STATUS and 0–6 log lines), and the reason
arrives one to two seconds after the fault (1.3 to 1.5 s on the iPhone,
measured from the serial command that provokes it to the message on the
phone). The last log lines still follow a few seconds later, which is usually
the context you want.

## Receiver lessons

- **A per-packet CRC is not enough on its own.** The packet CRC is 12 bits
  with a non-zero init: a receiver that tries many hypotheses per frame makes
  about one completed trial in 4096 a false accept, and the init guarantees
  that an all-dark or all-bright stretch (a blob edge) never decodes to a valid
  packet. On 23 recorded clips of the two phones, 8 of the 5358 packets the
  detector returns are wrong. A corrupted packet that passes its CRC poisons a
  fountain system for good, so the assembler keeps the raw rows and, when the
  message CRCs fail, re-solves leaving one row out at a time until the message
  checks out. On those clips 44 messages are delivered and none is wrong; in
  the test suite, with 2 % of the packets corrupted on purpose, no wrong
  message is delivered either.
- **Both message CRCs are required, except in the FAULT slot.** A slot whose
  text the board replaces while it is being received (a STATUS with a counter)
  ends up holding rows of two texts. The system solves to garbage, and against
  one CRC-8 garbage passes once in 256: with one CRC enough, a board updating
  its status about once a second shows a text it never sent in 0.05–0.8 % of
  the deliveries, with no channel error at all. Two CRCs make that 2⁻¹⁶, and
  cost little: on the 23 clips the same messages arrive 4 frames later on
  average (63 against 59). The leave-one-out recovery in turn accepts a
  solution only if all the other rows agree with it, because rows of two texts
  contradict each other whichever one is left out, and the CRCs alone would
  let about one such mixture in a thousand through (up to 56 trials at 2⁻¹⁶
  each). The FAULT slot delivers with one CRC: its text does not change, and a
  pulsed fault LED shows so few control packets in a short window that waiting
  for both often means no message.
- **A quality threshold does not separate false accepts on real data.** True
  packets from a saturated or a distant light fit their templates badly too:
  on the saturated iPhone 5–11 % of the true packets score between 0.5 and
  0.6, and with the phone moved back a threshold of 0.5 costs 6 % of the true
  packets and 0.6 costs 23 %, while wrong packets score up to 0.71. The
  threshold stays at 0.4 and the message CRCs do the separating.
- **An early abort tight enough to save time costs packets.** The first
  codewords of a packet fit worse than the rest while the detector's clock PLL
  is still converging. An abort limit tied to the quality threshold (a mean
  squared error of 0.075) throws away about one true packet in six; no abort
  at all costs 49 % more time. The limit is therefore a cost limit of its own,
  0.15, which keeps almost all of those packets for 21 % more time.
- **The same packet comes several times per frame.** Packets a board repeats,
  and the three channels of an RGB LED carrying one stream, give the same
  packet more than once in a frame: 32 % of what the detector returns with two
  copies, 42 % with three, 58 % with one stream on the three dies. A copy
  carries no information, and counting it inflates the rate (400 packets per
  second shown with two copies against 146 with one), so the receiver counts
  each (slot, seed, payload) once per frame and every rate is of distinct
  packets.
- **The clock comes from the sync's two edges, not from a correlation.** Two
  0.5-crossings 10 chips apart give the chip length to about 1 % even with
  smeared edges; a template correlation on a clock grid is several percent off,
  and at 15 rows per chip a few percent is more than a ±1-row timing slip per
  codeword can absorb. The detector therefore measures the ON run first and
  lets a small clock PLL in the Viterbi take the rest.
- **What is lost is packets cut by the blob, and framing recovers them.** A
  loss budget against ground truth shows that in clean conditions the decoder
  gets every packet that fits in the blob; what it misses are packets cut by
  the blob's edges. So the receiver reads the packet *before* each sync (its
  data field ends at the gap, the sync gives it clock and phase) and, with
  repeated packets, the tail of a cut packet from its previous copy. How much
  each gives depends on the geometry: with a blob taller than a packet the
  backward decode adds 1 % of the packets, with a blob of 0.8 packets 6 %. The
  cyclic decode gives nothing on a stream that does not repeat while costing a
  third of the decoder's time there, so it runs only where the signal one
  period earlier matches.
- **A flexible detector invents aliases.** With per-codeword timing slips the
  Viterbi can fit the stream at 2/3 of its clock (runs rounded alternately up
  and down), and that alias can pass the CRC — always the same packet, so it
  recurs. The cures are structural, not statistical: a candidate must have a
  10-chip ON run with two edges, modulated signal within 5 chips before its
  gap (the filler guarantees it), an exposure under 3 chips, and a decoded
  packet must re-fit on a rigid grid.
- **Frame times must be small numbers.** The receiver takes time as a float.
  Seconds since boot resolve 8 ms after 18 hours of uptime and 30 ms after
  three days, coarser than a frame, and everything that compares times across
  frames is lost; the apps count from the first frame.

## Tooling lessons

- **Record, then replay.** Judging a receiver change by watching the live
  counters is hopeless: the numbers move with how you hold the phone. Recording
  the frames with their timestamps and replaying them through the same C code
  turns every change into a measurement. The numbers in this document come
  from that loop.
- **Compression is not worth it.** LZ4 on camera frames gains about 1.4 × at
  roughly 15 ms per frame, which limits a recorder to 45 fps and makes
  recordings unrepresentative of live behaviour. Writing raw frames from a
  background queue records at the full 119 fps with no dropped frames.
- **Watch the thermal state.** After ten minutes to an hour of 120 fps capture
  the iPhone reaches a "serious" thermal state and the frame rate drifts
  between 85 and 110 fps. Comparing a measurement taken then with one taken on
  a cold phone is meaningless, so the iOS app reports the thermal state with
  its remote statistics.
