from pathlib import Path
from typing import Final

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


class WorkspaceError(Exception):
    """Raised when a path escapes the Forge workspace."""


class Workspace:
    def __init__(self, root: Path | None = None):
        self.root = (root or Path.cwd()).resolve()

    def resolve(self, relative_path: str) -> Path:
        """Resolve a path while preventing access outside the workspace."""
        requested = (self.root / relative_path).resolve()

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
