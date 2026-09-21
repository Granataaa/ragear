"""
Build Course Catalog for RAGEAR.
Extracts unique courses, faculties, degrees, CFU, and lesson counts from output_lezioni_pulito.csv.
"""

import os
import csv
import json
import re
from pathlib import Path

def parse_cfu(raw_cfu: str) -> int | None:
    if not raw_cfu:
        return None
    m = re.search(r'(\d+)', raw_cfu)
    return int(m.group(1)) if m else None

def clean_settore(raw_settore: str) -> str:
    if not raw_settore:
        return ""
    # Remove 'Settore:' prefix if present
    s = re.sub(r'^settore:\s*', '', raw_settore.strip(), flags=re.IGNORECASE)
    return s.strip()

def build_catalog(csv_path: str, output_path: str):
    csv_file = Path(csv_path)
    if not csv_file.exists():
        # Check parent folder or local
        alt_path = Path("..") / "rag_engine_l4all" / "output_lezioni_pulito.csv"
        if alt_path.exists():
            csv_file = alt_path
        else:
            raise FileNotFoundError(f"Cannot find CSV at {csv_path} or {alt_path}")

    print(f"Reading CSV from: {csv_file.resolve()}")
    catalog = {}

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            course_title = row.get("titoloCorso", "").strip()
            if not course_title:
                continue

            facolta = row.get("facolta", "").strip()
            corso_laurea = row.get("corso_laurea", "").strip()
            tipologia = row.get("tipologia_corso_laurea", "").strip()
            cfu_raw = row.get("CFU", "").strip()
            cfu_val = parse_cfu(cfu_raw)
            settore = clean_settore(row.get("settore", ""))
            link_corso = row.get("link_corso", "").strip()

            filename = row.get("filename", "").strip()
            hidden_filename = row.get("hiddenFilename", "").strip()
            video_url = filename or hidden_filename
            link_lezione = row.get("link_lezione", "").strip()
            titolo_lezione = row.get("titoloLezione", "").strip()
            docente = row.get("docenteVideo", "").strip()

            # Extract lesson number from video URL or title
            lez_num = None
            if video_url:
                m = re.search(r'Lez0*(\d+)', video_url, re.IGNORECASE)
                if m:
                    lez_num = int(m.group(1))
            if lez_num is None and titolo_lezione:
                m = re.search(r'(?:Lezione|Lez\.?)\s*0*(\d+)', titolo_lezione, re.IGNORECASE)
                if m:
                    lez_num = int(m.group(1))

            # Initialize course entry if new
            if course_title not in catalog:
                catalog[course_title] = {
                    "course_id": re.sub(r'[^a-zA-Z0-9]', '', course_title),
                    "course_title": course_title,
                    "facolta": facolta,
                    "corso_laurea": corso_laurea,
                    "tipologia": tipologia,
                    "cfu": cfu_val,
                    "settore": settore,
                    "link_corso": link_corso,
                    "docenti": set(),
                    "lessons": {}
                }

            course_entry = catalog[course_title]

            # Merge faculties if course is present in multiple faculties
            if facolta:
                existing_facs = [f.strip() for f in course_entry["facolta"].split(",") if f.strip()] if course_entry["facolta"] else []
                if facolta not in existing_facs:
                    existing_facs.append(facolta)
                    course_entry["facolta"] = ", ".join(existing_facs)

            # Merge degree courses if course is shared across multiple degrees
            if corso_laurea:
                existing_cdls = [c.strip() for c in course_entry["corso_laurea"].split(",") if c.strip()] if course_entry["corso_laurea"] else []
                if corso_laurea not in existing_cdls:
                    existing_cdls.append(corso_laurea)
                    course_entry["corso_laurea"] = ", ".join(existing_cdls)

            if not course_entry["tipologia"] and tipologia:
                course_entry["tipologia"] = tipologia
            elif tipologia and tipologia not in course_entry["tipologia"]:
                course_entry["tipologia"] = f"{course_entry['tipologia']}, {tipologia}"

            if course_entry["cfu"] is None and cfu_val is not None:
                course_entry["cfu"] = cfu_val
            if not course_entry["settore"] and settore:
                course_entry["settore"] = settore
            if not course_entry["link_corso"] and link_corso:
                course_entry["link_corso"] = link_corso
            if docente:
                course_entry["docenti"].add(docente)

            # Store lesson
            lesson_id = video_url if video_url else (link_lezione or f"lez_{len(course_entry['lessons'])+1}")
            if lesson_id not in course_entry["lessons"]:
                course_entry["lessons"][lesson_id] = {
                    "lesson_number": lez_num,
                    "title": titolo_lezione,
                    "video_url": video_url,
                    "link_lezione": link_lezione,
                    "docente": docente
                }

    # Post-process for clean JSON serialization
    serialized_catalog = {}
    for course_title, c in catalog.items():
        lessons_list = list(c["lessons"].values())
        # Sort lessons by lesson_number if available
        lessons_list.sort(key=lambda x: (x["lesson_number"] is None, x["lesson_number"] or 0))

        serialized_catalog[course_title] = {
            "course_id": c["course_id"],
            "course_title": c["course_title"],
            "facolta": c["facolta"],
            "corso_laurea": c["corso_laurea"],
            "tipologia": c["tipologia"],
            "cfu": c["cfu"],
            "settore": c["settore"],
            "link_corso": c["link_corso"],
            "docenti": sorted(list(c["docenti"])),
            "total_lessons": len(lessons_list),
            "lessons": lessons_list
        }

    # Save to JSON
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, mode="w", encoding="utf-8") as f:
        json.dump(serialized_catalog, f, ensure_ascii=False, indent=2)

    total_lessons = sum(c["total_lessons"] for c in serialized_catalog.values())
    print(f"Catalog successfully built: {len(serialized_catalog)} courses, {total_lessons} total lessons.")
    print(f"Saved to: {out_file.resolve()}")

if __name__ == "__main__":
    csv_input = os.getenv("CSV_PATH", "../rag_engine_l4all/output_lezioni_pulito.csv")
    json_output = os.getenv("CATALOG_PATH", "data/course_catalog.json")
    build_catalog(csv_input, json_output)
