# Rolling Shutter Logger

Log ottico da microcontrollore a telefono: la scheda (Arduino Nano R4)
lampeggia i suoi LED, l'app iPhone inquadra la scheda e ricostruisce i
messaggi sfruttando il rolling shutter della camera. Nessun cavo, nessuna
radio. Funziona anche quando la scheda è in hard fault: il fault handler
trasmette da solo la causa (PC, LR, CFSR) e la persiste in EEPROM.

Protocollo v2: pacchetti da 67 chip, codifica fountain, testo a 6 bit,
tre canali RGB con calibrazione automatica dai piloti, lampeggio visibile a
raffiche; il fault lampeggia sempre e solo sul LED rosso ("red LED of death").

Ispirato a [Measuring rolling shutter with a strobing LED](https://joancharmant.com/blog/measuring-rolling-shutter-with-a-strobing-led/).

## Repository

Questo è il repo ombrello: ogni componente è un repository indipendente,
incluso qui come submodule (`git submodule update --init --recursive`).

| Submodule | Repo | Contenuto |
|---|---|---|
| `core/` | blinko-core | protocollo, encoder, decoder, ricevitore in C portabile + tool Python |
| `arduino/` | blinko-arduino | libreria Arduino `Blinko` (Nano R4 / UNO R4) e sketch demo |
| `zephyr-module/` | blinko-zephyr | modulo Zephyr `blinko` (`CONFIG_BLINKO=y`) e demo con shell USB |
| `ios/` | blinko-ios | app iPhone (SwiftUI, AVFoundation) |
| `android/` | blinko-android | app Android (Kotlin, Camera2, NDK) |
| `unoq/` | blinko-unoq | kiosk per Arduino UNO Q + GigaDisplay + camera CSI (Python, GTK, GStreamer) |
| `docs/` | — | piano, roadmap, calibrazione |
| `assets/` | — | logo e icone |

Ogni componente porta il proprio `core/` come submodule; dopo una modifica al
core: commit in `core/`, poi `make sync-core` e commit nei componenti.

## Quick start

```sh
make setup               # submodule + venv
make test                # simulatore + decoder + assembler
make fw-upload           # firmware demo sul Nano R4 (porta auto)
make ios-install         # app su iPhone (firma automatica, team in project.yml)
make zephyr-flash        # demo Zephyr sulla Nano 33 BLE (touch 1200 baud automatico)
make android             # APK Android in android/build/Blinko-android-debug.apk
make unoq-headless REC=… # kiosk UNO Q su una registrazione (sviluppo)
```

Poi: apri la seriale a 115200 (`info ciao`, `warn x`, `fatal y`, `hf`,
`hang`, `chip 30`, `rgb 3|1`, `burst 150 50`, `strobe 2000`, `led on`, `reset`,
`stat`), avvicina il telefono ai LED (1–3 cm) e guarda la Console.

**Demo in due mosse** (Nano R4 e Nano 33 BLE): i LED trasmettono i log
(`info ...` dalla seriale/shell li aggiunge); **cortocircuita D2 con D3** e la
scheda va in hard fault vero: il LED rosso pulsa la causa (`HF p=... l=...` /
`ZF25 p=... l=...`) finché non premi RESET, dopo il quale il record persistito
viene ritrasmesso insieme alla causa del reset. `fatal <testo>` fa lo stesso
dalla libreria.

## Uso nel proprio sketch

```cpp
#include <Blinko.h>
void setup() {
  Blinko.begin();                      // 30 µs/chip, LED_BUILTIN + RGB
  Blinko.info("boot ok");
  Blinko.checkpoint("init-sensors");   // riportato se segue un reset da watchdog
  if (!sensor.begin()) Blinko.fatal(3, "sensor init");   // non ritorna: lampeggia il motivo
}
void loop() { Blinko.status("up=%lus", millis()/1000); }
```
