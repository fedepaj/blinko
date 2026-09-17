# RSLog — Roadmap

Stato al 16 settembre 2026: ricevitore allo stato "known good" (ROI globale,
100+ pacchetti/s da fermo con RGB a 120 fps), protocollo v2, modulo Zephyr
portabile, app iOS e Android, repository indipendenti.

## Problemi noti (misurati, non risolti)

| Problema | Evidenza | Dove si risolve |
|---|---|---|
| ~~Loop di fault troppo lento (chip ~84 µs invece di 30 sul R4, ~40 sulla Nano 33)~~ **risolto il 16/9**: temporizzazione a scadenza (DWT sul R4, `counter` in polling su Zephyr); verificato dal vivo: 6.0 righe/chip, fault decodificato su entrambe | fit sui run del frame del LED rosso: 16 righe/chip, pacchetto da 1100 righe > macchia (450) | fatto |
| Saturazione: il rosso del R4 satura a ISO minimo; i chip spenti si accorciano di un'esposizione (run ON 36 righe, OFF 6). **Mitigato il 17/9 nel ricevitore**: il nucleo saturo perde i gap da 1 chip ma l'alone intorno li conserva → i profili escludono le colonne che saturano in ≥ 2 righe (`rs_frame.c`, `RS_SAT_LEVEL`). Corpus: 132 → 315 pacchetti (ROI globale), 124 → 337 (multi); clip del fault R4 da 3.5 a ~20 pkt/s | frame del fault, `peak=255 sat=0.19`; replay del corpus | resta lato firmware: chip 45–60 µs o dimming PWM sulle schede molto luminose. Il decoder "a fronti" (`use_edges`) è stato provato e scartato: produceva pacchetti finti tutti a zero |
| Movimento: falsi piloti corrompono la matrice colore (cond 0.9 → 0.05), ROI per frame. **Causa principale trovata il 17/9**: il blocco pilota con P=8 (432 righe) era più alto della macchia → aggancio RGB raro; ora `RS_PILOT_P=4`. Nel sintetico 2-D (`synth2d.py`) l'aggancio arriva al 95 % dei frame fino a 40 px/frame | misura del 15/9 sera; sweep sintetico | verifica dal vivo con nuove registrazioni (le registrazioni "Motion" del corpus sono con P=8 e non possono agganciare) |
| Pochi messaggi con 100 pkt/s | il demo manda solo STATUS ogni 5 s; i falsi positivi del CRC-8 (1/256 dei sync corrotti) avvelenano il sistema lineare e azzerano lo slot. **Recupero fatto il 17/9** (fase 1.2/1.4 senza allungare il pacchetto): anello delle righe grezze, re-soluzione leave-one-out al fallimento del CRC del messaggio, due "strike" su META/CRC | test di corruzione: 55 messaggi recuperati, reset 488 → 97, 0 pacchetti errati | contatore di reset già esposto (`rs_rx_resets`) |
| LED RGB a 3 die: da vicino i tre dischi di colore sono sfalsati di ~40 % del diametro (passo dei die / apertura), con il passo lungo l'asse di scansione nessuna riga contiene i tre impulsi pilota → aggancio RGB impossibile sul R4 | registrazioni del 17/9 mattina: R4 rgb 0 pkt/s, 15 blocchi pilota visibili ma nessuno riconosciuto | **fatto il 17/9**: decodifica diretta dei tre canali camera quando la luce è tricolore e non c'è calibrazione (`rs_rx` modo 2). Corpus 438 → 814 pacchetti; R4 rgb 7.6, 33 rgb 8–50 pkt/s. Piloti ogni 30 ms invece di 100 (3.6 % di overhead) per agganciare più spesso |
| Distanza: a 30 cm la macchia del LED è ~60 righe, il pacchetto ne occupa ~400 → nessuna decodifica possibile | "R4 rgb 30 cm", "Entrambi" | limite fisico con chip da 30 µs: la macchia deve essere alta almeno ~450 righe (≈ 10–12 cm col grandangolo 1×). Alternative: chip più corti (meno righe/chip) o ottica ultra-grandangolare |
| Tracce fantasma ai bordi quando il LED è spento (rumore di colonna allungato dal filtro verticale) | replay multi del corpus: 4 tracce su una scheda sola | **risolto il 17/9**: la segmentazione scarta componenti larghe 1 cella e macchie sotto 48 / min+40 |

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

Stato 17/9: fatti i punti 2 (variante "leave-one-out" nell'assembler invece del chase
sui bit) e 4 (`rs_rx_resets`); il punto 1 (CRC-16) è stato scartato per non allungare
i pacchetti; il punto 3 è sostituito dall'esclusione delle colonne sature.

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

Stato 17/9: primo passo fatto, "ipotesi di timing" nel decoder: il sync da 8 chip
fissa la lunghezza del chip al ~2 %, cioè 1.4 chip di deriva a fine pacchetto
quando il PLL perde i fronti; un pacchetto che fallisce il CRC viene riprovato con
l'orologio del ricevitore (media su molti pacchetti e frame) e con il sync ±3 %,
accettato solo con confidenza doppia. Corpus 814 → 1601 pacchetti, 0 falsi nel
sintetico.

Secondo passo (17/9 pomeriggio): `rs_decode_at` decodifica un pacchetto a una
posizione nota senza cercare il sync, e il ricevitore prova le posizioni sulla
griglia (±67 chip) accanto a ogni pacchetto decodificato. Guadagno modesto sul
corpus (2120 → 2153) perché, misurato con `tools/loss_budget.py` sul simulatore
con verità nota, il decoder prende già il 100 % dei pacchetti disponibili nei
casi puliti e la predizione paga solo con saturazione pesante (sync distrutto,
bit vivi). Le perdite reali sono pacchetti tagliati dal bordo del frame e bit
danneggiati: la predizione della fase tra frame non le recupera, quindi il
modello temporale si ferma qui. Per aumentare i pacchetti per frame la leva è
il protocollo (chip più corti o pacchetti più corti), non il ricevitore.


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

Stato 17/9 pomeriggio: il profilo per traccia include l'alone (righe ±1 altezza,
colonne ±½ larghezza, ritagliato contro le tracce vicine); le colonne sono pesate
con l'energia delle differenze riga-riga (filtro passa-alto adattato alle strisce,
gradini verso la saturazione ignorati); si costruiscono due varianti (con e senza le
colonne saturate) e per ogni frame vince quella da cui il decoder tira fuori più
pacchetti. Corpus multi 1816 → 2349 pacchetti contro 1601 del ROI globale, 8 messaggi
corretti; il multi è ora la scelta giusta di default nell'app. Il confronto tra
varianti si fa ogni 8 frame (o dopo un frame vuoto) perché per-frame portava
l'iPhone a 40 fps; pesi calcolati ogni 4 righe e media solo sulle colonne pesate.
Le tracce che non hanno mai decodificato compaiono solo dopo 12 frame (riflessi
e puntini ai bordi non lampeggiano più come marker).

Stato 17/9 sera: fatti anche i punti 3 e 4. Due luci della stessa scheda si
riconoscono dalla relazione del carosello: la differenza dei seed di due pacchetti
dello stesso slot è uguale alla distanza in pacchetti (righe nel frame più tempo tra
i frame) per il numero di canali, più la differenza di canale, a meno dei tripletti
di controllo; l'evidenza si accumula con decadimento e isteresi, il gruppo prende
l'id minore (`rs_multi_track_group`), i messaggi escono con l'id del gruppo e le
app disegnano una linea tratteggiata tra le luci collegate. Ogni scheda annuncia
`id=xxxx` (FNV a 16 bit dell'id di fabbrica: `RSLog.boardId()`, `rslog_board_id()`)
nello STATUS di boot e in quello periodico della demo; l'app lo mostra sul marker.
Verificato dal vivo: R4 (e844) con RGB e arancione collegati, Nano 33 (55ee)
separata, nessun falso collegamento in 4 s di registrazione.

Stato 17/9: punti 1, 2 e 5 fatti (`rs_frame_segment_rgb`, `rs_multi`, marker
nell'anteprima iOS e Android, tag `src #n` in console; `replay.py --multi` per il
corpus). Restano 3 (fusione di macchie che trasmettono lo stesso pacchetto) e 4.

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

## Fase 4b — Sessioni remote (fatta il 17/9)

L'app apre un server TCP (porta 7777, Impostazioni > Debug per spegnerlo):
statistiche a 5 Hz, messaggi decodificati, comandi `get/set/stats/messages/reset/
frame/record`; `record` registra sul telefono e manda indietro il `.rsrec`.
Dal Mac: `make usb-forward` (pymobiledevice3, tunnel USB) e `make live ARGS="..."`
(`ios/tools/rslive.py`, anche come libreria). Le schede si pilotano con
`tools/board.py r4|n33 "comando"`. Il recorder scrive a 119 fps senza perdere
frame (buffer in pool, scrittura raw su coda in background: LZ4 comprimeva il
rumore solo 1.4× a 15 ms/frame); 2 s = 240 frame = 495 MB, ~20 s via USB.
La modalità registrazione manuale (tasto Record) è in Impostazioni > Debug,
spenta di default; `record` remoto funziona sempre e di default cancella il
file dal telefono dopo il trasferimento.

## Fase 4c — Fault pesato (fatto il 17/9)

Carosello con `rs_tx_set_fault_weight` (peso 3 di default nei loop di morte: 85 % dei
pacchetti al FAULT). Misurato dal vivo sul R4 via sessione remota (`hf` da seriale,
messaggio sul telefono): **FAULT completo dopo 1.3–1.5 s** dal guasto, STATUS a ~4 s,
INFO a ~6 s. Nota: il comando `hf` della demo arma un watchdog da 4 s, quindi il
loop di morte dura 4 s e poi la scheda riparte annunciando il record persistito.

## Fase 5 — Firmware

1. ~~Temporizzazione a scadenza nel loop di fault~~ (fatto il 16/9).
2. ~~Backend di log Zephyr~~ (fatto il 17/9: `CONFIG_RSLOG_LOG_BACKEND`, livello massimo
   inoltrato `CONFIG_RSLOG_LOG_BACKEND_LEVEL`, prefisso del modulo tolto, serve
   `CONFIG_LOG_MODE_DEFERRED`; demo `rslog zlog wrn testo`). ~~`RSLog.printf`~~ (fatto:
   `RSLogClass` è una `Print`, quindi `print/println/printf` → messaggi a `setPrintLevel`).
3. ~~Board id~~ (fatto) + versione nello STATUS; ~~mini backtrace nel fault~~ (fatto: fino a
   3 indirizzi di ritorno trovati sullo stack sopra il frame d'eccezione, log ERROR "bt …"
   copiato nel loop di morte; con il peso 3 del FAULT arriva dopo il FAULT stesso).
4. Port di prova: GIGA R1 (morta) e UNO Q (rimandato: richiede un setup diverso).
5. Dimming PWM per canale: **valutato e rimandato**. Serve una portante ≥ 500 kHz perché
   l'esposizione da 15 µs non veda il PWM (il PWM di `analogWrite` a 490 Hz batterebbe
   con le righe); i pin LED delle Nano non stanno tutti su canali timer adatti, e il
   ricevitore gestisce ormai bene la saturazione (pesi delle colonne, alone).

Ricevitore, 17/9 sera: filtro anti-diafonia nel multi-sorgente (le strisce di un LED
luminoso sfumano su tutta la larghezza del frame: un pacchetto identico nella stessa
riga appartiene alla luce che occupa quelle righe; un pacchetto molto più debole che
segue il carosello di un'altra traccia è la sua fuga) e consegna del messaggio con un
solo CRC quando il sistema è risolto (entrambi restano necessari per il recupero
leave-one-out). Messaggi del corpus 11 → 19, tutti corretti.

## Fase 6 — App

Icona (fatta), registratore (fase 0), vista sorgenti (fase 4). Da fare: storico
persistente dei messaggi, esportazione/condivisione di log e registrazioni, filtro
della console per sorgente, Lab mode sul corpus.

## Nome

Scelto il 17/9: **Blinko** (corto, pronunciabile, "lampeggia"). Il rinominare
(cartelle, librerie `RSLog` → `Blinko`, bundle id, prefissi `rs_`/`rslog_`) si fa in un
colpo solo prima del push su GitHub.

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
