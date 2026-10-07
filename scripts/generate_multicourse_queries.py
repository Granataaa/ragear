#!/usr/bin/env python3
"""
RAGEAR - Interdisciplinary / Multi-Course Synthetic Query Generator
Generates realistic student course recommendation queries bridging TWO different courses/lessons simultaneously.

Features:
- Samples pairs of lessons belonging to distinct courses (reproducible seed).
- Forces LLM to find authentic conceptual/application bridges between the two subjects.
- Compares models (e.g. 14B vs 7B) on the exact same pairs.
- Sequential execution with automatic VRAM cleanup (ollama stop).
- Robust JSON extraction with schema validation and retry.
- Comparative report generation (Markdown & JSON).
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

SYSTEM_PROMPT = """Sei un generatore esperto di query di studenti universitari per un sistema di Course Recommendation accademico (RAG).

OBIETTIVO INTERDISCIPLINARE:
Ti vengono fornite DUE lezioni universitarie appartenenti a DUE CORSI DIFFERENTI (con relativi metadati accademici ed estratti delle trascrizioni).
Il tuo compito è generare ESATTAMENTE 5 query realistiche di studenti in cui l'interesse o il bisogno formativo espresso TOCCA E COINVOLGE CONTEMPORANEAMENTE ENTRAMBI I CORSI.
L'obiettivo è che un motore di raccomandazione debba raccomandare ENTRAMBI i corsi (o che entrambi rispondano congiuntamente alla richiesta dello studente).

REGOLE RIGIDE (COSA NON FARE):
- NON fare una banale giustapposizione meccanica (ESEMPIO SBAGLIATO: "Vorrei fare il primo corso e vorrei anche fare il secondo corso").
- NON fare domande nozionistiche da esame o di verifica (ESEMPIO SBAGLIATO: "Come si definisce X nel corso 1 e come si calcola Y nel corso 2?").
- NON citare MAI parole come "la lezione", "le due lezioni", "il video", "il docente" o "la trascrizione" (ricorda: lo studente non sa che queste lezioni esistono!).
- NON menzionare i titoli esatti o i codici dei corsi nella query (esprimi bisogni e argomenti).

REGOLE DI STILE E PONTE CONCETTUALE:
- Trova un autentico collegamento logico, tecnologico, metodologico o professionale tra i due corsi: ad esempio come i concetti teorici del Corso A si applicano nelle tecnologie del Corso B, o come combinare le due competenze per una specifica figura lavorativa o progetto interdisciplinare.
- Scrivi in prima persona in italiano naturale (es: "Sto cercando un percorso che mi permetta di...", "Mi appassiona l'intersezione tra...", "Vorrei acquisire competenze su... per applicarle a...").

DEVI GENERARE ESATTAMENTE QUESTE 5 TIPOLOGIE:
1. "fondazionale": Principi teorici e concetti di base che creano un terreno comune tra le due discipline.
2. "tecnica": Terminologia, modelli formali o strumenti specifici che integrano gli argomenti di entrambi i corsi.
3. "applicativa": Scenario professionale, lavorativo o industriale in cui sono richieste contemporaneamente le competenze di entrambi i corsi.
4. "problem_solving": Problema complesso o sfida operativa la cui soluzione richiede la convergenza di nozioni da entrambi i campi.
5. "orientamento": Studente indeciso che vuole capire come strutturare il proprio piano di studi per combinare questi due ambiti nel proprio futuro.

FORMATO DI RISPOSTA:
Devi restituire ESCLUSIVAMENTE un oggetto JSON valido (senza testo prima o dopo) con la seguente struttura esatta:
{
  "queries": [
    {
      "type": "fondazionale",
      "query_text": "Testo naturale della query dello studente...",
      "key_topics_course_a": ["argomento_a1", "argomento_a2"],
      "key_topics_course_b": ["argomento_b1", "argomento_b2"],
      "conceptual_bridge": "Spiegazione sintetica (1 frase) del collegamento concettuale tra i due corsi"
    },
    {
      "type": "tecnica",
      "query_text": "...",
      "key_topics_course_a": ["..."],
      "key_topics_course_b": ["..."],
      "conceptual_bridge": "..."
    },
    {
      "type": "applicativa",
      "query_text": "...",
      "key_topics_course_a": ["..."],
      "key_topics_course_b": ["..."],
      "conceptual_bridge": "..."
    },
    {
      "type": "problem_solving",
      "query_text": "...",
      "key_topics_course_a": ["..."],
      "key_topics_course_b": ["..."],
      "conceptual_bridge": "..."
    },
    {
      "type": "orientamento",
      "query_text": "...",
      "key_topics_course_a": ["..."],
      "key_topics_course_b": ["..."],
      "conceptual_bridge": "..."
    }
  ]
}
"""

REQUIRED_TYPES = {"fondazionale", "tecnica", "applicativa", "problem_solving", "orientamento"}


def stop_ollama_model(model_name: str) -> bool:
    """Stops a model in Ollama to immediately release VRAM/RAM."""
    print(f"\n[VRAM Cleanup] Arresto del modello '{model_name}' da memoria GPU/RAM...")
    try:
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

    # API fallback
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
    """Extracts and validates JSON strictly."""
    if not raw_text or not raw_text.strip():
        return None, "Risposta vuota dal modello"

    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1].strip()
        else:
            return None, "Nessuna struttura JSON racchiusa tra parentesi graffe {} trovata"

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        cleaned = re.sub(r",\s*([\}\]])", r"\1", candidate)
        try:
            data = json.loads(cleaned)
        except Exception:
            return None, f"Errore decodifica JSON: {e}"

    if not isinstance(data, dict):
        return None, "Il JSON principale non è un dizionario"

    if "queries" not in data or not isinstance(data["queries"], list):
        return None, "Chiave 'queries' mancante o non è una lista"

    queries = data["queries"]
    if len(queries) == 0:
        return None, "La lista 'queries' è vuota"

    valid_queries = []
    for q in queries:
        if not isinstance(q, dict):
            continue
        q_text = str(q.get("query_text", "")).strip()
        q_type = str(q.get("type", "")).strip().lower()
        if not q_text:
            continue

        valid_queries.append({
            "type": q_type or "generale",
            "query_text": q_text,
            "key_topics_course_a": q.get("key_topics_course_a", []),
            "key_topics_course_b": q.get("key_topics_course_b", []),
            "conceptual_bridge": q.get("conceptual_bridge", "")
        })

    if not valid_queries:
        return None, "Nessuna query valida con 'query_text' presente"

    return {"queries": valid_queries}, None


def load_lessons_grouped_by_course(metadata_path: str = "data/lesson_metadata.json") -> Dict[str, List[Dict[str, Any]]]:
    """Loads valid lessons grouped by course title."""
    meta_file = Path(metadata_path)
    if not meta_file.exists():
        raise FileNotFoundError(f"File metadati non trovato: {metadata_path}")

    with open(meta_file, "r", encoding="utf-8") as f:
        all_metadata = json.load(f)

    courses = {}
    for item in all_metadata:
        transcript_path = item.get("transcript_path")
        course_title = item.get("titoloCorso")
        if not transcript_path or not course_title:
            continue
        p = Path(transcript_path)
        if not p.exists():
            p = Path("..") / transcript_path
            if not p.exists():
                continue

        try:
            if p.stat().st_size < 800:
                continue
        except Exception:
            continue

        courses.setdefault(course_title, []).append(item)

    print(f"[Catalogo] Trovati {len(courses)} corsi distinti con lezioni e trascrizioni valide.")
    return courses


def sample_pairs(
    courses_dict: Dict[str, List[Dict[str, Any]]],
    num_pairs: int = 5,
    seed: Optional[int] = 42,
    sample_file_path: Optional[str] = "data/sampled_pairs.json"
) -> List[Dict[str, Any]]:
    """Samples distinct pairs of lessons belonging to two different courses."""
    if sample_file_path and Path(sample_file_path).exists():
        print(f"[Campionamento] Caricamento coppie pre-esistenti da: {sample_file_path}")
        with open(sample_file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    if seed is not None:
        random.seed(seed)

    all_course_titles = list(courses_dict.keys())
    if len(all_course_titles) < 2:
        raise ValueError("Meno di 2 corsi disponibili per formare coppie.")

    pairs = []
    for i in range(1, num_pairs + 1):
        c_a, c_b = random.sample(all_course_titles, 2)
        lesson_a = random.choice(courses_dict[c_a])
        lesson_b = random.choice(courses_dict[c_b])

        pair_entry = {
            "pair_id": f"pair_{i}",
            "course_a": {
                "titoloCorso": lesson_a.get("titoloCorso"),
                "titoloLezione": lesson_a.get("titoloLezione"),
                "lesson_uid": lesson_a.get("lesson_uid"),
                "settore": lesson_a.get("settore"),
                "facolta": lesson_a.get("facolta_set"),
                "cfu": lesson_a.get("CFU"),
                "transcript_path": lesson_a.get("transcript_path")
            },
            "course_b": {
                "titoloCorso": lesson_b.get("titoloCorso"),
                "titoloLezione": lesson_b.get("titoloLezione"),
                "lesson_uid": lesson_b.get("lesson_uid"),
                "settore": lesson_b.get("settore"),
                "facolta": lesson_b.get("facolta_set"),
                "cfu": lesson_b.get("CFU"),
                "transcript_path": lesson_b.get("transcript_path")
            }
        }
        pairs.append(pair_entry)

    if sample_file_path:
        Path(sample_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(sample_file_path, "w", encoding="utf-8") as f:
            json.dump(pairs, f, indent=2, ensure_ascii=False)
        print(f"[Campionamento] Salvate {len(pairs)} coppie campione in: {sample_file_path}")

    return pairs


def read_transcript_snippet(path_str: str, max_chars: int = 5000) -> str:
    """Reads the first max_chars from transcript file."""
    p = Path(path_str)
    if not p.exists():
        p = Path("..") / path_str
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:max_chars].strip()
    except Exception as e:
        return f"[Errore lettura {path_str}: {e}]"


def run_generation_for_pairs(
    model_name: str,
    pairs: List[Dict[str, Any]],
    max_chars_per_lesson: int = 5000,
    max_retries: int = 2
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Runs query generation across all sampled pairs for a given model."""
    print(f"\n{'='*80}")
    print(f" AVVIO GENERAZIONE MULTI-CORSO CON MODELLO: {model_name}")
    print(f" Numero coppie da processare: {len(pairs)} (Totale lezioni coinvolte: {len(pairs)*2})")
    print(f"{'='*80}")

    records = []
    stats = {
        "model": model_name,
        "total_pairs": len(pairs),
        "successful_pairs": 0,
        "failed_pairs": 0,
        "total_queries_generated": 0,
        "typology_counts": {},
        "elapsed_seconds": 0.0,
        "avg_seconds_per_pair": 0.0,
        "errors": []
    }

    start_total_time = time.time()

    for idx, pair in enumerate(pairs, start=1):
        ca = pair["course_a"]
        cb = pair["course_b"]

        print(f"\n[{idx}/{len(pairs)}] Coppia: '{ca['titoloCorso']}' <---> '{cb['titoloCorso']}'")
        print(f"   - Lezione A: {ca['titoloLezione']} ({ca.get('settore', 'N/D')})")
        print(f"   - Lezione B: {cb['titoloLezione']} ({cb.get('settore', 'N/D')})")

        snippet_a = read_transcript_snippet(ca["transcript_path"], max_chars_per_lesson)
        snippet_b = read_transcript_snippet(cb["transcript_path"], max_chars_per_lesson)

        user_prompt = f"""=== CORSO A ===
- Titolo Corso: {ca['titoloCorso']}
- Lezione: {ca['titoloLezione']}
- Settore Scientifico: {ca.get('settore', 'N/D')}
Estratto Trascrizione A:
\"\"\"
{snippet_a}
\"\"\"

=== CORSO B ===
- Titolo Corso: {cb['titoloCorso']}
- Lezione: {cb['titoloLezione']}
- Settore Scientifico: {cb.get('settore', 'N/D')}
Estratto Trascrizione B:
\"\"\"
{snippet_b}
\"\"\"

Genera le 5 query interdisciplinari richieste (fondazionale, tecnica, applicativa, problem_solving, orientamento) che colleghino entrambi i corsi, rispettando il formato JSON:"""

        success = False
        parsed_data = None
        err_msg = ""
        pair_start = time.time()

        for attempt in range(1, max_retries + 1):
            try:
                temp = 0.7 if attempt == 1 else 0.4
                print(f"   Invocazione Ollama ({model_name}, tentativo {attempt}/{max_retries})...", end=" ", flush=True)
                raw_response = call_ollama(model_name, user_prompt, SYSTEM_PROMPT, temperature=temp)
                parsed_data, err_msg = extract_and_validate_json(raw_response)

                if parsed_data:
                    pair_elapsed = time.time() - pair_start
                    print(f"OK! ({pair_elapsed:.2f}s, {len(parsed_data['queries'])} query interdisciplinari)")
                    success = True
                    break
                else:
                    print(f"JSON NON VALIDO: {err_msg}")
            except Exception as e:
                print(f"ERRORE CHIAMATA: {e}")
                err_msg = str(e)

        if success and parsed_data:
            stats["successful_pairs"] += 1
            queries = parsed_data["queries"]
            stats["total_queries_generated"] += len(queries)

            for q in queries:
                t = q["type"]
                stats["typology_counts"][t] = stats["typology_counts"].get(t, 0) + 1

            record = {
                "pair_id": pair["pair_id"],
                "course_a": ca,
                "course_b": cb,
                "model": model_name,
                "generated_at": datetime.now().isoformat(),
                "queries": queries
            }
            records.append(record)
        else:
            stats["failed_pairs"] += 1
            stats["errors"].append({"pair_id": pair["pair_id"], "error": err_msg})
            print(f"   [FALLIMENTO DEFINITIVO] Nessuna query generata per questa coppia.")

    total_elapsed = time.time() - start_total_time
    stats["elapsed_seconds"] = round(total_elapsed, 2)
    stats["avg_seconds_per_pair"] = round(total_elapsed / max(1, len(pairs)), 2)

    return records, stats


def print_and_save_multicourse_report(
    model_stats: List[Dict[str, Any]],
    all_records: Dict[str, List[Dict[str, Any]]],
    output_dir: Path
):
    """Generates an aesthetic terminal report and writes a detailed markdown report."""
    report_lines = []
    report_lines.append("# 🌐 RAGEAR - Report Generazione Query Interdisciplinari (Coppie di Corsi)\n")
    report_lines.append(f"**Data Esecuzione**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    report_lines.append(f"**Modelli Valutati**: {', '.join([s['model'] for s in model_stats])}\n")

    print("\n" + "=" * 90)
    print("           🌐 RAGEAR - RIEPILOGO FINALE GENERAZIONE QUERY MULTI-CORSO")
    print("=" * 90)

    # 1. Performance Table
    print(f"{'Modello':<18} | {'Coppie':<8} | {'Successi':<9} | {'Falliti':<8} | {'Query Tot':<10} | {'Tempo Tot':<11} | {'Media/Coppia':<12}")
    print("-" * 90)
    for s in model_stats:
        print(f"{s['model']:<18} | {s['total_pairs']:<8} | {s['successful_pairs']:<9} | {s['failed_pairs']:<8} | {s['total_queries_generated']:<10} | {s['elapsed_seconds']:>8.1f}s | {s['avg_seconds_per_pair']:>9.2f}s")

    report_lines.append("## 1. Tabella Sintetica Performance\n")
    report_lines.append("| Modello | Coppie Valutate | Successi | Falliti | Query Generate | Tempo Totale | Media / Coppia |")
    report_lines.append("|---|---|---|---|---|---|---|")
    for s in model_stats:
        report_lines.append(f"| **{s['model']}** | {s['total_pairs']} | {s['successful_pairs']} | {s['failed_pairs']} | {s['total_queries_generated']} | {s['elapsed_seconds']:.1f}s | {s['avg_seconds_per_pair']:.2f}s |")

    # 2. Typology Distribution
    report_lines.append("\n## 2. Distribuzione Tipologie di Query Interdisciplinari\n")
    report_lines.append("| Modello | Fondazionale | Tecnica | Applicativa | Problem Solving | Orientamento |")
    report_lines.append("|---|---|---|---|---|---|")

    all_types = ["fondazionale", "tecnica", "applicativa", "problem_solving", "orientamento"]
    for s in model_stats:
        tc = s["typology_counts"]
        row = [f"**{s['model']}**"] + [str(tc.get(t, 0)) for t in all_types]
        report_lines.append(f"| {' | '.join(row)} |")

    # 3. Side-by-side Examples
    report_lines.append("\n## 3. Confronto Esempi Interdisciplinari per Coppia\n")
    models = list(all_records.keys())
    if models and all_records[models[0]]:
        first_pair = all_records[models[0]][0]
        ca = first_pair["course_a"]
        cb = first_pair["course_b"]

        report_lines.append(f"### Esempio: **{ca['titoloCorso']}** 🔗 **{cb['titoloCorso']}**\n")
        report_lines.append(f"- **Corso A**: *{ca['titoloCorso']}* — Lezione: *{ca['titoloLezione']}* ({ca.get('settore', '')})")
        report_lines.append(f"- **Corso B**: *{cb['titoloCorso']}* — Lezione: *{cb['titoloLezione']}* ({cb.get('settore', '')})\n")

        print("\n" + "-" * 90)
        print(f" Esempio Query per: '{ca['titoloCorso']}' + '{cb['titoloCorso']}'")
        print("-" * 90)

        for m in models:
            matching = [r for r in all_records[m] if r.get("pair_id") == first_pair["pair_id"]]
            if matching:
                rec = matching[0]
                print(f"\n▶ Modello: {m}")
                report_lines.append(f"#### Modello: `{m}`\n")
                for q in rec.get("queries", []):
                    bridge = q.get("conceptual_bridge", "")
                    print(f"  [{q['type'].upper()}]: \"{q['query_text']}\"")
                    if bridge:
                        print(f"     -> Ponte: {bridge}")
                    report_lines.append(f"- **{q['type'].upper()}**: {q['query_text']}")
                    if bridge:
                        report_lines.append(f"  *Ponte concettuale: {bridge}*")

    report_path = output_dir / "multicourse_query_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # Salva anche archivio permanente coi nomi dei modelli
    models_tag = "_".join([re.sub(r"[:/]", "_", m) for m in models])
    if models_tag:
        tag_report_path = output_dir / f"multicourse_query_report_{models_tag}.md"
        with open(tag_report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

    print("\n" + "=" * 90)
    print(f" Report salvato in: {report_path.resolve()}")
    if models_tag:
        print(f" Report permanente salvato in: {tag_report_path.resolve()}")
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Generatore di Query Sintetiche Multi-Corso Interdisciplinari (RAGEAR)")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["qwen2.5:14b", "qwen2.5:7b"],
        help="Lista di modelli Ollama da testare in sequenza (es: --models qwen2.5:14b qwen2.5:7b)"
    )
    parser.add_argument(
        "--num-pairs",
        type=int,
        default=5,
        help="Numero di coppie di corsi differenti da campionare (default: 5 coppie)"
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
        default=5000,
        help="Numero massimo di caratteri per lezione da inviare (default: 5000 per lezione, 10000 tot)"
    )
    parser.add_argument(
        "--no-stop",
        action="store_true",
        help="Non fermare il modello Ollama al termine dell'elaborazione"
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== RAGEAR MULTI-COURSE SYNTHETIC QUERY GENERATOR ===")
    print(f"Modelli da eseguire: {args.models}")
    print(f"Numero coppie: {args.num_pairs} (Seed: {args.seed})")

    # 1. Carica lezioni raggruppate per corso e campiona le coppie
    courses_dict = load_lessons_grouped_by_course(args.metadata_path)
    sample_file = output_dir / f"sampled_pairs_{args.num_pairs}.json"
    sampled_pairs = sample_pairs(courses_dict, num_pairs=args.num_pairs, seed=args.seed, sample_file_path=str(sample_file))

    all_model_stats = []
    all_model_records = {}

    # 2. Esegui per ciascun modello
    for idx, model_name in enumerate(args.models, start=1):
        records, stats = run_generation_for_pairs(
            model_name=model_name,
            pairs=sampled_pairs,
            max_chars_per_lesson=args.max_chars
        )

        all_model_stats.append(stats)
        all_model_records[model_name] = records

        clean_model_name = re.sub(r"[:/]", "_", model_name)
        model_output_file = output_dir / f"multicourse_queries_{clean_model_name}.json"
        with open(model_output_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"\n[Salvataggio] Salvate {len(records)} coppie con query in: {model_output_file}")

        flat_txt_file = output_dir / f"multicourse_queries_{clean_model_name}.txt"
        with open(flat_txt_file, "w", encoding="utf-8") as f:
            for r in records:
                for q in r.get("queries", []):
                    f.write(f"{q['query_text'].strip()}\n")
        print(f"[Salvataggio] Salvate {stats['total_queries_generated']} query flat per benchmark in: {flat_txt_file}")

        if not args.no_stop and (idx < len(args.models) or len(args.models) > 1):
            stop_ollama_model(model_name)

    # 3. File di confronto affiancato
    if len(args.models) > 1:
        comparison_records = []
        for pair in sampled_pairs:
            p_id = pair["pair_id"]
            comp_entry = {
                "pair_id": p_id,
                "course_a": pair["course_a"]["titoloCorso"],
                "lesson_a": pair["course_a"]["titoloLezione"],
                "course_b": pair["course_b"]["titoloCorso"],
                "lesson_b": pair["course_b"]["titoloLezione"],
                "models_comparison": {}
            }
            for m in args.models:
                recs = all_model_records.get(m, [])
                match = [r for r in recs if r.get("pair_id") == p_id]
                if match:
                    comp_entry["models_comparison"][m] = match[0]["queries"]
                else:
                    comp_entry["models_comparison"][m] = []
            comparison_records.append(comp_entry)

        comp_file = output_dir / "multicourse_queries_comparison.json"
        with open(comp_file, "w", encoding="utf-8") as f:
            json.dump(comparison_records, f, indent=2, ensure_ascii=False)

        models_tag = "_".join([re.sub(r"[:/]", "_", m) for m in args.models])
        tagged_comp_file = output_dir / f"multicourse_queries_comparison_{models_tag}.json"
        with open(tagged_comp_file, "w", encoding="utf-8") as f:
            json.dump(comparison_records, f, indent=2, ensure_ascii=False)

        print(f"\n[Confronto] Salvato file di confronto affiancato in: {comp_file}")
        print(f"[Confronto] Salvato file archivio permanente in: {tagged_comp_file}")

    # 4. Report
    print_and_save_multicourse_report(all_model_stats, all_model_records, output_dir)


if __name__ == "__main__":
    main()
