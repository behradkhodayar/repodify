"""SettingsRepository: persisted app settings (LLM overrides and stock voices)."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from repodify.models.db import AppSetting
from repodify.ports.llm import LlmOverrides

_LLM_KEYS = ("llm_backend", "openrouter_llm_model", "ollama_model")
_PREFERRED_VOICES_KEY = "preferred_stock_voices"


class SettingsRepository:
    """Read/write persisted app settings over an `app_settings` table."""

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
