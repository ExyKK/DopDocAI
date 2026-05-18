from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="INGEST_", extra="ignore")

    service_name: str = "ingestion_service"
    repos_service_url: str = "http://localhost:19200"
    request_timeout_s: float = 10.0
    database_url: str = "postgresql://dopdoc:dopdoc@localhost:5432/dopdoc"
    repo_db_schema: str = "repo"

    qdrant_url: AnyUrl = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_code_chunks_collection: str = "code_chunks_v1"
    qdrant_upsert_batch_size: int = 64

    embedding_provider: Literal["hash", "jina_http"] = Field(
        default="jina_http",
        validation_alias=AliasChoices("INGEST_EMBEDDING_PROVIDER", "DOPDOC_EMBEDDING_PROVIDER"),
    )
    embedding_model: str = Field(
        default="jinaai/jina-code-embeddings-0.5b",
        validation_alias=AliasChoices("INGEST_EMBEDDING_MODEL", "DOPDOC_EMBEDDING_MODEL"),
    )
    embedding_vector_size: int = Field(
        default=896,
        validation_alias=AliasChoices("INGEST_EMBEDDING_VECTOR_SIZE", "DOPDOC_EMBEDDING_VECTOR_SIZE"),
    )
    embedding_batch_size: int = Field(
        default=16,
        validation_alias=AliasChoices("INGEST_EMBEDDING_BATCH_SIZE", "DOPDOC_EMBEDDING_BATCH_SIZE"),
    )
    embedding_service_url: AnyUrl = Field(
        default="http://localhost:19400",
        validation_alias=AliasChoices("INGEST_EMBEDDING_SERVICE_URL", "DOPDOC_EMBEDDING_SERVICE_URL"),
    )
    embedding_request_timeout_s: float = Field(
        default=60.0,
        validation_alias=AliasChoices("INGEST_EMBEDDING_REQUEST_TIMEOUT_S", "DOPDOC_EMBEDDING_REQUEST_TIMEOUT_S"),
    )
    embedding_max_attempts: int = Field(
        default=3,
        validation_alias=AliasChoices("INGEST_EMBEDDING_MAX_ATTEMPTS", "DOPDOC_EMBEDDING_MAX_ATTEMPTS"),
    )
    embedding_retry_delay_s: float = Field(
        default=1.0,
        validation_alias=AliasChoices("INGEST_EMBEDDING_RETRY_DELAY_S", "DOPDOC_EMBEDDING_RETRY_DELAY_S"),
    )
    embedding_document_prefix: str = Field(
        default="Represent this code chunk for technical retrieval:\n",
        validation_alias=AliasChoices("INGEST_EMBEDDING_DOCUMENT_PREFIX", "DOPDOC_EMBEDDING_DOCUMENT_PREFIX"),
    )
    embedding_query_prefix: str = Field(
        default="Represent this technical question for retrieving relevant code:\n",
        validation_alias=AliasChoices("INGEST_EMBEDDING_QUERY_PREFIX", "DOPDOC_EMBEDDING_QUERY_PREFIX"),
    )

    s3_endpoint: AnyUrl = Field(
        default="http://localhost:9000",
        validation_alias=AliasChoices("INGEST_S3_ENDPOINT", "DOPDOC_S3_ENDPOINT"),
    )
    s3_access_key: str = Field(
        default="dopdoc",
        validation_alias=AliasChoices("INGEST_S3_ACCESS_KEY", "DOPDOC_S3_ACCESS_KEY"),
    )
    s3_secret_key: str = Field(
        default="dopdocstorage",
        validation_alias=AliasChoices("INGEST_S3_SECRET_KEY", "DOPDOC_S3_SECRET_KEY"),
    )
    s3_bucket: str = Field(
        default="dopdoc-artifacts",
        validation_alias=AliasChoices("INGEST_S3_BUCKET", "DOPDOC_S3_BUCKET"),
    )
    s3_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("INGEST_S3_REGION", "DOPDOC_S3_REGION"),
    )
    s3_upload_max_attempts: int = Field(
        default=3,
        validation_alias=AliasChoices("INGEST_S3_UPLOAD_MAX_ATTEMPTS", "DOPDOC_S3_UPLOAD_MAX_ATTEMPTS"),
    )
    s3_upload_retry_delay_s: float = Field(
        default=1.0,
        validation_alias=AliasChoices("INGEST_S3_UPLOAD_RETRY_DELAY_S", "DOPDOC_S3_UPLOAD_RETRY_DELAY_S"),
    )

    host: str = "127.0.0.1"
    port: int = 19100
    reload: bool = False

    worker_id: str | None = None
    worker_poll_interval_s: float = 5.0
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 15
    clone_root: Path = Path("/tmp/dopdoc-index-worker")


settings = Settings()
