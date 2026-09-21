from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class RecommendationFilters(BaseModel):
    facolta: Optional[str] = Field(None, description="Filtro per facoltà (es. 'Ingegneria', 'Economia')")
    cfu: Optional[int] = Field(None, description="Filtro per CFU esatto (es. 6, 9, 12)")
    min_cfu: Optional[int] = Field(None, description="CFU minimi")
    max_cfu: Optional[int] = Field(None, description="CFU massimi")
    tipologia_corso: Optional[str] = Field(None, description="Tipologia corso di laurea (es. 'triennale', 'magistrale')")
    settore: Optional[str] = Field(None, description="Filtro per settore scientifico disciplinare (es. 'ING-INF', 'SECS-P')")

class RecommendationRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Interessi o domanda di orientamento dello studente",
                          json_schema_extra={"example": "Vorrei seguire un corso su basi di dati, SQL e programmazione software"})
    top_k_chunks: int = Field(50, ge=1, le=200, description="Numero di chunk semantici da interrogare sul server RAG")
    score_key: str = Field("final_score", description="Punteggio da utilizzare (final_score, rrf_score, dense_score)")
    filters: Optional[RecommendationFilters] = Field(None, description="Filtri opzionali accademici")

class MatchedLesson(BaseModel):
    lesson_title: str
    lesson_number: Optional[int] = None
    video_url: Optional[str] = None
    link_lezione: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    formatted_time: str = ""
    snippet: str = ""
    score: float = 0.0

class ScoreBreakdown(BaseModel):
    term_1_score_ratio: float = Field(..., description="Term 1: Quota di punteggio del corso rispetto al totale dei chunk")
    term_2_chunk_rank_factor: float = Field(..., description="Term 2: Fattore di posizione (CRF) dei chunk nella graduatoria")
    term_3_lesson_rank_factor: float = Field(..., description="Term 3: Fattore di copertura lezioni (LRF) rispetto al corso")
    raw_score: float = Field(..., description="Prodotto Term1 * Term2 * Term3")
    matched_chunks_count: int
    unique_lessons_count: int
    total_course_lessons: int

class CourseRecommendation(BaseModel):
    rank: int
    course_id: str
    course_title: str
    facolta: str = ""
    corso_laurea: str = ""
    tipologia: str = ""
    cfu: Optional[int] = None
    settore: str = ""
    link_corso: Optional[str] = None
    recommendation_score: float
    confidence_percent: float = Field(..., description="Punteggio percentuale normalizzato (0-100%)")
    score_breakdown: ScoreBreakdown
    matched_lessons: List[MatchedLesson] = Field(default_factory=list)

class RecommendationResponse(BaseModel):
    query: str
    total_candidates_evaluated: int
    rag_server_url: str
    elapsed_seconds: float
    filters_applied: Optional[RecommendationFilters] = None
    recommendations: List[CourseRecommendation]

class CatalogStats(BaseModel):
    total_courses: int
    total_lessons: int
    faculties: List[str]
    degree_courses: List[str]
    available_cfus: List[int]
    settori: List[str]
    is_synced_with_rag: bool

class RAGStatusResponse(BaseModel):
    rag_server_url: str
    rag_frontend_url: str
    is_online: bool
    status_message: str
    catalog_stats: CatalogStats

class FilterOptionsResponse(BaseModel):
    faculties: List[str]
    degree_types: List[str]
    cfu_list: List[int]
    settori: List[str]
