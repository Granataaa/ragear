import pytest
import asyncio
from unittest.mock import AsyncMock
from app.services.recommender import RAGERRecommender
from app.schemas.models import RecommendationRequest, RecommendationFilters

@pytest.fixture
def recommender():
    rec = RAGERRecommender()
    return rec

def test_calculate_query_k(recommender):
    q1 = "computer software database algoritmi programmazione"
    k1 = recommender.calculate_query_k(q1)
    assert k1 >= 4

    q2 = "il la che per"
    k2 = recommender.calculate_query_k(q2)
    assert k2 == 1

def test_weighted_rank_sum(recommender):
    ranks = [1, 2, 3]
    k = 10
    expected = (1/11) + (1/12) + (1/13)
    val = recommender.weighted_rank_sum(ranks, k)
    assert pytest.approx(val, 0.0001) == expected

@pytest.mark.asyncio
async def test_recommend_with_mock_rag(recommender):
    # Mock RAG client response
    mock_rag_response = {
        "chunks": [
            {
                "chunk_id": "c1",
                "text": "Introduzione ai database relazionali e modelli entità-relazione.",
                "final_score": 0.95,
                "source": "https://streaming.test/video/db/Lez001.mp4",
                "start_time": 60.0,
                "end_time": 180.0,
                "metadata": {
                    "titoloCorso": "Basi di dati",
                    "titoloLezione": "Introduzione ai Database",
                    "facolta": "Ingegneria",
                    "corso_laurea": "Ingegneria Informatica",
                    "cfu": 9,
                    "settore": "ING-INF/05"
                }
            },
            {
                "chunk_id": "c2",
                "text": "Algebra relazionale e query SQL complesse.",
                "final_score": 0.88,
                "source": "https://streaming.test/video/db/Lez002.mp4",
                "start_time": 120.0,
                "end_time": 300.0,
                "metadata": {
                    "titoloCorso": "Basi di dati",
                    "titoloLezione": "Query SQL",
                    "facolta": "Ingegneria",
                    "corso_laurea": "Ingegneria Informatica",
                    "cfu": 9,
                    "settore": "ING-INF/05"
                }
            },
            {
                "chunk_id": "c3",
                "text": "Cenni sulla gestione aziendale e bilancio.",
                "final_score": 0.40,
                "source": "https://streaming.test/video/eco/Lez001.mp4",
                "start_time": 0.0,
                "end_time": 60.0,
                "metadata": {
                    "titoloCorso": "Economia aziendale",
                    "titoloLezione": "Introduzione al bilancio",
                    "facolta": "Economia",
                    "corso_laurea": "Economia e gestione",
                    "cfu": 12,
                    "settore": "SECS-P/07"
                }
            }
        ]
    }

    recommender.client.ask = AsyncMock(return_value=mock_rag_response)

    req = RecommendationRequest(
        question="Vorrei un corso su database e linguaggi SQL",
        top_k_chunks=3
    )

    res = await recommender.recommend(req)
    assert res is not None
    assert len(res.recommendations) == 2

    # First recommendation should be "Basi di dati"
    top_rec = res.recommendations[0]
    assert "Basi di dati" in top_rec.course_title
    assert top_rec.rank == 1
    assert top_rec.confidence_percent == 100.0
    assert len(top_rec.matched_lessons) == 2
    assert top_rec.matched_lessons[0].formatted_time == "00:01:00 - 00:03:00"

    # Second recommendation should have lower confidence
    second_rec = res.recommendations[1]
    assert "Economia" in second_rec.course_title
    assert second_rec.rank == 2
    assert second_rec.confidence_percent < 100.0

@pytest.mark.asyncio
async def test_recommend_with_filter(recommender):
    mock_rag_response = {
        "chunks": [
            {
                "chunk_id": "c1",
                "text": "Programmazione Java e OOP",
                "final_score": 0.90,
                "metadata": {
                    "titoloCorso": "Ingegneria del Software",
                    "facolta": "Ingegneria",
                    "cfu": 9
                }
            },
            {
                "chunk_id": "c2",
                "text": "Diritto dell'informatica",
                "final_score": 0.85,
                "metadata": {
                    "titoloCorso": "Diritto Privato",
                    "facolta": "Giurisprudenza",
                    "cfu": 12
                }
            }
        ]
    }
    recommender.client.ask = AsyncMock(return_value=mock_rag_response)

    # Filter by Ingegneria only
    req = RecommendationRequest(
        question="Programmazione",
        top_k_chunks=2,
        filters=RecommendationFilters(facolta="Ingegneria")
    )

    res = await recommender.recommend(req)
    assert len(res.recommendations) == 1
    assert "Ingegneria" in res.recommendations[0].course_title
