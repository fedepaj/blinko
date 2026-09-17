#!/usr/bin/env python3
"""Send a command to a board's serial shell and print the reply.

  board.py r4  info            Nano R4 demo sketch (info warn err debug status fatal hf hang clear chip rgb burst strobe led stat)
  board.py n33 "rslog stat"    Nano 33 BLE Zephyr shell
  board.py list                ports and which board is on each

Ports are matched by USB product name (Nano R4 / RSLog Nano33BLE), so the order of the
/dev/cu.usbmodem* entries does not matter. Requires pyserial (in the umbrella .venv).
"""
import glob, re, subprocess, sys, time

NAMES = {"r4": ("Nano R4",), "n33": ("RSLog Nano33BLE", "Arduino Nano 33 BLE")}


def usb_ports():
    """{port: product name} using the USB location id, as macOS names cu.usbmodem<location><1>."""
    out = subprocess.run(["ioreg", "-p", "IOUSB", "-l", "-w0"], capture_output=True, text=True).stdout
    found = {}
    name = None
    for line in out.splitlines():
        m = re.search(r'"USB Product Name" = "([^"]+)"', line)
        if m: name = m.group(1); continue
        m = re.search(r'"locationID" = (\d+)', line)
        if m and name:
            loc = int(m.group(1))
            prefix = f"/dev/cu.usbmodem{loc >> 16:x}"
            for p in glob.glob("/dev/cu.usbmodem*"):
                if p.lower().startswith(prefix.lower()): found[p] = name
            name = None
    return found


def port_for(board):
    for p, n in usb_ports().items():
        if any(n.startswith(x) for x in NAMES[board]): return p
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
