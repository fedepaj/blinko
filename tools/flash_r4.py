#!/usr/bin/env python3
"""Flash a Nano R4 when several are connected: 1200-bps touch on the chosen port, then dfu-util
addressed by the board's USB serial (arduino-cli's upload refuses with two DFU devices).

  flash_r4.py --port /dev/cu.usbmodem21301 [--bin arduino/build/BlinkoDemo/BlinkoDemo.ino.bin]
  flash_r4.py --board r4a|r4b|r4@21301|r4:<usb serial> ...     names as in tools/board.py
  flash_r4.py --serial 360B17...                    a board already in DFU mode (it has no port)

The serial is read from the port before the touch, and only the DFU device with that serial is
flashed; `dfu-util --list` shows the serials of the boards in DFU mode.
"""
import argparse, glob, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board as boardtool

DFU_GLOB = os.path.expanduser("~/Library/Arduino15/packages/arduino/tools/dfu-util/*/dfu-util")


def usb_serial_for_port(port):
    """USB serial number of the device behind a /dev/cu.usbmodem* port, None when it has none."""
    return next((srl for p, n, srl in boardtool.usb_devices() if p == port and srl), None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port"); ap.add_argument("--board")
    ap.add_argument("--serial", help="USB serial of the board: needed when it is already in DFU mode, where it has no port to read it from")
    ap.add_argument("--bin", default=os.path.join(HERE, "..", "arduino", "build", "BlinkoDemo", "BlinkoDemo.ino.bin"))
    a = ap.parse_args()
    port = a.port or (boardtool.port_for(a.board) if a.board else None)
    if not port and not a.serial: sys.exit("give --port, --board or --serial")
    dfu = sorted(glob.glob(DFU_GLOB))
    if not dfu: sys.exit("dfu-util not found (install the arduino:renesas_uno core)")
    dfu = dfu[-1]
    import serial as pyserial
    def dfu_serials():
        lst = subprocess.run([dfu, "--list"], capture_output=True, text=True).stdout
        return sorted(set(re.findall(r'Found DFU:.*serial="([0-9A-Fa-f]+)"', lst)))
    # The DFU device is chosen by serial and by nothing else: with a second board sitting in DFU
    # mode, "the device that appeared" or "the only device listed" can be that other board. The
    # serial has to be read while the board still has its port, so before the touch.
    want = a.serial
    if port and os.path.exists(port):
        want = want or usb_serial_for_port(port)
        if not want: sys.exit(f"{port}: no USB serial found for this port, so its DFU device cannot be told from another board's (give --serial)")
        print(f"{port}: USB serial {want}, touching 1200 bps")
        try:
            with pyserial.Serial(port, 1200) as s: s.dtr = False
        except Exception as e: print("touch:", e)
    elif want:
        print(f"{port or 'no port'}: assuming the board is already in DFU mode")
    else:
        sys.exit(f"{port} is gone and its serial is unknown: give --serial (DFU devices seen: {dfu_serials()})")
    serial = None
    for _ in range(40):
        time.sleep(0.25)
        serial = next((x for x in dfu_serials() if x.lower() == want.lower()), None)
        if serial: break
    if not serial:
        sys.exit(f"no DFU device with serial {want} (double-tap reset and retry; a board listed under another serial is flashed with --serial); DFU devices seen: {dfu_serials()}")
    print(f"flashing DFU device {serial}")
    cmd = [dfu, "--device", "2341:0374", "-S", serial, "-a", "0", "-D", a.bin, "--reset"]   # this dfu-util (0.11-arduino) wants the long form: "-R" demands an argument
    r = subprocess.run(cmd, capture_output=True, text=True)
    tail = [l for l in (r.stdout + r.stderr).splitlines() if l and not l.startswith("Download")][-3:]
    print("\n".join(tail))
    # "Done!" is printed once the download is complete and the board has accepted it; the only step
    # left after it is the USB reset asked with --reset, and dfu-util exits non-zero when that
    # fails ("error resetting after download", e.g. the board is already leaving DFU by itself).
    # The image is flashed either way, so a non-zero status counts only without "Done!".
    if r.returncode != 0 and "Done!" not in r.stdout: sys.exit(r.returncode)
    time.sleep(3)
    print("ports now:", " ".join(glob.glob("/dev/cu.usbmodem*")))


if __name__ == "__main__":
    main()
