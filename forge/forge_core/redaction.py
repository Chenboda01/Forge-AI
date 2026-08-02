import re
from collections.abc import Callable
from typing import Final

REDACTED: Final = "[REDACTED]"
JSON_SECRET: Final = re.compile(
    r'(?i)("(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|private[_-]?key|secret)"\s*:\s*)"[^"]*"'
)
ASSIGNMENT_SECRET: Final = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|PASSWORD|PRIVATE_KEY|SECRET)[A-Z0-9_]*\s*=\s*)[^\\\s\"]+"
)
BEARER_SECRET: Final = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\\\s\"]+")


def _replace_secret(match: re.Match[str]) -> str:
    return f'{match.group(1)}"{REDACTED}"'


def _replace_inline_secret(match: re.Match[str]) -> str:
    return f"{match.group(1)}{REDACTED}"


def redact_text(text: str) -> str:
    substitutions: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str]], ...] = (
        (JSON_SECRET, _replace_secret),
        (ASSIGNMENT_SECRET, _replace_inline_secret),
        (BEARER_SECRET, _replace_inline_secret),
    )
    redacted = text
    for pattern, replacement in substitutions:
        redacted = pattern.sub(replacement, redacted)
    return redacted
