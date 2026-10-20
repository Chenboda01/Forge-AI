from pathlib import Path
from typing import Final

from pathspec import GitIgnoreSpec

from .safe_io import SafeReadError, read_bytes_beneath

IGNORE_FILE_NAMES: Final = (".gitignore", ".forgeignore")
MAX_IGNORE_FILE_SIZE_BYTES: Final = 1_000_000
BUILTIN_EXCLUSIONS: Final = (
    ".git/",
    ".venv/",
    ".forge/",
    "__pycache__/",
    "node_modules/",
    "dist/",
    "build/",
)
SECRET_FILE_EXCLUSIONS: Final = (
    ".env",
    ".env.*",
    "*.key",
    "*.p12",
    "*.pem",
    "*.pfx",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "npmrc",
    "pypirc",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "service-account*.json",
    ".aws/credentials",
    "**/.aws/credentials",
)


class IgnorePolicyError(Exception):
    """Raised when an ignore configuration cannot be safely loaded."""


class IgnorePolicy:
    """Determines whether a workspace-relative path is excluded from model context."""

    def __init__(self, root: Path) -> None:
        self._hard_rules = GitIgnoreSpec.from_lines((*BUILTIN_EXCLUSIONS, *SECRET_FILE_EXCLUSIONS))
        project_rules = tuple(
            rule for file_name in IGNORE_FILE_NAMES for rule in _read_rules(root, file_name)
        )
        self._project_rules = GitIgnoreSpec.from_lines(project_rules)

    def matches(self, relative_path: Path, *, is_dir: bool) -> bool:
        candidate = relative_path.as_posix()
        if candidate == ".":
            return False
        if is_dir:
            candidate = f"{candidate}/"
        return self._hard_rules.match_file(candidate) or self._project_rules.match_file(candidate)


def _read_rules(root: Path, file_name: str) -> tuple[str, ...]:
    candidate = root / file_name
    try:
        content = read_bytes_beneath(root, candidate, max_bytes=MAX_IGNORE_FILE_SIZE_BYTES)
    except SafeReadError as error:
        if error.missing:
            return ()
        if error.too_large:
            raise IgnorePolicyError(
                f"Ignore configuration is larger than 1 MB: {file_name}"
            ) from error
        raise IgnorePolicyError(
            f"Ignore configuration changed during access: {file_name}"
        ) from error
    try:
        return tuple(content.decode("utf-8").splitlines())
    except UnicodeDecodeError as error:
        raise IgnorePolicyError(f"Ignore configuration is not UTF-8: {file_name}") from error
