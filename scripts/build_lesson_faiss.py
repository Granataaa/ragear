"""
Script per la generazione dell'indice FAISS delle Lezioni e del relativo catalogo metadati JSON.
Utilizza un modello di embedding Long-Context (default: BAAI/bge-m3, 8192 token).
Supporta auto-detection hardware (Apple Silicon MPS, NVIDIA CUDA, CPU),
checkpointing progressivo a blocchi (resume automatico), e normalizzazione L2 (Cosine Similarity).
"""

import os
import re
import sys
import csv
import json
import time
import shutil
import argparse
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional

import numpy as np

# Compatibilità encoding console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_cfu(raw_cfu: str) -> Optional[int]:
    if not raw_cfu:
        return None
    m = re.search(r'(\d+)', raw_cfu)
    return int(m.group(1)) if m else None


def clean_settore(raw_settore: str) -> str:
    if not raw_settore:
        return ""
    s = re.sub(r'^settore:\s*', '', raw_settore.strip(), flags=re.IGNORECASE)
    return s.strip()


def parse_lesson_number(filename: str, title: str) -> Optional[int]:
    if filename:
        m = re.search(r'Lez0*(\d+)', filename, re.IGNORECASE)
        if m:
            return int(m.group(1))
    if title:
        m = re.search(r'(?:Lezione|Lez\.?)\s*0*(\d+)', title, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def extract_topic_links(row: Dict[str, str]) -> List[Dict[str, str]]:
    topics = []
    for i in range(1, 16):
        topic_text = row.get(f"topic_{i}", "").strip()
        topic_link = row.get(f"topic_link_{i}", "").strip()
        if topic_text:
            time_match = re.search(r"'([^']+)'", topic_link)
            timestamp = time_match.group(1) if time_match else ""
            topics.append({
                "index": i,
                "topic": topic_text,
                "timestamp": timestamp,
                "raw_link": topic_link
            })
    return topics


def load_and_group_dataset(csv_path: Path, transcripts_dir: Path, limit: int = 0) -> List[Dict[str, Any]]:
    """
    Legge output_lezioni_pulito.csv, fa match 1:1 con i file .txt in transcripts_all,
    raggruppa le righe duplicate (lezioni condivise tra più CdL) e colleziona tutti i metadati.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"File CSV non trovato: {csv_path.resolve()}")
    if not transcripts_dir.exists():
        raise FileNotFoundError(f"Directory trascrizioni non trovata: {transcripts_dir.resolve()}")

    disk_files = set(f.name for f in transcripts_dir.glob("*.txt"))
    print(f"[Dataset] Trovati {len(disk_files)} file di trascrizione .txt su disco in '{transcripts_dir}'.")

    lessons_map: Dict[str, Dict[str, Any]] = {}

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get("filename", "").strip() or row.get("hiddenFilename", "").strip()
            if not fn:
                continue

            m = re.search(r'([0-9a-fA-F-]{36})/([^/?#]+)', fn)
            if not m:
                continue

            guid = m.group(1)
            raw_lez = m.group(2).split(".")[0]
            unquoted_lez = urllib.parse.unquote(raw_lez)

            matched_file = None
            for candidate in [f"{guid}_{raw_lez}.txt", f"{guid}_{unquoted_lez}.txt"]:
                if candidate in disk_files:
                    matched_file = candidate
                    break

            if not matched_file:
                continue

            lesson_uid = matched_file.replace(".txt", "")

            if lesson_uid not in lessons_map:
                lessons_map[lesson_uid] = {
                    "lesson_uid": lesson_uid,
                    "guid": guid,
                    "transcript_filename": matched_file,
                    "transcript_path": str((transcripts_dir / matched_file).as_posix()),
                    "rows": []
                }

            lessons_map[lesson_uid]["rows"].append(row)

    print(f"[Dataset] Mappate con successo {len(lessons_map)} lezioni uniche da '{csv_path.name}'.")

    # Ordina le chiavi deterministicamente
    sorted_uids = sorted(lessons_map.keys())
    if limit > 0:
        print(f"[Dry-run] Limitazione a {limit} lezioni prima del caricamento delle trascrizioni.")
        sorted_uids = sorted_uids[:limit]

    # Costruisci record completi
    from tqdm import tqdm
    structured_lessons: List[Dict[str, Any]] = []
    
    for uid in tqdm(sorted_uids, desc="[Dataset] Lettura trascrizioni", unit="lez"):
        data = lessons_map[uid]
        rows = data["rows"]
        # Riferimento primario (prima riga)
        primary = rows[0]

        course_title = primary.get("titoloCorso", "").strip()
        lesson_title = primary.get("titoloLezione", "").strip()
        docente = primary.get("docenteVideo", "").strip()
        raw_cfu = primary.get("CFU", "").strip()
        cfu_val = parse_cfu(raw_cfu)
        settore = clean_settore(primary.get("settore", ""))
        link_lezione = primary.get("link_lezione", "").strip()
        filename = primary.get("filename", "").strip()
        hidden_filename = primary.get("hiddenFilename", "").strip()
        video_url = filename or hidden_filename

        lesson_num = parse_lesson_number(video_url, lesson_title)

        # Set aggregati per lezioni condivise su più corsi di laurea
        facolta_set = sorted(list(set(r.get("facolta", "").strip() for r in rows if r.get("facolta", "").strip())))
        cdl_set = sorted(list(set(r.get("corso_laurea", "").strip() for r in rows if r.get("corso_laurea", "").strip())))
        tipologia_set = sorted(list(set(r.get("tipologia_corso_laurea", "").strip() for r in rows if r.get("tipologia_corso_laurea", "").strip())))
        classi_set = sorted(list(set(r.get("classe_laurea", "").strip() for r in rows if r.get("classe_laurea", "").strip())))
        indirizzi_set = sorted(list(set(r.get("indirizzo", "").strip() for r in rows if r.get("indirizzo", "").strip())))

        # Estrai topics
        topic_items = extract_topic_links(primary)
        topic_texts = [t["topic"] for t in topic_items]

        # Leggi trascrizione
        t_path = Path(data["transcript_path"])
        try:
            with open(t_path, "r", encoding="utf-8") as tf:
                transcript_text = tf.read().strip()
        except Exception as e:
            print(f"[Warning] Impossibile leggere {t_path}: {e}")
            transcript_text = ""

        lesson_record = {
            "lesson_uid": uid,
            "guid": data["guid"],
            "lesson_number": lesson_num,
            "titoloLezione": lesson_title,
            "titoloCorso": course_title,
            "docenteVideo": docente,
            "CFU": cfu_val,
            "raw_cfu": raw_cfu,
            "settore": settore,
            "link_lezione": link_lezione,
            "video_url": video_url,
            "topics": topic_texts,
            "topic_details": topic_items,
            "facolta_set": facolta_set,
            "corsi_laurea_set": cdl_set,
            "tipologia_corso_laurea_set": tipologia_set,
            "classi_laurea_set": classi_set,
            "indirizzi_set": indirizzi_set,
            "transcript_filename": data["transcript_filename"],
            "transcript_path": data["transcript_path"],
            "transcript_char_count": len(transcript_text),
            "transcript_word_count": len(transcript_text.split()),
            "transcript_text": transcript_text,
            "all_csv_records": rows
        }

        structured_lessons.append(lesson_record)

    # Ordina deterministicamente per uid
    structured_lessons.sort(key=lambda x: x["lesson_uid"])
    return structured_lessons


def get_device(requested_device: str) -> str:
    import torch
    if requested_device != "auto":
        return requested_device

    if torch.backends.mps.is_available():
        print("[Hardware] Rilevato Apple Silicon GPU (MPS) -> Esecuzione su MPS.")
        return "mps"
    elif torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"[Hardware] Rilevata GPU NVIDIA: {device_name} ({vram_gb:.1f} GB VRAM) -> Esecuzione su CUDA.")
        return "cuda"
    else:
        print("[Hardware] Nessun acceleratore hardware rilevato -> Esecuzione su CPU.")
        return "cpu"


def get_default_batch_size(device: str) -> int:
    if device == "mps":
        return 4  # Ideale per Mac con 16GB
    elif device == "cuda":
        return 2  # Prudente per GPU 4GB
    else:
        return 2  # CPU


def compute_embeddings(
    lessons: List[Dict[str, Any]],
    model_name: str,
    max_length: int,
    batch_size: int,
    device: str,
    cache_dir: Path,
    use_fp16: bool = True,
    include_header: bool = True
) -> np.ndarray:
    """
    Calcola gli embeddings con BGE-M3 (o altro modello HuggingFace/SentenceTransformers),
    usando batch checkpointing progressivo per garantire resume istantaneo in caso di interruzione.
    Supporta mezza precisione (FP16) su Apple Silicon MPS e CUDA per dimezzare la RAM e massimizzare il throughput.
    """
    import torch
    from sentence_transformers import SentenceTransformer
    from tqdm import tqdm

    cache_dir.mkdir(parents=True, exist_ok=True)
    num_samples = len(lessons)
    num_batches = (num_samples + batch_size - 1) // batch_size

    manifest_file = cache_dir / "cache_manifest.json"
    current_config = {
        "num_samples": num_samples,
        "batch_size": batch_size,
        "model_name": model_name,
        "max_length": max_length,
        "use_fp16": use_fp16 and device in ("mps", "cuda")
    }

    # Verifica compatibilità della cache esistente con i parametri correnti
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as mf:
                old_config = json.load(mf)
            if old_config != current_config:
                print(f"[Checkpoint] Parametri cambiati rispetto ai checkpoint precedenti (vecchi: {old_config}, attuali: {current_config}).")
                print("[Checkpoint] Reset della cache parziale per evitare disallineamenti di vettori.")
                for old_npy in cache_dir.glob("batch_*.npy"):
                    old_npy.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Warning] Impossibile verificare cache_manifest: {e}")
    else:
        # Se esistono file .npy ma non manifest, controlla se la prima forma combacia con batch_size
        existing_batches = list(cache_dir.glob("batch_*.npy"))
        if existing_batches:
            try:
                first_b = np.load(existing_batches[0])
                if first_b.shape[0] != batch_size and len(existing_batches) > 1:
                    print(f"[Checkpoint] Batch size mutato ({first_b.shape[0]} -> {batch_size}). Reset della cache parziale...")
                    for old_npy in existing_batches:
                        old_npy.unlink(missing_ok=True)
            except Exception:
                pass

    with open(manifest_file, "w", encoding="utf-8") as mf:
        json.dump(current_config, mf, indent=2)

    is_fp16_active = use_fp16 and device in ("mps", "cuda")
    print(f"\n[Embedding] Modello: '{model_name}' | Max Context: {max_length} token | FP16: {is_fp16_active}")
    print(f"[Embedding] Device: {device} | Batch Size: {batch_size} | Totale campioni: {num_samples} ({num_batches} batch)")
    print(f"[Embedding] Cache checkpoint: {cache_dir.resolve()}")

    # Prepara i testi da inviare al modello
    texts = []
    for l in lessons:
        body = l["transcript_text"]
        if include_header:
            header_parts = []
            if l["titoloCorso"]:
                header_parts.append(f"Corso: {l['titoloCorso']}")
            if l["settore"]:
                header_parts.append(f"Settore: {l['settore']}")
            if l["titoloLezione"]:
                header_parts.append(f"Lezione: {l['titoloLezione']}")
            if l["topics"]:
                header_parts.append(f"Argomenti: {', '.join(l['topics'][:5])}")
            
            header = " | ".join(header_parts) + "\n\n"
            full_input = header + body
        else:
            full_input = body
        texts.append(full_input)

    # Identifica i batch già calcolati
    completed_batches = set()
    for batch_file in cache_dir.glob("batch_*.npy"):
        try:
            b_idx = int(batch_file.stem.split("_")[1])
            completed_batches.add(b_idx)
        except ValueError:
            pass

    if completed_batches:
        print(f"[Checkpoint] Trovati {len(completed_batches)}/{num_batches} batch già calcolati in cache. Ripresa da checkpoint!")

    # Inizializza il modello solo se ci sono batch rimanenti
    missing_batches = [b for b in range(num_batches) if b not in completed_batches]
    
    if missing_batches:
        print(f"[Embedding] Caricamento modello '{model_name}' su device '{device}' (precisione: {'float16' if is_fp16_active else 'float32'})...")
        start_load = time.time()
        model_kwargs = {}
        if is_fp16_active:
            model_kwargs["torch_dtype"] = torch.float16

        model = SentenceTransformer(model_name, device=device, model_kwargs=model_kwargs)
        model.max_seq_length = max_length
        print(f"[Embedding] Modello caricato in {time.time() - start_load:.1f}s.")

        pbar = tqdm(total=num_batches, initial=len(completed_batches), desc="Embedding lezioni")

        for b_idx in range(num_batches):
            batch_file = cache_dir / f"batch_{b_idx:05d}.npy"
            if b_idx in completed_batches:
                continue

            start_idx = b_idx * batch_size
            end_idx = min(start_idx + batch_size, num_samples)
            batch_texts = texts[start_idx:end_idx]

            # encode con normalizzazione L2 (Cosine Similarity)
            batch_emb = model.encode(
                batch_texts,
                batch_size=len(batch_texts),
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True
            ).astype(np.float32)

            # Salva checkpoint
            np.save(batch_file, batch_emb)
            pbar.update(1)

        pbar.close()

    # Raccogli e concatena tutti i batch
    print("\n[Checkpoint] Assemblaggio di tutti i blocchi vettoriali...")
    all_embeddings_list = []
    for b_idx in range(num_batches):
        batch_file = cache_dir / f"batch_{b_idx:05d}.npy"
        if not batch_file.exists():
            raise RuntimeError(f"File di batch mancante: {batch_file}")
        all_embeddings_list.append(np.load(batch_file))

    all_embeddings = np.vstack(all_embeddings_list)
    print(f"[Embedding] Assemblaggio completato! Matrice vettoriale: {all_embeddings.shape} (dtype: {all_embeddings.dtype})")
    return all_embeddings


def save_faiss_and_metadata(
    lessons: List[Dict[str, Any]],
    embeddings: np.ndarray,
    output_dir: Path
):
    """
    Costruisce l'indice FAISS IndexFlatIP (Cosine Similarity) e salva il file di metadati JSON.
    """
    import faiss

    output_dir.mkdir(parents=True, exist_ok=True)
    num_lessons, dim = embeddings.shape

    # 1. Salva array numpy grezzo di backup
    npy_path = output_dir / "lesson_embeddings.npy"
    print(f"[Export] Salvataggio array vettoriale numpy su '{npy_path}'...")
    np.save(npy_path, embeddings)

    # 2. Crea indice FAISS Flat Inner Product
    # Dato che i vettori sono normalizzati L2, Inner Product == Cosine Similarity
    print(f"[Export] Creazione indice FAISS IndexFlatIP (dimensione: {dim}, campioni: {num_lessons})...")
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss_path = output_dir / "lesson_faiss.index"
    print(f"[Export] Scrittura indice binario FAISS su '{faiss_path}'...")
    faiss.write_index(index, str(faiss_path))

    # 3. Prepara e salva i metadati JSON
    json_path = output_dir / "lesson_metadata.json"
    print(f"[Export] Generazione catalogo metadati su '{json_path}'...")

    metadata_list = []
    for faiss_id, l in enumerate(lessons):
        item = {
            "faiss_id": faiss_id,
            "lesson_uid": l["lesson_uid"],
            "guid": l["guid"],
            "lesson_number": l["lesson_number"],
            "titoloLezione": l["titoloLezione"],
            "titoloCorso": l["titoloCorso"],
            "docenteVideo": l["docenteVideo"],
            "CFU": l["CFU"],
            "raw_cfu": l["raw_cfu"],
            "settore": l["settore"],
            "link_lezione": l["link_lezione"],
            "video_url": l["video_url"],
            "topics": l["topics"],
            "topic_details": l["topic_details"],
            "facolta_set": l["facolta_set"],
            "corsi_laurea_set": l["corsi_laurea_set"],
            "tipologia_corso_laurea_set": l["tipologia_corso_laurea_set"],
            "classi_laurea_set": l["classi_laurea_set"],
            "indirizzi_set": l["indirizzi_set"],
            "transcript_filename": l["transcript_filename"],
            "transcript_path": l["transcript_path"],
            "transcript_char_count": l["transcript_char_count"],
            "transcript_word_count": l["transcript_word_count"],
            "all_csv_records": l["all_csv_records"]
        }
        metadata_list.append(item)

    with open(json_path, mode="w", encoding="utf-8") as f:
        json.dump(metadata_list, f, ensure_ascii=False, indent=2)

    # 4. Statistiche finali
    faiss_size_mb = faiss_path.stat().st_size / (1024 * 1024)
    json_size_mb = json_path.stat().st_size / (1024 * 1024)
    npy_size_mb = npy_path.stat().st_size / (1024 * 1024)

    print("\n" + "=" * 80)
    print("[OK] GENERAZIONE INDICE FAISS & METADATI COMPLETATA CON SUCCESSO!")
    print(f"   * Lezioni indicizzate: {num_lessons}")
    print(f"   * Dimensione embedding: {dim}")
    print(f"   * Indice FAISS:        {faiss_path.name} ({faiss_size_mb:.2f} MB)")
    print(f"   * Metadati JSON:       {json_path.name} ({json_size_mb:.2f} MB)")
    print(f"   * Vettori NumPy:       {npy_path.name} ({npy_size_mb:.2f} MB)")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Costruisce l'indice FAISS e i metadati per le lezioni Uninettuno.")
    parser.add_argument("--csv-path", type=str, default="output_lezioni_pulito.csv", help="Percorso del CSV pulito")
    parser.add_argument("--transcripts-dir", type=str, default="transcripts_all", help="Directory con le trascrizioni .txt")
    parser.add_argument("--output-dir", type=str, default="data", help="Directory di output per index e metadata")
    parser.add_argument("--model-name", type=str, default="BAAI/bge-m3", help="Nome modello HuggingFace (es. BAAI/bge-m3)")
    parser.add_argument("--max-length", type=int, default=8192, help="Context window massima per token (default: 8192)")
    parser.add_argument("--batch-size", type=int, default=0, help="Batch size (0 = auto-detect in base all'hardware)")
    parser.add_argument("--device", type=str, default="auto", choices=["auto", "mps", "cuda", "cpu"], help="Device hardware")
    parser.add_argument("--fp16", dest="fp16", action="store_true", default=True, help="Usa mezza precisione FP16 su MPS/CUDA (default: True)")
    parser.add_argument("--no-fp16", dest="fp16", action="store_false", help="Disabilita FP16 e forza calcolo in FP32")
    parser.add_argument("--no-header", action="store_true", help="Non includere il blocco intestazione (titolo, corso, SSD) nella trascrizione")
    parser.add_argument("--clean-cache", action="store_true", help="Elimina i checkpoint intermedi precedenti e ricalcola da zero")
    parser.add_argument("--limit", type=int, default=0, help="Limita il numero di lezioni per un dry-run di test (0 = tutte)")

    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    transcripts_dir = Path(args.transcripts_dir)
    output_dir = Path(args.output_dir)
    cache_dir = output_dir / "embeddings_cache"

    if args.clean_cache and cache_dir.exists():
        print(f"[Cache] Rimozione cache precedente su '{cache_dir}'...")
        shutil.rmtree(cache_dir)

    # 1. Carica e raggruppa il dataset
    lessons = load_and_group_dataset(csv_path, transcripts_dir, limit=args.limit)

    # 2. Configura Device e Batch size
    device = get_device(args.device)
    batch_size = args.batch_size if args.batch_size > 0 else get_default_batch_size(device)

    # 3. Calcola Embeddings con Checkpointing
    embeddings = compute_embeddings(
        lessons=lessons,
        model_name=args.model_name,
        max_length=args.max_length,
        batch_size=batch_size,
        device=device,
        cache_dir=cache_dir,
        use_fp16=args.fp16,
        include_header=not args.no_header
    )

    # 4. Salva FAISS e Metadati
    save_faiss_and_metadata(lessons, embeddings, output_dir)


if __name__ == "__main__":
    main()
