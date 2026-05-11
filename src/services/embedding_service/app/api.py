from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, status

from app.config import settings
from app.runtime import EmbeddingDimensionError, EmbeddingOutOfMemoryError, EmbeddingRuntime
from app.schemas import EmbeddingRequest, EmbeddingResponse, HealthResponse


def create_app(runtime: EmbeddingRuntime | None = None) -> FastAPI:
    embedding_runtime = runtime or EmbeddingRuntime(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        embedding_runtime.preload()
        yield

    app = FastAPI(title="DopDoc Embedding Service", version="0.1.0", lifespan=lifespan)
    app.state.embedding_runtime = embedding_runtime

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(**asdict(embedding_runtime.status()))

    @app.post("/internal/embeddings", response_model=EmbeddingResponse)
    def embed(request: EmbeddingRequest) -> EmbeddingResponse:
        if request.model and request.model != embedding_runtime.model_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only model {embedding_runtime.model_name} is loaded.",
            )

        try:
            embeddings = embedding_runtime.embed(
                request.texts,
                normalize=request.normalize,
            )
        except EmbeddingOutOfMemoryError as exc:
            raise HTTPException(status_code=status.HTTP_507_INSUFFICIENT_STORAGE, detail=str(exc)) from exc
        except EmbeddingDimensionError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        return EmbeddingResponse(
            model=embedding_runtime.model_name,
            dimension=embedding_runtime.vector_size,
            input_type=request.input_type,
            embeddings=embeddings,
        )

    return app
