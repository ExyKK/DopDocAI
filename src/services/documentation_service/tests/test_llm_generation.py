import httpx

from app.infra.llm_client import (
    LlmClientConfig,
    LlmProviderError,
    OpenAiCompatibleLlmCompletionProvider,
    StubLlmCompletionProvider,
)
from app.pipeline.evidence import SectionEvidence
from app.pipeline.evidence_pack import EvidencePackBudget, build_evidence_pack
from app.pipeline.llm_generation import LlmSectionGenerator
from app.pipeline.prompt_contract import build_section_prompt_contract
from app.pipeline.rendered_evidence import build_rendered_evidence_pack


def test_stub_provider_generates_markdown_from_prompt_contract() -> None:
    section = _section_with_pack()
    contract = build_section_prompt_contract(section, output_language="ru")

    generated = LlmSectionGenerator(StubLlmCompletionProvider()).generate_section(contract)

    assert generated.section.section_key == "entry_points"
    assert generated.section.content_markdown.startswith("## Entry Points")
    assert "### Sources" in generated.section.content_markdown
    assert generated.section.generation is not None
    assert generated.section.generation["provider"] == "stub"
    assert generated.section.generation["model"] == "stub"
    assert generated.section.generation["quality_status"] == "ok"


def test_section_generator_strips_model_heading_and_records_warning() -> None:
    section = _section_with_pack()
    contract = build_section_prompt_contract(section, output_language="ru")

    class HeadingProvider(StubLlmCompletionProvider):
        def generate(self, messages, *, metadata=None):
            result = super().generate(messages, metadata=metadata)
            return result.__class__(
                content="## Лишний заголовок\n\nТело секции [S1].",
                provider=result.provider,
                model=result.model,
                finish_reason=result.finish_reason,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
                response_id=result.response_id,
            )

    generated = LlmSectionGenerator(HeadingProvider()).generate_section(contract)

    assert generated.section.content_markdown.startswith("## Entry Points\n\nТело секции")
    assert "## Лишний заголовок" not in generated.section.content_markdown
    assert generated.section.generation is not None
    assert generated.section.generation["warnings"][0]["code"] == "leading_heading_removed"
    assert generated.section.generation["quality_status"] == "ok"


def test_openai_compatible_provider_sends_openrouter_headers_and_provider_options(
    monkeypatch,
) -> None:
    requests = []

    def fake_post(url, *, headers, json, timeout):
        requests.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "model": "deepseek/deepseek-v4-flash",
                "choices": [
                    {
                        "message": {"content": "## Entry Points\n\nGenerated."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OpenAiCompatibleLlmCompletionProvider(
        LlmClientConfig(
            provider="openrouter",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            api_key="test-key",
            model="deepseek/deepseek-v4-flash",
            timeout_s=90,
            temperature=0.2,
            max_tokens=4096,
            top_p=0.95,
            openrouter_site_url="http://localhost",
            openrouter_app_title="DopDocAI",
            provider_options_json='{"sort":"throughput"}',
            provider_max_price_prompt=1.0,
            provider_max_price_completion=2.0,
        )
    )

    result = provider.generate([], metadata={"section_key": "entry_points"})

    assert result.prompt_tokens == 11
    assert result.completion_tokens == 7
    assert requests[0]["headers"]["HTTP-Referer"] == "http://localhost"
    assert requests[0]["headers"]["X-OpenRouter-Title"] == "DopDocAI"
    assert requests[0]["json"]["metadata"]["section_key"] == "entry_points"
    assert requests[0]["json"]["provider"] == {
        "sort": "throughput",
        "max_price": {
            "prompt": 1.0,
            "completion": 2.0,
        },
    }


def test_openai_compatible_provider_marks_rate_limit_retryable(monkeypatch) -> None:
    def fake_post(url, *, headers, json, timeout):
        return httpx.Response(429, text="too many requests")

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OpenAiCompatibleLlmCompletionProvider(
        LlmClientConfig(
            provider="openrouter",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            api_key="test-key",
            model="deepseek/deepseek-v4-flash",
            timeout_s=90,
            temperature=0.2,
            max_tokens=4096,
            top_p=0.95,
        )
    )

    try:
        provider.generate([])
    except LlmProviderError as exc:
        assert exc.error_code == "llm_provider_rate_limited"
        assert exc.retryable is True
    else:
        raise AssertionError("Expected LlmProviderError")


def _section_with_pack() -> SectionEvidence:
    section = SectionEvidence(
        section_key="entry_points",
        title="Entry Points",
        ordinal=4,
        status="evidence_ready",
        sources=[],
        evidence={"entry_points": [{"file_path": "cmd/server/main.go"}]},
    )
    section.evidence_pack = build_evidence_pack(
        section_key=section.section_key,
        title=section.title,
        ordinal=section.ordinal,
        evidence=section.evidence,
        sources=section.sources,
        budget=EvidencePackBudget(),
    )
    section.rendered_evidence_pack = build_rendered_evidence_pack(section.evidence_pack)
    return section
