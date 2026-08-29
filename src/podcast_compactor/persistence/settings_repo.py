"""SettingsRepository: persisted app settings (currently the LLM overrides)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from podcast_compactor.models.db import AppSetting
from podcast_compactor.ports.llm import LlmOverrides

_LLM_KEYS = ("llm_backend", "openrouter_llm_model", "ollama_model")


class SettingsRepository:
    """Read/write the persisted LLM override settings over an `app_settings` table."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def get_llm_overrides(self) -> LlmOverrides:
        with self._sf() as s:
            rows = s.scalars(select(AppSetting).where(AppSetting.key.in_(_LLM_KEYS))).all()
            values = {r.key: r.value for r in rows}
        return LlmOverrides(
            llm_backend=values.get("llm_backend"),
            openrouter_llm_model=values.get("openrouter_llm_model"),
            ollama_model=values.get("ollama_model"),
        )

    def set_llm_overrides(self, overrides: LlmOverrides) -> None:
        updates = {
            "llm_backend": overrides.llm_backend,
            "openrouter_llm_model": overrides.openrouter_llm_model,
            "ollama_model": overrides.ollama_model,
        }
        with self._sf() as s:
            for key, value in updates.items():
                if value is None:
                    continue  # partial update: leave an unspecified field untouched
                row = s.get(AppSetting, key)
                if row is None:
                    s.add(AppSetting(key=key, value=value))
                else:
                    row.value = value
            s.commit()
