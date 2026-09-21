import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # RAG Engine Backend & Frontend
    rag_server_url: str = os.getenv("RAG_SERVER_URL", "http://10.10.11.141:5005")
    rag_frontend_url: str = os.getenv("RAG_FRONTEND_URL", "http://10.10.11.141:3000")
    rag_timeout: float = float(os.getenv("RAG_TIMEOUT", "25.0"))

    # RAGER Recommender Hyperparameters
    default_top_k: int = int(os.getenv("DEFAULT_TOP_K", "50"))
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    
    # Catalog
    catalog_path: str = os.getenv("CATALOG_PATH", "data/course_catalog.json")
    sync_catalog_on_startup: bool = os.getenv("SYNC_CATALOG_ON_STARTUP", "true").lower() in ("true", "1", "yes")
    sync_catalog_interval_hours: int = int(os.getenv("SYNC_CATALOG_INTERVAL_HOURS", "24"))

    # App
    app_title: str = "RAGEAR - UNINETTUNO Course Recommender"
    app_version: str = "2.0.0"
    debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

settings = Settings()
