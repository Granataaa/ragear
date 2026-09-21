# UNINETTUNO RAGEAR 🎓

> **Intelligent Academic Course Recommender** powered by the **RAGER** algorithm and integrated with the central **UNINETTUNO RAG Engine** (`http://10.10.11.141:5005`).

---

## 🌟 Caratteristiche Principali

- **Architettura Disaccoppiata**: RAGEAR si collega al server RAG centrale tramite client asincrono ad alte prestazioni (`httpx`), sfruttando ChromaDB, Entity Linking su Wikidata e Cross-Encoder.
- **Formula RAGER Accademica**:
  1. **Score Distribution ($Term_1$)**: rilevanza aggregata dei chunk per ogni corso.
  2. **Chunk Rank Factor ($Term_2$)**: pesatura quadratica/smorzata delle posizioni dei chunk nella graduatoria.
  3. **Lesson Rank Factor ($Term_3$)**: copertura percentuale delle lezioni rispetto al totale lezioni del corso.
  4. **Punteggio Finale**: $\text{Score} = Term_1 \times CRF \times LRF$.
- **Sincronizzazione Dinamica del Catalogo**: All'avvio e tramite endpoint dedicato (`POST /api/v1/catalog/sync`), RAGEAR sincronizza corsi e lezioni da `GET /list` del server RAG, adattandosi automaticamente all'ingestione di nuovi corsi e lezioni.
- **Filtraggio Multicriterio**:
  - Filtro per **CFU** (es. 6 CFU, 9 CFU, 12 CFU, intervalli min/max).
  - Filtro per **Facoltà** (Ingegneria, Economia, Giurisprudenza, Lettere, Psicologia, Scienze della Comunicazione).
  - Filtro per **Livello di Laurea** (Triennale, Magistrale).
  - Filtro per **Settore Scientifico Disciplinare** (es. `ING-INF/05`, `SECS-P/08`, ecc.).
- **Interfaccia Web Istituzionale**:
  - Grafica moderna con palette UniNettuno, responsive sia su desktop che smartphone.
  - Chip con esempi rapidi tratti da `queries.txt`.
  - Spiegazione dettagliata per ogni corso: lezioni pertinenti, minutaggio video e link diretti alle lezioni.
  - Monitoraggio in tempo reale dello stato del server RAG (`10.10.11.141:5005`).
- **Container Docker Ultra-Leggero**:
  - Immagine Python 3.11 slim da <150MB, senza dipendenze pesanti da compilare (nessun bisogno di PyTorch o FAISS in locale).

---

## 🚀 Avvio Rapido

### 1. Avvio Locale con Python

```bash
# Installa le dipendenze
pip install -r requirements.txt

# Avvia l'applicazione
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

L'interfaccia web sarà disponibile su **`http://localhost:8000`**.
La documentazione OpenAPI / Swagger sarà consultabile su **`http://localhost:8000/docs`**.

### 2. Avvio con Docker Compose

```bash
docker compose up -d --build
```

---

## ⚙️ Variabili di Configurazione (`.env`)

| Variabile | Default | Descrizione |
|---|---|---|
| `RAG_SERVER_URL` | `http://10.10.11.141:5005` | URL dell'API backend RAG centrale |
| `RAG_FRONTEND_URL` | `http://10.10.11.141:3000` | URL del portale web RAG Explorer |
| `RAG_TIMEOUT` | `25.0` | Timeout in secondi per le chiamate al RAG |
| `DEFAULT_TOP_K` | `50` | Numero predefinito di chunk semantici da valutare |
| `SYNC_CATALOG_ON_STARTUP`| `true` | Sincronizza dinamicamente il catalogo da `GET /list` |
| `CATALOG_PATH` | `data/course_catalog.json`| Percorso file cache del catalogo corsi |

---

## 📡 API Endpoints Principali

- `POST /api/v1/recommend`: Calcola i corsi raccomandati per una query studente con filtri accademici opzionali.
- `GET /api/v1/filters`: Restituisce le facoltà, tipologie di laurea, CFU e settori disponibili nel catalogo.
- `GET /api/v1/courses`: Esplora il catalogo corsi con filtri per facoltà, CFU e ricerca testuale.
- `GET /api/v1/status`: Verifica lo stato di connessione verso `10.10.11.141:5005` e riporta le statistiche del catalogo.
- `POST /api/v1/catalog/sync`: Forza la risincronizzazione dinamica da `GET /list` del server RAG.
- `GET /api/v1/sample-queries`: Restituisce query di esempio realistiche.

---

## 🧪 Benchmark e Test

Per lanciare una batteria di test automatici sulle query realistiche degli studenti:

```bash
python scripts/benchmark_queries.py --limit 5 --top-k 50
```
