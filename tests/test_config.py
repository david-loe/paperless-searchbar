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
