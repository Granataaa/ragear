# 📊 RAGEAR - Report Generazione Query Sintetiche

**Data Esecuzione**: 2026-10-07 14:46:47  
**Modelli Valutati**: mistral-nemo:latest, phi4:latest

## 1. Tabella Sintetica Performance

| Modello | Lezioni Campionate | Successi | Falliti | Query Generate | Tempo Totale | Media / Lezione |
|---|---|---|---|---|---|---|
| **mistral-nemo:latest** | 10 | 10 | 0 | 50 | 486.0s | 48.60s |
| **phi4:latest** | 10 | 10 | 0 | 50 | 811.3s | 81.13s |

## 2. Distribuzione Tipologie di Query

| Modello | Fondazionale | Tecnica | Applicativa | Problem Solving | Orientamento | Altre |
|---|---|---|---|---|---|---|
| **mistral-nemo:latest** | 10 | 10 | 10 | 10 | 10 | 0 |
| **phi4:latest** | 10 | 10 | 10 | 10 | 10 | 0 |

## 3. Confronto Query Generate (Esempio Lezione)

### Lezione: *Sorgenti di informazione di tipo analogico (II)* (*Comunicazioni elettriche*)

#### Modello: `mistral-nemo:latest`

- **FONDAZIONALE**: Sono un principiante e vorrei capire come si forma un segnale televisivo. Potresti consigliarmi un corso che mi aiuti a costruire le basi teoriche?
  *Keywords: formazione del segnale televisivo, immagini in movimento*
- **TECNICA**: Mi interesserebbe approfondire la rappresentazione dei colori nei segnali televisivi. Qual è il corso giusto per imparare a gestire le componenti RGB?
  *Keywords: rappresentazione dei colori, componenti RGB*
- **APPLICATIVA**: Vorrei capire come si possono utilizzare i segnali televisivi in ambito professionale. Quale corso mi consiglia per acquisire competenze pratiche?
  *Keywords: utilizzo dei segnali televisivi, ambiente professionale*
- **PROBLEM_SOLVING**: Ho un problema di sfarfallio nell'immagine della mia telecamera. Quale corso mi aiuta a risolvere questo problema e capire la frequenza di ripetizione delle immagini?
  *Keywords: sfarfallio, frequenza di ripetizione delle immagini*
- **ORIENTAMENTO**: Sono indeciso tra due corsi che trattano segnali elettrici. Quale corso mi consiglia per avere una panoramica completa e decidere il mio piano di studi?
  *Keywords: panoramica sui segnali elettrici, orientamento nel piano di studi*
#### Modello: `phi4:latest`

- **FONDAZIONALE**: Sto cercando un corso che mi aiuti a comprendere i principi fondamentali dei segnali televisivi, in particolare come vengono formati e caratterizzati statisticamente e spettralmente.
  *Keywords: segnali televisivi, formazione del segnale, caratterizzazione statistica e spettrale*
- **TECNICA**: Mi appassiona approfondire i dettagli tecnici sulla rappresentazione delle immagini in movimento nei sistemi televisivi, inclusa la frequenza di ripetizione delle immagini e il principio della persistenza dell'immagine sulla retina.
  *Keywords: rappresentazione del movimento, frequenza di ripetizione, persistenza dell'immagine*
- **APPLICATIVA**: Vorrei acquisire competenze pratiche su come ottimizzare la qualità della trasmissione televisiva, utilizzando parametri oggettivi per valutare e migliorare le prestazioni.
  *Keywords: qualità della trasmissione, parametri di valutazione, ottimizzazione*
- **PROBLEM_SOLVING**: Mi trovo a dover risolvere problemi legati al disturbo dello sfarfallio nelle immagini televisive. Vorrei capire come le frequenze di ripetizione delle immagini influenzano questo fenomeno e quali soluzioni tecniche possono essere implementate.
  *Keywords: sfarfallio, frequenza di ripetizione, soluzioni tecniche*
- **ORIENTAMENTO**: Sono indeciso su quale indirizzo di studio seguire e vorrei esplorare un corso che mi dia una panoramica sui vari aspetti delle comunicazioni elettriche, con particolare attenzione alla rappresentazione dei colori e alla loro riproduzione nei sistemi digitali.
  *Keywords: comunicazioni elettriche, rappresentazione dei colori, sistemi digitali*