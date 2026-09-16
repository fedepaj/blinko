# Rolling Shutter Logger — Piano di progetto

Obiettivo: un microcontrollore (Arduino Nano R4) trasmette messaggi di log
facendo lampeggiare i suoi LED; un telefono (iPhone, poi Android) inquadra la
scheda e decodifica i messaggi sfruttando il **rolling shutter** della camera.
Nessun cavo, nessuna radio, nessun pairing: basta guardare la scheda.

Caso d'uso principale: la scheda si è "brickata" (hard fault, watchdog,
assert, brown-out). Non risponde su seriale, ma il LED continua a lampeggiare
e racconta *perché* si è fermata.

## 1. Principio fisico

Le camere CMOS espongono le righe del sensore una alla volta, dall'alto in
basso. Se il LED lampeggia molto più velocemente del frame rate, ogni riga
"vede" il LED in un istante diverso: nel fotogramma compaiono bande orizzontali
chiare/scure. **La coordinata verticale del fotogramma è un asse temporale.**

Grandezze in gioco (da misurare in fase di calibrazione, vedi
`docs/CALIBRATION.md`):

| Grandezza | Simbolo | Ordine di grandezza atteso su iPhone 14 |
|---|---|---|
| tempo di lettura di una riga | `t_row` | 5–15 µs |
| righe del frame | `H` | 1080 (1920×1080) |
| finestra temporale per frame | `H · t_row` | 8–16 ms |
| esposizione minima | `t_exp` | 20–125 µs |
| durata di un chip (mezzo bit Manchester) | `T_chip` | 50–200 µs (parametrico) |
| righe per chip | `T_chip / t_row` | ≥ 4 per decodificare bene |

Ogni fotogramma cattura quindi una "finestra" di qualche millisecondo del
flusso di bit; fra un fotogramma e l'altro c'è tempo morto. Il protocollo deve
essere robusto a questo: pacchetti **corti, autonomi e ripetuti**.

Perché la macchia del LED sia alta (tante righe = tanti bit per frame) il LED
va **sfocato**: fuoco bloccato a infinito e telefono a 0.5–3 cm dalla scheda.
Con il LED quasi a contatto con l'obiettivo la luce inonda l'intero sensore.

## 2. Architettura

```
┌──────────────── firmware (Nano R4) ────────────────┐   ┌──────────── iPhone ────────────┐
│ app sketch                                          │   │ SwiftUI app "RSLog Viewer"      │
│  └─ RSLog.log()/warn()/fatal()                      │   │  ├─ CameraController (AVFoundation)
│     └─ message store (carousel a priorità)          │   │  │   esposizione min, fuoco lock, │
│        └─ rs_encoder (core C) → chip                │   │  │   fps, wide/ultrawide/front    │
│           └─ GPT timer ISR → LED_BUILTIN + RGB      │ ~ │  ├─ FrameProcessor (Accelerate)  │
│ hard-fault / watchdog / fatal:                      │luce│  │   ROI + profilo per riga       │
│  .noinit record + EEPROM + bit-bang loop            │   │  ├─ rs_decoder (core C)          │
└─────────────────────────────────────────────────────┘   │  ├─ MessageAssembler + LogStore │
                                                          │  ├─ Lab mode (calibrazione)     │
          core/  (C portabile, condiviso)                 │  └─ CoreMotion, haptics, share  │
          ├─ rs_proto.h  (formato pacchetto, CRC)         └─────────────────────────────────┘
          ├─ rs_encoder.c (messaggio → chip)
          └─ rs_decoder.c (profilo righe → pacchetti)
          tools/ (Python: simulatore rolling shutter, test del core, analisi foto)
```

Scelte chiave:

- **Core in C puro** (`core/`), senza dipendenze: lo stesso encoder gira sul
  Nano R4, lo stesso decoder gira su iOS (bridging header), su Android (NDK)
  e nei test Python (ctypes). Il porting cambia solo il guscio.
- **Firmware come libreria Arduino** (`firmware/libraries/RSLog`): l'utente
  aggiunge `RSLog.begin()` e chiama `RSLog.log(...)`. La trasmissione è su
  interrupt di timer hardware (GPT), indipendente da `loop()` e da `delay()`.
- **Modulazione OOK + Manchester**: autosincronizzante, DC-balanced, tollera
  esposizione automatica e soglie che derivano. Bit 1 = chip `01`, bit 0 = `10`.
- **Sync non-Manchester** (`1111 0000`, run di 4 chip, impossibili nei dati):
  il ricevitore misura le righe-per-chip direttamente dal sync di ogni
  pacchetto → **nessuna calibrazione richiesta**, qualunque telefono.
- **Pacchetti da 1 byte di payload** con id messaggio + indice, CRC-8: entrano
  in finestre di pochi ms; il telefono li raccoglie su più frame e riassembla.
- **Carosello a priorità**: FAULT sempre trasmesso, poi STATUS, poi i log
  recenti. Un fotogramma casuale ha alta probabilità di beccare ciò che conta.
- **Brick**: `HardFault_Handler` proprietario salva PC/LR/causa in RAM
  `.noinit`, poi trasmette il fault con un loop bit-bang (nessun interrupt
  necessario). Al reset successivo il record è persistito in EEPROM e
  ritrasmesso insieme alla causa del reset (`RSTSR`).

## 3. Fasi

| # | Fase | Deliverable | Verifica |
|---|---|---|---|
| 0 | Ricognizione ambiente | toolchain, device, pin map | fatto |
| 1 | Core protocollo + simulatore | `core/`, `tools/simulate.py`, test | test Python: ≥95% pacchetti decodificati a SNR realistico, 0 falsi positivi CRC |
| 2 | Firmware | libreria RSLog, sketch demo, sketch strobe di calibrazione | compila con arduino-cli, upload sul Nano R4 |
| 3 | App iOS MVP | camera lock, profilo righe, decoder, console | build + install su iPhone; decodifica dal vivo |
| 4 | Calibrazione e tuning | Lab mode, misura `t_row`, scelta `T_chip` | tabella parametri per iPhone 14 |
| 5 | Robustezza brick | hard fault handler, EEPROM, reset cause, watchdog | provocare un fault e leggerlo dal telefono |
| 6 | Estensioni | RGB (3 canali paralleli), multi-cam, LED esterno, Android | opzionale |

## 4. Periferiche del telefono e loro ruolo

- **Camera wide posteriore**: decoder principale (apertura grande → sfocatura
  grande → macchia alta). Esposizione manuale minima, ISO basso, fuoco bloccato,
  stabilizzazione off, formato YUV (si usa solo la luminanza).
- **Ultra-wide**: fuoco fisso, apertura piccola: macchia più piccola ma niente
  da regolare. Selezionabile; utile come confronto di `t_row`.
- **Camera frontale**: per inquadrare la scheda "a specchio" con il telefono
  appoggiato. Selezionabile.
- **Accelerometro/giroscopio**: indicatore "tieni fermo"; il decoder scarta i
  frame con moto elevato (mosso orizzontale sporca il profilo).
- **Haptics + audio**: feedback a messaggio nuovo / fault ricevuto.
- **Torch**: no (accecherebbe il sensore). Multi-cam (front+back insieme) in fase 6.

## 5. Struttura del repository

```
core/                 C portabile (proto, encoder, decoder)
firmware/libraries/   libreria Arduino RSLog (include copia di core/)
firmware/sketches/    rslog_demo, strobe_calib, fault_demo
ios/RSLogViewer/      app SwiftUI (xcodegen)
tools/                simulatore, test, analisi immagini
docs/                 PLAN, PROTOCOL, CALIBRATION
Makefile              build/upload firmware, build/install app, test
```

## 6. Stato (2026-09-15, sera)

- Fase 1 ✅ core C + simulatore (`make test-full`).
- Fase 2 ✅ firmware Nano R4 caricato e verificato dal vivo.
- Fase 3 ✅ app iOS installata sull'iPhone 14: 33–38 pkt/s, messaggi in console.
- Fase 4 ✅ calibrazione: `t_row` = 5.1 µs, esposizione min 19 µs → `T_chip` = 30 µs.
- Fase 5 ✅ fault verificati dal vivo: hard fault reale (`hf`) trasmesso dal
  loop bit-bang entro 2 s, riportato dopo il riavvio (RAM alta) e dopo un
  reset software (data flash), `WDT reset @checkpoint`, `clear`. Scoperte:
  il bootloader azzera la `.noinit` in RAM bassa (record spostato a
  0x20007A00), la EEPROM virtuale non è usabile dal fault handler (usata la
  data flash grezza, ultimo blocco), un upload DFU appare come reset WDT
  (filtrato con l'id di build).
- Protocollo v2 ✅ (fountain coding + CRC messaggio 16 bit + testo a 6 bit +
  raffiche visibili): 51–65 pkt/s a 120 fps dal vivo, zero messaggi errati.
- Android ✅ app minima e APK (`make android`), da provare su un telefono.
- RGB ✅ tre flussi con piloti di calibrazione; dal vivo su iPhone: modalità
  RGB agganciata (55 piloti, condizionamento 0.91), 70–78 pkt/s. Android via
  profili RGB derivati dai piani YUV (crominanza a mezza risoluzione).
- Fase 6 ✅ port Zephyr come modulo portabile (counter/gpio/flash_map) (`zephyr-modules/rslog`, `CONFIG_RSLOG=y`):
  Nano 33 BLE Rev2 verificata dal vivo, red LED of death decodificato
  dall'iPhone (`docs/ZEPHYR.md`). Android: piano in `docs/ANDROID.md`.
