from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

PIPELINE_TRACE_SCHEMA_VERSION = 1
MAX_TRACE_EVENTS = 500
MAX_TRACE_STRING_LENGTH = 1200


class PipelineTrace:
    def __init__(
        self,
        *,
        documentation_run_id: str,
        repository_id: str,
        snapshot_id: str,
        attempt: int,
        requested_template_kind: str | None,
    ):
        self.documentation_run_id = documentation_run_id
        self.repository_id = repository_id
        self.snapshot_id = snapshot_id
        self.attempt = attempt
        self.requested_template_kind = requested_template_kind
        self.effective_template_kind: str | None = None
        self.template_selection: dict[str, Any] | None = None
        self.repository_classification: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []

    def set_template_context(
        self,
        *,
        effective_template_kind: str,
        template_selection: dict[str, Any],
        repository_classification: dict[str, Any],
    ) -> None:
        self.effective_template_kind = effective_template_kind
        self.template_selection = _sanitize(template_selection)
        self.repository_classification = _sanitize(repository_classification)

    def record(self, event_type: str, **fields: Any) -> None:
        if len(self._events) >= MAX_TRACE_EVENTS:
            if len(self._events) == MAX_TRACE_EVENTS:
                self._events.append(
                    {
                        "ordinal": len(self._events) + 1,
                        "occurred_at": _utc_now(),
                        "event_type": "trace_truncated",
                        "message": f"Trace is capped at {MAX_TRACE_EVENTS} events.",
                    }
                )
            return

        event = {
            "ordinal": len(self._events) + 1,
            "occurred_at": _utc_now(),
            "event_type": event_type,
        }
        event.update(_sanitize(fields))
        self._events.append(event)

    def summary(self) -> dict[str, Any]:
        counts = Counter(str(event.get("event_type")) for event in self._events)
        return {
            "events_total": len(self._events),
            "event_counts": dict(sorted(counts.items())),
            "last_event_type": self._events[-1].get("event_type") if self._events else None,
            "failed": any(event.get("event_type") == "pipeline_failed" for event in self._events),
            "llm_retry_errors_total": sum(
                int(event.get("retry_errors_total") or 0)
                for event in self._events
                if str(event.get("event_type", "")).startswith("llm_")
            ),
        }

    def to_dict(self, *, status: str) -> dict[str, Any]:
        return {
            "schema_version": PIPELINE_TRACE_SCHEMA_VERSION,
            "artifact_kind": "pipeline_trace",
            "status": status,
            "documentation_run_id": self.documentation_run_id,
            "repository_id": self.repository_id,
            "snapshot_id": self.snapshot_id,
            "attempt": self.attempt,
            "requested_template_kind": self.requested_template_kind,
            "effective_template_kind": self.effective_template_kind,
            "template_selection": self.template_selection,
            "repository_classification": self.repository_classification,
            "summary": self.summary(),
            "events": list(self._events),
        }


def error_payload(error: Exception) -> dict[str, Any]:
    details = getattr(error, "details", {}) or {}
    return {
        "error_type": error.__class__.__name__,
        "error_code": getattr(error, "error_code", "unknown_error"),
        "retryable": bool(getattr(error, "retryable", False)),
        "status_code": getattr(error, "status_code", None),
        "message": _truncate(str(error), 2000),
        "details": _sanitize(details),
    }


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _truncate(value, MAX_TRACE_STRING_LENGTH)
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if not _looks_sensitive(str(key))
        }
    if isinstance(value, list | tuple | set):
        return [_sanitize(item) for item in list(value)[:50]]
    return _truncate(str(value), MAX_TRACE_STRING_LENGTH)


def _looks_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("secret", "api_key", "apikey", "token", "password", "authorization"))


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[:max_length]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
