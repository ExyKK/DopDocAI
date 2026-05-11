from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBED_", extra="ignore")

    service_name: str = "embedding_service"
    host: str = "0.0.0.0"
    port: int = 19400

    model_name: str = "jinaai/jina-code-embeddings-0.5b"
    vector_size: int = 896
    batch_size: int = 8
    device: str | None = None
    trust_remote_code: bool = True
    normalize_embeddings: bool = True


settings = Settings()
