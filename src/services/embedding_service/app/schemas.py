from typing import Literal

from pydantic import BaseModel, Field

EmbeddingInputType = Literal["document", "query"]


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)
    input_type: EmbeddingInputType = "document"
    model: str | None = None
    normalize: bool = True


class EmbeddingResponse(BaseModel):
    model: str
    dimension: int
    input_type: EmbeddingInputType
    embeddings: list[list[float]]


class HealthResponse(BaseModel):
    status: Literal["starting", "ok"]
    service: str
    model: str
    dimension: int
    device: str | None
    batch_size: int
    max_seq_length: int | None
    torch_dtype: str | None
