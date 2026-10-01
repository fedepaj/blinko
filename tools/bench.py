#!/usr/bin/env python3
"""Live protocol bench: drives the boards (chip length) and the phones (remote sessions), samples
packet yields and records .rsrec clips for offline analysis, in a fixed order.

  bench.py matrix   [--chips 30,45,60,75,90] [--seconds 10] [--rec 2]      both phones, chip sweep
  bench.py exposure [--chips 30,45,60] [--exposures 15,30,45,57] [--phone iphone]   exposure x chip
  bench.py analyze DIR                   replay (single / multi-source receiver) on every clip
  bench.py repeat   [--chips 90,105,120] [--reps 1,2,3] [--rgb 3] [--phones iphone,samsung]   chip x repetition

Setup (tools/board.py names, remote ports): see PHONES below. Results go to DIR/results.md.
"""
import argparse, json, math, os, subprocess, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ios", "tools")); sys.path.insert(0, HERE)
from rslive import RSLive
import board as boardtool

PHONES = {
    "iphone":  dict(port=7777, board="r4:360B17", row_us=5.1),     # boards by USB serial: port names swap when a board reboots
    "samsung": dict(port=7778, board="r4:360D19", row_us=2.65),
}
PY = os.path.join(ROOT, ".venv", "bin", "python")


def board_cmd(b, cmd, wait=0.6):
    out = boardtool.send(b, cmd, wait=wait).strip().splitlines()
    return out[-1] if out else ""


def log(out_dir, line):
    print(line, flush=True)
    with open(os.path.join(out_dir, "results.md"), "a") as f: f.write(line + "\n")


def sample(phone, seconds):
    """Yield over `seconds`: the app's own packets-per-second estimate sampled once a second and
    averaged (the raw totals are unreliable: iOS resets them asynchronously and per track).
    Messages are counted from the console after a reset. Returns (packets, messages, fps, exposure_us, last stats)."""
    with RSLive(port=PHONES[phone]["port"]) as s:
        s.reset(); time.sleep(1.0)
        rates = []; st = None
        for _ in range(int(seconds)):
            time.sleep(1.0); st = s.stats(); rates.append(float(st["pkt_per_s"]))
        msgs = len(s.messages())
    pps = sum(rates) / max(1, len(rates))
    return pps * seconds, msgs, float(st.get("fps", 0)), float(st.get("exposure_us", 0)), st


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
    log(out, f"\n## Chip sweep {datetime.now():%Y-%m-%d %H:%M} — {a.seconds} s per cell, {a.rec} s clips\n")
    log(out, "| chip µs | " + " | ".join(f"{p} pkt/s | {p} msgs | {p} clip" for p in phones) + " |")
    log(out, "|---|" + "---|---|---|" * len(phones))
    try:
        for c in chips:
            for p in phones: board_cmd(PHONES[p]["board"], f"chip {c}")
            time.sleep(1.0)
            cells = []
            for p in phones:
                pk, ms, fps, exp, st = sample(p, a.seconds)
                name, summary = record(p, a.rec, f"bench {p} chip{c} exp{exp:.0f}", out)
                cells.append(f"{pk / a.seconds:.1f} | {ms} | {name}")
                with open(os.path.join(out, "stats.jsonl"), "a") as f: f.write(json.dumps(dict(kind="chip", phone=p, chip=c, seconds=a.seconds, stats=st, clip=name)) + "\n")
            log(out, f"| {c} | " + " | ".join(cells) + " |")
    finally:
        for p in phones: board_cmd(PHONES[p]["board"], "chip 30")


def exposure(a):
    out = a.out; os.makedirs(out, exist_ok=True)
    p = a.phone; b = PHONES[p]["board"]
    chips = [int(c) for c in a.chips.split(",")]; exps = [float(e) for e in a.exposures.split(",")]
    log(out, f"\n## Exposure × chip on {p} {datetime.now():%Y-%m-%d %H:%M} — {a.seconds} s per cell\n")
    log(out, "| chip µs | " + " | ".join(f"E={e:.0f} µs pkt/s" for e in exps) + " |")
    log(out, "|---|" + "---|" * len(exps))
    try:
        for c in chips:
            board_cmd(b, f"chip {c}"); time.sleep(1.0)
            cells = []
            for e in exps:
                real = set_exposure_us(p, e)
                pk, ms, fps, exp, st = sample(p, a.seconds)
                name, summary = record(p, a.rec, f"bench {p} chip{c} exp{real:.0f}", out)
                cells.append(f"{pk / a.seconds:.1f} (E/T {real / c:.2f}, {name})")
                with open(os.path.join(out, "stats.jsonl"), "a") as f: f.write(json.dumps(dict(kind="exposure", phone=p, chip=c, exposure_us=real, seconds=a.seconds, stats=st, clip=name)) + "\n")
            log(out, f"| {c} | " + " | ".join(cells) + " |")
    finally:
        set_exposure_us(p, 0); board_cmd(b, "chip 30")


def repeat(a):
    """E1/E2: chip length x packet repetition on both phones, each on its own board."""
    out = a.out; os.makedirs(out, exist_ok=True)
    chips = [int(c) for c in a.chips.split(",")]; reps = [int(r) for r in a.reps.split(",")]
    phones = a.phones.split(",")
    log(out, f"\n## Chip x repeat {datetime.now():%Y-%m-%d %H:%M} — {a.seconds} s per cell, rgb {a.rgb}\n")
    log(out, "| chip µs | repeat | " + " | ".join(f"{p} pkt/s | {p} fps | {p} thermal" for p in phones) + " |")
    log(out, "|---|---|" + "---|---|---|" * len(phones))
    try:
        for p in phones: board_cmd(PHONES[p]["board"], f"rgb {a.rgb}")
        for c in chips:
            for r in reps:
                for p in phones: board_cmd(PHONES[p]["board"], f"chip {c}"); board_cmd(PHONES[p]["board"], f"rep {r}")
                time.sleep(1.5)
                cells = []
                for p in phones:
                    pk, ms, fps, exp, st = sample(p, a.seconds)
                    cells.append(f"{pk / a.seconds:.1f} | {fps:.0f} | {st.get('thermal', '?')}")
                    with open(os.path.join(out, "stats.jsonl"), "a") as f: f.write(json.dumps(dict(kind="repeat", phone=p, chip=c, rep=r, rgb=a.rgb, seconds=a.seconds, stats=st)) + "\n")
                log(out, f"| {c} | {r} | " + " | ".join(cells) + " |")
    finally:
        for p in phones: board_cmd(PHONES[p]["board"], "chip 60"); board_cmd(PHONES[p]["board"], "rep 1"); board_cmd(PHONES[p]["board"], "rgb 3")


def analyze(a):
    out = os.path.abspath(a.dir)
    clips = sorted(f for f in os.listdir(out) if f.endswith(".rsrec"))
    log(out, f"\n## Offline analysis {datetime.now():%Y-%m-%d %H:%M} — whole clips\n")
    log(out, "| clip | note | E/T | single receiver (whole clip) | multi-source receiver (whole clip) |")
    log(out, "|---|---|---|---|---|")
    tools = os.path.join(ROOT, "core", "tools")
    for c in clips:
        path = os.path.join(out, c)
        hdr = json.loads(open(path, "rb").read(4096)[12:12 + int.from_bytes(open(path, "rb").read(12)[8:12], "little")])
        note = hdr.get("note", ""); exp = float(hdr.get("exposureUs", 0))
        chip = next((int(t[4:]) for t in note.split() if t.startswith("chip")), 30)
        def run(args):
            r = subprocess.run([PY] + args, capture_output=True, text=True, cwd=tools)
            if r.returncode != 0: print(f"  {args[0]} failed on {c}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}", flush=True)
            return r.stdout.strip().splitlines()
        def field(lines, key):
            return next((l.split(key)[1].split()[0] for l in lines if key in l), "?")
        single = run(["replay.py", path, "--quiet"]); multi = run(["replay.py", path, "--quiet", "--multi"])
        # replay prints pkt/s over the whole clip and the number of frames with packets
        cls = lambda lines: f"{field(lines, 'pkt/s=')} pkt/s, {field(lines, 'frames_with_pkts=')} frames, {field(lines, 'msgs=')} msgs"
        log(out, f"| {c} | {note} | {exp / chip:.2f} | {cls(single)} | {cls(multi)} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    m = sub.add_parser("matrix"); m.add_argument("--chips", default="30,45,60,75,90"); m.add_argument("--seconds", type=float, default=10)
    m.add_argument("--rec", type=float, default=2); m.add_argument("--phones", default="iphone,samsung"); m.add_argument("--out", default=os.path.join(ROOT, "testdata", "bench", stamp))
    e = sub.add_parser("exposure"); e.add_argument("--chips", default="30,45,60"); e.add_argument("--exposures", default="15,30,45,57")
    e.add_argument("--seconds", type=float, default=8); e.add_argument("--rec", type=float, default=1.5); e.add_argument("--phone", default="iphone"); e.add_argument("--out", default=os.path.join(ROOT, "testdata", "bench", stamp))
    an = sub.add_parser("analyze"); an.add_argument("dir"); an.add_argument("--frames", type=int, default=40)
    r = sub.add_parser("repeat"); r.add_argument("--chips", default="60,90,120"); r.add_argument("--reps", default="1,2"); r.add_argument("--rgb", default="3")
    r.add_argument("--seconds", type=float, default=10); r.add_argument("--phones", default="iphone,samsung"); r.add_argument("--out", default=os.path.join(ROOT, "testdata", "bench", stamp))
    a = ap.parse_args()
    {"matrix": matrix, "exposure": exposure, "analyze": analyze, "repeat": repeat}[a.cmd](a)


if __name__ == "__main__":
    main()
