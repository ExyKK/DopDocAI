from contextlib import asynccontextmanager
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

from app.config import settings

_model: SentenceTransformer | None = None


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)
    input_type: Literal["document", "query"] = "document"
    model: str | None = None
    normalize: bool = True


class EmbeddingResponse(BaseModel):
    model: str
    dimension: int
    input_type: str
    embeddings: list[list[float]]


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_model()
    yield


app = FastAPI(title="DopDoc Embedding Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok" if _model is not None else "starting",
        "service": settings.service_name,
        "model": settings.model_name,
        "dimension": settings.vector_size,
    }


@app.post("/internal/embeddings", response_model=EmbeddingResponse)
def embed(request: EmbeddingRequest) -> EmbeddingResponse:
    if request.model and request.model != settings.model_name:
        raise HTTPException(
            status_code=400,
            detail=f"Only model {settings.model_name} is loaded.",
        )

    model = _load_model()
    vectors = model.encode(
        request.texts,
        batch_size=settings.batch_size,
        normalize_embeddings=request.normalize and settings.normalize_embeddings,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    embeddings = [[float(value) for value in vector] for vector in vectors]
    if embeddings and len(embeddings[0]) != settings.vector_size:
        raise HTTPException(
            status_code=500,
            detail=f"Model returned {len(embeddings[0])} dimensions, expected {settings.vector_size}.",
        )

    return EmbeddingResponse(
        model=settings.model_name,
        dimension=settings.vector_size,
        input_type=request.input_type,
        embeddings=embeddings,
    )


def _load_model() -> SentenceTransformer:
    global _model
    if _model is None:
        kwargs = {"trust_remote_code": settings.trust_remote_code}
        if settings.device:
            kwargs["device"] = settings.device
        _model = SentenceTransformer(settings.model_name, **kwargs)
    return _model


def main() -> None:
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
