#!/usr/bin/env python3
"""
RAGEAR - Synthetic Course Recommendation Query Generator
Generates realistic student course recommendation queries from lesson transcripts using local LLMs via Ollama.

Features:
- Random sampling of N lessons from lesson_metadata.json (with reproducible seed).
- Structured output: source transcript & course metadata wrapped around the generated queries.
- Multi-model sequential execution: runs Model 1 -> stops Model 1 (frees VRAM) -> runs Model 2.
- Robust JSON extraction: discards any preambles, markdown formatting, or postambles.
- Schema validation with retry on malformed outputs.
- Comprehensive end-of-run comparative report (console & Markdown file).
"""

import os
import re
import sys
import json
import time
import random
import argparse
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# System Prompt explicitly instructing the model to act as a student seeking course recommendations
SYSTEM_PROMPT = """Sei un generatore esperto di query di studenti universitari per un sistema di Course Recommendation accademico (RAG).

OBIETTIVO:
Data la trascrizione di una lezione universitaria e i relativi metadati accademici (titolo corso, facoltà, titolo lezione, settore), genera esattamente 5 query realistiche di studenti che descrivono i propri interessi e bisogni formativi per farsi raccomandare il corso accademico più adatto.

REGOLE RIGIDE (COSA NON FARE):
- NON fare domande nozionistiche da esame o di verifica (ESEMPI SBAGLIATI: "Cos'è un protone?", "Come si calcola la massa?", "Chi ha inventato il transistor?").
- NON citare MAI la lezione, il video, il professore, le slide o la trascrizione. NON dire mai frasi come "in questa lezione", "gli argomenti di questa lezione" o "il docente spiega" (ricorda: lo studente non ha visto la lezione, sta solo cercando un corso che tratti quegli argomenti nel suo piano di studi!).
- NON menzionare il titolo esatto del corso nella query (la query deve esprimere bisogni e argomenti, non il nome dell'esame).

REGOLE DI STILE E TONO:
- Scrivi in prima persona in italiano naturale (es: "Sto cercando un corso che...", "Mi appassiona...", "Vorrei acquisire competenze su...", "Vorrei capire come risolvere...").
- Lo studente esprime argomenti di interesse, dubbi formativi, competenze da acquisire o scenari pratici riconducibili ai contenuti della lezione.

DEVI GENERARE ESATTAMENTE QUESTE 5 TIPOLOGIE:
1. "fondazionale": Principiante che vuole costruire o consolidare le basi teoriche e i concetti primi.
2. "tecnica": Studente con basi che cerca approfondimenti specifici, formule, modelli o terminologia tecnica avanzata.
3. "applicativa": Studente orientato al mondo del lavoro, alla pratica ingegneristica o all'impatto industriale/aziendale.
4. "problem_solving": Studente che parte da una sfida o problema concreto da risolvere (ottimizzazione, guasti, analisi).
5. "orientamento": Studente indeciso che cerca una panoramica formativa o un collegamento interdisciplinare per orientare il proprio piano di studi.

FORMATO DI RISPOSTA:
Devi restituire ESCLUSIVAMENTE un oggetto JSON valido (senza testo introduttivo o conclusivo) con la seguente struttura esatta:
{
  "queries": [
    {
      "type": "fondazionale",
      "query_text": "Testo naturale della query dello studente...",
      "key_topics": ["argomento1", "argomento2"]
    },
    {
      "type": "tecnica",
      "query_text": "...",
      "key_topics": ["..."]
    },
    {
      "type": "applicativa",
      "query_text": "...",
      "key_topics": ["..."]
    },
    {
      "type": "problem_solving",
      "query_text": "...",
      "key_topics": ["..."]
    },
    {
      "type": "orientamento",
      "query_text": "...",
      "key_topics": ["..."]
    }
  ]
}
"""

REQUIRED_TYPES = {"fondazionale", "tecnica", "applicativa", "problem_solving", "orientamento"}


def stop_ollama_model(model_name: str) -> bool:
    """Stops a model in Ollama to immediately release VRAM/RAM."""
    print(f"\n[VRAM Cleanup] Arresto del modello '{model_name}' da memoria GPU/RAM...")
    try:
        # 1. Direct CLI stop command
        res = subprocess.run(
            ["ollama", "stop", model_name],
            capture_output=True,
            text=True,
            timeout=15
        )
        if res.returncode == 0:
            print(f"[VRAM Cleanup] Modello '{model_name}' scaricato con successo.")
        else:
            print(f"[VRAM Cleanup] CLI stop warning: {res.stderr.strip()}")
    except Exception as e:
        print(f"[VRAM Cleanup] Fallback API stop ({e})...")

    # 2. API fallback (keep_alive: 0 unloads the model immediately)
    try:
        req_data = {"model": model_name, "keep_alive": 0}
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=json.dumps(req_data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception:
        pass

    time.sleep(2)
    return True


def call_ollama(model_name: str, prompt: str, system: str, temperature: float = 0.7, timeout: int = 180) -> str:
    """Calls Ollama HTTP API with JSON format enforcement."""
    payload = {
        "model": model_name,
        "system": system,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 8192
        }
    }

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res.get("response", "")


def extract_and_validate_json(raw_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Robust JSON extractor:
    - Strips markdown code blocks (```json ... ```)
    - Strips preambles, chat chatter, or trailing explanations
    - Validates schema (dict, 'queries' key, items with 'type' and 'query_text')
    """
    if not raw_text or not raw_text.strip():
        return None, "Risposta vuota dal modello"

    text = raw_text.strip()

    # Pattern 1: Markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
    else:
        # Pattern 2: Find outermost braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1].strip()
        else:
            return None, "Nessuna struttura JSON racchiusa tra parentesi graffe {} trovata"

    # Attempt parse
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        # Try minor cleanup (trailing commas)
        cleaned = re.sub(r",\s*([\}\]])", r"\1", candidate)
        try:
            data = json.loads(cleaned)
        except Exception:
            return None, f"Errore di decodifica JSON: {e}"

    if not isinstance(data, dict):
        return None, "Il JSON principale non è un dizionario"

    if "queries" not in data or not isinstance(data["queries"], list):
        return None, "Chiave 'queries' mancante o non è una lista"

    queries = data["queries"]
    if len(queries) == 0:
        return None, "La lista 'queries' è vuota"

    valid_queries = []
    for idx, q in enumerate(queries):
        if not isinstance(q, dict):
            continue
        q_text = str(q.get("query_text", "")).strip()
        q_type = str(q.get("type", "")).strip().lower()
        if not q_text:
            continue
        key_topics = q.get("key_topics", [])
        if not isinstance(key_topics, list):
            key_topics = [str(key_topics)]

        valid_queries.append({
            "type": q_type or "generale",
            "query_text": q_text,
            "key_topics": [str(t).strip() for t in key_topics if str(t).strip()]
        })

    if not valid_queries:
        return None, "Nessuna query valida con 'query_text' valorizzato"

    return {"queries": valid_queries}, None


def load_lessons_pool(metadata_path: str = "data/lesson_metadata.json") -> List[Dict[str, Any]]:
    """Loads all valid lessons from metadata that have an existing transcript file."""
    meta_file = Path(metadata_path)
    if not meta_file.exists():
        raise FileNotFoundError(f"File metadati non trovato: {metadata_path}")

    with open(meta_file, "r", encoding="utf-8") as f:
        all_metadata = json.load(f)

    valid_lessons = []
    for item in all_metadata:
        transcript_path = item.get("transcript_path")
        if not transcript_path:
            continue
        p = Path(transcript_path)
        if not p.exists():
            # Check relative to repo
            p = Path("..") / transcript_path
            if not p.exists():
                continue

        # Check size > 800 chars
        try:
            if p.stat().st_size < 800:
                continue
        except Exception:
            continue

        valid_lessons.append(item)

    print(f"[Catalogo] Trovate {len(valid_lessons)} lezioni con trascrizione valida su disco.")
    return valid_lessons


def sample_lessons(
    lessons_pool: List[Dict[str, Any]],
    n: int = 10,
    seed: Optional[int] = 42,
    sample_file_path: Optional[str] = "data/sampled_lessons.json"
) -> List[Dict[str, Any]]:
    """Selects N random lessons or loads from a shared sample file."""
    if sample_file_path and Path(sample_file_path).exists():
        print(f"[Campionamento] Caricamento del campione pre-esistente da: {sample_file_path}")
        with open(sample_file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    if seed is not None:
        random.seed(seed)

    sampled = random.sample(lessons_pool, min(n, len(lessons_pool)))

    if sample_file_path:
        Path(sample_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(sample_file_path, "w", encoding="utf-8") as f:
            json.dump(sampled, f, indent=2, ensure_ascii=False)
        print(f"[Campionamento] Salvate {len(sampled)} lezioni campione in: {sample_file_path}")

    return sampled


def run_generation_for_model(
    model_name: str,
    lessons: List[Dict[str, Any]],
    max_chars: int = 10000,
    max_retries: int = 2
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Executes query generation across all sampled lessons for a single model."""
    print(f"\n{'='*80}")
    print(f" AVVIO GENERAZIONE CON MODELLO: {model_name}")
    print(f" Numero lezioni da processare: {len(lessons)}")
    print(f"{'='*80}")

    records = []
    stats = {
        "model": model_name,
        "total_lessons": len(lessons),
        "successful_lessons": 0,
        "failed_lessons": 0,
        "total_queries_generated": 0,
        "typology_counts": {},
        "elapsed_seconds": 0.0,
        "avg_seconds_per_lesson": 0.0,
        "errors": []
    }

    start_total_time = time.time()

    for idx, lesson in enumerate(lessons, start=1):
        transcript_file = lesson.get("transcript_path", "")
        p = Path(transcript_file)
        if not p.exists():
            p = Path("..") / transcript_file

        course_title = lesson.get("titoloCorso", "N/D")
        lesson_title = lesson.get("titoloLezione", "N/D")
        settore = lesson.get("settore", "N/D")
        facolta = lesson.get("facolta_set", ["N/D"])
        facolta_str = facolta[0] if isinstance(facolta, list) and facolta else str(facolta)

        print(f"\n[{idx}/{len(lessons)}] Lezione: '{lesson_title}' | Corso: '{course_title}'")

        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()
        except Exception as e:
            print(f"   [ERRORE LETTURA] {p}: {e}")
            stats["failed_lessons"] += 1
            stats["errors"].append({"lesson": lesson_title, "error": str(e)})
            continue

        transcript_snippet = raw_text[:max_chars].strip()

        user_prompt = f"""INFORMAZIONI ACCADEMICHE:
- Corso di Laurea / Facoltà: {facolta_str}
- Corso: {course_title}
- Titolo Lezione: {lesson_title}
- Settore Scientifico Disciplinare: {settore}

ESTRATTO TRASCRIZIONE LEZIONE:
\"\"\"
{transcript_snippet}
\"\"\"

Genera le 5 query richieste rispettando rigorosamente le 5 tipologie e il formato JSON:"""

        success = False
        parsed_data = None
        err_msg = ""
        lesson_start = time.time()

        for attempt in range(1, max_retries + 1):
            try:
                temp = 0.7 if attempt == 1 else 0.4
                print(f"   Invocazione Ollama ({model_name}, attempt {attempt}/{max_retries})...", end=" ", flush=True)
                raw_response = call_ollama(model_name, user_prompt, SYSTEM_PROMPT, temperature=temp)
                parsed_data, err_msg = extract_and_validate_json(raw_response)

                if parsed_data:
                    lesson_elapsed = time.time() - lesson_start
                    print(f"OK! ({lesson_elapsed:.2f}s, {len(parsed_data['queries'])} query estratte)")
                    success = True
                    break
                else:
                    print(f"JSON NON VALIDO: {err_msg}")
            except Exception as e:
                print(f"ERRORE CHIAMATA: {e}")
                err_msg = str(e)

        if success and parsed_data:
            stats["successful_lessons"] += 1
            queries = parsed_data["queries"]
            stats["total_queries_generated"] += len(queries)

            for q in queries:
                t = q["type"]
                stats["typology_counts"][t] = stats["typology_counts"].get(t, 0) + 1

            record = {
                "source_transcript": str(lesson.get("transcript_filename") or p.name),
                "transcript_path": str(lesson.get("transcript_path")),
                "lesson_uid": lesson.get("lesson_uid"),
                "titoloCorso": course_title,
                "titoloLezione": lesson_title,
                "settore": settore,
                "facolta": facolta,
                "cfu": lesson.get("CFU"),
                "model": model_name,
                "generated_at": datetime.now().isoformat(),
                "queries": queries
            }
            records.append(record)
        else:
            stats["failed_lessons"] += 1
            stats["errors"].append({"lesson": lesson_title, "error": err_msg})
            print(f"   [FALLIMENTO DEFINITIVO] Nessuna query generata per questa lezione.")

    total_elapsed = time.time() - start_total_time
    stats["elapsed_seconds"] = round(total_elapsed, 2)
    stats["avg_seconds_per_lesson"] = round(total_elapsed / max(1, len(lessons)), 2)

    return records, stats


def print_and_save_report(
    model_stats: List[Dict[str, Any]],
    all_records: Dict[str, List[Dict[str, Any]]],
    output_dir: Path
):
    """Generates an aesthetic terminal report and writes a detailed markdown report."""
    report_lines = []
    report_lines.append("# 📊 RAGEAR - Report Generazione Query Sintetiche\n")
    report_lines.append(f"**Data Esecuzione**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    report_lines.append(f"**Modelli Valutati**: {', '.join([s['model'] for s in model_stats])}\n")

    print("\n" + "=" * 90)
    print("                    📊 RAGEAR - RIEPILOGO FINALE GENERAZIONE QUERY")
    print("=" * 90)

    # 1. Tabella Performance
    print(f"{'Modello':<18} | {'Lezioni':<9} | {'Successi':<9} | {'Falliti':<8} | {'Query Tot':<10} | {'Tempo Tot':<11} | {'Media/Lez':<10}")
    print("-" * 90)
    for s in model_stats:
        print(f"{s['model']:<18} | {s['total_lessons']:<9} | {s['successful_lessons']:<9} | {s['failed_lessons']:<8} | {s['total_queries_generated']:<10} | {s['elapsed_seconds']:>8.1f}s | {s['avg_seconds_per_lesson']:>7.2f}s")

    report_lines.append("## 1. Tabella Sintetica Performance\n")
    report_lines.append("| Modello | Lezioni Campionate | Successi | Falliti | Query Generate | Tempo Totale | Media / Lezione |")
    report_lines.append("|---|---|---|---|---|---|---|")
    for s in model_stats:
        report_lines.append(f"| **{s['model']}** | {s['total_lessons']} | {s['successful_lessons']} | {s['failed_lessons']} | {s['total_queries_generated']} | {s['elapsed_seconds']:.1f}s | {s['avg_seconds_per_lesson']:.2f}s |")

    # 2. Distribuzione Tipologie
    print("\n" + "-" * 90)
    print(" Distribuzione Tipologie per Modello:")
    report_lines.append("\n## 2. Distribuzione Tipologie di Query\n")
    report_lines.append("| Modello | Fondazionale | Tecnica | Applicativa | Problem Solving | Orientamento | Altre |")
    report_lines.append("|---|---|---|---|---|---|---|")

    all_types = ["fondazionale", "tecnica", "applicativa", "problem_solving", "orientamento"]

    for s in model_stats:
        tc = s["typology_counts"]
        print(f" Modello: {s['model']}")
        for t in all_types:
            print(f"   - {t:<15}: {tc.get(t, 0)}")
        other = sum(v for k, v in tc.items() if k not in all_types)
        if other > 0:
            print(f"   - {'altre':<15}: {other}")

        row = [f"**{s['model']}**"] + [str(tc.get(t, 0)) for t in all_types] + [str(other)]
        report_lines.append(f"| {' | '.join(row)} |")

    # 3. Esempi a Confronto
    report_lines.append("\n## 3. Confronto Query Generate (Esempio Lezione)")
    models = list(all_records.keys())
    if len(models) >= 1 and all_records[models[0]]:
        first_lesson = all_records[models[0]][0]
        lesson_title = first_lesson.get("titoloLezione")
        course_title = first_lesson.get("titoloCorso")

        print("\n" + "-" * 90)
        print(f" Esempio Query Generate per: '{lesson_title}' ({course_title})")
        print("-" * 90)

        report_lines.append(f"\n### Lezione: *{lesson_title}* (*{course_title}*)\n")

        for m in models:
            records = all_records[m]
            matching = [r for r in records if r.get("titoloLezione") == lesson_title]
            if matching:
                rec = matching[0]
                print(f"\n▶ Modello: {m}")
                report_lines.append(f"#### Modello: `{m}`\n")
                for q in rec.get("queries", []):
                    line_preview = f"  [{q['type'].upper()}]: \"{q['query_text']}\""
                    print(line_preview)
                    report_lines.append(f"- **{q['type'].upper()}**: {q['query_text']}")
                    if q.get("key_topics"):
                        report_lines.append(f"  *Keywords: {', '.join(q['key_topics'])}*")

    # Salva report Markdown
    report_path = output_dir / "query_generation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print("\n" + "=" * 90)
    print(f" Report salvato in: {report_path.resolve()}")
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Generatore di Query Sintetiche di Raccomandazione Corsi (RAGEAR)")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["qwen2.5:14b", "qwen2.5:7b"],
        help="Lista di modelli Ollama da testare in sequenza (es: --models qwen2.5:14b qwen2.5:7b)"
    )
    parser.add_argument(
        "--num-lessons",
        type=int,
        default=10,
        help="Numero di lezioni da campionare casualmente (default: 10)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed casuale per rendere riproducibile la selezione (default: 42)"
    )
    parser.add_argument(
        "--metadata-path",
        type=str,
        default="data/lesson_metadata.json",
        help="Percorso al file JSON metadati lezioni"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data",
        help="Directory dove salvare i file JSON e il report (default: data)"
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=10000,
        help="Numero massimo di caratteri della trascrizione da inviare al modello (default: 10000)"
    )
    parser.add_argument(
        "--no-stop",
        action="store_true",
        help="Non fermare il modello Ollama al termine dell'elaborazione (lascialo in VRAM)"
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== RAGEAR SYNTHETIC QUERY GENERATOR ===")
    print(f"Modelli da eseguire: {args.models}")
    print(f"Numero lezioni: {args.num_lessons} (Seed: {args.seed})")

    # 1. Carica lezioni e campiona
    pool = load_lessons_pool(args.metadata_path)
    sample_file = output_dir / f"sampled_lessons_{args.num_lessons}.json"
    sampled_lessons = sample_lessons(pool, n=args.num_lessons, seed=args.seed, sample_file_path=str(sample_file))

    all_model_stats = []
    all_model_records = {}

    # 2. Esegui per ciascun modello
    for idx, model_name in enumerate(args.models, start=1):
        records, stats = run_generation_for_model(
            model_name=model_name,
            lessons=sampled_lessons,
            max_chars=args.max_chars
        )

        all_model_stats.append(stats)
        all_model_records[model_name] = records

        # Salva output JSON specifico per questo modello
        clean_model_name = re.sub(r"[:/]", "_", model_name)
        model_output_file = output_dir / f"synthetic_queries_{clean_model_name}.json"
        with open(model_output_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"\n[Salvataggio] Salvate {len(records)} lezioni con query in: {model_output_file}")

        # Salva anche file txt piatto pronto per benchmark_queries.py
        flat_txt_file = output_dir / f"synthetic_queries_{clean_model_name}.txt"
        with open(flat_txt_file, "w", encoding="utf-8") as f:
            for r in records:
                for q in r.get("queries", []):
                    f.write(f"{q['query_text'].strip()}\n")
        print(f"[Salvataggio] Salvate {stats['total_queries_generated']} query flat per benchmark in: {flat_txt_file}")

        # Se non è l'ultimo modello (o se non disabilitato da --no-stop), libera la VRAM prima di passare al successivo!
        if not args.no_stop and (idx < len(args.models) or len(args.models) > 1):
            stop_ollama_model(model_name)

    # 3. Se ci sono più modelli, crea un JSON di confronto affiancato
    if len(args.models) > 1:
        comparison_records = []
        for lesson in sampled_lessons:
            l_uid = lesson.get("lesson_uid")
            c_title = lesson.get("titoloCorso")
            l_title = lesson.get("titoloLezione")
            comp_entry = {
                "lesson_uid": l_uid,
                "titoloCorso": c_title,
                "titoloLezione": l_title,
                "models_comparison": {}
            }
            for m in args.models:
                recs = all_records = all_model_records.get(m, [])
                match = [r for r in recs if r.get("titoloLezione") == l_title]
                if match:
                    comp_entry["models_comparison"][m] = match[0]["queries"]
                else:
                    comp_entry["models_comparison"][m] = []
            comparison_records.append(comp_entry)

        comp_file = output_dir / "synthetic_queries_comparison.json"
        with open(comp_file, "w", encoding="utf-8") as f:
            json.dump(comparison_records, f, indent=2, ensure_ascii=False)
        print(f"\n[Confronto] Salvato file di confronto affiancato in: {comp_file}")

    # 4. Stampa e salva report
    print_and_save_report(all_model_stats, all_model_records, output_dir)


if __name__ == "__main__":
    main()
