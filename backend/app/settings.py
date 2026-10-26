from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://rental:rental@localhost:5433/rental"
    app_env: str = "development"
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:5173"]
    private_storage_dir: Path = PROJECT_ROOT / "var" / "private"
    private_storage_backend: Literal["local", "supabase"] = "local"
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    supabase_storage_bucket: str = "hearth-private"
    resend_api_key: str | None = None
    email_from: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_api_version: str | None = None
    whatsapp_payment_template: str = "payment_receipt"
    whatsapp_template_language: str = "en_US"

    @model_validator(mode="after")
    def validate_private_storage_settings(self) -> "Settings":
        if self.private_storage_backend == "supabase" and not (self.supabase_url and self.supabase_secret_key):
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for Supabase file storage")
        if self.private_storage_backend == "supabase" and not self.supabase_storage_bucket.strip():
            raise ValueError("SUPABASE_STORAGE_BUCKET cannot be blank")
        return self

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")


settings = Settings()
