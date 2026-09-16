# Calibrazione del rolling shutter

Il decoder è autocalibrante (misura le righe-per-chip dal sync di ogni
pacchetto), ma per scegliere `T_chip` e sapere quanti bit entrano in un
fotogramma conviene misurare una volta il **tempo di riga** `t_row` della
camera, con il metodo dell'articolo di Joan Charmant.

## Procedura

1. Flash `firmware/sketches/strobe_calib` (onda quadra a 2000 Hz su tutti i
   LED) oppure invia `strobe 2000` alla demo via seriale.
2. Nell'app apri **Lab**, attiva *Strobe calibration mode*, imposta 2000 Hz.
3. Avvicina il telefono al LED (1–3 cm) finché la macchia riempie il profilo.
4. Leggi:
   - **Band period** `P` (righe per periodo dello strobe)
   - **Row time** `t_row = 1 / (f_strobe · P)`
   - **Frame readout** `t_row · H`
   - **Peak strength** per i due assi: se le bande sono sull'altro asse
     (telefono/sensore orientati diversamente), premi *switch*.

## Scelta di `T_chip`

- serve `T_chip ≥ 4 · t_row` (almeno 4 righe per chip);
- l'esposizione deve essere `≤ T_chip` (meglio `≤ T_chip/2`);
- l'altezza del pacchetto è `59 · T_chip / t_row` righe: deve essere
  **inferiore all'altezza della macchia**, altrimenti nessun pacchetto entra
  intero in un frame.

Esempio: `t_row = 10 µs`, macchia di 700 righe → `T_chip = 100 µs` dà
pacchetti alti 590 righe (ok, ~0.2 pacchetti/frame), `T_chip = 60 µs` dà 354
righe (~1 pacchetto/frame). Nel firmware: `chip 60` via seriale o
`cfg.chip_us = 60`.

## Verifica del segnale dati

In **Live**, con la demo in esecuzione:
- il profilo giallo mostra le bande; la statistica *rows/chip* si popola
  appena arrivano pacchetti validi;
- *pkt/s* > 0 e le barre degli slot si riempiono; i messaggi compaiono nella
  Console con feedback aptico.

Se *contrast* è alto ma non arrivano pacchetti: esposizione troppo lunga
(chip sfumati), oppure macchia più bassa dell'altezza del pacchetto
(avvicinati o riduci `chip`), oppure asse di scansione sbagliato (Lab).

## Risultati misurati (2026-09-15, iPhone 14, camera wide, 1920×1080 @ 60 fps)

| Grandezza | Valore |
|---|---|
| esposizione minima | **19 µs** (ISO min 34) |
| tempo di riga `t_row` | **5.1 µs** (30 µs/chip → 5.9 righe/chip) |
| lettura del frame | ≈ 5.5 ms su 16.7 ms di periodo (33 % di copertura) |
| asse di scansione | righe del buffer nativo (bande orizzontali in landscape) |
| `T_chip` scelto | **30 µs** (esposizione = 0.63 chip; 16.6 kbit/s lordi) |
| altezza pacchetto | 59 × 5.9 ≈ 350 righe |
| pacchetti decodificati | 33–38 pkt/s con la scheda a ~5 cm (macchia ≈ 170 righe + alone) |
| chip nel loop bit-bang (fault) | ≈ 38 µs (7.6 righe/chip): il ricevitore si adatta da solo |

Con `T_chip = 100 µs` (valore iniziale) il pacchetto sarebbe alto 1180 righe,
più dell'intero frame: nessun pacchetto decodificabile. La calibrazione è
quindi essenziale per ogni nuova camera.
