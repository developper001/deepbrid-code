from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.context import ContextFile, build_prompt, iter_project_files, read_text_context


class ContextTests(unittest.TestCase):
    def test_project_walk_omits_dependency_and_generated_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "package.js").write_text("", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("", encoding="utf-8")

            paths = {path.relative_to(root).as_posix() for path in iter_project_files(root)}

            self.assertEqual(paths, {"src/app.py"})

    def test_prompt_contains_selected_text_and_marks_image_for_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "main.py"
            source.write_text("print('hello')", encoding="utf-8")
            image = root / "diagram.png"
            image.write_bytes(b"selected image")

            prompt = build_prompt(
                "Explain this project",
                [ContextFile(source, "text"), ContextFile(image, "image")],
                root,
            )

            self.assertIn("Explain this project", prompt)
            self.assertIn("--- main.py ---", prompt)
            self.assertNotIn(str(root), prompt)
            self.assertIn("print('hello')", prompt)
            self.assertIn("[Selected image: diagram.png]", prompt)

    def test_text_context_rejects_large_and_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            binary = root / "binary.py"
            binary.write_bytes(b"\x00")
            with self.assertRaisesRegex(ValueError, "binary file"):
                read_text_context(binary)
            large = root / "large.py"
            large.write_bytes(b"x" * (256 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "256 KiB"):
                read_text_context(large)

    def test_context_rejects_files_outside_the_open_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            project.mkdir()
            external_file = Path(temporary_directory) / "outside.py"
            external_file.write_text("private", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "outside the opened project"):
                build_prompt("Review", [ContextFile(external_file, "text")], project)

if __name__ == "__main__":
    unittest.main()
