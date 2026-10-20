from __future__ import annotations

import fcntl
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import assert_never
from uuid import uuid4

from forge.checkpoints import CheckpointError, CheckpointManager
from forge.forge_core.safe_io import (
    SafeReadError,
    SafeWriteError,
    atomic_write_text_beneath,
    ensure_directory_beneath,
    link_file_beneath,
    open_file_beneath,
    regular_file_mode_beneath,
    replace_file_beneath,
    unlink_file_beneath,
)
from forge.forge_core.workspace import Workspace, WorkspaceError

from .models import (
    PatchApplicationError,
    PatchApplicationRecord,
    PatchApplicationStatus,
    PatchError,
    PatchOperation,
    PatchProposal,
)
from .parser import parse_patch
from .safety import reject_dirty_deletions
from .transactions import PatchTransaction, failed_record
from .transform import apply_file_patch


@dataclass(frozen=True, slots=True)
class _StagedChange:
    target: Path
    temporary: Path | None
    operation: PatchOperation


class PatchApplier:
    def __init__(self, workspace: Workspace, checkpoints: CheckpointManager) -> None:
        self.workspace = workspace
        self.checkpoints = checkpoints
        self.root = workspace.root / ".forge" / "patches"
        try:
            ensure_directory_beneath(workspace.root, self.root)
        except SafeWriteError as error:
            raise PatchApplicationError("Forge state directory changed during access.") from error
        self.lock_path = workspace.root / ".forge" / "patch-application.lock"

    def apply(
        self,
        raw_diff: str,
        task_id: str,
        patch_id: str,
    ) -> PatchApplicationRecord:
        transaction = PatchTransaction(uuid4().hex[:12], task_id, patch_id)
        descriptor = self._acquire_lock()
        try:
            try:
                proposal = parse_patch(raw_diff, self.workspace)
            except PatchError as error:
                record = failed_record(transaction, f"Patch validation failed: {error}")
                self._write_record(record)
                raise PatchApplicationError(record.detail) from error
            return self._apply_validated(transaction, raw_diff, proposal)
        finally:
            os.close(descriptor)

    def _apply_validated(
        self,
        transaction: PatchTransaction,
        raw_diff: str,
        proposal: PatchProposal,
    ) -> PatchApplicationRecord:
        reject_dirty_deletions(self.workspace.root, proposal)
        checkpoint = self.checkpoints.create(
            proposal,
            transaction.task_id,
            transaction.patch_id,
        )
        transaction = replace(
            transaction,
            checkpoint_id=checkpoint.id,
            affected_files=proposal.affected_files,
        )
        self._write_record(
            PatchApplicationRecord(
                transaction_id=transaction.transaction_id,
                task_id=transaction.task_id,
                patch_id=transaction.patch_id,
                checkpoint_id=transaction.checkpoint_id,
                status=PatchApplicationStatus.IN_PROGRESS,
                affected_files=transaction.affected_files,
                detail="Patch application is in progress.",
            )
        )
        staged: tuple[_StagedChange, ...] = ()
        try:
            staged = self._stage(proposal, transaction.transaction_id)
            try:
                confirmed = parse_patch(raw_diff, self.workspace)
            except PatchError as error:
                detail = f"Patch current content changed before commit: {error}"
                self._write_record(failed_record(transaction, detail))
                raise PatchApplicationError(detail) from error
            if confirmed != proposal:
                raise PatchApplicationError("Patch current content changed before commit.")
            return self._commit(transaction, proposal, staged)
        except OSError as error:
            detail = f"Patch staging failed before commit: {error}"
            self._write_record(failed_record(transaction, detail))
            raise PatchApplicationError(detail) from error
        finally:
            for change in staged:
                if change.temporary is not None:
                    try:
                        unlink_file_beneath(self.workspace.root, change.temporary)
                    except SafeWriteError:
                        continue

    def _commit(
        self,
        transaction: PatchTransaction,
        proposal: PatchProposal,
        staged: tuple[_StagedChange, ...],
    ) -> PatchApplicationRecord:
        checkpoint_id = transaction.checkpoint_id
        if checkpoint_id is None:
            raise PatchApplicationError("Patch transaction has no checkpoint.")
        created: list[Path] = []
        try:
            for change in staged:
                if change.operation is not PatchOperation.CREATE:
                    continue
                if change.temporary is None:
                    raise OSError("staged patch content is missing")
                self._create(change.temporary, change.target)
                created.append(change.target)
        except OSError as error:
            for target in created:
                unlink_file_beneath(self.workspace.root, target)
            detail = f"Patch create target already exists or changed: {error}"
            self._write_record(failed_record(transaction, detail))
            raise PatchApplicationError(detail) from error
        try:
            for change in staged:
                match change.operation:
                    case PatchOperation.CREATE:
                        continue
                    case PatchOperation.MODIFY:
                        if change.temporary is None:
                            raise OSError("staged patch content is missing")
                        self._replace(change.temporary, change.target)
                    case PatchOperation.DELETE:
                        unlink_file_beneath(self.workspace.root, change.target)
                    case unreachable:
                        assert_never(unreachable)
            record = PatchApplicationRecord(
                transaction_id=transaction.transaction_id,
                task_id=transaction.task_id,
                patch_id=transaction.patch_id,
                checkpoint_id=checkpoint_id,
                status=PatchApplicationStatus.SUCCEEDED,
                affected_files=proposal.affected_files,
                detail="Patch applied successfully.",
            )
            self._write_record(record)
            return record
        except OSError as error:
            try:
                self.checkpoints.undo(checkpoint_id)
            except (OSError, CheckpointError) as rollback_error:
                raise PatchApplicationError(
                    f"Patch application failed and rollback failed: {rollback_error}"
                ) from error
            detail = f"Patch application failed; restored checkpoint {checkpoint_id}: {error}"
            self._write_record(failed_record(transaction, detail))
            raise PatchApplicationError(detail) from error

    def _stage(self, proposal: PatchProposal, transaction_id: str) -> tuple[_StagedChange, ...]:
        staged: list[_StagedChange] = []
        for index, file_patch in enumerate(proposal.files):
            target = self.workspace.resolve(file_patch.path)
            if file_patch.operation is PatchOperation.DELETE:
                staged.append(_StagedChange(target, None, file_patch.operation))
                continue
            try:
                original = (
                    ""
                    if file_patch.operation is PatchOperation.CREATE
                    else self.workspace.read_text(file_patch.path)
                )
            except WorkspaceError as error:
                raise OSError(str(error)) from error
            content = apply_file_patch(file_patch, original)
            temporary = self.root / f".{transaction_id}.{index}.tmp"
            mode = 0o600
            if file_patch.operation is PatchOperation.MODIFY:
                try:
                    mode = regular_file_mode_beneath(self.workspace.root, target)
                except SafeReadError as error:
                    raise OSError(str(error)) from error
            descriptor = open_file_beneath(
                self.workspace.root,
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                mode,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            staged.append(_StagedChange(target, temporary, file_patch.operation))
        return tuple(staged)

    def _acquire_lock(self) -> int:
        try:
            descriptor = open_file_beneath(
                self.workspace.root,
                self.lock_path,
                os.O_WRONLY | os.O_CREAT,
            )
        except SafeWriteError as error:
            raise PatchApplicationError("Patch lock changed during access.") from error
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(descriptor)
            raise PatchApplicationError(
                "Another patch application is already in progress."
            ) from error
        return descriptor

    def _write_record(self, record: PatchApplicationRecord) -> None:
        target = self.root / f"{record.transaction_id}.json"
        payload = json.dumps(asdict(record), indent=2)
        try:
            atomic_write_text_beneath(self.workspace.root, target, payload)
        except SafeWriteError as error:
            raise PatchApplicationError("Patch record changed during access.") from error

    def _replace(self, source: Path, target: Path) -> None:
        replace_file_beneath(self.root, source, self.workspace.root, target)

    def _create(self, source: Path, target: Path) -> None:
        link_file_beneath(self.root, source, self.workspace.root, target)
