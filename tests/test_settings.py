from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.settings import AUTO_OPEN_CHROME, DARK_THEME, LAST_PROJECT, WRAP_TEXT, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_persists_boolean_and_last_project_values_in_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = SettingsStore(Path(temporary_directory) / "settings.sqlite3")
            self.assertTrue(store.get_bool(AUTO_OPEN_CHROME, default=True))
            self.assertTrue(store.get_bool(WRAP_TEXT, default=True))

            store.set_bool(AUTO_OPEN_CHROME, False)
            store.set_bool(DARK_THEME, True)
            store.set_bool(WRAP_TEXT, False)
            store.set(LAST_PROJECT, "C:/projects/example")

            reopened = SettingsStore(store.database_path)
            self.assertFalse(reopened.get_bool(AUTO_OPEN_CHROME, default=True))
            self.assertTrue(reopened.get_bool(DARK_THEME, default=False))
            self.assertFalse(reopened.get_bool(WRAP_TEXT, default=True))
            self.assertEqual(reopened.get(LAST_PROJECT), "C:/projects/example")

    def test_invalid_boolean_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = SettingsStore(Path(temporary_directory) / "settings.sqlite3")
            store.set(AUTO_OPEN_CHROME, "yes")

            with self.assertRaisesRegex(ValueError, "must be 'true' or 'false'"):
                store.get_bool(AUTO_OPEN_CHROME, default=True)


if __name__ == "__main__":
    unittest.main()
