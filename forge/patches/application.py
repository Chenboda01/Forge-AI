from __future__ import annotations

import fcntl
import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import assert_never
from uuid import uuid4

from forge.checkpoints import CheckpointError, CheckpointManager
from forge.forge_core.workspace import Workspace

from .models import (
    PatchApplicationError,
    PatchApplicationRecord,
    PatchApplicationStatus,
    PatchError,
    PatchOperation,
    PatchProposal,
)
from .parser import parse_patch
from .transform import apply_file_patch


@dataclass(frozen=True, slots=True)
class _StagedChange:
    target: Path
    temporary: Path | None
    operation: PatchOperation


@dataclass(frozen=True, slots=True)
class _Transaction:
    transaction_id: str
    task_id: str
    patch_id: str
    checkpoint_id: str | None = None
    affected_files: tuple[str, ...] = ()


class PatchApplier:
    def __init__(self, workspace: Workspace, checkpoints: CheckpointManager) -> None:
        self.workspace = workspace
        self.checkpoints = checkpoints
        self.root = workspace.root / ".forge" / "patches"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.lock_path = workspace.root / ".forge" / "patch-application.lock"

    def apply(
        self,
        raw_diff: str,
        task_id: str,
        patch_id: str,
    ) -> PatchApplicationRecord:
        transaction = _Transaction(uuid4().hex[:12], task_id, patch_id)
        descriptor = self._acquire_lock()
        try:
            try:
                proposal = parse_patch(raw_diff, self.workspace)
            except PatchError as error:
                record = self._record(transaction, f"Patch validation failed: {error}")
                self._write_record(record)
                raise PatchApplicationError(record.detail) from error
            return self._apply_validated(transaction, raw_diff, proposal)
        finally:
            os.close(descriptor)

    def _apply_validated(
        self,
        transaction: _Transaction,
        raw_diff: str,
        proposal: PatchProposal,
    ) -> PatchApplicationRecord:
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
                self._write_record(self._record(transaction, detail))
                raise PatchApplicationError(detail) from error
            if confirmed != proposal:
                raise PatchApplicationError("Patch current content changed before commit.")
            return self._commit(transaction, proposal, staged)
        except OSError as error:
            detail = f"Patch staging failed before commit: {error}"
            self._write_record(self._record(transaction, detail))
            raise PatchApplicationError(detail) from error
        finally:
            for change in staged:
                if change.temporary is not None:
                    change.temporary.unlink(missing_ok=True)

    def _commit(
        self,
        transaction: _Transaction,
        proposal: PatchProposal,
        staged: tuple[_StagedChange, ...],
    ) -> PatchApplicationRecord:
        checkpoint_id = transaction.checkpoint_id
        if checkpoint_id is None:
            raise PatchApplicationError("Patch transaction has no checkpoint.")
        try:
            for change in staged:
                change.target.parent.mkdir(parents=True, exist_ok=True)
                match change.operation:
                    case PatchOperation.CREATE | PatchOperation.MODIFY:
                        if change.temporary is None:
                            raise OSError("staged patch content is missing")
                        self._replace(change.temporary, change.target)
                    case PatchOperation.DELETE:
                        change.target.unlink()
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
            self._write_record(self._record(transaction, detail))
            raise PatchApplicationError(detail) from error

    def _stage(self, proposal: PatchProposal, transaction_id: str) -> tuple[_StagedChange, ...]:
        staged: list[_StagedChange] = []
        for index, file_patch in enumerate(proposal.files):
            target = self.workspace.resolve(file_patch.path)
            if file_patch.operation is PatchOperation.DELETE:
                staged.append(_StagedChange(target, None, file_patch.operation))
                continue
            original = (
                ""
                if file_patch.operation is PatchOperation.CREATE
                else target.read_text(encoding="utf-8")
            )
            content = apply_file_patch(file_patch, original)
            temporary = self.root / f".{transaction_id}.{index}.tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if file_patch.operation is PatchOperation.MODIFY:
                temporary.chmod(stat.S_IMODE(target.stat().st_mode))
            staged.append(_StagedChange(target, temporary, file_patch.operation))
        return tuple(staged)

    def _acquire_lock(self) -> int:
        descriptor = os.open(
            self.lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC,
            0o600,
        )
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
        temporary = self.root / f".{record.transaction_id}.{uuid4().hex}.tmp"
        payload = json.dumps(asdict(record), indent=2)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _record(transaction: _Transaction, detail: str) -> PatchApplicationRecord:
        return PatchApplicationRecord(
            transaction_id=transaction.transaction_id,
            task_id=transaction.task_id,
            patch_id=transaction.patch_id,
            checkpoint_id=transaction.checkpoint_id,
            status=PatchApplicationStatus.FAILED,
            affected_files=transaction.affected_files,
            detail=detail,
        )

    @staticmethod
    def _replace(source: Path, target: Path) -> None:
        os.replace(source, target)
