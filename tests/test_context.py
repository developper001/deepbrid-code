from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.context import (
    ContextFile,
    build_prompt,
    context_kind,
    iter_project_files,
    read_text_context,
    upload_context_kind,
)


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

    def test_context_kind_sniffs_extensionless_text_and_rejects_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            license_file = root / "LICENSE"
            license_file.write_bytes(b"MIT License\nPermission is hereby granted.\n")
            binary_file = root / "archive.dat"
            binary_file.write_bytes(b"\x00\x01\x02\xff")

            self.assertEqual(context_kind(license_file), "text")
            self.assertEqual(read_text_context(license_file), "MIT License\nPermission is hereby granted.\n")
            self.assertIsNone(context_kind(binary_file))

    def test_context_kind_recognizes_images_by_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            image = Path(temporary_directory) / "screenshot.data"
            image.write_bytes(b"\x89PNG\r\n\x1a\nmore bytes")

            self.assertEqual(context_kind(image), "image")

    def test_supported_upload_extensions_become_attachments_without_reading_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = root / "report.pdf"
            document.write_bytes(b"\x00\x01binary document")
            source = root / "main.py"
            source.write_text("print('hello')", encoding="utf-8")
            unsupported = root / "archive.bin"
            unsupported.write_bytes(b"\x00\x01")

            self.assertEqual(upload_context_kind(document), "file")
            self.assertEqual(upload_context_kind(source), "file")
            self.assertIsNone(upload_context_kind(unsupported))
            prompt = build_prompt(
                "Review these files",
                [ContextFile(document, "file"), ContextFile(source, "file")],
                root,
            )
            self.assertIn("[Selected file: report.pdf]", prompt)
            self.assertIn("[Selected file: main.py]", prompt)
            self.assertNotIn("binary document", prompt)
            self.assertNotIn("print('hello')", prompt)

    def test_pasted_external_image_can_be_added_without_open_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            image = Path(temporary_directory) / "clipboard.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n")

            prompt = build_prompt(
                "Describe this screenshot.",
                [ContextFile(image, "image", external=True, label="Clipboard image 1")],
            )

            self.assertIn("[Selected image: Clipboard image 1]", prompt)
            self.assertNotIn(temporary_directory, prompt)

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
