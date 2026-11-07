from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


AUTO_OPEN_CHROME = "auto_open_chrome"
LAST_PROJECT = "last_project"


class SettingsStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS app_settings "
                "(name TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def get(self, name: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE name = ?",
                (name,),
            ).fetchone()
        return str(row[0]) if row else None

    def set(self, name: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO app_settings (name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (name, value),
            )

    def get_bool(self, name: str, default: bool) -> bool:
        value = self.get(name)
        if value is None:
            return default
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError(f"Saved setting {name!r} must be 'true' or 'false', not {value!r}.")

    def set_bool(self, name: str, value: bool) -> None:
        self.set(name, "true" if value else "false")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
