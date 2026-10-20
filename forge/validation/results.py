import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from forge.forge_core.redaction import redact_text
from forge.forge_core.safe_io import (
    atomic_write_text_beneath,
    ensure_directory_beneath,
)

from .models import CommandExecutionResult, ValidationRecord, ValidationStatus


class ValidationResultStore:
    def __init__(self, root: Path) -> None:
        self.workspace_root = root.resolve()
        self.root = self.workspace_root / ".forge" / "validation"
        ensure_directory_beneath(self.workspace_root, self.root)

    def record_execution(self, result: CommandExecutionResult) -> ValidationRecord:
        if result.truncated:
            status = ValidationStatus.INCOMPLETE
        elif result.passed:
            status = ValidationStatus.PASSED
        else:
            status = ValidationStatus.FAILED
        record = ValidationRecord(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC).isoformat(),
            arguments=tuple(redact_text(argument) for argument in result.arguments),
            status=status,
            exit_code=result.exit_code,
            duration_seconds=result.duration_seconds,
            output=redact_text(result.output),
            output_bytes=result.output_bytes,
            truncated=result.truncated,
            detail="Command timed out." if result.timed_out else "Command completed.",
        )
        self._write(record)
        return record

    def record_not_run(self, arguments: tuple[str, ...], detail: str) -> ValidationRecord:
        record = self._nonexecution(arguments, ValidationStatus.NOT_RUN, detail)
        self._write(record)
        return record

    def record_unavailable(self, arguments: tuple[str, ...], detail: str) -> ValidationRecord:
        record = self._nonexecution(arguments, ValidationStatus.COULD_NOT_RUN, detail)
        self._write(record)
        return record

    @staticmethod
    def _nonexecution(
        arguments: tuple[str, ...],
        status: ValidationStatus,
        detail: str,
    ) -> ValidationRecord:
        return ValidationRecord(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC).isoformat(),
            arguments=tuple(redact_text(argument) for argument in arguments),
            status=status,
            exit_code=None,
            duration_seconds=None,
            output="",
            output_bytes=0,
            truncated=False,
            detail=redact_text(detail),
        )

    def _write(self, record: ValidationRecord) -> None:
        target = self.root / f"{record.id}.json"
        payload = json.dumps(asdict(record), indent=2)
        atomic_write_text_beneath(self.workspace_root, target, payload)


def render_validation_result(record: ValidationRecord) -> str:
    exit_code = "not available" if record.exit_code is None else str(record.exit_code)
    duration = (
        "not available" if record.duration_seconds is None else f"{record.duration_seconds:.3f}s"
    )
    output = record.output or record.detail
    return (
        f"Command: {json.dumps(list(record.arguments))}\n"
        f"Status: {record.status.value}\n"
        f"Exit code: {exit_code}\n"
        f"Duration: {duration}\n"
        f"Truncated: {'yes' if record.truncated else 'no'}\n"
        f"Output:\n{output}"
    )
