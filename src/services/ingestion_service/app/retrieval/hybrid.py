import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.retrieval.qdrant_store import CodeChunkSearchHit

_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b")
_PATH_RE = re.compile(r"\b[\w.-]+(?:/[\w.-]+)+\b")
_FILE_RE = re.compile(r"\b[\w.-]+\.(?:go|cs|ts|tsx|js|jsx|py|md|json|ya?ml|sql|svg|mod|sum)\b")
_WORD_RE = re.compile(r"[a-zа-яё0-9_]{3,}")
_CAMEL_RE = re.compile(r"[a-z][A-Z]|[A-Z]{2,}[a-z]")

_STOPWORDS = {
    "about",
    "after",
    "all",
    "and",
    "are",
    "code",
    "does",
    "file",
    "find",
    "for",
    "from",
    "get",
    "how",
    "into",
    "load",
    "loaded",
    "method",
    "repo",
    "repository",
    "service",
    "the",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "без",
    "где",
    "для",
    "его",
    "если",
    "есть",
    "зачем",
    "или",
    "как",
    "какая",
    "какие",
    "какой",
    "код",
    "когда",
    "метод",
    "найди",
    "находится",
    "объясни",
    "пакет",
    "почему",
    "покажи",
    "про",
    "работает",
    "расскажи",
    "репозиторий",
    "репозитории",
    "сервис",
    "файл",
    "функция",
    "что",
    "через",
    "это",
    "этот",
}


@dataclass(frozen=True)
class HybridQuery:
    original: str
    expanded: str
    terms: tuple[str, ...]
    path_hints: tuple[str, ...]
    symbol_hints: tuple[str, ...]

    @property
    def has_specific_hints(self) -> bool:
        return bool(self.path_hints or self.symbol_hints)


@dataclass(frozen=True)
class HybridRankFactors:
    dense: float
    path: float = 0.0
    symbol: float = 0.0
    lexical: float = 0.0

    @property
    def total_boost(self) -> float:
        return self.path + self.symbol + self.lexical

    @property
    def final_score(self) -> float:
        return self.dense + self.total_boost


@dataclass(frozen=True)
class HybridRankedHit:
    hit: CodeChunkSearchHit
    factors: HybridRankFactors


def analyze_query(query: str) -> HybridQuery:
    normalized_query = query.strip()
    path_hints = _unique_tuple(_normalize_path_hint(value) for value in _path_candidates(query))
    symbol_hints = _unique_tuple(_normalize_symbol(value) for value in _symbol_candidates(query))
    terms = _unique_tuple(_word_terms(query))

    expansion_parts: list[str] = [normalized_query]
    if symbol_hints:
        expansion_parts.append("Symbols: " + " ".join(symbol_hints))
    if path_hints:
        expansion_parts.append("Paths: " + " ".join(path_hints))

    return HybridQuery(
        original=normalized_query,
        expanded="\n".join(part for part in expansion_parts if part),
        terms=terms,
        path_hints=path_hints,
        symbol_hints=symbol_hints,
    )


def rerank_hits(
    hits: tuple[CodeChunkSearchHit, ...],
    *,
    query: HybridQuery,
    top_k: int,
) -> tuple[HybridRankedHit, ...]:
    ranked = tuple(HybridRankedHit(hit=hit, factors=_rank_factors(hit, query)) for hit in hits)
    return tuple(
        sorted(
            ranked,
            key=lambda item: (
                item.factors.final_score,
                item.factors.dense,
                item.hit.payload.get("source_scope") == "runtime",
                str(item.hit.payload.get("file_path", "")),
                str(item.hit.payload.get("chunk_id", item.hit.point_id)),
            ),
            reverse=True,
        )[:top_k]
    )


def _rank_factors(hit: CodeChunkSearchHit, query: HybridQuery) -> HybridRankFactors:
    payload = hit.payload
    return HybridRankFactors(
        dense=hit.score,
        path=_path_boost(payload, query),
        symbol=_symbol_boost(payload, query),
        lexical=_lexical_boost(payload, query),
    )


def _path_boost(payload: dict[str, Any], query: HybridQuery) -> float:
    file_path = _normalize_path_hint(str(payload.get("file_path", "")))
    if not file_path or not query.path_hints:
        return 0.0

    file_name = PurePosixPath(file_path).name
    file_stem = PurePosixPath(file_path).stem.lower()
    best = 0.0
    for hint in query.path_hints:
        hint_name = PurePosixPath(hint).name
        hint_stem = PurePosixPath(hint).stem.lower()
        if hint == file_path:
            best = max(best, 0.14)
        elif file_path.endswith(f"/{hint}") or hint.endswith(f"/{file_path}"):
            best = max(best, 0.12)
        elif hint_name == file_name:
            best = max(best, 0.08)
        elif hint_stem and hint_stem == file_stem:
            best = max(best, 0.04)
    return best


def _symbol_boost(payload: dict[str, Any], query: HybridQuery) -> float:
    if not query.symbol_hints:
        return 0.0

    name = _normalize_symbol(str(payload.get("name", "")))
    signature = _normalize_symbol(str(payload.get("symbol_signature", "")))
    package_id = _normalize_symbol(str(payload.get("package_id", "")))
    workspace = _normalize_symbol(str(payload.get("workspace_unit_id", "")))
    searchable = " ".join(value for value in (name, signature, package_id, workspace) if value)
    name_leaf = name.rsplit(".", 1)[-1] if name else ""

    best = 0.0
    for hint in query.symbol_hints:
        hint_leaf = hint.rsplit(".", 1)[-1]
        if hint and hint == name:
            best = max(best, 0.16)
        elif hint_leaf and hint_leaf == name_leaf:
            best = max(best, 0.12)
        elif hint and hint in searchable:
            best = max(best, 0.08)
        elif hint_leaf and hint_leaf in searchable:
            best = max(best, 0.05)
    return best


def _lexical_boost(payload: dict[str, Any], query: HybridQuery) -> float:
    if not query.terms or not query.has_specific_hints:
        return 0.0

    weighted_fields = (
        (str(payload.get("name", "")), 0.012),
        (str(payload.get("file_path", "")), 0.010),
        (str(payload.get("symbol_signature", "")), 0.008),
        (str(payload.get("text", ""))[:4096], 0.004),
    )
    score = 0.0
    for text, weight in weighted_fields:
        terms = set(_word_terms(text))
        if not terms:
            continue
        score += len(set(query.terms) & terms) * weight
    return min(score, 0.05)


def _path_candidates(query: str) -> tuple[str, ...]:
    return tuple(_PATH_RE.findall(query) + _FILE_RE.findall(query))


def _symbol_candidates(query: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for match in _IDENTIFIER_RE.finditer(query):
        value = match.group(0)
        normalized = _normalize_symbol(value)
        if not normalized or normalized in _STOPWORDS or _FILE_RE.fullmatch(normalized):
            continue
        follows_call = query[match.end() :].lstrip().startswith("(")
        is_quoted = match.start() > 0 and query[match.start() - 1] in "`'"
        if "." in normalized or "_" in normalized or _CAMEL_RE.search(value) or follows_call or is_quoted:
            candidates.append(normalized)
    return tuple(candidates)


def _word_terms(text: str) -> tuple[str, ...]:
    terms: list[str] = []
    for value in _WORD_RE.findall(text.lower()):
        if value in _STOPWORDS:
            continue
        terms.append(value)
    return tuple(terms)


def _normalize_path_hint(value: str) -> str:
    return value.strip().strip("`'\".,:;()[]{}").replace("\\", "/").lower()


def _normalize_symbol(value: str) -> str:
    return value.strip().strip("`'\".,:;()[]{}").lower()


def _unique_tuple(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
