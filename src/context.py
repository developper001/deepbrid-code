from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cc",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".jsonc",
    ".kt",
    ".md",
    ".mjs",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".rst",
    ".sass",
    ".scss",
    ".sh",
    ".sql",
    ".svelte",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
SPECIAL_TEXT_NAMES = {".gitignore", ".dockerignore", "dockerfile", "makefile"}
MAX_CONTEXT_FILE_BYTES = 256 * 1024
MAX_CONTEXT_TOTAL_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ContextFile:
    path: Path
    kind: str


def context_kind(path: Path) -> str | None:
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return "image"
    if path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in SPECIAL_TEXT_NAMES:
        return "text"
    return None


def iter_project_files(root: Path) -> Iterator[Path]:
    def raise_walk_error(error: OSError) -> None:
        raise error

    for current, directories, filenames in os.walk(
        root,
        followlinks=False,
        onerror=raise_walk_error,
    ):
        directories[:] = sorted(
            name
            for name in directories
            if name.lower() not in IGNORED_DIRECTORIES
            and not (Path(current) / name).is_symlink()
        )
        current_path = Path(current)
        for filename in sorted(filenames, key=str.lower):
            path = current_path / filename
            if not path.is_symlink():
                yield path


def read_text_context(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"{path.name} became a symbolic link and cannot be added as context.")
    with path.open("rb") as file:
        content = file.read(MAX_CONTEXT_FILE_BYTES + 1)
    if len(content) > MAX_CONTEXT_FILE_BYTES:
        raise ValueError(f"{path.name} is larger than the {MAX_CONTEXT_FILE_BYTES // 1024} KiB context limit.")
    if b"\0" in content:
        raise ValueError(f"{path.name} appears to be a binary file and cannot be added as text.")
    return content.decode("utf-8", errors="replace")


def build_prompt(
    message: str,
    selected: list[ContextFile],
    project_root: Path | None = None,
) -> str:
    sections = [message.strip()] if message.strip() else []
    total_bytes = 0
    for item in selected:
        if item.path.is_symlink():
            raise ValueError(f"{item.path.name} became a symbolic link and cannot be added as context.")
        if project_root is not None:
            resolved_root = project_root.resolve(strict=True)
            resolved_path = item.path.resolve(strict=True)
            try:
                relative = resolved_path.relative_to(resolved_root)
            except ValueError as error:
                raise ValueError(f"{item.path.name} is outside the opened project folder.") from error
        else:
            relative = item.path
        relative = (
            relative.as_posix()
            if project_root is not None
            else relative.name
        )
        if item.kind == "image":
            sections.append(f"[Selected image: {relative}]")
            continue
        text = read_text_context(item.path)
        total_bytes += len(text.encode("utf-8"))
        if total_bytes > MAX_CONTEXT_TOTAL_BYTES:
            raise ValueError(f"Selected text context exceeds the {MAX_CONTEXT_TOTAL_BYTES // 1024} KiB total limit.")
        sections.append(f"--- {relative} ---\n{text}")
    return "\n\n".join(sections)
