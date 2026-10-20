from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from forge.checkpoints import CheckpointManager
from forge.forge_core.safe_io import (
    SafeReadError,
    SafeWriteError,
    atomic_write_text_beneath,
    ensure_directory_beneath,
    read_bytes_beneath,
    unlink_file_beneath,
)
from forge.forge_core.workspace import Workspace

from .models import RecoveryError, RecoveryItem, RecoveryKind

TERMINAL_TASK_STATES = frozenset({"completed", "failed", "cancelled"})
MAX_RECOVERY_BYTES = 10_000_000


class RecoveryManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.state_root = self.root / ".forge"
        try:
            ensure_directory_beneath(self.root, self.state_root)
        except SafeWriteError as error:
            raise RecoveryError("Forge recovery state changed during access.") from error
        self.items = self.inspect()

    def inspect(self) -> tuple[RecoveryItem, ...]:
        try:
            ensure_directory_beneath(self.root, self.state_root)
        except SafeWriteError as error:
            raise RecoveryError("Forge recovery state changed during access.") from error
        items: list[RecoveryItem] = []
        represented: set[Path] = set()
        session_root = self.state_root / "sessions"
        for path in sorted(session_root.glob("*.json")):
            if not self._is_state_path(path):
                continue
            try:
                payload = json.loads(
                    read_bytes_beneath(
                        session_root,
                        path,
                        max_bytes=MAX_RECOVERY_BYTES,
                    ).decode("utf-8")
                )
            except (SafeReadError, UnicodeDecodeError, json.JSONDecodeError):
                items.append(self._item(RecoveryKind.CORRUPT_SESSION, path, "Session is corrupt."))
                represented.add(path)
                continue
            task = payload.get("task") if isinstance(payload, dict) else None
            if isinstance(task, dict) and task.get("status") not in TERMINAL_TASK_STATES:
                items.append(
                    self._item(
                        RecoveryKind.INTERRUPTED_TASK,
                        path,
                        "Task did not reach a terminal state.",
                        session_id=path.stem,
                    )
                )

        checkpoint_root = self.state_root / "checkpoints"
        for path in sorted(checkpoint_root.glob("*.tmp")):
            items.append(
                self._item(
                    RecoveryKind.INCOMPLETE_CHECKPOINT,
                    path,
                    "Checkpoint write was interrupted.",
                )
            )
            represented.add(path)

        patch_root = self.state_root / "patches"
        for path in sorted(patch_root.glob("*.json")):
            if not self._is_state_path(path):
                continue
            try:
                payload = json.loads(
                    read_bytes_beneath(
                        patch_root,
                        path,
                        max_bytes=MAX_RECOVERY_BYTES,
                    ).decode("utf-8")
                )
            except (SafeReadError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("status") == "in_progress":
                items.append(
                    self._item(
                        RecoveryKind.PARTIAL_PATCH,
                        path,
                        "Patch transaction was interrupted.",
                        checkpoint_id=payload.get("checkpoint_id"),
                    )
                )
                represented.add(path)

        for path in sorted(self.state_root.glob("**/*.tmp")):
            if path not in represented:
                items.append(
                    self._item(
                        RecoveryKind.TEMPORARY_FILE,
                        path,
                        "Temporary persistence file remains.",
                    )
                )
        return tuple(items)

    def restore(self, item_id: str) -> str:
        item = self._get(item_id)
        if item.kind is not RecoveryKind.PARTIAL_PATCH or item.checkpoint_id is None:
            raise RecoveryError("Only a partial patch with a checkpoint can be restored.")
        if not self._is_state_path(item.path):
            raise RecoveryError("Recovery data is outside Forge state.")
        CheckpointManager(Workspace(self.root)).undo(item.checkpoint_id)
        try:
            payload = json.loads(
                read_bytes_beneath(
                    self.state_root / "patches",
                    item.path,
                    max_bytes=MAX_RECOVERY_BYTES,
                ).decode("utf-8")
            )
        except (SafeReadError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RecoveryError("Recovery data changed during access.") from error
        payload["status"] = "failed"
        payload["detail"] = f"Recovered from checkpoint {item.checkpoint_id}."
        self._atomic_write(item.path, json.dumps(payload, indent=2))
        self.items = self.inspect()
        return item.checkpoint_id

    def resume(self, item_id: str) -> str:
        item = self._get(item_id)
        if item.kind is not RecoveryKind.INTERRUPTED_TASK or item.session_id is None:
            raise RecoveryError("Only an interrupted task can be resumed.")
        return item.session_id

    def discard(self, item_id: str) -> None:
        item = self._get(item_id)
        try:
            item.path.relative_to(self.state_root)
        except ValueError as error:
            raise RecoveryError("Recovery data is outside Forge state.") from error
        try:
            unlink_file_beneath(self.root, item.path)
        except SafeWriteError as error:
            raise RecoveryError("Recovery data changed during access.") from error
        self.items = self.inspect()

    def _get(self, item_id: str) -> RecoveryItem:
        item = next((candidate for candidate in self.items if candidate.id == item_id), None)
        if item is None:
            raise RecoveryError(f"Unknown recovery item: {item_id}")
        return item

    def _is_state_path(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.state_root)
        except ValueError:
            return False
        return True

    @staticmethod
    def _item(
        kind: RecoveryKind,
        path: Path,
        detail: str,
        checkpoint_id: str | None = None,
        session_id: str | None = None,
    ) -> RecoveryItem:
        return RecoveryItem(uuid4().hex[:12], kind, path, detail, checkpoint_id, session_id)

    def _atomic_write(self, path: Path, content: str) -> None:
        try:
            atomic_write_text_beneath(self.root, path, content)
        except SafeWriteError as error:
            raise RecoveryError("Recovery data changed during access.") from error
