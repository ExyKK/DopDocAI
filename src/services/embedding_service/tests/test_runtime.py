import pytest

from app.config import Settings
from app.runtime import EmbeddingDimensionError, EmbeddingOutOfMemoryError, EmbeddingRuntime


def test_runtime_loads_model_with_configured_dtype_and_sequence_length() -> None:
    created: dict[str, object] = {}

    def factory(model_name: str, kwargs: dict[str, object]) -> FakeModel:
        created["model_name"] = model_name
        created["kwargs"] = kwargs
        return FakeModel(dimension=3)

    runtime = EmbeddingRuntime(
        Settings(
            model_name="test-model",
            vector_size=3,
            batch_size=4,
            device="cuda",
            torch_dtype="auto",
            max_seq_length=1024,
        ),
        model_factory=factory,
    )

    runtime.preload()

    assert created["model_name"] == "test-model"
    assert created["kwargs"] == {
        "trust_remote_code": True,
        "device": "cuda",
        "model_kwargs": {"torch_dtype": "auto"},
    }
    assert runtime.status().device == "cuda:0"
    assert runtime.status().max_seq_length == 1024


def test_runtime_retries_cuda_oom_with_smaller_batch_size() -> None:
    model = FakeModel(dimension=3, oom_until_batch_size=2)
    runtime = EmbeddingRuntime(
        Settings(vector_size=3, batch_size=8),
        model_factory=lambda _model_name, _kwargs: model,
    )

    embeddings = runtime.embed(["a", "b"], normalize=True)

    assert embeddings == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    assert model.batch_sizes == [8, 4, 2]


def test_runtime_returns_oom_error_after_batch_size_one_fails() -> None:
    runtime = EmbeddingRuntime(
        Settings(vector_size=3, batch_size=2),
        model_factory=lambda _model_name, _kwargs: FakeModel(dimension=3, oom_until_batch_size=0),
    )

    with pytest.raises(EmbeddingOutOfMemoryError, match="batch_size=1"):
        runtime.embed(["too long"], normalize=True)


def test_runtime_validates_vector_dimension() -> None:
    runtime = EmbeddingRuntime(
        Settings(vector_size=4, batch_size=2),
        model_factory=lambda _model_name, _kwargs: FakeModel(dimension=3),
    )

    with pytest.raises(EmbeddingDimensionError, match="expected 4"):
        runtime.embed(["a"], normalize=True)


class FakeModel:
    device = "cuda:0"

    def __init__(self, *, dimension: int, oom_until_batch_size: int | None = None) -> None:
        self.dimension = dimension
        self.oom_until_batch_size = oom_until_batch_size
        self.batch_sizes: list[int] = []
        self.max_seq_length = 4096

    def encode(
        self,
        sentences,
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
    ):
        self.batch_sizes.append(batch_size)
        if self.oom_until_batch_size is not None and batch_size > self.oom_until_batch_size:
            raise RuntimeError("CUDA out of memory")

        assert normalize_embeddings is True
        assert convert_to_numpy is True
        assert show_progress_bar is False
        return [[1, 2, 3] for _ in sentences]
