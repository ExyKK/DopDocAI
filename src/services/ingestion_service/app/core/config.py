from pathlib import Path

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

    jina_model: str = "jinaai/jina-code-embeddings-0.5b"

    max_tokens: int = 512
    overlap: int = 64
    vector_size: int = 896
    qdrant_batch_size: int = 64

    host: str = "127.0.0.1"
    port: int = 19100
    reload: bool = False

    worker_id: str | None = None
    worker_poll_interval_s: float = 5.0
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 15
    clone_root: Path = Path("/tmp/dopdoc-index-worker")


settings = Settings()
