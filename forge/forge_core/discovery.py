from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .discovery_metadata import (
    INSTRUCTION_FILENAMES,
    _discoverable_files,
    _formatters,
    _metadata_tokens,
    _project_types,
    _read_metadata,
    _test_frameworks,
    _type_checkers,
)

GIT_HEAD_PREFIX: Final = "ref: refs/heads/"


@dataclass(frozen=True, slots=True)
class ProjectDiscovery:
    """Deterministic, non-executing metadata about one project root."""

    root: Path
    git_repository: bool
    current_branch: str | None
    project_types: tuple[str, ...]
    test_frameworks: tuple[str, ...]
    formatters: tuple[str, ...]
    type_checkers: tuple[str, ...]
    instruction_files: tuple[str, ...]
    relevant_files: tuple[str, ...]


def discover_project(start: Path) -> ProjectDiscovery:
    """Inspect known project metadata without importing or executing it."""
    root = _project_root(start)
    present = _discoverable_files(root)
    metadata = _metadata_tokens(root, present)
    git_repository, current_branch = _git_details(root)
    return ProjectDiscovery(
        root=root,
        git_repository=git_repository,
        current_branch=current_branch,
        project_types=_project_types(present),
        test_frameworks=_test_frameworks(present, metadata),
        formatters=_formatters(present, metadata),
        type_checkers=_type_checkers(present, metadata),
        instruction_files=tuple(name for name in INSTRUCTION_FILENAMES if name in present),
        relevant_files=tuple(sorted(present)),
    )


def _project_root(start: Path) -> Path:
    resolved = start.resolve()
    if resolved.is_file():
        resolved = resolved.parent
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved


def _git_details(root: Path) -> tuple[bool, str | None]:
    marker = root / ".git"
    if not marker.exists():
        return False, None
    git_directory = _git_directory(marker)
    if git_directory is None:
        return True, None
    head = _read_metadata(git_directory / "HEAD")
    if head is None:
        return True, None
    value = head.strip()
    if not value.startswith(GIT_HEAD_PREFIX):
        return True, None
    branch = value.removeprefix(GIT_HEAD_PREFIX).strip()
    return True, branch or None


def _git_directory(marker: Path) -> Path | None:
    if marker.is_dir():
        return marker
    content = _read_metadata(marker)
    if content is None:
        return None
    prefix, separator, value = content.strip().partition(":")
    if prefix != "gitdir" or not separator or not value.strip():
        return None
    path = Path(value.strip())
    return path if path.is_absolute() else marker.parent / path
