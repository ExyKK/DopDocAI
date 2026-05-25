import logging

import psycopg
import uvicorn
from fastapi import FastAPI, HTTPException

from app.core.config import settings
from app.infra.object_storage import ObjectStorageClient

logger = logging.getLogger("documentation_service")

app = FastAPI(title="DopDoc documentation_service", version="0.1.0")


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/health/ready")
def ready() -> dict[str, object]:
    problems: dict[str, str] = {}

    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover - readiness diagnostic
        problems["postgres"] = str(exc)

    try:
        storage = _object_storage()
        if not storage.bucket_exists():
            problems["minio"] = f"bucket {storage.bucket} does not exist"
    except Exception as exc:  # pragma: no cover - readiness diagnostic
        problems["minio"] = str(exc)

    if problems:
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "checks": problems},
        )

    return {
        "status": "ok",
        "service": settings.service_name,
        "checks": {"postgres": "ok", "minio": "ok"},
    }


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.info("Starting documentation_service API on %s:%s", settings.host, settings.port)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


def _object_storage() -> ObjectStorageClient:
    return ObjectStorageClient(
        endpoint_url=str(settings.s3_endpoint),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
    )


if __name__ == "__main__":
    main()
