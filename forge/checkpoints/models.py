from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CheckpointError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class CheckpointFile:
    path: str
    existed: bool
    content: str | None


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    id: str
    task_id: str
    patch_id: str
    created_at: str
    files: tuple[CheckpointFile, ...]
