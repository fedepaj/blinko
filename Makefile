# blinko — umbrella repository. Each component is an independent git repo (submodule).
PY := $(CURDIR)/.venv/bin/python
ZEPHYR_ENV := ZEPHYR_TOOLCHAIN_VARIANT=zephyr ZEPHYR_SDK_INSTALL_DIR=$(CURDIR)/toolchain/zephyr-sdk-1.0.1
.PHONY: help setup sync-core test test-full fw fw-upload zephyr zephyr-flash ios ios-install usb-forward live android android-install android-forward live-android status

help:
	@echo "make setup        init submodules, python venv"
	@echo "make sync-core    point every component's core/ submodule at the root core/ HEAD"
	@echo "make test         core tests (simulator)"
	@echo "make fw-upload    Arduino demo on the Nano R4 (PORT=... with two boards; tools/board.py r4a|r4b to drive them)"
	@echo "make zephyr-flash Zephyr demo on the Nano 33 BLE"
	@echo "make ios-install  iOS app on the paired iPhone"
	@echo "make usb-forward  USB tunnel to the app's remote session (port 7777)"
	@echo "make live ARGS=.. drive the app: get | stats | watch | set K V | frame out.png | record --seconds 2 --note X --out DIR"
	@echo "make android      Android debug APK"
	@echo "make android-install  build, install and launch on the adb device"
	@echo "make android-forward  USB tunnel to the Android app's remote session (local port 7778)"
	@echo "make live-android ARGS=..  same as live, against the Android app"
	@echo "make status       git status of every repo"

setup:
	git submodule update --init --recursive
	test -d .venv || (python3 -m venv .venv && .venv/bin/pip install -q numpy scipy pillow pyserial matplotlib west pyelftools)

sync-core:
	@rev=$$(git -C core rev-parse HEAD); for d in arduino zephyr-module ios android unoq; do \
	  git -C $$d/core fetch -q ../../core 2>/dev/null || git -C $$d/core fetch -q "$(CURDIR)/core"; \
	  git -C $$d/core checkout -q $$rev && echo "$$d/core -> $$rev"; done

test:
	$(PY) core/tools/test_core.py --quick
test-full:
	$(PY) core/tools/test_core.py
fw:
	arduino/build.sh BlinkoDemo
fw-upload:        # two boards: make fw-upload PORT=/dev/cu.usbmodem21301
	PORT=$(PORT) arduino/build.sh BlinkoDemo upload
zephyr:
	$(ZEPHYR_ENV) .venv/bin/west build -b arduino_nano_33_ble -d zephyr-module/build zephyr-module/samples/blinko_demo
zephyr-flash: zephyr
	PY=$(PY) zephyr-module/samples/blinko_demo/flash.sh
ios:
	ios/build.sh
ios-install:
	ios/build.sh install launch
usb-forward:      # USB tunnel to the app's remote session (then: make live ARGS="stats")
	.venv/bin/pymobiledevice3 usbmux forward 7777 7777
live:             # remote session client, e.g. make live ARGS="record --seconds 2 --note 'R4 rgb' --out testdata"
	.venv/bin/python ios/tools/rslive.py $(ARGS)
android:
	$(MAKE) -C android apk
android-install: android
	adb install -r -g android/build/Blinko-android-debug.apk && adb shell monkey -p com.federicopaglioni.blinko -c android.intent.category.LAUNCHER 1 >/dev/null
android-forward:  # then: make live-android ARGS="stats"; logs: adb logcat -s Blinko
	adb forward tcp:7778 tcp:7777
live-android:
	.venv/bin/python ios/tools/rslive.py --port 7778 $(ARGS)
unoq-headless:    # UNO Q kiosk on a recording, on this computer: make unoq-headless REC=testdata/x.rsrec
	$(PY) unoq/blinko_kiosk.py --source $(REC) --headless --fast
status:
	@for d in . core arduino zephyr-module ios android unoq; do echo "== $$d"; git -C $$d status -sb | head -5; done
