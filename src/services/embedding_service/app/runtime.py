import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class SentenceEmbeddingModel(Protocol):
    max_seq_length: int

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
    ) -> Any:
        pass


ModelFactory = Callable[[str, dict[str, object]], SentenceEmbeddingModel]


@dataclass(frozen=True)
class RuntimeStatus:
    status: Literal["starting", "ok"]
    service: str
    model: str
    dimension: int
    device: str | None
    batch_size: int
    max_seq_length: int | None
    torch_dtype: str | None


class EmbeddingDimensionError(RuntimeError):
    pass


class EmbeddingOutOfMemoryError(RuntimeError):
    pass


class EmbeddingRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self._settings = settings
        self._model_factory = model_factory or _sentence_transformer_factory
        self._model: SentenceEmbeddingModel | None = None
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._settings.model_name

    @property
    def vector_size(self) -> int:
        return self._settings.vector_size

    def preload(self) -> None:
        self._load_model()

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(
            status="ok" if self._model is not None else "starting",
            service=self._settings.service_name,
            model=self._settings.model_name,
            dimension=self._settings.vector_size,
            device=self._model_device(),
            batch_size=self._settings.batch_size,
            max_seq_length=self._settings.max_seq_length,
            torch_dtype=self._settings.torch_dtype,
        )

    def embed(self, texts: Sequence[str], *, normalize: bool) -> list[list[float]]:
        model = self._load_model()
        with self._encode_lock:
            vectors = self._encode_with_oom_retry(model=model, texts=texts, normalize=normalize)

        embeddings = [[float(value) for value in vector] for vector in vectors]
        if embeddings and len(embeddings[0]) != self._settings.vector_size:
            raise EmbeddingDimensionError(
                f"Model returned {len(embeddings[0])} dimensions, "
                f"expected {self._settings.vector_size}."
            )
        return embeddings

    def _load_model(self) -> SentenceEmbeddingModel:
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is not None:
                return self._model

            kwargs: dict[str, object] = {"trust_remote_code": self._settings.trust_remote_code}
            if self._settings.device:
                kwargs["device"] = self._settings.device

            model_kwargs = self._build_model_kwargs()
            if model_kwargs:
                kwargs["model_kwargs"] = model_kwargs

            logger.info(
                "Loading embedding model model=%s device=%s dtype=%s max_seq_length=%s",
                self._settings.model_name,
                self._settings.device or "auto",
                self._settings.torch_dtype or "model-default",
                self._settings.max_seq_length or "model-default",
            )
            model = self._model_factory(self._settings.model_name, kwargs)
            if self._settings.max_seq_length:
                model.max_seq_length = self._settings.max_seq_length

            self._model = model
            logger.info(
                "Embedding model loaded model=%s device=%s dimension=%s max_seq_length=%s",
                self._settings.model_name,
                self._model_device(),
                self._settings.vector_size,
                getattr(model, "max_seq_length", None),
            )
            return model

    def _encode_with_oom_retry(
        self,
        *,
        model: SentenceEmbeddingModel,
        texts: Sequence[str],
        normalize: bool,
    ) -> Any:
        batch_size = max(1, self._settings.batch_size)
        while True:
            try:
                return model.encode(
                    texts,
                    batch_size=batch_size,
                    normalize_embeddings=normalize and self._settings.normalize_embeddings,
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
                        "with batch_size=1 and "
                        f"max_seq_length={self._settings.max_seq_length or 'model-default'}. "
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

    def _build_model_kwargs(self) -> dict[str, object]:
        torch_dtype = _resolve_torch_dtype(self._settings.torch_dtype)
        if torch_dtype is None:
            return {}
        return {"torch_dtype": torch_dtype}

    def _model_device(self) -> str | None:
        if self._model is None:
            return self._settings.device

        device = getattr(self._model, "device", None)
        if device is None:
            return self._settings.device
        return str(device)


def _sentence_transformer_factory(
    model_name: str,
    kwargs: dict[str, object],
) -> SentenceEmbeddingModel:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, **kwargs)


def _resolve_torch_dtype(dtype_value: str | None) -> object | None:
    if not dtype_value:
        return None

    dtype = dtype_value.lower()
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
