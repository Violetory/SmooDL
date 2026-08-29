from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SMOODL_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "SmooDL"
    version: str = "0.1.0"
    data_dir: Path = Path(".data")
    public_base_url: str = "http://127.0.0.1:8000"
    signing_secret: str = "replace-this-in-production"
    api_key: str | None = None
    job_timeout_seconds: int = 300
    download_token_ttl_seconds: int = 3600
    event_token_ttl_seconds: int = 3600
    preview_token_ttl_seconds: int = 900
    max_download_bytes: int = 2 * 1024 * 1024 * 1024
    http_timeout_seconds: int = 60
    yt_dlp_cookies_file: Path | None = None
    gallery_dl_cookies_file: Path | None = None

    @property
    def artifact_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"
