# src/rag_service/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from core.security import require_api_key
from core.database import (Base, engine)
from api.v1.conversations import router as conversations_router
from api.v1.messages import router as messages_router
from api.v1.documents import router as documents_router
from api.v1.assistant_turns import router as assistant_turns_router


# بارگذاری اولیه مدل reranker برای بهبود نتایج جستجو
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    # preload reranker
    try:
        from services.reranker_service import _ensure_reranker
        _ensure_reranker()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Reranker preload failed: %s", exc
        )

    yield


app = FastAPI(
    title="Arian Enterprise Assistant API",
    lifespan=lifespan,
)


# --------------------------------------------------
# Routers
# --------------------------------------------------

app.include_router(
    conversations_router,
)

app.include_router(
    messages_router,
)

app.include_router(
    documents_router,
)

app.include_router(
    assistant_turns_router,
)

# --------------------------------------------------
# Health
# --------------------------------------------------

@app.get("/health")
async def health():

    return {
        "status": "healthy"
    }

@app.get("/test-protected", dependencies=[Depends(require_api_key)])
async def test_protected():
    return {
            "status": "healthy"
        }