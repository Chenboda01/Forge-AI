import re
from collections.abc import Callable
from threading import RLock
from typing import Final

REDACTED: Final = "[REDACTED]"
MIN_REGISTERED_SECRET_LENGTH: Final = 8
_REGISTERED_SECRETS: Final[set[str]] = set()
_REGISTERED_SECRETS_LOCK: Final = RLock()
JSON_SECRET: Final = re.compile(
    r'(?i)("(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|private[_-]?key|secret)"\s*:\s*)"[^"]*"'
)
QUOTED_ASSIGNMENT_SECRET: Final = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|PASSWORD|PRIVATE_KEY|SECRET)[A-Z0-9_]*\s*=\s*)(\\?[\"'])[^\"'\r\n]+\2"
)
ASSIGNMENT_SECRET: Final = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|PASSWORD|PRIVATE_KEY|SECRET)[A-Z0-9_]*\s*=\s*)[^\\\s\"]+"
)
BEARER_SECRET: Final = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\\\s\"]+")
RAW_PROVIDER_SECRET: Final = re.compile(
    r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,})(?![A-Za-z0-9])"
)


def _replace_secret(match: re.Match[str]) -> str:
    return f'{match.group(1)}"{REDACTED}"'


def _replace_inline_secret(match: re.Match[str]) -> str:
    return f"{match.group(1)}{REDACTED}"


def _replace_quoted_secret(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{REDACTED}{match.group(2)}"


def _replace_raw_secret(_match: re.Match[str]) -> str:
    return REDACTED


def redact_text(text: str) -> str:
    substitutions: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str]], ...] = (
        (JSON_SECRET, _replace_secret),
        (QUOTED_ASSIGNMENT_SECRET, _replace_quoted_secret),
        (ASSIGNMENT_SECRET, _replace_inline_secret),
        (BEARER_SECRET, _replace_inline_secret),
        (RAW_PROVIDER_SECRET, _replace_raw_secret),
    )
    redacted = text
    with _REGISTERED_SECRETS_LOCK:
        registered_secrets = tuple(sorted(_REGISTERED_SECRETS, key=len, reverse=True))
    for secret in registered_secrets:
        redacted = redacted.replace(secret, REDACTED)
    for pattern, replacement in substitutions:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def register_secret(secret: str) -> None:
    normalized = secret.strip()
    if len(normalized) < MIN_REGISTERED_SECRET_LENGTH:
        return
    with _REGISTERED_SECRETS_LOCK:
        _REGISTERED_SECRETS.add(normalized)
