import os
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from app.config import settings
from app.schemas.models import CatalogStats, FilterOptionsResponse, RecommendationFilters

logger = logging.getLogger("ragear.catalog")

class CatalogService:
    def __init__(self, catalog_path: str = None):
        self.catalog_path = Path(catalog_path or settings.catalog_path)
        self.catalog: Dict[str, Dict[str, Any]] = {}
        self.normalized_to_canonical: Dict[str, str] = {}
        self.total_lessons_by_course: Dict[str, int] = {}
        self.is_synced: bool = False
        
        # Load local cache first
        self.load_cache()

    def normalize_name(self, name: str) -> str:
        """
        Normalize course names for robust matching (lowercase, no punctuation/whitespace).
        """
        if not name:
            return ""
        return re.sub(r'[^a-zA-Z0-9]', '', name.lower())

    def load_cache(self) -> bool:
        """
        Load course catalog from the JSON file.
        """
        if not self.catalog_path.exists():
            logger.warning(f"Catalog file not found at {self.catalog_path}. Attempting to build or wait for sync.")
            return False

        try:
            with open(self.catalog_path, mode="r", encoding="utf-8") as f:
                self.catalog = json.load(f)
            
            self._rebuild_indices()
            logger.info(f"Loaded {len(self.catalog)} courses from cache: {self.catalog_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading catalog cache: {e}")
            return False

    def _rebuild_indices(self):
        """
        Rebuild internal normalization and lesson count maps.
        """
        self.normalized_to_canonical.clear()
        self.total_lessons_by_course.clear()

        for canonical_title, info in self.catalog.items():
            norm = self.normalize_name(canonical_title)
            self.normalized_to_canonical[norm] = canonical_title
            
            # Also index by course_id if available
            cid = info.get("course_id")
            if cid:
                self.normalized_to_canonical[self.normalize_name(cid)] = canonical_title

            total_lez = info.get("total_lessons", 0)
            if not total_lez and "lessons" in info:
                total_lez = len(info["lessons"])
            
            # Default minimum 1 to prevent division by zero in LRF
            self.total_lessons_by_course[canonical_title] = max(1, total_lez)

    def sync_from_rag_chunks(self, chunks: List[Dict[str, Any]]) -> bool:
        """
        Dynamically update or expand the course catalog using chunk metadata returned by RAG /list.
        """
        if not chunks:
            logger.warning("Empty chunk list provided for catalog sync.")
            return False

        logger.info(f"Syncing catalog from {len(chunks)} RAG chunks...")
        lessons_by_course = {}

        for chunk in chunks:
            meta = chunk.get("metadata", {})
            if not meta:
                continue

            # titoloCorso can be a string or a list of strings
            courses_raw = meta.get("titoloCorso")
            if not courses_raw:
                continue
            
            courses = [courses_raw] if isinstance(courses_raw, str) else list(courses_raw)
            
            # Extract lesson identifier
            source = meta.get("filename") or chunk.get("source") or meta.get("link_lezione") or ""
            titolo_lezione = meta.get("titoloLezione", "")
            lesson_id = source or titolo_lezione or f"chunk_{chunk.get('chunk_id')}"

            # Extract other metadata
            facolta = meta.get("facolta", "")
            if isinstance(facolta, list):
                facolta = ", ".join(facolta)
            corso_laurea = meta.get("corso_laurea", "")
            if isinstance(corso_laurea, list):
                corso_laurea = ", ".join(corso_laurea)
            cfu_raw = meta.get("cfu")
            cfu_val = None
            if cfu_raw is not None:
                m = re.search(r'(\d+)', str(cfu_raw))
                if m:
                    cfu_val = int(m.group(1))

            settore = meta.get("settore", "")
            if isinstance(settore, list):
                settore = ", ".join(settore)
            settore = re.sub(r'^settore:\s*', '', str(settore).strip(), flags=re.IGNORECASE)

            for c_title in courses:
                c_title = c_title.strip()
                if not c_title:
                    continue

                if c_title not in self.catalog:
                    self.catalog[c_title] = {
                        "course_id": re.sub(r'[^a-zA-Z0-9]', '', c_title),
                        "course_title": c_title,
                        "facolta": facolta,
                        "corso_laurea": corso_laurea,
                        "tipologia": meta.get("tipologia_corso_laurea", ""),
                        "cfu": cfu_val,
                        "settore": settore,
                        "link_corso": meta.get("link_corso", ""),
                        "docenti": [],
                        "total_lessons": 0,
                        "lessons": []
                    }

                c_entry = self.catalog[c_title]
                if facolta:
                    existing_f = [f.strip() for f in c_entry["facolta"].split(",") if f.strip()] if c_entry["facolta"] else []
                    new_f = [f.strip() for f in facolta.split(",") if f.strip()]
                    for nf in new_f:
                        if nf not in existing_f:
                            existing_f.append(nf)
                    c_entry["facolta"] = ", ".join(existing_f)

                if corso_laurea:
                    existing_c = [c.strip() for c in c_entry["corso_laurea"].split(",") if c.strip()] if c_entry["corso_laurea"] else []
                    new_c = [c.strip() for c in corso_laurea.split(",") if c.strip()]
                    for nc in new_c:
                        if nc not in existing_c:
                            existing_c.append(nc)
                    c_entry["corso_laurea"] = ", ".join(existing_c)

                if c_entry["cfu"] is None and cfu_val is not None:
                    c_entry["cfu"] = cfu_val
                if not c_entry["settore"] and settore:
                    c_entry["settore"] = settore

                lessons_by_course.setdefault(c_title, set()).add(lesson_id)

        # Update total lessons count
        for c_title, lez_set in lessons_by_course.items():
            if c_title in self.catalog:
                existing_lez = self.catalog[c_title].get("total_lessons", 0)
                self.catalog[c_title]["total_lessons"] = max(existing_lez, len(lez_set))

        self._rebuild_indices()
        self.is_synced = True

        # Save to cache file
        try:
            self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.catalog_path, mode="w", encoding="utf-8") as f:
                json.dump(self.catalog, f, ensure_ascii=False, indent=2)
            logger.info(f"Catalog successfully synced and cached: {len(self.catalog)} courses.")
        except Exception as e:
            logger.error(f"Failed to write synced catalog to disk: {e}")

        return True

    def find_canonical_course(self, name: str) -> Optional[str]:
        """
        Resolve any course name or variant to its canonical title.
        """
        if not name:
            return None
        if name in self.catalog:
            return name
        norm = self.normalize_name(name)
        return self.normalized_to_canonical.get(norm)

    def get_course_info(self, name: str) -> Optional[Dict[str, Any]]:
        canonical = self.find_canonical_course(name)
        if canonical and canonical in self.catalog:
            return self.catalog[canonical]
        return None

    def get_total_lessons(self, name: str) -> int:
        canonical = self.find_canonical_course(name)
        if canonical and canonical in self.total_lessons_by_course:
            return self.total_lessons_by_course[canonical]
        return 20  # Sensible default average if completely unindexed

    def filter_courses(self, filters: Optional[RecommendationFilters]) -> Optional[Set[str]]:
        """
        Returns a set of canonical course titles that satisfy the given academic filters.
        If no filters or no constraints, returns None (meaning all courses allowed).
        """
        if not filters:
            return None

        has_filter = any([
            filters.facolta,
            filters.cfu is not None,
            filters.min_cfu is not None,
            filters.max_cfu is not None,
            filters.tipologia_corso,
            filters.settore
        ])
        if not has_filter:
            return None

        allowed = set()
        for title, info in self.catalog.items():
            # 1. Facolta filter
            if filters.facolta:
                course_fac = info.get("facolta", "").lower()
                req_fac = filters.facolta.lower().strip()
                if "beni culturali" in req_fac or "lettere" in req_fac:
                    match_fac = ("beni culturali" in course_fac or "lettere" in course_fac)
                elif "ingegneria" in req_fac:
                    match_fac = "ingegneria" in course_fac
                else:
                    match_fac = req_fac in course_fac
                if not match_fac:
                    continue

            # 2. CFU filters
            course_cfu = info.get("cfu")
            if filters.cfu is not None:
                if course_cfu != filters.cfu:
                    continue
            if filters.min_cfu is not None:
                if course_cfu is None or course_cfu < filters.min_cfu:
                    continue
            if filters.max_cfu is not None:
                if course_cfu is None or course_cfu > filters.max_cfu:
                    continue

            # 3. Tipologia (triennale/magistrale)
            if filters.tipologia_corso:
                tip = info.get("tipologia", "").lower()
                cdl = info.get("corso_laurea", "").lower()
                req_tip = filters.tipologia_corso.lower()
                if req_tip not in tip and req_tip not in cdl:
                    continue

            # 4. Settore filter
            if filters.settore:
                course_settore = info.get("settore", "").lower()
                if filters.settore.lower() not in course_settore:
                    continue

            allowed.add(title)

        return allowed

    def get_stats(self) -> CatalogStats:
        faculties = set()
        degree_courses = set()
        cfus = set()
        settori = set()
        total_lessons = sum(self.total_lessons_by_course.values())

        for info in self.catalog.values():
            fac = info.get("facolta")
            if fac:
                # Split if multiple
                for p in str(fac).split(","):
                    p_clean = p.strip()
                    if p_clean:
                        faculties.add(p_clean)
            cdl = info.get("corso_laurea")
            if cdl:
                for p in str(cdl).split(","):
                    p_clean = p.strip()
                    if p_clean:
                        degree_courses.add(p_clean)
            cfu = info.get("cfu")
            if cfu is not None:
                cfus.add(cfu)
            settore = info.get("settore")
            if settore:
                settori.add(settore)

        return CatalogStats(
            total_courses=len(self.catalog),
            total_lessons=total_lessons,
            faculties=sorted(list(faculties)),
            degree_courses=sorted(list(degree_courses)),
            available_cfus=sorted(list(cfus)),
            settori=sorted(list(settori)),
            is_synced_with_rag=self.is_synced
        )

    def get_filter_options(self) -> FilterOptionsResponse:
        stats = self.get_stats()
        # Curate standard clean faculty list for UI dropdowns
        curated_faculties = [
            "Ingegneria",
            "Economia",
            "Giurisprudenza",
            "Lettere / Beni Culturali",
            "Psicologia",
            "Scienze della Comunicazione"
        ]
        return FilterOptionsResponse(
            faculties=curated_faculties,
            degree_types=["Triennale", "Magistrale"],
            cfu_list=stats.available_cfus,
            settori=sorted(list({s.split('/')[0].strip() for s in stats.settori if '/' in s}))
        )

catalog_service = CatalogService()
