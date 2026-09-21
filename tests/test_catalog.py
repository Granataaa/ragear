import pytest
from app.services.catalog import CatalogService
from app.schemas.models import RecommendationFilters

@pytest.fixture
def catalog_svc():
    return CatalogService("data/course_catalog.json")

def test_catalog_load(catalog_svc):
    assert len(catalog_svc.catalog) > 0
    stats = catalog_svc.get_stats()
    assert stats.total_courses >= 200
    assert stats.total_lessons > 4000
    assert len(stats.faculties) > 0
    assert len(stats.available_cfus) > 0

def test_course_normalization(catalog_svc):
    norm1 = catalog_svc.normalize_name("Ingegneria del Software")
    norm2 = catalog_svc.normalize_name("ingegneria-del_software!!!")
    assert norm1 == norm2 == "ingegneriadelsoftware"

def test_filter_courses_by_cfu(catalog_svc):
    filters = RecommendationFilters(cfu=12)
    allowed = catalog_svc.filter_courses(filters)
    assert allowed is not None
    assert len(allowed) > 0
    # Verify each allowed course actually has 12 CFU
    for title in allowed:
        info = catalog_svc.catalog[title]
        assert info["cfu"] == 12

def test_filter_courses_by_faculty(catalog_svc):
    filters = RecommendationFilters(facolta="Ingegneria")
    allowed = catalog_svc.filter_courses(filters)
    assert allowed is not None
    assert len(allowed) > 0
    for title in allowed:
        info = catalog_svc.catalog[title]
        assert "ingegneria" in info["facolta"].lower()

def test_sync_from_mock_rag_chunks():
    svc = CatalogService("non_existent_file.json")
    mock_chunks = [
        {
            "chunk_id": "1",
            "source": "https://streaming.test/video/uid1/Lez001.mp4",
            "metadata": {
                "titoloCorso": "Corso di Test Avanzato",
                "titoloLezione": "Introduzione ai Test",
                "facolta": "Ingegneria",
                "corso_laurea": "Ingegneria Informatica",
                "cfu": 6,
                "settore": "ING-INF/05"
            }
        },
        {
            "chunk_id": "2",
            "source": "https://streaming.test/video/uid1/Lez002.mp4",
            "metadata": {
                "titoloCorso": "Corso di Test Avanzato",
                "titoloLezione": "Approfondimento",
                "facolta": "Ingegneria",
                "corso_laurea": "Ingegneria Informatica",
                "cfu": 6,
                "settore": "ING-INF/05"
            }
        }
    ]

    success = svc.sync_from_rag_chunks(mock_chunks)
    assert success is True
    assert "Corso di Test Avanzato" in svc.catalog
    info = svc.catalog["Corso di Test Avanzato"]
    assert info["cfu"] == 6
    assert info["facolta"] == "Ingegneria"
    assert svc.get_total_lessons("Corso di Test Avanzato") == 2
