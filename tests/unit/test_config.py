from podcast_compactor.config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("USE_FAKES", raising=False)
    monkeypatch.delenv("WPM", raising=False)
    s = Settings(_env_file=None)
    assert s.wpm == 130
    assert s.use_fakes is True
    assert str(s.database_url).startswith("sqlite")


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("WPM", "150")
    monkeypatch.setenv("USE_FAKES", "false")
    s = Settings(_env_file=None)
    assert s.wpm == 150
    assert s.use_fakes is False
