import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.infra.llm_client import (
    LlmCompletionProvider,
    LlmCompletionResult,
    LlmMessage,
    LlmProviderError,
)

logger = logging.getLogger("documentation_llm")


@dataclass(frozen=True)
class LlmCallOutcome:
    result: LlmCompletionResult
    parsed_value: Any = None
    attempts_total: int = 1
    retry_errors: list[dict[str, Any]] = field(default_factory=list)


def call_llm_with_retry(
    provider: LlmCompletionProvider,
    messages: list[LlmMessage],
    *,
    metadata: dict[str, str],
    response_format: dict[str, Any] | None = None,
    max_attempts: int = 3,
    retry_delay_s: float = 0.0,
    validator: Callable[[LlmCompletionResult], Any] | None = None,
    retry_message_factory: Callable[[LlmProviderError, int], LlmMessage | None] | None = None,
) -> LlmCallOutcome:
    attempts = max(1, max_attempts)
    retry_errors: list[dict[str, Any]] = []
    current_messages = list(messages)
    last_error: LlmProviderError | None = None

    for attempt in range(1, attempts + 1):
        task = metadata.get("task", "llm_call")
        section_key = metadata.get("section_key")
        repair_round = metadata.get("repair_round")
        source_count = metadata.get("source_count")
        estimated_input_tokens = metadata.get("estimated_input_tokens")
        logger.info(
            (
                "LLM call started task=%s section_key=%s repair_round=%s "
                "attempt=%s/%s provider=%s response_format=%s source_count=%s "
                "estimated_input_tokens=%s"
            ),
            task,
            section_key,
            repair_round,
            attempt,
            attempts,
            provider.provider_name,
            bool(response_format),
            source_count,
            estimated_input_tokens,
        )
        try:
            result = provider.generate(
                current_messages,
                metadata={**metadata, "llm_attempt": str(attempt)},
                response_format=response_format,
            )
            parsed_value = validator(result) if validator is not None else None
        except LlmProviderError as exc:
            last_error = exc
            error_payload = _error_payload(exc, attempt=attempt)
            retry_errors.append(error_payload)
            logger.warning(
                "LLM call failed task=%s section_key=%s attempt=%s/%s error_code=%s retryable=%s",
                task,
                section_key,
                attempt,
                attempts,
                exc.error_code,
                exc.retryable,
            )
            if not exc.retryable or attempt >= attempts:
                _attach_call_details(
                    exc,
                    metadata=metadata,
                    attempts_total=attempt,
                    retry_errors=retry_errors,
                    response_format=response_format,
                )
                raise
            retry_message = retry_message_factory(exc, attempt) if retry_message_factory else None
            if retry_message is not None:
                current_messages = [*messages, retry_message]
            if retry_delay_s > 0:
                time.sleep(retry_delay_s)
            continue

        logger.info(
            (
                "LLM call completed task=%s section_key=%s attempt=%s/%s provider=%s "
                "model=%s response_id=%s finish_reason=%s prompt_tokens=%s "
                "completion_tokens=%s total_tokens=%s latency_ms=%s"
            ),
            task,
            section_key,
            attempt,
            attempts,
            result.provider,
            result.model,
            result.response_id,
            result.finish_reason,
            result.prompt_tokens,
            result.completion_tokens,
            result.total_tokens,
            result.latency_ms,
        )
        return LlmCallOutcome(
            result=result,
            parsed_value=parsed_value,
            attempts_total=attempt,
            retry_errors=retry_errors,
        )

    assert last_error is not None
    raise last_error


def _attach_call_details(
    exc: LlmProviderError,
    *,
    metadata: dict[str, str],
    attempts_total: int,
    retry_errors: list[dict[str, Any]],
    response_format: dict[str, Any] | None,
) -> None:
    exc.details = {
        **getattr(exc, "details", {}),
        "llm_task": metadata.get("task"),
        "section_key": metadata.get("section_key"),
        "template_kind": metadata.get("template_kind"),
        "repair_round": metadata.get("repair_round"),
        "source_count": metadata.get("source_count"),
        "estimated_input_tokens": metadata.get("estimated_input_tokens"),
        "attempts_total": attempts_total,
        "retry_errors": retry_errors,
        "response_format": response_format,
    }


def _error_payload(exc: LlmProviderError, *, attempt: int) -> dict[str, Any]:
    details = getattr(exc, "details", {}) or {}
    return {
        "attempt": attempt,
        "error_code": exc.error_code,
        "retryable": exc.retryable,
        "status_code": exc.status_code,
        "message": str(exc),
        "response_id": details.get("response_id"),
        "model": details.get("model"),
        "finish_reason": details.get("finish_reason"),
        "raw_response_excerpt": details.get("raw_response_excerpt"),
    }
