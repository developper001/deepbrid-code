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
TEXT_PROBE_BYTES = 8192
MAX_CONTEXT_FILE_BYTES = 256 * 1024
MAX_CONTEXT_TOTAL_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ContextFile:
    path: Path
    kind: str
    external: bool = False
    label: str | None = None


def context_kind(path: Path) -> str | None:
    if path.is_symlink():
        raise ValueError(f"{path.name} is a symbolic link and cannot be inspected as context.")
    with path.open("rb") as file:
        prefix = file.read(TEXT_PROBE_BYTES)
    if prefix.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")):
        return "image"
    if prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
        return "image"
    if _is_text(prefix):
        return "text"
    return None


def _is_text(content: bytes) -> bool:
    if content.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")):
        return True
    if b"\0" in content:
        return False
    if not content:
        return True
    control_bytes = sum(
        byte < 32 and byte not in {7, 8, 9, 10, 12, 13, 27}
        for byte in content
    )
    return control_bytes / len(content) <= 0.02


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
    if not _is_text(content):
        raise ValueError(f"{path.name} appears to be a binary file and cannot be added as text.")
    if content.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return content.decode("utf-32", errors="replace")
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16", errors="replace")
    return content.decode("utf-8-sig", errors="replace")


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
        if project_root is not None and not item.external:
            resolved_root = project_root.resolve(strict=True)
            resolved_path = item.path.resolve(strict=True)
            try:
                relative = resolved_path.relative_to(resolved_root)
            except ValueError as error:
                raise ValueError(f"{item.path.name} is outside the opened project folder.") from error
        elif item.external:
            relative = Path(item.label or item.path.name)
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
