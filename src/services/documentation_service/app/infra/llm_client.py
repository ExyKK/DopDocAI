import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class LlmClientConfig:
    provider: str
    endpoint: str
    api_key: str
    model: str
    timeout_s: float
    temperature: float
    max_tokens: int
    top_p: float
    repetition_penalty: float | None = None
    openrouter_site_url: str = "http://localhost"
    openrouter_app_title: str = "DopDocAI"
    provider_options_json: str | None = None
    provider_max_price_prompt: float | None = None
    provider_max_price_completion: float | None = None


@dataclass(frozen=True)
class LlmMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LlmCompletionResult:
    content: str
    model: str
    provider: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    response_id: str | None = None
    raw_response_excerpt: str | None = None


class LlmProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "llm_provider_failed",
        status_code: int | None = None,
        retryable: bool = True,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


class LlmCompletionProvider(Protocol):
    @property
    def provider_name(self) -> str:
        ...

    def generate(
        self,
        messages: list[LlmMessage],
        *,
        metadata: dict[str, str] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LlmCompletionResult:
        ...


class StubLlmCompletionProvider:
    provider_name = "stub"

    def generate(
        self,
        messages: list[LlmMessage],
        *,
        metadata: dict[str, str] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LlmCompletionResult:
        started = time.monotonic()
        payload = _user_payload(messages)
        section = payload.get("section") if isinstance(payload, dict) else {}
        section = section if isinstance(section, dict) else {}
        evidence_pack = payload.get("evidence_pack") if isinstance(payload, dict) else {}

        title = _str_or_default(section.get("title"), "Section")
        source_ids = _source_ids(evidence_pack)
        first_source = source_ids[0] if source_ids else None

        lines = [
            f"## {title}",
            "",
            "LLM stub mode is enabled, so this section was generated without an external model call.",
            "",
            "### Evidence Contract",
            f"- Section key: `{metadata.get('section_key') if metadata else section.get('key', 'unknown')}`.",
            f"- Evidence sources available: {len(source_ids)}.",
        ]
        if first_source is not None:
            lines.append(f"- First allowed source id: [{first_source}].")
        else:
            lines.append("- No evidence source ids were provided.")

        content = "\n".join(lines).rstrip() + "\n"
        return LlmCompletionResult(
            content=content,
            model="stub",
            provider=self.provider_name,
            finish_reason="stop",
            prompt_tokens=_estimate_tokens("\n".join(message.content for message in messages)),
            completion_tokens=_estimate_tokens(content),
            total_tokens=None,
            latency_ms=_elapsed_ms(started),
            response_id=None,
        )


class OpenAiCompatibleLlmCompletionProvider:
    def __init__(self, config: LlmClientConfig):
        self._config = config

    @property
    def provider_name(self) -> str:
        return self._config.provider

    def generate(
        self,
        messages: list[LlmMessage],
        *,
        metadata: dict[str, str] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LlmCompletionResult:
        if not self._config.api_key:
            raise LlmProviderError(
                "LLM API key is required when provider is not stub.",
                error_code="llm_api_key_missing",
                retryable=False,
            )

        request = self._build_request(messages, metadata=metadata, response_format=response_format)
        headers = self._headers()
        started = time.monotonic()
        try:
            response = httpx.post(
                self._config.endpoint,
                headers=headers,
                json=request,
                timeout=self._config.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise LlmProviderError(
                "LLM provider request timed out.",
                error_code="llm_provider_timeout",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise LlmProviderError(
                f"LLM provider request failed before response: {exc}",
                error_code="llm_provider_unavailable",
                retryable=True,
            ) from exc

        latency_ms = _elapsed_ms(started)
        if not response.is_success:
            body = _truncate(response.text, 1024)
            raise LlmProviderError(
                f"LLM provider request failed: status={response.status_code} body={body}",
                error_code=_http_error_code(response.status_code),
                status_code=response.status_code,
                retryable=_is_retryable_status(response.status_code),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise LlmProviderError(
                "LLM provider response was not valid JSON.",
                error_code="llm_response_invalid",
                retryable=True,
            ) from exc

        return _completion_from_payload(
            payload,
            provider=self._config.provider,
            fallback_model=self._config.model,
            latency_ms=latency_ms,
        )

    def _build_request(
        self,
        messages: list[LlmMessage],
        *,
        metadata: dict[str, str] | None,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "top_p": self._config.top_p,
            "stream": False,
        }
        if self._config.repetition_penalty is not None:
            request["repetition_penalty"] = self._config.repetition_penalty
        if response_format:
            request["response_format"] = response_format
        if metadata:
            request["metadata"] = {
                key: value
                for key, value in metadata.items()
                if key and value and len(key) <= 64 and len(value) <= 512
            }

        provider_options = _provider_options(self._config)
        if provider_options:
            request["provider"] = provider_options

        return request

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._config.provider == "openrouter":
            headers["HTTP-Referer"] = self._config.openrouter_site_url
            headers["X-OpenRouter-Title"] = self._config.openrouter_app_title
            headers["X-Title"] = self._config.openrouter_app_title
        return headers


def create_llm_provider(config: LlmClientConfig) -> LlmCompletionProvider:
    if config.provider == "stub":
        return StubLlmCompletionProvider()
    if config.provider in {"openai_compatible", "openrouter"}:
        return OpenAiCompatibleLlmCompletionProvider(config)
    raise LlmProviderError(
        f"Unsupported LLM provider '{config.provider}'.",
        error_code="llm_provider_unsupported",
        retryable=False,
    )


def _completion_from_payload(
    payload: dict[str, Any],
    *,
    provider: str,
    fallback_model: str,
    latency_ms: int,
) -> LlmCompletionResult:
    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else None
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = _content_parts_to_text(content)

    if not isinstance(content, str) or not content.strip():
        raise LlmProviderError(
            "LLM provider response did not contain message content.",
            error_code="llm_response_empty",
            retryable=True,
            details={
                "response_id": _optional_str(payload.get("id")),
                "model": _str_or_default(payload.get("model"), fallback_model),
                "finish_reason": _optional_str(choice.get("finish_reason") if isinstance(choice, dict) else None),
                "raw_response_excerpt": _truncate(json.dumps(payload, ensure_ascii=False, default=str), 1024),
            },
        )

    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return LlmCompletionResult(
        content=content.strip(),
        model=_str_or_default(payload.get("model"), fallback_model),
        provider=provider,
        finish_reason=_optional_str(choice.get("finish_reason") if isinstance(choice, dict) else None),
        prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
        completion_tokens=_int_or_none(usage.get("completion_tokens")),
        total_tokens=_int_or_none(usage.get("total_tokens")),
        latency_ms=latency_ms,
        response_id=_optional_str(payload.get("id")),
        raw_response_excerpt=_truncate(json.dumps(payload, ensure_ascii=False, default=str), 1024),
    )


def _provider_options(config: LlmClientConfig) -> dict[str, Any]:
    provider_options = _json_object(config.provider_options_json, "llm_provider_options_json")
    if config.provider_max_price_prompt is not None or config.provider_max_price_completion is not None:
        max_price: dict[str, float] = {}
        if config.provider_max_price_prompt is not None:
            max_price["prompt"] = config.provider_max_price_prompt
        if config.provider_max_price_completion is not None:
            max_price["completion"] = config.provider_max_price_completion
        provider_options["max_price"] = max_price
    return provider_options


def _json_object(value: str | None, setting_name: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise LlmProviderError(
            f"{setting_name} must be a JSON object.",
            error_code="llm_provider_options_invalid",
            retryable=False,
        ) from exc
    if not isinstance(parsed, dict):
        raise LlmProviderError(
            f"{setting_name} must be a JSON object.",
            error_code="llm_provider_options_invalid",
            retryable=False,
        )
    return parsed


def _user_payload(messages: list[LlmMessage]) -> dict[str, Any]:
    user_message = next((message.content for message in reversed(messages) if message.role == "user"), "{}")
    try:
        payload = json.loads(user_message)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_ids(evidence_pack: Any) -> list[str]:
    if not isinstance(evidence_pack, dict):
        return []
    sources = evidence_pack.get("sources")
    if not isinstance(sources, list):
        return []
    result: list[str] = []
    for source in sources:
        if isinstance(source, dict) and isinstance(source.get("source_id"), str):
            result.append(source["source_id"])
    return result


def _content_parts_to_text(parts: list[Any]) -> str:
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    return "\n".join(text_parts)


def _http_error_code(status_code: int) -> str:
    if status_code == 408:
        return "llm_provider_timeout"
    if status_code == 429:
        return "llm_provider_rate_limited"
    if status_code in {401, 403}:
        return "llm_provider_auth_failed"
    if status_code == 402:
        return "llm_provider_payment_required"
    if status_code == 413:
        return "llm_prompt_too_large"
    if status_code >= 500:
        return "llm_provider_unavailable"
    return "llm_provider_failed"


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 429} or status_code >= 500


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _estimate_tokens(value: str) -> int:
    if not value:
        return 0
    return max(1, (len(value) + 3) // 4)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _str_or_default(value: Any, default: str) -> str:
    text = _optional_str(value)
    return text if text is not None else default


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truncate(value: str, max_length: int) -> str:
    if not value:
        return ""
    return value if len(value) <= max_length else value[:max_length]
