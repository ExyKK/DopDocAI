from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="REPOS_", extra="ignore")

    service_name: str = "repos_service"
    
    database_url: str = "postgresql+psycopg://dopdoc:dopdoc@localhost:5432/dopdoc"
    db_schema: str = "repos"

    host: str = "127.0.0.1"
    port: int = 19300

settings = Settings()
