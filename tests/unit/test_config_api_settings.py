from podcast_compactor.config import Settings


def test_api_settings_defaults():
    s = Settings(_env_file=None)
    assert s.api_token is None
    assert s.cors_allow_origins == ["*"]


def test_api_token_override():
    s = Settings(_env_file=None, api_token="secret")
    assert s.api_token == "secret"
