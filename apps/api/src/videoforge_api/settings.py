from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDEOFORGE_", env_file=".env", extra="ignore")

    service_name: str = "videoforge-api"
    version: str = "0.0.1"
    cors_origins: list[str] = ["http://localhost:5173"]
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
