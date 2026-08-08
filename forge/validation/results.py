import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import CommandExecutionResult, ValidationRecord, ValidationStatus


class ValidationResultStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve() / ".forge" / "validation"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)

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
            arguments=result.arguments,
            status=status,
            exit_code=result.exit_code,
            duration_seconds=result.duration_seconds,
            output=result.output,
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
            arguments=arguments,
            status=status,
            exit_code=None,
            duration_seconds=None,
            output="",
            output_bytes=0,
            truncated=False,
            detail=detail,
        )

    def _write(self, record: ValidationRecord) -> None:
        target = self.root / f"{record.id}.json"
        temporary = self.root / f".{record.id}.{uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(asdict(record), stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise


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
