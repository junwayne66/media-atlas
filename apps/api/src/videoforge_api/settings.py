from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDEOFORGE_", env_file=".env", extra="ignore")

    service_name: str = "videoforge-api"
    version: str = "0.0.1"
    cors_origins: list[str] = ["http://localhost:5173"]
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    database_url: str = "postgresql+psycopg://videoforge:videoforge@localhost:5432/videoforge"
    # 渲染中转目录：编译产出的 output_path 落在此处，且它是 ffmpeg 路径白名单的一员
    # （VF-307 `_path_within`——渲染器只允许看见白名单内的路径）。
    render_staging_dir: str = "/tmp/videoforge/staging"
