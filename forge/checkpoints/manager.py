from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from forge.forge_core.safe_io import (
    SafeReadError,
    SafeWriteError,
    atomic_write_text_beneath,
    ensure_directory_beneath,
    read_bytes_beneath,
    unlink_file_beneath,
)
from forge.forge_core.workspace import Workspace, WorkspaceError

from .models import CheckpointError, CheckpointFile, CheckpointRecord

if TYPE_CHECKING:
    from forge.patches.models import PatchProposal

CHECKPOINT_ID: Final = re.compile(r"^[0-9a-f]{12}$")
MAX_CHECKPOINT_BYTES: Final = 10_000_000


class CheckpointManager:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.root = workspace.root / ".forge" / "checkpoints"
        try:
            ensure_directory_beneath(workspace.root, self.root)
        except SafeWriteError as error:
            raise CheckpointError("Forge state directory changed during access.") from error

    def create(
        self,
        proposal: PatchProposal,
        task_id: str,
        patch_id: str,
    ) -> CheckpointRecord:
        files = tuple(self._capture(path) for path in proposal.affected_files)
        record = CheckpointRecord(
            id=uuid4().hex[:12],
            task_id=task_id,
            patch_id=patch_id,
            created_at=datetime.now(UTC).isoformat(),
            files=files,
        )
        payload = json.dumps(asdict(record), indent=2)
        self._atomic_write(self.root / f"{record.id}.json", payload)
        return record

    def load(self, checkpoint_id: str) -> CheckpointRecord:
        path = self._record_path(checkpoint_id)
        if not path.is_file():
            raise CheckpointError(f"Checkpoint not found: {checkpoint_id}")
        try:
            payload = json.loads(
                read_bytes_beneath(self.root, path, max_bytes=MAX_CHECKPOINT_BYTES).decode("utf-8")
            )
            files = tuple(
                CheckpointFile(
                    path=file["path"],
                    existed=file["existed"],
                    content=file["content"],
                )
                for file in payload["files"]
            )
            record = CheckpointRecord(
                id=payload["id"],
                task_id=payload["task_id"],
                patch_id=payload["patch_id"],
                created_at=payload["created_at"],
                files=files,
            )
        except SafeReadError as error:
            raise CheckpointError(f"Checkpoint changed during access: {checkpoint_id}") from error
        except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as error:
            raise CheckpointError(f"Checkpoint is corrupt: {checkpoint_id}") from error
        if record.id != checkpoint_id or not all(self._valid_file(file) for file in record.files):
            raise CheckpointError(f"Checkpoint is corrupt: {checkpoint_id}")
        return record

    def latest(self) -> CheckpointRecord | None:
        records = tuple(self.load(path.stem) for path in self.root.glob("*.json"))
        return max(records, key=lambda record: record.created_at, default=None)

    def undo(self, checkpoint_id: str) -> CheckpointRecord:
        record = self.load(checkpoint_id)
        for file in record.files:
            target = self._restore_target(file.path)
            if file.existed:
                if file.content is None:
                    raise CheckpointError(f"Checkpoint is corrupt: {checkpoint_id}")
                self._atomic_write(target, file.content)
            elif target.exists():
                if not target.is_file():
                    raise CheckpointError(f"Undo target is not a file: {file.path}")
                try:
                    unlink_file_beneath(self.workspace.root, target)
                except SafeWriteError as error:
                    raise CheckpointError(f"Path changed during access: {file.path}") from error
        return record

    def incomplete_checkpoints(self) -> tuple[str, ...]:
        return tuple(path.name for path in sorted(self.root.glob("*.tmp")))

    def _capture(self, relative_path: str) -> CheckpointFile:
        path = self.workspace.resolve(relative_path)
        if not path.exists():
            return CheckpointFile(relative_path, False, None)
        if not path.is_file():
            raise CheckpointError(f"Checkpoint target is not a file: {relative_path}")
        try:
            content = self.workspace.read_text(relative_path)
        except WorkspaceError as error:
            raise CheckpointError(str(error)) from error
        except UnicodeDecodeError as error:
            raise CheckpointError(
                f"Checkpoint target is not UTF-8 text: {relative_path}"
            ) from error
        return CheckpointFile(relative_path, True, content)

    def _restore_target(self, relative_path: str) -> Path:
        lexical = self.workspace.root / relative_path
        try:
            resolved = self.workspace.resolve(relative_path)
        except WorkspaceError as error:
            raise CheckpointError(str(error)) from error
        if lexical.absolute() != resolved:
            raise CheckpointError(f"Undo target changed through a symlink: {relative_path}")
        return lexical

    def _record_path(self, checkpoint_id: str) -> Path:
        if CHECKPOINT_ID.fullmatch(checkpoint_id) is None:
            raise CheckpointError(f"Invalid checkpoint ID: {checkpoint_id}")
        path = self.root / f"{checkpoint_id}.json"
        try:
            path.resolve().relative_to(self.root)
        except ValueError as error:
            raise CheckpointError(
                f"Checkpoint is outside Forge checkpoint storage: {checkpoint_id}"
            ) from error
        return path

    @staticmethod
    def _valid_file(file: CheckpointFile) -> bool:
        return (
            bool(file.path)
            and isinstance(file.existed, bool)
            and (file.content is None or isinstance(file.content, str))
            and (file.existed or file.content is None)
        )

    def _atomic_write(self, path: Path, content: str) -> None:
        trusted_root = self.root if path.is_relative_to(self.root) else self.workspace.root
        try:
            atomic_write_text_beneath(trusted_root, path, content, create_parents=True)
        except SafeWriteError as error:
            raise CheckpointError(f"Path changed during access: {path}") from error
