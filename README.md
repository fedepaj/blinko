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

## Struttura

| Percorso | Contenuto |
|---|---|
| `docs/PLAN.md` | piano di progetto, architettura, fasi |
| `docs/PROTOCOL.md` | formato dei pacchetti e del carosello |
| `docs/CALIBRATION.md` | misura del tempo di riga e scelta di `T_chip` |
| `core/` | C portabile: protocollo, trasmettitore, decoder, assembler |
| `firmware/libraries/RSLog` | libreria Arduino (timer ISR, fault handler, EEPROM) |
| `firmware/sketches/` | `rslog_demo` (comandi seriali), `strobe_calib` |
| `ios/RSLogViewer` | app SwiftUI (xcodegen) |
| `zephyr-modules/rslog` | modulo Zephyr (nRF52840 / Nano 33 BLE): `CONFIG_RSLOG=y` → red LED of death |
| `zephyr-app/` | demo Zephyr con shell USB, manifest west, `flash.sh` |
| `android/RSLogViewer` | app Android (Camera2 + core C via NDK), APK con `make android` |
| `docs/ZEPHYR.md`, `docs/ANDROID.md` | port Zephyr e app Android |
| `tools/` | simulatore rolling shutter, test, decodifica offline di foto |

## Quick start

```sh
make test                # simulatore + decoder + assembler
make fw-upload           # firmware demo sul Nano R4 (porta auto)
make ios-install         # app su iPhone (firma automatica, team in project.yml)
make zephyr-flash        # demo Zephyr sulla Nano 33 BLE (touch 1200 baud automatico)
make android             # APK Android in build/RSLog-android-debug.apk
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
#include <RSLog.h>
void setup() {
  RSLog.begin();                      // 30 µs/chip, LED_BUILTIN + RGB
  RSLog.info("boot ok");
  RSLog.checkpoint("init-sensors");   // riportato se segue un reset da watchdog
  if (!sensor.begin()) RSLog.fatal(3, "sensor init");   // non ritorna: lampeggia il motivo
}
void loop() { RSLog.status("up=%lus", millis()/1000); }
```
