from typing import Literal

from pydantic import AliasChoices, AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCS_", extra="ignore")

    service_name: str = "documentation_service"
    host: str = "0.0.0.0"
    port: int = 19500
    reload: bool = False

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
        default="deepseek/deepseek-v3.2",
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
        default=1536,
        validation_alias=AliasChoices("DOCS_LLM_MAX_TOKENS", "DOPDOC_LLM_MAX_TOKENS"),
    )
    llm_top_p: float = Field(
        default=0.95,
        validation_alias=AliasChoices("DOCS_LLM_TOP_P", "DOPDOC_LLM_TOP_P"),
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


settings = Settings()
