#!/usr/bin/env python3
"""Send a command to a board's serial shell and print the reply.

  board.py r4  info            Nano R4 demo sketch (info warn err debug status fatal hf hang clear chip rgb burst strobe led stat)
  board.py r4a stat / r4b stat two identical boards, by port order; r4@21301 by port suffix
  board.py n33 "blinko stat"    Nano 33 BLE Zephyr shell
  board.py list                ports and which board is on each

Ports are matched by USB product name (Nano R4 / Blinko Nano33BLE), so the order of the
/dev/cu.usbmodem* entries does not matter. Requires pyserial (in the umbrella .venv).
"""
import glob, re, subprocess, sys, time

NAMES = {"r4": ("Nano R4",), "n33": ("Blinko Nano33BLE", "RSLog Nano33BLE", "Arduino Nano 33 BLE")}


def usb_devices():
    """[(port, product name, usb serial)] from ioreg. Each device prints its properties in one
    block; the product name, the serial and the location id come in no fixed order, so a block
    is closed when its location id has been seen. macOS names the port cu.usbmodem<location><1>,
    and that name changes when a board re-enumerates (reboot, hub change): the serial does not."""
    out = subprocess.run(["ioreg", "-p", "IOUSB", "-l", "-w0"], capture_output=True, text=True).stdout
    found = []
    cur = {}
    for line in out.splitlines():
        if re.match(r"\s*[|+-]*-o ", line): cur = {}                     # a new device node
        m = re.search(r'"USB Product Name" = "([^"]+)"', line)
        if m: cur["name"] = m.group(1)
        m = re.search(r'"USB Serial Number" = "([^"]+)"', line)
        if m: cur["serial"] = m.group(1)
        m = re.search(r'"locationID" = (\d+)', line)
        if m: cur["loc"] = int(m.group(1))
        if "name" in cur and "loc" in cur and ("serial" in cur or "nameless" in cur):
            prefix = f"/dev/cu.usbmodem{cur['loc'] >> 16:x}"
            for p in glob.glob("/dev/cu.usbmodem*"):
                if p.lower().startswith(prefix.lower()): found.append((p, cur["name"], cur.get("serial", "")))
            cur = {}
    return found


def usb_ports():
    """{port: product name}."""
    return {p: n for p, n, s in usb_devices()}


_cache = {}


def port_for(board):
    """Cached: ioreg takes ~1 s, so the lookup is repeated only when the cached port is gone.
    Several identical boards: `r4a`, `r4b`, ... pick the 1st, 2nd, ... by port name; `r4@21301` picks
    the port /dev/cu.usbmodem21301; `/dev/cu.usbmodemXXXX` is used as is."""
    if board.startswith("/dev/"): return board
    p = _cache.get(board)
    if p and p in glob.glob("/dev/cu.usbmodem*"): return p
    if ":" in board and not board.startswith("/dev/"):                      # r4:<usb serial, or a unique part of it>
        kind, _, ser = board.partition(":")
        ports = [p for p, n, srl in usb_devices() if any(n.startswith(x) for x in NAMES.get(kind, ())) and ser.lower() in srl.lower()]
        if len(ports) != 1: raise SystemExit(f"{board}: {len(ports)} boards match serial {ser!r}: {[(p, srl) for p, n, srl in usb_devices()]}")
        _cache[board] = ports[0]; return ports[0]
    kind, _, sel = board.partition("@")
    idx = 0
    if not sel and kind[-1] in "abcd" and kind[:-1] in NAMES: idx = "abcd".index(kind[-1]); kind = kind[:-1]
    if kind not in NAMES: raise SystemExit(f"{board}: unknown board (known: {', '.join(NAMES)})")
    ports = sorted(p for p, n in usb_ports().items() if any(n.startswith(x) for x in NAMES[kind]))
    if sel: ports = [p for p in ports if p.endswith(sel)]
    if idx < len(ports): _cache[board] = ports[idx]; return ports[idx]
    raise SystemExit(f"{board}: board not found (ports: {usb_ports()})")


def send(board, cmd, wait=1.0, baud=115200):
    import serial
    p = port_for(board)
    with serial.Serial(p, baud, timeout=0.3) as s:
        time.sleep(0.3); s.reset_input_buffer()
        s.write(("\r\n" + cmd + "\r\n").encode()); time.sleep(wait)
        out = s.read(65536).decode(errors="replace")
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)          # strip Zephyr shell colours
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        for p, n in usb_ports().items(): print(p, n)
        sys.exit(0)
    board, cmd = sys.argv[1], " ".join(sys.argv[2:])
    print(send(board, cmd).strip())
