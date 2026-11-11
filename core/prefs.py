"""Non-secret preferences saved from the UI, stored in the `app_settings` table."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session

from core.models import AppSettingRecord


class UserPrefs(BaseModel):
    """Preferences that override `.env` defaults when set."""

    default_model: str | None = None
    cheap_model: str | None = None
    show_all_models: bool = False
    git_author_name: str | None = None
    git_author_email: str | None = None


class PrefStore:
    """Load/save `UserPrefs` as key/value rows."""

    def __init__(self, db: Engine) -> None:
        self._db = db

    def load(self) -> UserPrefs:
        """Current preferences (defaults for anything unset)."""
        values: dict[str, Any] = {}
        with Session(self._db) as s:
            for name in UserPrefs.model_fields:
                rec = s.get(AppSettingRecord, name)
                if rec is not None:
                    values[name] = json.loads(rec.value_json)
        return UserPrefs.model_validate(values)

    def save(self, **changes: Any) -> UserPrefs:
        """Update some preferences; `None` clears a value back to its default."""
        prefs = self.load().model_copy(update=changes)
        UserPrefs.model_validate(prefs.model_dump())  # validate types
        with Session(self._db) as s:
            for name, value in changes.items():
                if name not in UserPrefs.model_fields:
                    raise KeyError(name)
                rec = s.get(AppSettingRecord, name)
                if value is None:
                    if rec is not None:
                        s.delete(rec)
                    continue
                rec = rec or AppSettingRecord(key=name, value_json="null")
                rec.value_json, rec.updated_at = json.dumps(value), datetime.now(UTC)
                s.add(rec)
            s.commit()
        return prefs
