from pathlib import Path
from typing import Final

from .ignore import IgnorePolicy, IgnorePolicyError
from .safe_io import SafeReadError, read_bytes_beneath

RESTRICTED_NAMES: Final = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials.json",
        "id_ed25519",
        "id_rsa",
        "npmrc",
        "pypirc",
    }
)
RESTRICTED_SUFFIXES: Final = frozenset({".key", ".p12", ".pem", ".pfx"})
MAX_FILE_SIZE_BYTES: Final = 1_000_000


class WorkspaceError(Exception):
    """Raised when a path escapes the Forge workspace."""


class Workspace:
    def __init__(self, root: Path | None = None):
        self.root = root.resolve() if root is not None else _find_git_root(Path.cwd())
        try:
            self._ignore_policy = IgnorePolicy(self.root)
        except IgnorePolicyError as error:
            raise WorkspaceError(str(error)) from error

    def resolve(self, relative_path: str) -> Path:
        """Resolve a path while preventing access outside the workspace."""
        requested_path = Path(relative_path)
        if requested_path.is_absolute():
            raise WorkspaceError(
                "Path must be relative to the workspace; absolute path escapes the workspace: "
                f"{relative_path}"
            )
        requested = (self.root / requested_path).resolve()

        try:
            requested.relative_to(self.root)
        except ValueError as error:
            raise WorkspaceError(f"Path escapes the workspace: {relative_path}") from error

        relative = requested.relative_to(self.root)
        lowered_parts = tuple(part.lower() for part in relative.parts)
        name = requested.name.lower()
        restricted = (
            ".forge" in lowered_parts
            or name in RESTRICTED_NAMES
            or name.startswith(".env.")
            or name.startswith("service-account")
            and name.endswith(".json")
            or requested.suffix.lower() in RESTRICTED_SUFFIXES
            or len(lowered_parts) >= 2
            and lowered_parts[-2:] == (".aws", "credentials")
        )
        if restricted:
            raise WorkspaceError(f"Path is restricted: {relative_path}")

        return requested

    def resolve_for_context(self, relative_path: str) -> Path:
        """Resolve a model-facing path while enforcing the workspace ignore policy."""
        requested = self.resolve(relative_path)
        relative = requested.relative_to(self.root)
        if self._ignore_policy.matches(relative, is_dir=requested.is_dir()):
            raise WorkspaceError(f"Path is ignored: {relative_path}")
        return requested

    def read_text(self, relative_path: str) -> str:
        """Read a bounded UTF-8 text file through the workspace boundary."""
        file_path = self.resolve_for_context(relative_path)
        if not file_path.exists():
            raise WorkspaceError(f"File does not exist: {relative_path}")
        if not file_path.is_file():
            raise WorkspaceError(f"Not a file: {relative_path}")
        try:
            content = read_bytes_beneath(
                self.root,
                file_path,
                max_bytes=MAX_FILE_SIZE_BYTES,
            )
        except SafeReadError as error:
            if error.too_large:
                raise WorkspaceError("File is larger than 1 MB.") from error
            raise WorkspaceError(f"Path changed during access: {relative_path}") from error
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise WorkspaceError("File is larger than 1 MB.")
        if b"\x00" in content:
            raise WorkspaceError("Forge cannot read this binary file.")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise WorkspaceError("Forge cannot read this binary file.") from error


def _find_git_root(start: Path) -> Path:
    resolved_start = start.resolve()
    for candidate in (resolved_start, *resolved_start.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved_start
