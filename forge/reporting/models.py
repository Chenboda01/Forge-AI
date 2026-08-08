from dataclasses import dataclass
from enum import StrEnum

from forge.validation import ValidationStatus


class PatchStatus(StrEnum):
    APPLIED = "applied"
    FAILED = "failed"
    NOT_APPLIED = "not_applied"


@dataclass(frozen=True, slots=True)
class FinalReportEvidence:
    summary: str
    files_inspected: tuple[str, ...]
    files_changed: tuple[str, ...]
    patch_status: PatchStatus
    validation: tuple[ValidationStatus, ...]
    limitations: tuple[str, ...]
    warnings: tuple[str, ...]
    checkpoint_id: str | None
