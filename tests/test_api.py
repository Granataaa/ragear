import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ragear"

def test_filters_endpoint():
    res = client.get("/api/v1/filters")
    assert res.status_code == 200
    data = res.json()
    assert "faculties" in data
    assert "cfu_list" in data
    assert len(data["faculties"]) > 0

def test_sample_queries_endpoint():
    res = client.get("/api/v1/sample-queries")
    assert res.status_code == 200
    data = res.json()
    assert "queries" in data
    assert len(data["queries"]) > 0

def test_courses_catalog_endpoint():
    res = client.get("/api/v1/courses?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    assert len(data["courses"]) <= 10

@patch("app.client.rag_client.rag_client.ask", new_callable=AsyncMock)
def test_recommend_api(mock_ask):
    mock_ask.return_value = {
        "chunks": [
            {
                "chunk_id": "c1",
                "text": "Algoritmi e complessità computazionale",
                "final_score": 0.95,
                "metadata": {
                    "titoloCorso": "Algoritmi e Strutture Dati",
                    "facolta": "Ingegneria",
                    "cfu": 12
                }
            }
        ]
    }

    res = client.post("/api/v1/recommend", json={
        "question": "Vorrei approfondire gli algoritmi e le strutture dati",
        "top_k_chunks": 10
    })

    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "Vorrei approfondire gli algoritmi e le strutture dati"
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["course_title"] == "Algoritmi e Strutture Dati"
