from typing import Literal

from pydantic import AliasChoices, AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCS_", extra="ignore")

    service_name: str = "documentation_service"
    host: str = "0.0.0.0"
    port: int = 19500
    reload: bool = False
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("DOCS_LOG_LEVEL", "DOPDOC_DOCS_LOG_LEVEL"),
    )

    repos_service_url: str = "http://localhost:19200"
    request_timeout_s: float = 10.0
    retrieval_service_url: str = "http://localhost:19100"
    retrieval_request_timeout_s: float = 60.0
    retrieval_enabled: bool = True
    retrieval_top_k: int = 5
    retrieval_include_tests: bool = True
    retrieval_score_threshold: float | None = None

    llm_provider: Literal["stub", "openai_compatible", "openrouter"] = Field(
        default="openrouter",
        validation_alias=AliasChoices("DOCS_LLM_PROVIDER", "DOPDOC_LLM_PROVIDER"),
    )
    llm_endpoint: AnyUrl = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        validation_alias=AliasChoices("DOCS_LLM_ENDPOINT", "DOPDOC_LLM_ENDPOINT"),
    )
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DOCS_LLM_API_KEY", "DOPDOC_LLM_API_KEY"),
    )
    llm_model: str = Field(
        default="deepseek/deepseek-v4-flash",
        validation_alias=AliasChoices("DOCS_LLM_MODEL", "DOPDOC_LLM_MODEL"),
    )
    llm_timeout_seconds: float = Field(
        default=90.0,
        validation_alias=AliasChoices("DOCS_LLM_TIMEOUT_SECONDS", "DOPDOC_LLM_TIMEOUT_SECONDS"),
    )
    llm_temperature: float = Field(
        default=0.2,
        validation_alias=AliasChoices("DOCS_LLM_TEMPERATURE", "DOPDOC_LLM_TEMPERATURE"),
    )
    llm_max_tokens: int = Field(
        default=8192,
        validation_alias=AliasChoices(
            "DOCS_LLM_MAX_TOKENS",
            "DOPDOC_DOCS_LLM_MAX_TOKENS",
            "DOPDOC_LLM_MAX_TOKENS",
        ),
    )
    llm_top_p: float = Field(
        default=0.95,
        validation_alias=AliasChoices("DOCS_LLM_TOP_P", "DOPDOC_LLM_TOP_P"),
    )
    llm_repetition_penalty: float | None = Field(
        default=1.05,
        validation_alias=AliasChoices("DOCS_LLM_REPETITION_PENALTY", "DOPDOC_LLM_REPETITION_PENALTY"),
    )
    llm_openrouter_site_url: str = Field(
        default="http://localhost",
        validation_alias=AliasChoices(
            "DOCS_LLM_OPENROUTER_SITE_URL",
            "DOPDOC_LLM_OPENROUTER_SITE_URL",
        ),
    )
    llm_openrouter_app_title: str = Field(
        default="DopDocAI",
        validation_alias=AliasChoices(
            "DOCS_LLM_OPENROUTER_APP_TITLE",
            "DOPDOC_LLM_OPENROUTER_APP_TITLE",
        ),
    )
    llm_provider_options_json: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DOCS_LLM_PROVIDER_OPTIONS_JSON",
            "DOPDOC_LLM_PROVIDER_OPTIONS_JSON",
        ),
    )
    llm_provider_max_price_prompt: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DOCS_LLM_PROVIDER_MAX_PRICE_PROMPT",
            "DOPDOC_LLM_PROVIDER_MAX_PRICE_PROMPT",
        ),
    )
    llm_provider_max_price_completion: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DOCS_LLM_PROVIDER_MAX_PRICE_COMPLETION",
            "DOPDOC_LLM_PROVIDER_MAX_PRICE_COMPLETION",
        ),
    )
    prompt_output_language: str = Field(
        default="ru",
        validation_alias=AliasChoices("DOCS_PROMPT_OUTPUT_LANGUAGE", "DOPDOC_DOCS_OUTPUT_LANGUAGE"),
    )
    evidence_pack_max_tokens: int = Field(
        default=250_000,
        validation_alias=AliasChoices(
            "DOCS_EVIDENCE_PACK_MAX_TOKENS",
            "DOPDOC_DOCS_EVIDENCE_PACK_MAX_TOKENS",
        ),
    )
    evidence_pack_max_source_tokens: int = Field(
        default=32_000,
        validation_alias=AliasChoices(
            "DOCS_EVIDENCE_PACK_MAX_SOURCE_TOKENS",
            "DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCE_TOKENS",
        ),
    )
    evidence_pack_max_sources: int = Field(
        default=120,
        validation_alias=AliasChoices(
            "DOCS_EVIDENCE_PACK_MAX_SOURCES",
            "DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCES",
        ),
    )
    verification_mode: Literal["deterministic", "llm", "hybrid"] = Field(
        default="hybrid",
        validation_alias=AliasChoices(
            "DOCS_VERIFICATION_MODE",
            "DOPDOC_DOCS_VERIFICATION_MODE",
        ),
    )
    max_repair_rounds: int = Field(
        default=1,
        validation_alias=AliasChoices(
            "DOCS_MAX_REPAIR_ROUNDS",
            "DOPDOC_DOCS_MAX_REPAIR_ROUNDS",
        ),
    )
    llm_call_max_attempts: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "DOCS_LLM_CALL_MAX_ATTEMPTS",
            "DOPDOC_DOCS_LLM_CALL_MAX_ATTEMPTS",
        ),
    )
    llm_call_retry_delay_s: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "DOCS_LLM_CALL_RETRY_DELAY_S",
            "DOPDOC_DOCS_LLM_CALL_RETRY_DELAY_S",
        ),
    )
    llm_json_mode_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "DOCS_LLM_JSON_MODE_ENABLED",
            "DOPDOC_DOCS_LLM_JSON_MODE_ENABLED",
        ),
    )
    pipeline_trace_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "DOCS_PIPELINE_TRACE_ENABLED",
            "DOPDOC_DOCS_PIPELINE_TRACE_ENABLED",
        ),
    )

    database_url: str = "postgresql://dopdoc:dopdoc@localhost:5432/dopdoc"
    repo_db_schema: str = "repo"

    s3_endpoint: AnyUrl = Field(
        default="http://localhost:9000",
        validation_alias=AliasChoices("DOCS_S3_ENDPOINT", "DOPDOC_S3_ENDPOINT"),
    )
    s3_access_key: str = Field(
        default="dopdoc",
        validation_alias=AliasChoices("DOCS_S3_ACCESS_KEY", "DOPDOC_S3_ACCESS_KEY"),
    )
    s3_secret_key: str = Field(
        default="dopdocstorage",
        validation_alias=AliasChoices("DOCS_S3_SECRET_KEY", "DOPDOC_S3_SECRET_KEY"),
    )
    s3_bucket: str = Field(
        default="dopdoc-artifacts",
        validation_alias=AliasChoices("DOCS_S3_BUCKET", "DOPDOC_S3_BUCKET"),
    )
    s3_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("DOCS_S3_REGION", "DOPDOC_S3_REGION"),
    )
    s3_upload_max_attempts: int = Field(
        default=3,
        validation_alias=AliasChoices("DOCS_S3_UPLOAD_MAX_ATTEMPTS", "DOPDOC_S3_UPLOAD_MAX_ATTEMPTS"),
    )
    s3_upload_retry_delay_s: float = Field(
        default=1.0,
        validation_alias=AliasChoices("DOCS_S3_UPLOAD_RETRY_DELAY_S", "DOPDOC_S3_UPLOAD_RETRY_DELAY_S"),
    )
    s3_validate_on_start: bool = False

    worker_id: str | None = None
    worker_poll_interval_s: float = 5.0
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 15

    @field_validator(
        "llm_provider_max_price_prompt",
        "llm_provider_max_price_completion",
        mode="before",
    )
    @classmethod
    def _empty_optional_float(cls, value):
        if value == "":
            return None
        return value


settings = Settings()
