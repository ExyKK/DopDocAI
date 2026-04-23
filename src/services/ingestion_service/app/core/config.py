from pathlib import Path

from pydantic import AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="INGEST_", extra="ignore")

    service_name: str = "ingestion_service"
    repos_service_url: str = "http://localhost:19200"
    request_timeout_s: float = 10.0
    database_url: str = "postgresql://dopdoc:dopdoc@localhost:5432/dopdoc"
    repo_db_schema: str = "repo"

    qdrant_url: AnyUrl = "http://172.17.0.1:6333"
    qdrant_api_key: str | None = None

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
