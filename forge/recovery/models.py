from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RecoveryKind(StrEnum):
    INTERRUPTED_TASK = "interrupted_task"
    INCOMPLETE_CHECKPOINT = "incomplete_checkpoint"
    PARTIAL_PATCH = "partial_patch"
    CORRUPT_SESSION = "corrupt_session"
    TEMPORARY_FILE = "temporary_file"


@dataclass(frozen=True, slots=True)
class RecoveryError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class RecoveryItem:
    id: str
    kind: RecoveryKind
    path: Path
    detail: str
    checkpoint_id: str | None = None
    session_id: str | None = None
