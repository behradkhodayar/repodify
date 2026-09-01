"""SettingsRepository: persisted app settings (LLM overrides and stock voices)."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from repodify.config import Settings
from repodify.models.db import AppSetting
from repodify.ports.llm import LlmOverrides

_LLM_KEYS = ("llm_backend", "openrouter_llm_model", "ollama_model")
_PREFERRED_VOICES_KEY = "preferred_stock_voices"

# User-picked runtime config. Secrets live here too (never returned by GET).
OVERRIDE_FIELDS: frozenset[str] = frozenset(
    {
        *_LLM_KEYS,
        "whisper_model",
        "ollama_base_url",
        "diarization_model",
        "openrouter_stt_model",
        "openrouter_tts_model",
        "openrouter_api_key",
        "map_model",
        "reduce_model",
        "anthropic_api_key",
        "pyannoteai_model",
        "pyannoteai_api_key",
        "hf_token",
    }
)

SECRET_FIELDS: frozenset[str] = frozenset(
    {
        "openrouter_api_key",
        "anthropic_api_key",
        "pyannoteai_api_key",
        "hf_token",
    }
)


def apply_overrides(settings: Settings, overrides: dict[str, str]) -> Settings:
    """Layer persisted overrides over env-based settings, per field."""
    update = {k: v for k, v in overrides.items() if k in OVERRIDE_FIELDS and v}
    return settings.model_copy(update=update) if update else settings


class SettingsRepository:
    """Read/write persisted app settings over an `app_settings` table."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def get_overrides(self) -> dict[str, str]:
        with self._sf() as s:
            rows = s.scalars(select(AppSetting).where(AppSetting.key.in_(OVERRIDE_FIELDS))).all()
        return {r.key: r.value for r in rows if r.value}

    def set_overrides(self, updates: dict[str, str | None]) -> None:
        with self._sf() as s:
            for key, value in updates.items():
                if key not in OVERRIDE_FIELDS or value is None:
                    continue
                row = s.get(AppSetting, key)
                if value == "":
                    if row is not None:
                        s.delete(row)
                    continue
                if row is None:
                    s.add(AppSetting(key=key, value=value))
                else:
                    row.value = value
            s.commit()

    def get_llm_overrides(self) -> LlmOverrides:
        values = self.get_overrides()
        return LlmOverrides(
            llm_backend=values.get("llm_backend"),
            openrouter_llm_model=values.get("openrouter_llm_model"),
            ollama_model=values.get("ollama_model"),
        )

    def set_llm_overrides(self, overrides: LlmOverrides) -> None:
        self.set_overrides(
            {
                "llm_backend": overrides.llm_backend,
                "openrouter_llm_model": overrides.openrouter_llm_model,
                "ollama_model": overrides.ollama_model,
            }
        )

    def get_preferred_stock_voices(self) -> list[str]:
        with self._sf() as s:
            row = s.get(AppSetting, _PREFERRED_VOICES_KEY)
        if row is None or not row.value:
            return []
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            return []
        return data

    def set_preferred_stock_voices(self, ids: list[str]) -> None:
        payload = json.dumps(list(ids))
        with self._sf() as s:
            row = s.get(AppSetting, _PREFERRED_VOICES_KEY)
            if row is None:
                s.add(AppSetting(key=_PREFERRED_VOICES_KEY, value=payload))
            else:
                row.value = payload
            s.commit()
