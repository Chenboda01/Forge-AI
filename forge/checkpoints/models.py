from dataclasses import dataclass


class CheckpointError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

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
