import re
import time
import math
import logging
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional, Set
from app.config import settings
from app.client.rag_client import rag_client
from app.services.catalog import catalog_service
from app.schemas.models import (
    RecommendationRequest,
    RecommendationResponse,
    CourseRecommendation,
    ScoreBreakdown,
    MatchedLesson,
    RecommendationFilters
)

logger = logging.getLogger("ragear.recommender")

ITALIAN_STOPWORDS = {
    "anche", "avere", "come", "con", "che", "dei", "del", "della", "delle",
    "dello", "degli", "gli", "il", "in", "la", "le", "lo", "mi", "nel",
    "nella", "nelle", "per", "piu", "sul", "sulla", "un", "una", "vorrei",
    "sono", "essere", "modo", "corso", "corsi", "argomenti", "lezione",
    "lezioni", "universita", "esame", "esami", "imparare", "studiare"
}

def format_timestamp(seconds: float) -> str:
    """
    Format seconds (e.g. 754.0) into HH:MM:SS format (e.g. 00:12:34).
    """
    if seconds is None or seconds < 0:
        return "00:00:00"
    total_sec = int(round(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"

class RAGERRecommender:
    def __init__(self):
        self.client = rag_client
        self.catalog = catalog_service

    def calculate_query_k(self, question: str) -> int:
        """
        Calculates the query-dependent damping factor k for rank weighting.
        """
        tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{4,}", question.lower())
        informative = [t for t in tokens if t not in ITALIAN_STOPWORDS]
        return max(1, min(len(informative), 20))

    def weighted_rank_sum(self, ranks: List[int], k: int) -> float:
        return sum(1.0 / (k + rank) for rank in ranks if isinstance(rank, int) and rank > 0)

    def extract_course_names_from_chunk(self, chunk: Dict[str, Any]) -> List[str]:
        """
        Extract canonical course titles from chunk metadata or fields.
        """
        meta = chunk.get("metadata") or {}
        raw = meta.get("titoloCorso") or chunk.get("COURSE_TITLE") or chunk.get("COURSE_TITLE_NO_WS_TITLE")
        if not raw:
            return []

        courses_list = [raw] if isinstance(raw, str) else list(raw)
        canonical_courses = []
        for c in courses_list:
            c_clean = str(c).strip()
            canonical = self.catalog.find_canonical_course(c_clean)
            if canonical:
                canonical_courses.append(canonical)
            else:
                canonical_courses.append(c_clean)
        return list(set(canonical_courses))

    def extract_lesson_info(self, chunk: Dict[str, Any]) -> Tuple[str, Optional[int], str, str, str]:
        """
        Extract (lesson_identifier, lesson_number, title, video_url, link_lezione).
        Safely handles metadata fields that might be lists of strings.
        """
        meta = chunk.get("metadata") or {}
        raw_vid = meta.get("filename") or chunk.get("source") or meta.get("hiddenFilename") or ""
        video_url = raw_vid[0] if isinstance(raw_vid, list) and raw_vid else (raw_vid if isinstance(raw_vid, str) else "")

        raw_link = meta.get("link_lezione") or ""
        link_lez = raw_link[0] if isinstance(raw_link, list) and raw_link else (raw_link if isinstance(raw_link, str) else "")

        raw_title = meta.get("titoloLezione") or chunk.get("LESSON_TITLE") or ""
        title = raw_title[0] if isinstance(raw_title, list) and raw_title else (raw_title if isinstance(raw_title, str) else "")

        lez_num = None
        if video_url:
            m = re.search(r'Lez0*(\d+)', video_url, re.IGNORECASE)
            if m:
                lez_num = int(m.group(1))
        if lez_num is None and title:
            m = re.search(r'(?:Lezione|Lez\.?)\s*0*(\d+)', title, re.IGNORECASE)
            if m:
                lez_num = int(m.group(1))
        if lez_num is None and chunk.get("LESSON_NUMBER"):
            try:
                lez_num = int(chunk["LESSON_NUMBER"])
            except:
                pass

        ident = video_url or link_lez or title or f"chunk_{chunk.get('chunk_id')}"
        return ident, lez_num, title, video_url, link_lez

    async def recommend(self, req: RecommendationRequest) -> RecommendationResponse:
        start_time = time.time()
        question = req.question.strip()
        top_k = req.top_k_chunks

        # 1. Fetch relevant chunks from central RAG server
        rag_data = await self.client.ask(question, k_ric=top_k, llm_help=False)
        raw_chunks = rag_data.get("chunks", [])

        if not raw_chunks:
            return RecommendationResponse(
                query=question,
                total_candidates_evaluated=0,
                rag_server_url=self.client.base_url,
                elapsed_seconds=round(time.time() - start_time, 3),
                filters_applied=req.filters,
                recommendations=[]
            )

        # 2. Check academic filters
        allowed_courses: Optional[Set[str]] = self.catalog.filter_courses(req.filters)

        # 3. Filter and assign rank to chunks
        ranked_chunks = []
        for rank, chunk in enumerate(raw_chunks, start=1):
            chunk_copy = dict(chunk)
            chunk_copy["rank"] = rank
            
            # Determine score
            score = chunk.get(req.score_key)
            if score is None:
                score = chunk.get("final_score") or chunk.get("rrf_score") or chunk.get("dense_score") or 0.0
            
            # Map score to non-negative weight:
            # - If cross-encoder output is a logit (or negative), map via sigmoid: 1 / (1 + e^-s)
            # - Otherwise keep positive float
            score = float(score)
            if req.score_key == "final_score" or score < 0:
                clamped_logit = min(15.0, max(-15.0, score))
                chunk_copy["computed_score"] = 1.0 / (1.0 + math.exp(-clamped_logit))
            else:
                chunk_copy["computed_score"] = max(0.0001, score)
            
            # Resolve courses
            course_titles = self.extract_course_names_from_chunk(chunk_copy)
            
            # Apply filter
            if allowed_courses is not None:
                passed_courses = []
                for c in course_titles:
                    if c in allowed_courses:
                        passed_courses.append(c)
                    else:
                        # Check chunk's own metadata as fallback
                        meta = chunk_copy.get("metadata") or {}
                        meta_fac = str(meta.get("facolta", "")).lower()
                        req_fac = (req.filters.facolta or "").lower() if req.filters else ""
                        if req_fac and req_fac in meta_fac:
                            passed_courses.append(c)
                course_titles = passed_courses

            if course_titles:
                chunk_copy["assigned_courses"] = course_titles
                ranked_chunks.append(chunk_copy)

        if not ranked_chunks:
            return RecommendationResponse(
                query=question,
                total_candidates_evaluated=len(raw_chunks),
                rag_server_url=self.client.base_url,
                elapsed_seconds=round(time.time() - start_time, 3),
                filters_applied=req.filters,
                recommendations=[]
            )

        # 4. RAGER Calculations
        k = self.calculate_query_k(question)
        total_score_sum = sum(c["computed_score"] for c in ranked_chunks)

        # Group ranks and scores by course
        scores_by_course = defaultdict(float)
        ranks_by_course = defaultdict(list)
        chunks_by_course = defaultdict(list)
        best_lesson_ranks_by_course = defaultdict(dict)

        for chunk in ranked_chunks:
            rank = chunk["rank"]
            c_score = chunk["computed_score"]
            lez_id, lez_num, lez_title, vid_url, link_lez = self.extract_lesson_info(chunk)

            for course_title in chunk["assigned_courses"]:
                scores_by_course[course_title] += c_score
                ranks_by_course[course_title].append(rank)
                chunks_by_course[course_title].append(chunk)

                # Track best rank for this lesson in this course
                current_best = best_lesson_ranks_by_course[course_title].get(lez_id)
                if current_best is None or rank < current_best:
                    best_lesson_ranks_by_course[course_title][lez_id] = rank

        # Denominator for Chunk Rank Factor (CRF)
        denominator_crf = self.weighted_rank_sum(range(1, len(ranked_chunks) + 1), k)
        if denominator_crf <= 0:
            denominator_crf = 1.0

        all_candidate_courses = set(scores_by_course.keys())
        scored_courses = []

        for course_title in all_candidate_courses:
            # Term 1: Score distribution
            c_score_sum = scores_by_course[course_title]
            term_1 = (c_score_sum / total_score_sum) if total_score_sum > 0 else 0.0

            # Term 2: Chunk Rank Factor (CRF)
            crf_numerator = self.weighted_rank_sum(ranks_by_course[course_title], k)
            term_2 = crf_numerator / denominator_crf

            # Term 3: Lesson Rank Factor (LRF)
            total_course_lessons = self.catalog.get_total_lessons(course_title)
            lesson_ranks = list(best_lesson_ranks_by_course[course_title].values())
            lrf_numerator = self.weighted_rank_sum(lesson_ranks, k)
            term_3 = (lrf_numerator / total_course_lessons) if total_course_lessons > 0 else 0.0

            final_recommendation_score = term_1 * term_2 * term_3

            # Extract matched lesson items for this course
            seen_lessons = set()
            matched_lessons_list = []
            
            # Sort chunks for this course by rank (best first)
            course_chunks = sorted(chunks_by_course[course_title], key=lambda x: x["rank"])
            for ch in course_chunks:
                lez_id, lez_num, lez_title, vid_url, link_lez = self.extract_lesson_info(ch)
                if lez_id in seen_lessons:
                    continue
                seen_lessons.add(lez_id)

                meta = ch.get("metadata") or {}
                start_sec = float(ch.get("start_time") or meta.get("start_time") or 0.0)
                end_sec = float(ch.get("end_time") or meta.get("end_time") or 0.0)
                
                formatted_time = f"{format_timestamp(start_sec)} - {format_timestamp(end_sec)}"
                snippet = ch.get("text", "").strip()
                if len(snippet) > 280:
                    snippet = snippet[:280] + "..."

                matched_lessons_list.append(MatchedLesson(
                    lesson_title=lez_title or f"Lezione {lez_num or ''}".strip() or "Lezione",
                    lesson_number=lez_num,
                    video_url=vid_url or ch.get("source"),
                    link_lezione=link_lez or None,
                    start_time=start_sec,
                    end_time=end_sec,
                    formatted_time=formatted_time,
                    snippet=snippet,
                    score=round(ch["computed_score"], 4)
                ))

            # Retrieve academic course metadata
            course_info = self.catalog.get_course_info(course_title) or {}

            scored_courses.append({
                "course_title": course_title,
                "course_id": course_info.get("course_id") or re.sub(r'[^a-zA-Z0-9]', '', course_title),
                "facolta": course_info.get("facolta", ""),
                "corso_laurea": course_info.get("corso_laurea", ""),
                "tipologia": course_info.get("tipologia", ""),
                "cfu": course_info.get("cfu"),
                "settore": course_info.get("settore", ""),
                "link_corso": course_info.get("link_corso", ""),
                "recommendation_score": final_recommendation_score,
                "score_breakdown": ScoreBreakdown(
                    term_1_score_ratio=round(term_1, 6),
                    term_2_chunk_rank_factor=round(term_2, 6),
                    term_3_lesson_rank_factor=round(term_3, 6),
                    raw_score=final_recommendation_score,
                    matched_chunks_count=len(ranks_by_course[course_title]),
                    unique_lessons_count=len(lesson_ranks),
                    total_course_lessons=total_course_lessons
                ),
                "matched_lessons": matched_lessons_list[:5]  # Top 5 most relevant lessons
            })

        # Sort courses descending by recommendation score
        scored_courses.sort(key=lambda x: x["recommendation_score"], reverse=True)

        # Compute confidence percent normalized against top score
        top_score = scored_courses[0]["recommendation_score"] if scored_courses else 1.0
        if top_score <= 0:
            top_score = 1.0

        recommendations = []
        for idx, item in enumerate(scored_courses, start=1):
            ratio = max(0.0, item["recommendation_score"] / top_score)
            # Use cubic-root normalization because RAGER is a 3-way product (Term1 * CRF * LRF).
            # This provides meaningful relative affinity percentages across ranks without collapsing to 0.0%.
            conf = round(min(100.0, (ratio ** (1.0 / 3.0)) * 100.0), 1)
            recommendations.append(CourseRecommendation(
                rank=idx,
                course_id=item["course_id"],
                course_title=item["course_title"],
                facolta=item["facolta"],
                corso_laurea=item["corso_laurea"],
                tipologia=item["tipologia"],
                cfu=item["cfu"],
                settore=item["settore"],
                link_corso=item["link_corso"],
                recommendation_score=item["recommendation_score"],
                confidence_percent=conf,
                score_breakdown=item["score_breakdown"],
                matched_lessons=item["matched_lessons"]
            ))

        elapsed = round(time.time() - start_time, 3)
        return RecommendationResponse(
            query=question,
            total_candidates_evaluated=len(raw_chunks),
            rag_server_url=self.client.base_url,
            elapsed_seconds=elapsed,
            filters_applied=req.filters,
            recommendations=recommendations
        )

recommender = RAGERRecommender()
