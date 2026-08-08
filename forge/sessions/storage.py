from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Final
from uuid import uuid4

from forge.forge_core.redaction import redact_text
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


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve() / ".forge" / "sessions"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)

    def save(self, snapshot: SessionSnapshot) -> None:
        target = self._path(snapshot.id)
        temporary = self.root / f".{snapshot.id}.{uuid4().hex}.tmp"
        payload = redact_text(json.dumps(asdict(snapshot), indent=2))
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

    def load(self, session_id: str) -> SessionSnapshot | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
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
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise SessionStorageError(f"Session is corrupt: {session_id}") from error
        if snapshot.id != session_id:
            raise SessionStorageError(f"Session is corrupt: {session_id}")
        return snapshot

    def _path(self, session_id: str) -> Path:
        if SESSION_ID.fullmatch(session_id) is None:
            raise SessionStorageError(f"Invalid session ID: {session_id}")
        return self.root / f"{session_id}.json"


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
