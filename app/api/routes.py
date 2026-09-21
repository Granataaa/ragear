import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.config import settings
from app.client.rag_client import rag_client
from app.services.catalog import catalog_service
from app.services.recommender import recommender
from app.schemas.models import (
    RecommendationRequest,
    RecommendationResponse,
    RAGStatusResponse,
    FilterOptionsResponse,
    CatalogStats
)

router = APIRouter(prefix="/api/v1", tags=["Course Recommendation & Catalog"])

@router.post("/recommend", response_model=RecommendationResponse, summary="Raccomanda corsi basandosi sugli interessi dello studente")
async def recommend_courses(request: RecommendationRequest):
    """
    Esegue il processo di raccomandazione end-to-end:
    1. Interroga l'indice semantico del server RAG centrale (ChromaDB + Cross-Encoder).
    2. Applica eventuali filtri accademici (CFU, Facoltà, Tipologia di Laurea, Settore disciplinare).
    3. Calcola il ranking RAGER combinando score aggregati, Chunk Rank Factor (CRF) e Lesson Rank Factor (LRF).
    4. Estrae le lezioni più pertinenti con minutaggio e link video per ciascun corso raccomandato.
    """
    try:
        res = await recommender.recommend(request)
        return res
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante il calcolo della raccomandazione: {str(e)}")

@router.get("/filters", response_model=FilterOptionsResponse, summary="Opzioni disponibili per i filtri accademici")
async def get_filter_options():
    """
    Restituisce l'elenco delle facoltà, tipologie di laurea, CFU e settori scientifici
    disponibili nel catalogo per popolare i selettori della UI.
    """
    return catalog_service.get_filter_options()

@router.get("/status", response_model=RAGStatusResponse, summary="Stato del server RAG e del catalogo corsi")
async def get_status():
    """
    Verifica la raggiungibilità del server RAG remoto (10.10.11.141:5005)
    e restituisce le statistiche attuali del catalogo corsi.
    """
    is_online, msg = await rag_client.check_health()
    stats = catalog_service.get_stats()
    return RAGStatusResponse(
        rag_server_url=settings.rag_server_url,
        rag_frontend_url=settings.rag_frontend_url,
        is_online=is_online,
        status_message=msg,
        catalog_stats=stats
    )

@router.post("/catalog/sync", summary="Sincronizza dinamicamente il catalogo con il server RAG")
async def sync_catalog():
    """
    Interroga l'endpoint GET /list del server RAG e aggiorna dinamicamente
    il catalogo dei corsi e il conteggio delle lezioni senza dover riavviare il servizio.
    """
    chunks = await rag_client.list_all()
    if not chunks:
        raise HTTPException(
            status_code=502,
            detail="Nessun dato ricevuto dal server RAG o server non raggiungibile. Impossibile completare il sync."
        )

    success = catalog_service.sync_from_rag_chunks(chunks)
    if not success:
        raise HTTPException(status_code=500, detail="Errore durante l'elaborazione dei chunk del catalogo.")

    return {
        "success": True,
        "message": "Catalogo sincronizzato con successo con il server RAG.",
        "catalog_stats": catalog_service.get_stats()
    }

@router.get("/courses", summary="Esplora il catalogo corsi con filtri")
async def list_courses(
    facolta: Optional[str] = Query(None, description="Filtro facoltà"),
    cfu: Optional[int] = Query(None, description="Filtro CFU esatto"),
    search: Optional[str] = Query(None, description="Testo da cercare nel titolo corso"),
    limit: int = Query(50, ge=1, le=300)
):
    """
    Restituisce l'elenco dei corsi con i relativi metadati accademici e conteggio lezioni.
    """
    results = []
    for title, info in catalog_service.catalog.items():
        if facolta and facolta.lower() not in info.get("facolta", "").lower():
            continue
        if cfu is not None and info.get("cfu") != cfu:
            continue
        if search and search.lower() not in title.lower():
            continue

        results.append({
            "course_id": info.get("course_id"),
            "course_title": title,
            "facolta": info.get("facolta"),
            "corso_laurea": info.get("corso_laurea"),
            "cfu": info.get("cfu"),
            "settore": info.get("settore"),
            "total_lessons": info.get("total_lessons", 0),
            "link_corso": info.get("link_corso")
        })

    return {
        "total": len(results),
        "courses": results[:limit]
    }

@router.get("/sample-queries", summary="Query di orientamento consigliate")
async def get_sample_queries():
    """
    Restituisce una selezione curata di query di orientamento per gli studenti.
    """
    samples = [
        "Vorrei seguire un corso sulla programmazione ad oggetti, algoritmi e Java",
        "Mi interessano le basi di dati, SQL e i sistemi informativi aziendali",
        "Cerco un corso su reti di calcolatori, protocolli internet e cybersecurity",
        "Vorrei approfondire l'intelligenza artificiale, il machine learning e i Big Data",
        "Mi appassionano l'elettronica, i circuiti digitali e i sistemi a microcontrollore",
        "Cerco un corso di ingegneria del software su metodologie agili e testing",
        "Vorrei studiare economia aziendale, bilancio e gestione delle imprese",
        "Mi interessa la psicologia dei processi cognitivi e della comunicazione"
    ]
    return {"queries": samples}
