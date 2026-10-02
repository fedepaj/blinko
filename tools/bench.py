#!/usr/bin/env python3
"""Live protocol bench: drives the boards (chip length) and the phones (remote sessions), samples
packet yields and records .rsrec clips for offline analysis, in a fixed order.

  bench.py matrix   [--chips 30,45,60,75,90] [--seconds 10] [--rec 2]      both phones, chip sweep
  bench.py exposure [--chips 30,45,60] [--exposures 15,30,45,57] [--phone iphone]   exposure x chip
  bench.py analyze DIR                   replay (single / multi-source receiver) on every clip
  bench.py repeat   [--chips 60,90,120] [--reps 1,2] [--rgb 3] [--phones iphone,samsung]   chip x repetition

Setup (tools/board.py names, remote ports): see PHONES below. Results go to DIR/results.md.
Every setting sent to a board is checked against its reply: a cell whose board did not confirm
is marked and not measured. When a run ends the boards get back the chip length they had.
"""
import argparse, json, math, os, re, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ios", "tools")); sys.path.insert(0, HERE)
from rslive import RSLive
import board as boardtool

PHONES = {
    "iphone":  dict(port=7777, board="r4:360B17"),     # boards by USB serial: port names swap when a board reboots
    "samsung": dict(port=7778, board="r4:360D19"),
}
# What the demo sketch (BlinkoDemo.ino) answers to a setting. `chip` reports the value in force;
# `rep` and `rgb` only echo what they were asked.
CONFIRM = {"chip": lambda v: rf"chip_us={int(v)}\b", "rep": lambda v: rf"repeat={int(v)}\b",
           "rgb": lambda v: "1 channel" if int(v) == 1 else "3 channels"}
NOT_SET = "board not set"                                  # in a cell whose board did not confirm


class BoardError(Exception):
    pass


def board_cmd(b, cmd, wait=0.6):
    """The board's whole reply to one command."""
    try: return boardtool.send(b, cmd, wait=wait).strip()
    except (SystemExit, OSError) as e: raise BoardError(f"{b}: `{cmd}`: {e}")      # board not found, port busy or gone


def board_set(b, name, value):
    """`name value` on the board, checked against its reply: a board that did not take the
    setting (it rebooted, the port answers for another board, the value is out of range) would
    be measured under the wrong label."""
    out = board_cmd(b, f"{name} {value}")
    if not re.search(CONFIRM[name](value), out):
        raise BoardError(f"{b}: `{name} {value}` not confirmed, the board answered {out.splitlines()[-1] if out else 'nothing'!r}")


def set_boards(phones, settings, skip=()):
    """Apply [(name, value), ...] to the board of each phone. Returns the phones whose board did
    not confirm, `skip` included: their cells are not measured."""
    failed = set(skip)
    for p in phones:
        if p in failed: continue
        try:
            for name, value in settings: board_set(PHONES[p]["board"], name, value)
        except BoardError as e:
            failed.add(p); print(f"  {p}: cell skipped: {e}", flush=True)
    return failed


def saved_chips(phones):
    """{board: chip_us} from each board's `stat`, read before a run changes anything. A board
    that does not answer stops the run here: there would be nothing to put back."""
    saved = {}
    for p in phones:
        b = PHONES[p]["board"]
        try: out = board_cmd(b, "stat", wait=1.0)
        except BoardError as e: raise SystemExit(str(e))
        m = re.search(r"chip_us=(\d+)", out)
        if not m: raise SystemExit(f"{b}: no chip_us in the reply to `stat`: {out!r}")
        saved[b] = int(m.group(1))
    return saved


def restore_boards(saved, also=()):
    """Put back the chip lengths read by saved_chips, then the `also` settings. Runs in a
    `finally`: a board that fails is reported and the others are still restored."""
    for b, chip in saved.items():
        for name, value in (("chip", chip),) + tuple(also):
            try: board_set(b, name, value)
            except BoardError as e: print(f"  not restored: {e}", flush=True)


def log(out_dir, line):
    print(line, flush=True)
    with open(os.path.join(out_dir, "results.md"), "a") as f: f.write(line + "\n")


def sample(phone, seconds):
    """Yield over `seconds`: the app's packet and message totals at the last stats sample minus
    those at the first, over the phone's own clock. The receiver is not reset to start the totals
    from zero: a reset in either app also drops the camera description (exposure, row time) the
    receiver was given, and the cell would be measured with a detector that assumes half a chip.
    A total that went backwards means somebody reset the receiver during the cell: the cell then
    takes the app's own packets-per-second estimate, sampled once a second and averaged, and the
    messages since that reset. Returns (packets, messages, fps, exposure_us, last stats)."""
    with RSLive(port=PHONES[phone]["port"]) as s:
        st0 = st = s.stats(); rates = []
        for _ in range(int(seconds)):
            time.sleep(1.0); st = s.stats(); rates.append(float(st["pkt_per_s"]))
    dt = float(st["t"]) - float(st0["t"])
    pk = st["packets"] - st0["packets"]; ms = st["messages"] - st0["messages"]
    if pk < 0 or ms < 0 or dt <= 0: pk = sum(rates) / max(1, len(rates)) * seconds; ms = st["messages"]
    else: pk = pk * seconds / dt                               # the samples span a little more than `seconds`
    return pk, ms, float(st.get("fps", 0)), float(st.get("exposure_us", 0)), st


def record(phone, seconds, note, out_dir):
    with RSLive(port=PHONES[phone]["port"]) as s:
        path, summary = s.record(seconds, note, out_dir)
    return os.path.basename(path), summary


def set_exposure_us(phone, us):
    """Set the exposure (log-scale fraction on iOS, exposure_us on Android), wait for the camera to
    apply it and return what it reports; one correction step if the mapping is off."""
    with RSLive(port=PHONES[phone]["port"]) as s:
        st = s.get()
        if "exposure_us" in st and phone != "iphone":
            s.set("exposure_us", us); time.sleep(2.5); return s.stats()["exposure_us"]
        min_e = float(st.get("min_exposure_us", 15)); max_e = 4000.0
        f = 0.0 if us <= min_e else min(1.0, math.log(us / min_e) / math.log(max_e / min_e))
        s.set("exposure", f)
        got = 0.0
        for _ in range(12):                                   # the camera applies it asynchronously
            time.sleep(0.5); got = s.stats()["exposure_us"]
            if abs(got - max(us, min_e)) <= 0.12 * max(us, min_e): break
        if us > min_e and abs(got - us) > 0.15 * us and got > 0:
            f = min(1.0, max(0.0, f + math.log(us / got) / math.log(max_e / min_e)))
            s.set("exposure", f)
            for _ in range(12):
                time.sleep(0.5); got = s.stats()["exposure_us"]
                if abs(got - us) <= 0.12 * us: break
        return got


def matrix(a):
    out = a.out; os.makedirs(out, exist_ok=True)
    chips = [int(c) for c in a.chips.split(",")]
    phones = a.phones.split(",")
    saved = saved_chips(phones)
    log(out, f"\n## Chip sweep {datetime.now():%Y-%m-%d %H:%M} — {a.seconds} s per cell, {a.rec} s clips\n")
    log(out, "| chip µs | " + " | ".join(f"{p} pkt/s | {p} msgs | {p} clip" for p in phones) + " |")
    log(out, "|---|" + "---|---|---|" * len(phones))
    try:
        for c in chips:
            failed = set_boards(phones, [("chip", c)])
            time.sleep(1.0)
            cells = []
            for p in phones:
                if p in failed: cells.append(f"{NOT_SET} | — | —"); continue
                pk, ms, fps, exp, st = sample(p, a.seconds)
                name, summary = record(p, a.rec, f"bench {p} chip{c} exp{exp:.0f}", out)
                cells.append(f"{pk / a.seconds:.1f} | {ms} | {name}")
                with open(os.path.join(out, "stats.jsonl"), "a") as f: f.write(json.dumps(dict(kind="chip", phone=p, chip=c, seconds=a.seconds, stats=st, clip=name)) + "\n")
            log(out, f"| {c} | " + " | ".join(cells) + " |")
    finally:
        restore_boards(saved)


def exposure(a):
    out = a.out; os.makedirs(out, exist_ok=True)
    p = a.phone
    chips = [int(c) for c in a.chips.split(",")]; exps = [float(e) for e in a.exposures.split(",")]
    saved = saved_chips([p])
    log(out, f"\n## Exposure × chip on {p} {datetime.now():%Y-%m-%d %H:%M} — {a.seconds} s per cell\n")
    log(out, "| chip µs | " + " | ".join(f"E={e:.0f} µs pkt/s" for e in exps) + " |")
    log(out, "|---|" + "---|" * len(exps))
    try:
        for c in chips:
            if set_boards([p], [("chip", c)]): log(out, f"| {c} | " + " | ".join(NOT_SET for e in exps) + " |"); continue
            time.sleep(1.0)
            cells = []
            for e in exps:
                real = set_exposure_us(p, e)
                pk, ms, fps, exp, st = sample(p, a.seconds)
                name, summary = record(p, a.rec, f"bench {p} chip{c} exp{real:.0f}", out)
                cells.append(f"{pk / a.seconds:.1f} (E/T {real / c:.2f}, {name})")
                with open(os.path.join(out, "stats.jsonl"), "a") as f: f.write(json.dumps(dict(kind="exposure", phone=p, chip=c, exposure_us=real, seconds=a.seconds, stats=st, clip=name)) + "\n")
            log(out, f"| {c} | " + " | ".join(cells) + " |")
    finally:
        restore_boards(saved); set_exposure_us(p, 0)              # the board first: it must not depend on the phone answering


def repeat(a):
    """E1/E2: chip length x packet repetition on both phones, each on its own board."""
    out = a.out; os.makedirs(out, exist_ok=True)
    chips = [int(c) for c in a.chips.split(",")]; reps = [int(r) for r in a.reps.split(",")]
    phones = a.phones.split(",")
    saved = saved_chips(phones)
    log(out, f"\n## Chip x repeat {datetime.now():%Y-%m-%d %H:%M} — {a.seconds} s per cell, rgb {a.rgb}\n")
    log(out, "| chip µs | repeat | " + " | ".join(f"{p} pkt/s | {p} fps | {p} thermal" for p in phones) + " |")
    log(out, "|---|---|" + "---|---|---|" * len(phones))
    try:
        no_rgb = set_boards(phones, [("rgb", a.rgb)])              # set once: these phones sit out the whole run
        for c in chips:
            for r in reps:
                failed = set_boards(phones, [("chip", c), ("rep", r)], skip=no_rgb)
                time.sleep(1.5)
                cells = []
                for p in phones:
                    if p in failed: cells.append(f"{NOT_SET} | — | —"); continue
                    pk, ms, fps, exp, st = sample(p, a.seconds)
                    cells.append(f"{pk / a.seconds:.1f} | {fps:.0f} | {st.get('thermal', '?')}")
                    with open(os.path.join(out, "stats.jsonl"), "a") as f: f.write(json.dumps(dict(kind="repeat", phone=p, chip=c, rep=r, rgb=a.rgb, seconds=a.seconds, stats=st)) + "\n")
                log(out, f"| {c} | {r} | " + " | ".join(cells) + " |")
    finally:
        # the demo's `stat` prints the chip length but neither the repetition nor the channels,
        # so those two cannot be read before the run: they go back to the sketch's defaults
        restore_boards(saved, also=(("rep", 1), ("rgb", 3)))


def analyze(a):
    out = os.path.abspath(a.dir)
    clips = sorted(f for f in os.listdir(out) if f.endswith(".rsrec"))
    # imported here: rscore compiles the receiver on import, which the live commands do not need
    sys.path.insert(0, os.path.join(ROOT, "core", "tools"))
    from rsrec import Recording
    from replay import replay
    log(out, f"\n## Offline analysis {datetime.now():%Y-%m-%d %H:%M} — whole clips\n")
    log(out, "| clip | note | E/T | single receiver (whole clip) | multi-source receiver (whole clip) |")
    log(out, "|---|---|---|---|---|")
    for c in clips:
        path = os.path.join(out, c)
        hdr = Recording(path).header
        note = hdr.get("note", ""); exp = float(hdr.get("exposureUs") or 0)
        m = re.search(r"\bchip(\d+)", note)                        # the bench notes carry the chip length; other clips have no E/T
        def cell(multi):
            try: r = replay(path, quiet=True, multi=multi)
            except Exception as e: print(f"  replay{' --multi' if multi else ''} failed on {c}: {e}", flush=True); return "? pkt/s, ? frames, ? msgs"
            return f"{r['pkt_per_s']} pkt/s, {r['frames_with_packets']} frames, {r['messages']} msgs"
        log(out, f"| {c} | {note} | {f'{exp / int(m.group(1)):.2f}' if m else '?'} | {cell(False)} | {cell(True)} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    m = sub.add_parser("matrix"); m.add_argument("--chips", default="30,45,60,75,90"); m.add_argument("--seconds", type=float, default=10)
    m.add_argument("--rec", type=float, default=2); m.add_argument("--phones", default="iphone,samsung"); m.add_argument("--out", default=os.path.join(ROOT, "testdata", "bench", stamp))
    e = sub.add_parser("exposure"); e.add_argument("--chips", default="30,45,60"); e.add_argument("--exposures", default="15,30,45,57")
    e.add_argument("--seconds", type=float, default=8); e.add_argument("--rec", type=float, default=1.5); e.add_argument("--phone", default="iphone"); e.add_argument("--out", default=os.path.join(ROOT, "testdata", "bench", stamp))
    an = sub.add_parser("analyze"); an.add_argument("dir")
    r = sub.add_parser("repeat"); r.add_argument("--chips", default="60,90,120"); r.add_argument("--reps", default="1,2"); r.add_argument("--rgb", default="3")
    r.add_argument("--seconds", type=float, default=10); r.add_argument("--phones", default="iphone,samsung"); r.add_argument("--out", default=os.path.join(ROOT, "testdata", "bench", stamp))
    a = ap.parse_args()
    {"matrix": matrix, "exposure": exposure, "analyze": analyze, "repeat": repeat}[a.cmd](a)


if __name__ == "__main__":
    main()
