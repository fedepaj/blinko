#!/usr/bin/env python3
"""Flash a Nano R4 when several are connected: 1200-bps touch on the chosen port, then dfu-util
addressed by the board's USB serial (arduino-cli's upload refuses with two DFU devices).

  flash_r4.py --port /dev/cu.usbmodem21301 [--bin arduino/build/BlinkoDemo/BlinkoDemo.ino.bin]
  flash_r4.py --board r4a|r4b|r4@21301 ...          names as in tools/board.py
"""
import argparse, glob, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board as boardtool

DFU_GLOB = os.path.expanduser("~/Library/Arduino15/packages/arduino/tools/dfu-util/*/dfu-util")


def usb_serial_for_port(port):
    """USB serial number of the device behind /dev/cu.usbmodem<location>1 (ioreg)."""
    out = subprocess.run(["ioreg", "-p", "IOUSB", "-l", "-w0"], capture_output=True, text=True).stdout
    serial = None; loc = None
    for line in out.splitlines():
        m = re.search(r'"USB Serial Number" = "([^"]+)"', line)
        if m: serial = m.group(1)
        m = re.search(r'"locationID" = (\d+)', line)
        if m:
            loc = int(m.group(1)); prefix = f"/dev/cu.usbmodem{loc >> 16:x}"
            if port.lower().startswith(prefix.lower()) and serial: return serial
            serial = None
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port"); ap.add_argument("--board")
    ap.add_argument("--bin", default=os.path.join(HERE, "..", "arduino", "build", "BlinkoDemo", "BlinkoDemo.ino.bin"))
    a = ap.parse_args()
    port = a.port or (boardtool.port_for(a.board) if a.board else None)
    if not port: sys.exit("give --port or --board")
    dfu = sorted(glob.glob(DFU_GLOB))
    if not dfu: sys.exit("dfu-util not found (install the arduino:renesas_uno core)")
    dfu = dfu[-1]
    import serial as pyserial
    def dfu_serials():
        lst = subprocess.run([dfu, "--list"], capture_output=True, text=True).stdout
        return sorted(set(re.findall(r'Found DFU:.*serial="([0-9A-Fa-f]+)"', lst)))
    before = dfu_serials()
    if os.path.exists(port):
        print(f"{port}: touching 1200 bps")
        try:
            with pyserial.Serial(port, 1200) as s: s.dtr = False
        except Exception as e: print("touch:", e)
    else:
        print(f"{port} is gone: assuming the board is already in DFU mode")
    serial = None
    for _ in range(40):
        time.sleep(0.25)
        now = dfu_serials()
        new = [x for x in now if x not in before]
        if new: serial = new[0]; break
        if not os.path.exists(port) and len(now) == 1: serial = now[0]; break
    if not serial:
        sys.exit("board did not enter DFU mode (double-tap reset and retry); DFU devices seen: %s" % dfu_serials())
    print(f"flashing DFU device {serial}")
    cmd = [dfu, "--device", "2341:0374", "-S", serial, "-a", "0", "-D", a.bin, "--reset"]   # this dfu-util (0.11-arduino) wants the long form: "-R" demands an argument
    r = subprocess.run(cmd, capture_output=True, text=True)
    tail = [l for l in (r.stdout + r.stderr).splitlines() if l and not l.startswith("Download")][-3:]
    print("\n".join(tail))
    if r.returncode != 0 and "Done!" not in r.stdout: sys.exit(r.returncode)
    time.sleep(3)
    print("ports now:", " ".join(glob.glob("/dev/cu.usbmodem*")))


if __name__ == "__main__":
    main()
