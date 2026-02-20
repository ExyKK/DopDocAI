from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHATS_", extra="ignore")

    service_name: str = "chats_service"

    repos_service_url: str = "http://172.17.0.1:19300"
    repos_service_timeout_s: float = 5.0
    ingestion_service_url: str = "http://172.17.0.1:19100"

    database_url: str = "postgresql+psycopg://dopdoc:dopdoc@172.17.0.1:5432/dopdoc"
    db_schema: str = "chats"

    host: str = "127.0.0.1"
    port: int = 19400

    # LLM router
    llm_router_api: str = "https://openrouter.ai/api/v1/chat/completions"
    llm_api_key: str = ""
    llm_model: str = "deepseek/deepseek-v3.2"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1536
    llm_top_p: float = 0.95
    llm_repetition_penalty: float = 1.05
    # сколько сообщений истории подмешивать
    llm_history_limit: int = 20
    llm_default_system_prompt: str = "You are a helpful assistant for answering questions related to code repositories."

    rag_top_k: int = 8

settings = Settings()
