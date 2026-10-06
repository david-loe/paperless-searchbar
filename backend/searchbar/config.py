import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = "sqlite:////data/searchbar.db"
    app_url: str = "http://localhost:8000"
    paperless_url: str
    paperless_public_url: str
    paperless_token: SecretStr
    paperless_http_remote_user_header_name: str = "HTTP_REMOTE_USER"
    secret_key: SecretStr
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = SecretStr("")
    paperless_cache_ttl_seconds: int = Field(default=300, ge=0, le=300)
    static_dir: str = "frontend/dist"

    @field_validator("paperless_http_remote_user_header_name")
    @classmethod
    def valid_remote_user_header(cls, value: str) -> str:
        # Paperless expects the Django request.META name, not the wire header.
        if not re.fullmatch(r"HTTP_[A-Z0-9]+(?:_[A-Z0-9]+)*", value):
            raise ValueError(
                "PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME im Format HTTP_X_AUTH_USER angeben."
            )
        if value.removeprefix("HTTP_") in {
            "AUTHORIZATION",
            "PROXY_AUTHORIZATION",
            "COOKIE",
            "HOST",
            "CONTENT_LENGTH",
            "CONTENT_TYPE",
            "TRANSFER_ENCODING",
            "CONNECTION",
            "TE",
            "TRAILER",
            "UPGRADE",
            "ACCEPT_ENCODING",
            "RANGE",
            "IF_RANGE",
        }:
            raise ValueError(
                "Der Remote-User-Header darf keinen Authentifizierungs- oder Transportheader ersetzen."
            )
        return value

    @property
    def paperless_remote_user_header(self) -> str:
        return self.paperless_http_remote_user_header_name.removeprefix("HTTP_").replace("_", "-")

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
