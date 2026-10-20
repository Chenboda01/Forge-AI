import os
import tempfile
from pathlib import Path

import pytest

from forge.forge_core.tools import ToolError, create_tool_registry
from forge.forge_core.workspace import Workspace, WorkspaceError


def test_workspace_uses_nearest_git_root_when_no_root_is_supplied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a directory nested inside a Git repository
    repository = tmp_path / "repository"
    nested = repository / "src" / "package"
    nested.mkdir(parents=True)
    (repository / ".git").mkdir()
    monkeypatch.chdir(nested)

    # When: Forge selects its default workspace
    workspace = Workspace()

    # Then: the workspace is confined to the repository root
    assert workspace.root == repository


def test_workspace_rejects_absolute_path_inside_workspace(tmp_path: Path) -> None:
    # Given: an absolute path that happens to point inside the workspace
    workspace = Workspace(tmp_path)

    # When / Then: Forge accepts only workspace-relative model paths
    with pytest.raises(WorkspaceError, match="relative"):
        workspace.resolve(str(tmp_path / "inside.txt"))


def test_workspace_rejects_external_file_symlink(tmp_path: Path) -> None:
    # Given: a workspace symlink targeting a file outside the workspace
    with tempfile.TemporaryDirectory() as external_directory:
        external_file = Path(external_directory) / "secret.txt"
        external_file.write_text("outside", encoding="utf-8")
        (tmp_path / "escape-file").symlink_to(external_file)
        workspace = Workspace(tmp_path)

        # When / Then: resolved containment rejects the escape
        with pytest.raises(WorkspaceError, match="escapes the workspace"):
            workspace.resolve("escape-file")


def test_workspace_rejects_binary_and_oversized_text_reads(tmp_path: Path) -> None:
    # Given: binary and oversized files inside an otherwise valid workspace
    (tmp_path / "binary.dat").write_bytes(b"safe\x00binary")
    (tmp_path / "large.txt").write_bytes(b"x" * 1_000_001)
    workspace = Workspace(tmp_path)

    # When / Then: model-facing text reads reject both unsafe content classes
    with pytest.raises(WorkspaceError, match="binary"):
        workspace.read_text("binary.dat")
    with pytest.raises(WorkspaceError, match="larger than 1 MB"):
        workspace.read_text("large.txt")


def test_file_listing_hides_restricted_and_external_entries(tmp_path: Path) -> None:
    # Given: visible project content alongside restricted and escaping entries
    (tmp_path / "visible.txt").write_text("visible", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=not-for-model", encoding="utf-8")
    with tempfile.TemporaryDirectory() as external_directory:
        external_file = Path(external_directory) / "external.txt"
        external_file.write_text("outside", encoding="utf-8")
        (tmp_path / "escape-file").symlink_to(external_file)
        registry = create_tool_registry(Workspace(tmp_path))

        # When: the model lists workspace files
        result = registry.execute("list_files", {})

        # Then: only allowed workspace entries are exposed
        assert "visible.txt" in result
        assert ".env" not in result
        assert "escape-file" not in result


def test_search_excludes_restricted_file_content(tmp_path: Path) -> None:
    # Given: the same marker in a project file and a restricted credential file
    marker = "workspace-guard-marker"
    (tmp_path / "visible.txt").write_text(marker, encoding="utf-8")
    (tmp_path / ".env").write_text(marker, encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))

    # When: the model searches project content
    result = registry.execute("search_files", {"query": marker})

    # Then: only allowed project content is returned
    assert "visible.txt" in result
    assert ".env" not in result


def test_search_rejects_file_replacement_before_ripgrep(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a validated search candidate replaced with an external symlink before ripgrep
    workspace = Workspace(tmp_path)
    registry = create_tool_registry(workspace)
    target = tmp_path / "target.txt"
    target.write_text("inside-marker\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-search"
    outside.write_text("external-marker\n", encoding="utf-8")
    from forge.forge_core import filesystem_tools

    original_run = filesystem_tools.subprocess.run

    def replace_before_run(*args, **kwargs):
        target.unlink()
        target.symlink_to(outside)
        return original_run(*args, **kwargs)

    monkeypatch.setattr(filesystem_tools.subprocess, "run", replace_before_run)

    # When: the model searches for content present only outside the workspace
    result = registry.execute("search_files", {"query": "external-marker"})

    # Then: the external content never crosses the tool boundary
    assert result == "No matches found."


def test_read_file_rejects_binary_content_at_the_tool_boundary(tmp_path: Path) -> None:
    # Given: a binary file inside the workspace
    (tmp_path / "binary.dat").write_bytes(b"safe\x00binary")
    registry = create_tool_registry(Workspace(tmp_path))

    # When / Then: the tool reports a structured model-safe error
    with pytest.raises(ToolError, match="binary"):
        registry.execute("read_file", {"path": "binary.dat"})


def test_workspace_read_rejects_symlink_replacement_after_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a validated workspace file replaced with an external symlink before reading
    target = tmp_path / "target.txt"
    target.write_text("inside", encoding="utf-8")
    with tempfile.TemporaryDirectory() as external_directory:
        external = Path(external_directory) / "outside.txt"
        external.write_text("outside", encoding="utf-8")
        workspace = Workspace(tmp_path)
        original_is_file = Path.is_file

        def replace_before_read(path: Path) -> bool:
            if path == target:
                target.unlink()
                target.symlink_to(external)
                return True
            return original_is_file(path)

        monkeypatch.setattr(Path, "is_file", replace_before_read)

        # When / Then: the changed path is rejected instead of exposing external content
        with pytest.raises(WorkspaceError, match="changed during access"):
            workspace.read_text("target.txt")


def test_workspace_read_rejects_parent_directory_symlink_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a validated parent directory replaced with an external symlink before reading
    directory = tmp_path / "nested"
    directory.mkdir()
    target = directory / "target.txt"
    target.write_text("inside", encoding="utf-8")
    with tempfile.TemporaryDirectory() as external_directory:
        external = Path(external_directory)
        (external / "target.txt").write_text("outside", encoding="utf-8")
        workspace = Workspace(tmp_path)
        original_is_file = Path.is_file

        def replace_parent_before_read(path: Path) -> bool:
            if path == target:
                directory.rename(tmp_path / "nested-original")
                directory.symlink_to(external, target_is_directory=True)
                return True
            return original_is_file(path)

        monkeypatch.setattr(Path, "is_file", replace_parent_before_read)

        # When / Then: every path component is opened without following symlinks
        with pytest.raises(WorkspaceError, match="changed during access"):
            workspace.read_text("nested/target.txt")


def test_runtime_rejects_external_forge_state_root(tmp_path: Path) -> None:
    # Given: project-local runtime state redirected outside the workspace
    from forge.forge import ForgeRuntimeError, build_runtime

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / ".forge").symlink_to(outside, target_is_directory=True)

    # When / Then: startup fails closed before creating external runtime state
    with pytest.raises(ForgeRuntimeError, match="state"):
        build_runtime(workspace)
    assert not tuple(outside.iterdir())


def test_workspace_limits_bytes_requested_from_file_descriptor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an observable descriptor stream for a model-facing file
    target = tmp_path / "large.txt"
    target.write_text("content", encoding="utf-8")
    requested_sizes: list[int] = []
    from forge.forge_core import safe_io

    class RecordingStream:
        def __init__(self, descriptor: int) -> None:
            self.descriptor = descriptor

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            os.close(self.descriptor)

        def read(self, size: int = -1) -> bytes:
            requested_sizes.append(size)
            return b"x" * size if size > 0 else b"x"

    monkeypatch.setattr(safe_io.os, "fdopen", lambda descriptor, _mode: RecordingStream(descriptor))

    # When / Then: Forge requests at most the configured limit plus one sentinel byte
    with pytest.raises(WorkspaceError, match="larger than 1 MB"):
        Workspace(tmp_path).read_text("large.txt")
    assert requested_sizes == [1_000_001]
