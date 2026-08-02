import os
import tempfile
from pathlib import Path

import pytest

from forge.forge_core.workspace import Workspace, WorkspaceError


class TestWorkspace:
    def test_resolve_simple_path(self):
        ws = Workspace(Path("/home/user/project"))
        resolved = ws.resolve("src/main.py")
        assert resolved == Path("/home/user/project/src/main.py").resolve()

    def test_resolve_dot(self):
        ws = Workspace(Path("/home/user/project"))
        resolved = ws.resolve(".")
        assert resolved == Path("/home/user/project").resolve()

    def test_resolve_nested(self):
        ws = Workspace(Path("/home/user/project"))
        resolved = ws.resolve("src/forge_core/tools.py")
        expected = Path("/home/user/project/src/forge_core/tools.py").resolve()
        assert resolved == expected

    def test_reject_parent_traversal(self):
        ws = Workspace(Path("/home/user/project"))
        with pytest.raises(WorkspaceError, match="escapes the workspace"):
            ws.resolve("../secret.txt")

    def test_reject_deep_parent_traversal(self):
        ws = Workspace(Path("/home/user/project"))
        with pytest.raises(WorkspaceError, match="escapes the workspace"):
            ws.resolve("../../.ssh/id_rsa")

    def test_reject_absolute_path_outside_workspace(self):
        ws = Workspace(Path("/home/user/project"))
        with pytest.raises(WorkspaceError, match="escapes the workspace"):
            ws.resolve("/etc/passwd")

    def test_reject_relative_escaping(self):
        ws = Workspace(Path("/home/user/project"))
        with pytest.raises(WorkspaceError, match="escapes the workspace"):
            ws.resolve("subdir/../../../etc/passwd")

    def test_accept_path_within_workspace_with_dots(self):
        ws = Workspace(Path("/home/user/project"))
        resolved = ws.resolve("subdir/../subdir/file.txt")
        expected = Path("/home/user/project/subdir/file.txt").resolve()
        assert resolved == expected

    def test_default_root_is_cwd(self):
        ws = Workspace()
        assert ws.root == Path.cwd().resolve()

    def test_resolve_with_tmpdir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "subdir").mkdir()

            ws = Workspace(root)
            resolved = ws.resolve("subdir")
            assert resolved == (root / "subdir").resolve()

    def test_symlink_escape_detection(self):
        """Verify symlinks pointing outside are caught."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ws = Workspace(root)

            # Create a symlink pointing outside
            external = Path("/tmp")
            symlink = root / "escape_link"
            os.symlink(external, symlink)

            # Resolving the symlink should detect escape
            with pytest.raises(WorkspaceError, match="escapes"):
                ws.resolve("escape_link")

    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.local",
            "certs/client.pem",
            "keys/signing.key",
            ".aws/credentials",
            ".forge/sessions/current.json",
            "service-account-prod.json",
        ],
    )
    def test_reject_restricted_paths(self, path: str) -> None:
        # Given: a workspace path commonly containing credentials or private state
        ws = Workspace(Path("/home/user/project"))

        # When / Then: model-facing resolution denies it before file access
        with pytest.raises(WorkspaceError, match="restricted"):
            ws.resolve(path)
