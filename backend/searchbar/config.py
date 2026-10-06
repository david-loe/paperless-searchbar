import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = "sqlite:////data/searchbar.db"
    app_url: str = "http://localhost:8000"
    paperless_url: str
    paperless_public_url: str
    paperless_token: SecretStr
    secret_key: SecretStr
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = SecretStr("")
    static_dir: str = "frontend/dist"

    @field_validator("app_url", "paperless_url", "paperless_public_url", "oidc_issuer")
    @classmethod
    def valid_url(cls, value: str, info: ValidationInfo) -> str:
        if not value:
            return value
        u = urlsplit(value)
        if u.scheme not in {"http", "https"} or not u.netloc or u.username or u.query or u.fragment:
            raise ValueError("Eine HTTP(S)-Adresse ohne Zugangsdaten, Query oder Fragment angeben.")
        return value if info.field_name == "oidc_issuer" else value.rstrip("/")

    @model_validator(mode="after")
    def validate_config(self):
        if len(self.secret_key.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY muss mindestens 32 Zeichen lang sein.")
        if not self.paperless_token.get_secret_value():
            raise ValueError("PAPERLESS_TOKEN fehlt.")
        if bool(self.oidc_issuer) != bool(self.oidc_client_id):
            raise ValueError("OIDC_ISSUER und OIDC_CLIENT_ID gemeinsam konfigurieren.")
        if urlsplit(self.app_url).path:
            raise ValueError("APP_URL muss eine Origin ohne Unterpfad sein.")
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Diese Version unterstützt SQLite.")
        return self

    @property
    def secure_cookie(self) -> bool:
        return self.app_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    # _FILE takes precedence without copying secrets into the process environment.
    values = {}
    file_settings = dotenv_values(".env")
    for name in ("secret_key", "paperless_token", "oidc_client_secret"):
        if filename := os.getenv(name.upper() + "_FILE", file_settings.get(name.upper() + "_FILE")):
            values[name] = Path(filename).read_text().strip()
    return Settings(**values)
