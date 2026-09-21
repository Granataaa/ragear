import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import router as api_router
from app.client.rag_client import rag_client
from app.services.catalog import catalog_service

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ragear.main")

async def background_catalog_sync():
    try:
        logger.info("Avvio sincronizzazione dinamica catalogo in background dal server RAG...")
        chunks = await rag_client.list_all()
        if chunks:
            catalog_service.sync_from_rag_chunks(chunks)
            logger.info(f"Sincronizzazione dinamica completata: {len(catalog_service.catalog)} corsi aggiornati.")
        else:
            logger.info("Nessun chunk ricevuto dal RAG per il sync, continuo con la cache locale.")
    except Exception as e:
        logger.warning(f"Errore durante la sincronizzazione catalogo in background: {e}")

async def periodic_catalog_sync_loop():
    import asyncio
    # 1. Initial sync on startup if enabled
    if settings.sync_catalog_on_startup:
        await background_catalog_sync()

    # 2. Periodic sync if interval > 0
    if settings.sync_catalog_interval_hours > 0:
        interval_seconds = settings.sync_catalog_interval_hours * 3600
        logger.info(f"Schedulato aggiornamento periodico catalogo ogni {settings.sync_catalog_interval_hours}h ({interval_seconds}s).")
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                logger.info("Esecuzione aggiornamento schedulato periodico del catalogo corsi...")
                await background_catalog_sync()
            except asyncio.CancelledError:
                logger.info("Loop di aggiornamento periodico catalogo interrotto.")
                break
            except Exception as e:
                logger.warning(f"Errore durante l'aggiornamento periodico catalogo: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    logger.info(f"Avvio di {settings.app_title} v{settings.app_version}")
    logger.info(f"Target RAG Server: {settings.rag_server_url}")

    # Check connection to remote RAG server
    is_online, msg = await rag_client.check_health()
    sync_task = None
    if is_online:
        logger.info(f"[OK] {msg}")
        if settings.sync_catalog_on_startup or settings.sync_catalog_interval_hours > 0:
            # Run in background so Uvicorn starts listening immediately
            sync_task = asyncio.create_task(periodic_catalog_sync_loop())
    else:
        logger.warning(f"[AVVISO] {msg}. RAGEAR opererà usando il catalogo locale.")

    yield

    if sync_task:
        sync_task.cancel()
    logger.info("Chiusura servizio RAGEAR.")

app = FastAPI(
    title=settings.app_title,
    description="Motore di Raccomandazione Corsi Universitari basato sull'algoritmo RAGER e integrato con il server UNINETTUNO RAG.",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "ragear",
        "version": settings.app_version,
        "rag_server_url": settings.rag_server_url
    }

@app.get("/", tags=["UI"], include_in_schema=False)
async def serve_ui():
    return FileResponse("static/index.html")
