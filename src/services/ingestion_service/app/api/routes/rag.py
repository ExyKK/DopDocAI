from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import get_embedder, get_qdrant

router = APIRouter(prefix="/rag", tags=["rag"])


class RagSearchRequest(BaseModel):
    collection: str
    query: str = Field(min_length=1, max_length=50_000)
    top_k: int = Field(default=8, ge=1, le=50)


class RagChunk(BaseModel):
    score: float
    file_path: str | None = None
    language: str | None = None
    body: str
    chunk_index: int | None = None
    start_code_line: int | None = None
    end_code_line: int | None = None
    name: str | None = None
    kind: str | None = None


class RagSearchResponse(BaseModel):
    chunks: list[RagChunk]


@router.post("/search", response_model=RagSearchResponse)
def rag_search(payload: RagSearchRequest) -> RagSearchResponse:
    embedder = get_embedder()
    qdrant = get_qdrant(payload.collection)

    # ВАЖНО: query prompt (парный к document)
    vec = embedder.encode([payload.query], prompt_name="code2code_query")[0].astype(float).tolist()
    hits = qdrant.search(vec, limit=payload.top_k)

    chunks: list[RagChunk] = []
    for h in hits:
        p = h.payload or {}
        chunks.append(
            RagChunk(
                score=float(h.score),
                file_path=p.get("file_path"),
                language=p.get("language"),
                body=p.get("body", ""),
                chunk_index=p.get("chunk_index"),
                start_code_line=p.get("start_code_line"),
                end_code_line=p.get("end_code_line"),
                name=p.get("name"),
                kind=p.get("kind"),
            )
        )

    return RagSearchResponse(chunks=chunks)
