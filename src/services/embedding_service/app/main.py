import logging
from contextlib import asynccontextmanager
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

from app.config import settings

_model: SentenceTransformer | None = None
logger = logging.getLogger(__name__)


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
        "device": _model_device(),
        "batch_size": settings.batch_size,
        "max_seq_length": settings.max_seq_length,
        "torch_dtype": settings.torch_dtype,
    }


@app.post("/internal/embeddings", response_model=EmbeddingResponse)
def embed(request: EmbeddingRequest) -> EmbeddingResponse:
    if request.model and request.model != settings.model_name:
        raise HTTPException(
            status_code=400,
            detail=f"Only model {settings.model_name} is loaded.",
        )

    model = _load_model()
    try:
        vectors = _encode_with_oom_retry(
            model=model,
            texts=request.texts,
            normalize=request.normalize and settings.normalize_embeddings,
        )
    except EmbeddingOutOfMemoryError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
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
        kwargs: dict[str, object] = {"trust_remote_code": settings.trust_remote_code}
        if settings.device:
            kwargs["device"] = settings.device
        model_kwargs = _build_model_kwargs()
        if model_kwargs:
            kwargs["model_kwargs"] = model_kwargs
        logger.info(
            "Loading embedding model model=%s device=%s dtype=%s max_seq_length=%s",
            settings.model_name,
            settings.device or "auto",
            settings.torch_dtype or "model-default",
            settings.max_seq_length or "model-default",
        )
        _model = SentenceTransformer(settings.model_name, **kwargs)
        if settings.max_seq_length:
            _model.max_seq_length = settings.max_seq_length
        logger.info(
            "Embedding model loaded model=%s device=%s dimension=%s max_seq_length=%s",
            settings.model_name,
            _model_device(),
            settings.vector_size,
            getattr(_model, "max_seq_length", None),
        )
    return _model


class EmbeddingOutOfMemoryError(RuntimeError):
    pass


def _encode_with_oom_retry(
    *,
    model: SentenceTransformer,
    texts: list[str],
    normalize: bool,
):
    batch_size = max(1, settings.batch_size)
    while True:
        try:
            return model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except RuntimeError as exc:
            if not _is_cuda_oom(exc):
                raise

            _clear_cuda_cache()
            if batch_size == 1:
                message = (
                    "CUDA out of memory while embedding request "
                    f"with batch_size=1 and max_seq_length={settings.max_seq_length or 'model-default'}. "
                    "Lower EMBED_MAX_SEQ_LENGTH or use the CPU/hash mode for this run."
                )
                logger.exception(message)
                raise EmbeddingOutOfMemoryError(message) from exc

            next_batch_size = max(1, batch_size // 2)
            logger.warning(
                "CUDA OOM while embedding request; retrying with smaller batch size "
                "previous_batch_size=%s next_batch_size=%s",
                batch_size,
                next_batch_size,
            )
            batch_size = next_batch_size


def _build_model_kwargs() -> dict[str, object]:
    torch_dtype = _resolve_torch_dtype()
    if torch_dtype is None:
        return {}
    return {"torch_dtype": torch_dtype}


def _resolve_torch_dtype() -> object | None:
    if not settings.torch_dtype:
        return None

    dtype = settings.torch_dtype.lower()
    if dtype == "auto":
        return "auto"

    import torch

    aliases = {
        "fp16": "float16",
        "float16": "float16",
        "bf16": "bfloat16",
        "bfloat16": "bfloat16",
        "fp32": "float32",
        "float32": "float32",
    }
    torch_name = aliases.get(dtype)
    if torch_name is None:
        raise ValueError(
            "Unsupported EMBED_TORCH_DTYPE. Use one of: auto, float16, bfloat16, float32."
        )
    return getattr(torch, torch_name)


def _is_cuda_oom(exc: RuntimeError) -> bool:
    return exc.__class__.__name__ == "OutOfMemoryError" or "CUDA out of memory" in str(exc)


def _clear_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        logger.debug("Failed to clear CUDA cache after OOM", exc_info=True)


def _model_device() -> str | None:
    if _model is None:
        return settings.device

    device = getattr(_model, "device", None)
    if device is None:
        return settings.device
    return str(device)


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        access_log=settings.access_log,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
