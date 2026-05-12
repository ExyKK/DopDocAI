import logging
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.deps import get_treesitter
from app.api.routes.retrieval import router as retrieval_router
from app.core.config import settings

logger = logging.getLogger("ingestion_service")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    logger.info("Service starting: %s", settings.service_name)

    t0 = time.monotonic()
    try:
        logger.info("Warmup: initializing tree-sitter...")
        get_treesitter()
        logger.info("Warmup: tree-sitter initialized.")

        dt = time.monotonic() - t0
        logger.info("Warmup complete in %.2fs. Service is ready.", dt)

    except Exception as e:
        logger.exception("Warmup failed: %s", e)
        raise

    yield

    logger.info("Service shutting down: %s", settings.service_name)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.include_router(retrieval_router)

    @app.get("/health")
    async def healthcheck():
        return {"service": settings.service_name, "status": "healthy"}

    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
