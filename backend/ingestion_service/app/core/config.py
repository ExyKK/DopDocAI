from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="INGEST_", extra="ignore")

    service_name: str = "ingestion_service"
    repos_service_url: str = "http://172.17.0.1:19300"
    request_timeout_s: float = 10.0

    qdrant_url: AnyUrl = "http://172.17.0.1:6333"
    qdrant_api_key: str | None = None

    jina_model: str = "jinaai/jina-code-embeddings-0.5b"

    max_tokens: int = 512
    overlap: int = 64
    vector_size: int = 896
    qdrant_batch_size: int = 64

    host: str = "127.0.0.1"
    port: int = 19100

settings = Settings()
