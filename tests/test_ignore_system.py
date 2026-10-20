import os
from pathlib import Path

import pytest

from forge.forge_core.tools import ToolError, create_tool_registry
from forge.forge_core.workspace import Workspace, WorkspaceError


def test_list_files_honors_gitignore_and_forgeignore(tmp_path: Path) -> None:
    # Given: project and Forge ignore rules with an explicit ordinary-path override
    (tmp_path / ".gitignore").write_text("generated/\nrestored/\n", encoding="utf-8")
    (tmp_path / ".forgeignore").write_text("local-only/\n!restored/keep.txt\n", encoding="utf-8")
    (tmp_path / "visible.txt").write_text("visible", encoding="utf-8")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "hidden.txt").write_text("hidden", encoding="utf-8")
    (tmp_path / "local-only").mkdir()
    (tmp_path / "local-only" / "hidden.txt").write_text("hidden", encoding="utf-8")
    (tmp_path / "restored").mkdir()
    (tmp_path / "restored" / "keep.txt").write_text("keep", encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))

    # When: Forge lists the full model-facing workspace tree
    result = registry.execute("list_files", {"recursive": True})

    # Then: source rules hide paths while .forgeignore can restore ordinary content
    assert "visible.txt" in result
    assert "restored/keep.txt" in result
    assert "generated/hidden.txt" not in result
    assert "local-only/hidden.txt" not in result


def test_read_file_rejects_gitignored_content(tmp_path: Path) -> None:
    # Given: a file excluded by the project Git ignore rules
    (tmp_path / ".gitignore").write_text("generated.txt\n", encoding="utf-8")
    (tmp_path / "generated.txt").write_text("not for context", encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))

    # When / Then: a direct model-facing read cannot bypass the ignore policy
    with pytest.raises(ToolError, match="ignored"):
        registry.execute("read_file", {"path": "generated.txt"})


def test_search_excludes_forgeignored_content(tmp_path: Path) -> None:
    # Given: the same marker in visible and Forge-ignored files
    marker = "ignore-system-search-marker"
    (tmp_path / ".forgeignore").write_text("private-notes.txt\n", encoding="utf-8")
    (tmp_path / "visible.txt").write_text(marker, encoding="utf-8")
    (tmp_path / "private-notes.txt").write_text(marker, encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))

    # When: Forge searches the workspace
    result = registry.execute("search_files", {"query": marker})

    # Then: only context-eligible content is returned
    assert "visible.txt" in result
    assert "private-notes.txt" not in result


def test_forgeignore_reincludes_an_ordinary_gitignored_path_in_search(tmp_path: Path) -> None:
    # Given: Forge explicitly restores one ordinary path under a Git-ignored directory
    marker = "ignore-system-override-marker"
    (tmp_path / ".gitignore").write_text("generated/\n", encoding="utf-8")
    (tmp_path / ".forgeignore").write_text("!generated/keep.txt\n", encoding="utf-8")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "keep.txt").write_text(marker, encoding="utf-8")
    (tmp_path / "generated" / "hidden.txt").write_text(marker, encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))

    # When: Forge searches the workspace after applying both sources in order
    result = registry.execute("search_files", {"query": marker})

    # Then: the explicit .forgeignore override wins for ordinary content only
    assert "generated/keep.txt" in result
    assert "generated/hidden.txt" not in result


def test_forgeignore_cannot_reinclude_builtin_exclusions(tmp_path: Path) -> None:
    # Given: Forge ignore rules that try to restore a built-in excluded directory
    (tmp_path / ".forgeignore").write_text("!dist/keep.txt\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "keep.txt").write_text("generated output", encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))

    # When / Then: direct context reads cannot override built-in exclusions
    with pytest.raises(ToolError, match="ignored"):
        registry.execute("read_file", {"path": "dist/keep.txt"})


def test_ignore_policy_rejects_file_replacement_before_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a contained ignore file replaced with an external symlink after validation
    target = tmp_path / ".forgeignore"
    target.write_text("local-only.txt\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-ignore"
    outside.write_text("external-only.txt\n", encoding="utf-8")
    original_open = os.open

    def replace_before_read(path, flags, *args, **kwargs):
        if path == target.name:
            target.unlink()
            target.symlink_to(outside)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("forge.forge_core.safe_io.os.open", replace_before_read)

    # When / Then: external rules cannot become model-context policy
    with pytest.raises(WorkspaceError, match="changed|configuration"):
        Workspace(tmp_path)
