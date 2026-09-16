# rslog — umbrella repository. Each component is an independent git repo (submodule).
PY := $(CURDIR)/.venv/bin/python
ZEPHYR_ENV := ZEPHYR_TOOLCHAIN_VARIANT=zephyr ZEPHYR_SDK_INSTALL_DIR=$(CURDIR)/toolchain/zephyr-sdk-1.0.1
.PHONY: help setup sync-core test test-full fw fw-upload zephyr zephyr-flash ios ios-install android status

help:
	@echo "make setup        init submodules, python venv"
	@echo "make sync-core    point every component's core/ submodule at the root core/ HEAD"
	@echo "make test         core tests (simulator)"
	@echo "make fw-upload    Arduino demo on the Nano R4"
	@echo "make zephyr-flash Zephyr demo on the Nano 33 BLE"
	@echo "make ios-install  iOS app on the paired iPhone"
	@echo "make android      Android debug APK"
	@echo "make status       git status of every repo"

setup:
	git submodule update --init --recursive
	test -d .venv || (python3 -m venv .venv && .venv/bin/pip install -q numpy scipy pillow pyserial matplotlib west pyelftools)

sync-core:
	@rev=$$(git -C core rev-parse HEAD); for d in arduino zephyr-module ios android; do \
	  git -C $$d/core fetch -q ../../core 2>/dev/null || git -C $$d/core fetch -q "$(CURDIR)/core"; \
	  git -C $$d/core checkout -q $$rev && echo "$$d/core -> $$rev"; done

test:
	$(PY) core/tools/test_core.py --quick
test-full:
	$(PY) core/tools/test_core.py
fw:
	arduino/build.sh rslog_demo
fw-upload:
	arduino/build.sh rslog_demo upload
zephyr:
	$(ZEPHYR_ENV) .venv/bin/west build -b arduino_nano_33_ble -d zephyr-module/build zephyr-module/samples/rslog_demo
zephyr-flash: zephyr
	PY=$(PY) zephyr-module/samples/rslog_demo/flash.sh
ios:
	ios/build.sh
ios-install:
	ios/build.sh install launch
android:
	$(MAKE) -C android apk
status:
	@for d in . core arduino zephyr-module ios android; do echo "== $$d"; git -C $$d status -sb | head -5; done
