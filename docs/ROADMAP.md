# RSLog — Roadmap

Stato al 16 settembre 2026: ricevitore allo stato "known good" (ROI globale,
100+ pacchetti/s da fermo con RGB a 120 fps), protocollo v2, modulo Zephyr
portabile, app iOS e Android, repository indipendenti.

## Problemi noti (misurati, non risolti)

| Problema | Evidenza | Dove si risolve |
|---|---|---|
| ~~Loop di fault troppo lento (chip ~84 µs invece di 30 sul R4, ~40 sulla Nano 33)~~ **risolto il 16/9**: temporizzazione a scadenza (DWT sul R4, `counter` in polling su Zephyr); verificato dal vivo: 6.0 righe/chip, fault decodificato su entrambe | fit sui run del frame del LED rosso: 16 righe/chip, pacchetto da 1100 righe > macchia (450) | fatto |
| Saturazione: il rosso del R4 satura a ISO minimo; i chip spenti si accorciano di un'esposizione (run ON 36 righe, OFF 6) | frame del fault, `peak=255 sat=0.19` | ricevitore: canale non saturo (il verde vede il rosso attenuato) + compensazione dello smear; firmware: opzione dimming PWM |
| Movimento: falsi piloti corrompono la matrice colore (cond 0.9 → 0.05), ROI per frame | misura del 15/9 sera | fase 3 |
| Pochi messaggi con 100 pkt/s | il demo manda solo STATUS ogni 5 s; i falsi positivi del CRC-8 (1/256 dei sync corrotti) avvelenano il sistema lineare e azzerano lo slot | fase 1 (CRC-16, soft decoding) + contatore di reset esposto nell'app |

## Fase 0 — Strumenti (prima di tutto)

1. **Registratore di frame** nelle app: 2–3 s di frame grezzi a piena
   risoluzione (BGRA/YUV) con metadati (esposizione, ISO, fps, giroscopio)
   in un file; **replay offline** in Python attraverso il core C con metriche
   (pkt/s, messaggi/s, falsi positivi, reset). Ogni modifica al ricevitore si
   valuta su registrazioni reali, non dal vivo.
2. **Corpus** di registrazioni etichettate: fermo/moto lento/moto veloce,
   RGB/mono, fault, vicino/lontano, R4/Nano 33/GIGA, iPhone/Android.
   Repo `rslog-testdata` (git-lfs).
3. `make test` = simulazione + replay del corpus con soglie di regressione.
4. `tools/board.py`: CLI unica per seriale R4 e shell Zephyr (`log`, `fatal`,
   `hf`, `rgb`, `burst`, `chip`, `stat`) usata dai test end-to-end.

## Fase 1 — Robustezza del pacchetto

1. **CRC-16** sul pacchetto (67 → 75 chip, +12 %): con la codifica fountain
   ogni falso positivo costa un messaggio intero.
2. **Decodifica soft**: ogni bit ha una confidenza; se il CRC fallisce si
   provano fino a 2–3 inversioni tra i bit meno affidabili (≤ 30 tentativi,
   "chase decoding"). Recupera i pacchetti con 1–2 errori invece di buttarli.
3. Smear di esposizione: stimato dall'asimmetria ON/OFF dei sync validi
   (mediana su molti pacchetti, non per pacchetto) e usato per riallineare
   le finestre dei bit.
4. Salute per slot nell'app: rango, reset, età dell'ultimo pacchetto.

## Fase 2 — Sincronizzazione (modello temporale nel ricevitore)

Oggi ogni frame ricomincia da zero. Il periodo del chip (in righe), la fase e
il periodo del pacchetto (67 chip) sono stabili: un tracker li stima dai sync
validati e **predice dove cadranno i sync nel frame successivo** (lo
scorrimento frame/pacchetto è deterministico). Vantaggi: finestre di ricerca
strette (meno falsi sync), aggancio anche con sync rovinato, stato "lock"
visibile in app, stima robusta di smear e righe/chip. Lato firmware non serve
un beacon: il sync per pacchetto già porta l'informazione; manca la memoria
tra frame.

## Fase 3 — Resistenza al movimento

1. **Tracker della macchia** (centroide, raggio, velocità) su thumbnail con
   filtro a velocità costante; ROI dal tracker, **inclinata** secondo la
   velocità per il moto durante la lettura del frame (la versione corretta
   dell'esperimento "a bande", che usava stime per banda troppo rumorose).
2. **Giroscopio** come predizione del tracker (v_px ≈ ω·f, f ≈ 1500 px per il
   wide a 1080p); accelerometro per lo stato fermo/moto e per allargare la
   ROI. Latenza zero sullo spostamento.
3. Calibrazione colore condizionata: aggiornamento immediato da fermo,
   candidato + conferma in moto, mai da piloti con condizionamento < 0.4;
   in moto si usa la calibrazione già misurata.
4. Saturazione: scelta automatica del canale non saturo per il decode mono;
   in firmware opzione di dimming PWM (> 300 kHz) per LED troppo luminosi.
5. Obiettivo misurabile sul corpus: ≥ 50 % dei pacchetti "da fermo" con moto
   lento della mano.

## Fase 4 — Multi-sorgente

1. Segmentazione della thumbnail in macchie (componenti connesse) e tracking
   multi-oggetto con ID stabili.
2. Un ricevitore `rs_rx` per macchia: calibrazione, modalità (RGB/mono) e
   assembler indipendenti; messaggi taggati con la sorgente. RGB e mono
   insieme funzionano già per costruzione.
3. Associazione: macchie che trasmettono gli stessi pacchetti nello stesso
   istante (LED RGB e LED builtin della stessa scheda da vicino) diventano
   una sola sorgente logica.
4. Identità: board id e versione firmware nello STATUS → "Nano R4 #A1".
5. UI: marker sui centroidi nell'anteprima con colore e ultimo messaggio;
   console filtrabile per sorgente.

## Fase 5 — Firmware

1. Temporizzazione a scadenza nel loop di fault (DWT su R4, `counter` su Zephyr).
2. Backend di log Zephyr (`LOG_ERR()` → LED, `CONFIG_RSLOG_LOG_BACKEND`);
   `RSLog.printf` per Arduino.
3. Board id + versione nello STATUS; mini backtrace nel fault (2–3 LR).
4. Port di prova: GIGA R1 (STM32H747, LED RGB, Zephyr in-tree) e UNO Q.
5. Dimming PWM opzionale per canale.

## Fase 6 — App

Icona (fatta), registratore (fase 0), vista sorgenti (fase 4), storico
persistente, condivisione delle registrazioni, Lab mode sul corpus.

## Setup di sviluppo

- **Repo**: `rslog` (ombrello) referenzia `rslog-core`, `rslog-arduino`,
  `rslog-zephyr`, `rslog-ios`, `rslog-android`; ogni componente ha `core/`
  come submodule. Ciclo: modifica in `core/`, commit, `make sync-core`,
  commit nei componenti. Su GitHub: creare i sei repo con questi nomi, poi
  `git push -u origin main` da ognuno e `git submodule sync`.
- **Schede**: Nano R4 e Nano 33 BLE per i due percorsi (Arduino, Zephyr);
  GIGA R1 come terza board Zephyr (RGB, STM32) per la portabilità; UNO Q da
  valutare (lato MCU STM32U585 in Zephyr, flash tramite il lato Linux).
- **Telefoni**: iPhone per sviluppo; Android appena disponibile. Nel
  frattempo il percorso Android si valida offline con il corpus (stesso core C).
- **Strumenti**: `make setup` (submodule + venv), `make test`, `make fw-upload`,
  `make zephyr-flash`, `make ios-install`, `make android`, `make status`.
