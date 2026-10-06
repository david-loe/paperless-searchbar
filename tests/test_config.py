import pytest
from pydantic import ValidationError
from searchbar.config import Settings, get_settings


def test_oidc_issuer_preserves_trailing_slash():
    config = Settings(
        paperless_url="http://paperless.test/",
        paperless_public_url="https://docs.test/",
        secret_key="a" * 40,
        paperless_token="test",
        oidc_client_id="app",
        oidc_issuer="https://sso.test/application/o/searchbar/",
    )
    assert config.oidc_issuer == "https://sso.test/application/o/searchbar/"
    assert config.paperless_url == "http://paperless.test"


def test_file_secrets_from_dotenv_and_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    token = tmp_path / "token"
    token.write_text("file-secret-token\n")
    key = tmp_path / "key"
    key.write_text("k" * 40)
    (tmp_path / ".env").write_text(
        f"PAPERLESS_URL=http://paperless.test\nPAPERLESS_PUBLIC_URL=http://docs.test\nPAPERLESS_TOKEN_FILE={token}\n"
    )
    monkeypatch.setenv("SECRET_KEY_FILE", str(key))
    get_settings.cache_clear()
    result = get_settings()
    assert result.paperless_token.get_secret_value() == "file-secret-token"
    assert result.secret_key.get_secret_value() == "k" * 40
    get_settings.cache_clear()


def test_config_errors_do_not_echo_secrets():
    with pytest.raises(ValidationError) as error:
        Settings(
            paperless_url="not-a-url", paperless_token="do-not-leak-token", secret_key="s" * 40
        )
    assert "do-not-leak-token" not in str(error.value)


@pytest.mark.parametrize(
    "configured, expected",
    [
        (None, "REMOTE-USER"),
        ("HTTP_X_AUTH_USER", "X-AUTH-USER"),
        ("HTTP_X_AUTHENTIK_USERNAME", "X-AUTHENTIK-USERNAME"),
    ],
)
def test_remote_user_header_from_environment(monkeypatch, configured, expected):
    monkeypatch.delenv("PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME", raising=False)
    if configured is not None:
        monkeypatch.setenv("PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME", configured)
    settings = Settings(
        _env_file=None,
        paperless_url="http://paperless.test",
        paperless_public_url="http://paperless.test",
        paperless_token="test",
        secret_key="s" * 40,
    )
    assert settings.paperless_remote_user_header == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "HTTP_",
        "Remote-User",
        "HTTP_X-AUTH-USER",
        "HTTP_X_USER\r\nInjected: yes",
        "HTTP_X_USER:bad",
        "http_x_user",
        "HTTP_X_ÜSER",
        "HTTP_X_USER ",
        "HTTP_AUTHORIZATION",
        "HTTP_COOKIE",
        "HTTP_HOST",
        "HTTP_CONTENT_LENGTH",
        "HTTP_RANGE",
        "HTTP_IF_RANGE",
        "HTTP_ACCEPT_ENCODING",
    ],
)
def test_invalid_or_conflicting_remote_user_headers_rejected(value):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            paperless_url="http://paperless.test",
            paperless_public_url="http://paperless.test",
            paperless_token="test",
            secret_key="s" * 40,
            paperless_http_remote_user_header_name=value,
        )


@pytest.mark.parametrize("ttl", [-1, 301])
def test_cache_ttl_bounds(ttl):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            paperless_url="http://paperless.test",
            paperless_public_url="http://paperless.test",
            paperless_token="test",
            secret_key="s" * 40,
            paperless_cache_ttl_seconds=ttl,
        )
