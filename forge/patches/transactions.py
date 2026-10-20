from dataclasses import dataclass

from .models import PatchApplicationRecord, PatchApplicationStatus


@dataclass(frozen=True, slots=True)
class PatchTransaction:
    transaction_id: str
    task_id: str
    patch_id: str
    checkpoint_id: str | None = None
    affected_files: tuple[str, ...] = ()


def failed_record(transaction: PatchTransaction, detail: str) -> PatchApplicationRecord:
    return PatchApplicationRecord(
        transaction_id=transaction.transaction_id,
        task_id=transaction.task_id,
        patch_id=transaction.patch_id,
        checkpoint_id=transaction.checkpoint_id,
        status=PatchApplicationStatus.FAILED,
        affected_files=transaction.affected_files,
        detail=detail,
    )
