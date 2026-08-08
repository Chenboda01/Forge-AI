from dataclasses import dataclass
from enum import StrEnum
from typing import Final

MAX_PATCH_BYTES: Final = 1_000_000


class PatchOperation(StrEnum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class PatchErrorCode(StrEnum):
    EMPTY = "empty"
    TOO_LARGE = "too_large"
    MALFORMED = "malformed"
    PATH_REJECTED = "path_rejected"
    CONTEXT_MISMATCH = "context_mismatch"


class PatchApplicationStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PatchError(Exception):
    code: PatchErrorCode
    detail: str

    def __str__(self) -> str:
        return f"{self.code.value.replace('_', ' ')}: {self.detail}"


@dataclass(frozen=True, slots=True)
class PatchApplicationError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]

    @property
    def additions(self) -> int:
        return sum(line.startswith("+") for line in self.lines)

    @property
    def deletions(self) -> int:
        return sum(line.startswith("-") for line in self.lines)


@dataclass(frozen=True, slots=True)
class FilePatch:
    path: str
    operation: PatchOperation
    hunks: tuple[PatchHunk, ...]

    @property
    def additions(self) -> int:
        return sum(hunk.additions for hunk in self.hunks)

    @property
    def deletions(self) -> int:
        return sum(hunk.deletions for hunk in self.hunks)


@dataclass(frozen=True, slots=True)
class PatchProposal:
    raw_diff: str
    files: tuple[FilePatch, ...]

    @property
    def affected_files(self) -> tuple[str, ...]:
        return tuple(file.path for file in self.files)

    @property
    def additions(self) -> int:
        return sum(file.additions for file in self.files)

    @property
    def deletions(self) -> int:
        return sum(file.deletions for file in self.files)


@dataclass(frozen=True, slots=True)
class PatchApplicationRecord:
    transaction_id: str
    task_id: str
    patch_id: str
    checkpoint_id: str | None
    status: PatchApplicationStatus
    affected_files: tuple[str, ...]
    detail: str
