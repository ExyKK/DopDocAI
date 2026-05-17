from pydantic import AliasChoices, AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCS_", extra="ignore")

    service_name: str = "documentation_service"
    host: str = "0.0.0.0"
    port: int = 19500
    reload: bool = False

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
    s3_validate_on_start: bool = False

    worker_id: str | None = None
    worker_poll_interval_s: float = 5.0
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 15


settings = Settings()
