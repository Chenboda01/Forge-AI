from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Final

from forge.forge_core.redaction import redact_text
from forge.forge_core.safe_io import (
    SafeReadError,
    SafeWriteError,
    atomic_write_text_beneath,
    ensure_directory_beneath,
    read_bytes_beneath,
)
from forge.validation import ValidationRecord, ValidationStatus

from .models import (
    ApprovalDecisionRecord,
    PatchSessionRecord,
    SessionMessageRecord,
    SessionSnapshot,
    SessionStorageError,
    SubagentSessionRecord,
    TaskStateRecord,
    ToolExchangeRecord,
    UsageRecord,
)

SESSION_ID: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_SESSION_BYTES: Final = 10_000_000


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.workspace_root = root.resolve()
        self.root = self.workspace_root / ".forge" / "sessions"
        try:
            ensure_directory_beneath(self.workspace_root, self.root)
        except SafeWriteError as error:
            raise SessionStorageError("Forge state directory changed during access.") from error

    def save(self, snapshot: SessionSnapshot) -> None:
        target = self._path(snapshot.id)
        payload = redact_text(json.dumps(asdict(snapshot), indent=2))
        try:
            atomic_write_text_beneath(self.workspace_root, target, payload)
        except SafeWriteError as error:
            raise SessionStorageError(f"Session changed during access: {snapshot.id}") from error

    def load(self, session_id: str) -> SessionSnapshot | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(
                read_bytes_beneath(self.root, path, max_bytes=MAX_SESSION_BYTES).decode("utf-8")
            )
            snapshot = SessionSnapshot(
                id=payload["id"],
                created_at=payload["created_at"],
                task=TaskStateRecord(**payload["task"]),
                messages=tuple(SessionMessageRecord(**item) for item in payload["messages"]),
                tools=tuple(ToolExchangeRecord(**item) for item in payload["tools"]),
                approvals=tuple(ApprovalDecisionRecord(**item) for item in payload["approvals"]),
                patches=tuple(
                    PatchSessionRecord(
                        id=item["id"],
                        status=item["status"],
                        affected_files=tuple(item["affected_files"]),
                        checkpoint_id=item["checkpoint_id"],
                    )
                    for item in payload["patches"]
                ),
                validations=tuple(_validation(item) for item in payload["validations"]),
                subagents=tuple(SubagentSessionRecord(**item) for item in payload["subagents"]),
                usage=UsageRecord(**payload["usage"]),
            )
        except SafeReadError as error:
            raise SessionStorageError(f"Session changed during access: {session_id}") from error
        except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
            raise SessionStorageError(f"Session is corrupt: {session_id}") from error
        if snapshot.id != session_id:
            raise SessionStorageError(f"Session is corrupt: {session_id}")
        return snapshot

    def _path(self, session_id: str) -> Path:
        if SESSION_ID.fullmatch(session_id) is None:
            raise SessionStorageError(f"Invalid session ID: {session_id}")
        path = self.root / f"{session_id}.json"
        try:
            path.resolve().relative_to(self.root)
        except ValueError as error:
            raise SessionStorageError(
                f"Session is outside Forge session storage: {session_id}"
            ) from error
        return path


def _validation(item) -> ValidationRecord:
    return ValidationRecord(
        id=item["id"],
        created_at=item["created_at"],
        arguments=tuple(item["arguments"]),
        status=ValidationStatus(item["status"]),
        exit_code=item["exit_code"],
        duration_seconds=item["duration_seconds"],
        output=item["output"],
        output_bytes=item["output_bytes"],
        truncated=item["truncated"],
        detail=item["detail"],
    )
