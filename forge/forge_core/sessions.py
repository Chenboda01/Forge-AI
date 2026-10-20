from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from forge.sessions import SessionMessageRecord, SessionSnapshot, SessionStorageError, SessionStore
from forge.sessions.storage import SESSION_ID

from .redaction import redact_text
from .safe_io import (
    SafeReadError,
    SafeWriteError,
    atomic_write_text_beneath,
    ensure_directory_beneath,
    read_bytes_beneath,
)

MAX_SESSION_BYTES = 10_000_000


@dataclass(frozen=True, slots=True)
class SessionMeta:
    id: str
    name: str
    created_at: str
    updated_at: str
    model: str
    message_count: int
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ResumeData:
    messages: tuple[SessionMessageRecord, ...]
    input_tokens: int
    output_tokens: int


class SessionManager:
    def __init__(self, root: Path | None = None):
        self.project_root = (root or Path.cwd()).resolve()
        self.root = self.project_root / ".forge" / "sessions"
        try:
            ensure_directory_beneath(self.project_root, self.root)
        except SafeWriteError as error:
            raise SessionStorageError("Forge state directory changed during access.") from error
        self.snapshots = SessionStore(self.project_root)

    def save_snapshot(self, snapshot: SessionSnapshot) -> None:
        self.snapshots.save(snapshot)

    def load_snapshot(self, session_id: str) -> SessionSnapshot | None:
        return self.snapshots.load(session_id)

    def save(
        self,
        messages: list[dict[str, Any]],
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        name: str | None = None,
    ) -> SessionMeta:
        session_id = uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        if name is None:
            name = self._auto_name(messages)

        meta = SessionMeta(
            id=session_id,
            name=name,
            created_at=now,
            updated_at=now,
            model=model,
            message_count=len([m for m in messages if m.get("role") != "system"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        data = {
            "meta": {
                "id": meta.id,
                "name": meta.name,
                "created_at": meta.created_at,
                "updated_at": meta.updated_at,
                "model": meta.model,
                "message_count": meta.message_count,
                "input_tokens": meta.input_tokens,
                "output_tokens": meta.output_tokens,
            },
            "messages": messages,
        }

        filepath = self.root / f"{session_id}.json"
        try:
            atomic_write_text_beneath(
                self.project_root,
                filepath,
                redact_text(json.dumps(data, indent=2)),
            )
        except SafeWriteError as error:
            raise SessionStorageError(f"Session changed during access: {session_id}") from error

        return meta

    def load(self, session_id: str) -> dict[str, Any] | None:
        filepath = self._session_path(session_id)
        if filepath is None:
            return None
        if not filepath.exists():
            return None
        try:
            return json.loads(
                read_bytes_beneath(self.root, filepath, max_bytes=MAX_SESSION_BYTES).decode("utf-8")
            )
        except (SafeReadError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def resume_data(self, session_id: str) -> ResumeData | None:
        filepath = self._session_path(session_id)
        if filepath is None:
            return None
        if not filepath.is_file():
            return None
        try:
            payload = json.loads(
                read_bytes_beneath(self.root, filepath, max_bytes=MAX_SESSION_BYTES).decode("utf-8")
            )
            if "task" in payload:
                snapshot = self.snapshots.load(session_id)
                if snapshot is None:
                    return None
                messages = tuple(
                    message
                    for message in snapshot.messages
                    if message.role in {"user", "assistant"} and message.content
                )
                return ResumeData(
                    messages,
                    snapshot.usage.input_tokens,
                    snapshot.usage.output_tokens,
                )
            meta = payload["meta"]
            messages = tuple(
                SessionMessageRecord(message["role"], message["content"])
                for message in payload["messages"]
                if message.get("role") in {"user", "assistant"}
                and isinstance(message.get("content"), str)
                and message["content"]
            )
            return ResumeData(
                messages,
                meta.get("input_tokens", 0),
                meta.get("output_tokens", 0),
            )
        except (SafeReadError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            return None

    def _session_path(self, session_id: str) -> Path | None:
        if SESSION_ID.fullmatch(session_id) is None:
            return None
        path = self.root / f"{session_id}.json"
        try:
            path.resolve().relative_to(self.root)
        except ValueError:
            return None
        return path

    def list_sessions(self) -> list[SessionMeta]:
        sessions: list[SessionMeta] = []
        for fp in sorted(self.root.glob("*.json"), reverse=True):
            filepath = self._session_path(fp.stem)
            if filepath is None:
                continue
            try:
                data = json.loads(
                    read_bytes_beneath(
                        self.root,
                        filepath,
                        max_bytes=MAX_SESSION_BYTES,
                    ).decode("utf-8")
                )
                if "task" in data:
                    snapshot = self.snapshots.load(filepath.stem)
                    if snapshot is None:
                        continue
                    sessions.append(
                        SessionMeta(
                            id=snapshot.id,
                            name=snapshot.task.objective,
                            created_at=snapshot.created_at,
                            updated_at=snapshot.created_at,
                            model=snapshot.usage.model,
                            message_count=len(snapshot.messages),
                            input_tokens=snapshot.usage.input_tokens,
                            output_tokens=snapshot.usage.output_tokens,
                        )
                    )
                    continue
                m = data["meta"]
                sessions.append(
                    SessionMeta(
                        id=m["id"],
                        name=m["name"],
                        created_at=m["created_at"],
                        updated_at=m["updated_at"],
                        model=m["model"],
                        message_count=m["message_count"],
                        input_tokens=m.get("input_tokens", 0),
                        output_tokens=m.get("output_tokens", 0),
                    )
                )
            except (SafeReadError, UnicodeDecodeError, json.JSONDecodeError, KeyError):
                continue
        return sessions

    @staticmethod
    def _auto_name(messages: list[dict[str, Any]]) -> str:
        """Generate a meaningful session name from user messages."""
        user_texts = [
            m.get("content", "")
            for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]

        if not user_texts:
            return f"Session {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}"

        first = user_texts[0].strip()

        # Extract meaningful phrases
        patterns = [
            r"(?i)(?:fix|debug|resolve)\s+(.+?)(?:\s+(?:in|on|for|with|$)|$)",
            r"(?i)(?:explain|analyze|review|read|inspect)\s+(.+?)(?:\s+(?:in|on|for|$)|$)",
            r"(?i)(?:add|create|build|implement|write)\s+(.+?)(?:\s+(?:in|on|for|$)|$)",
            r"(?i)(?:refactor|improve|optimize|update)\s+(.+?)(?:\s+(?:in|on|for|$)|$)",
            r"(?i)(?:list|show|find|search)\s+(.+?)(?:\s+(?:in|on|for|$)|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, first)
            if match:
                verb = re.search(r"^\w+", first, re.IGNORECASE)
                verb_text = verb.group(0).capitalize() if verb else ""
                target = match.group(1).strip().rstrip(".")
                if len(target) < 40:
                    return f"{verb_text} {target}" if verb_text else target.capitalize()

        # Fallback: first sentence or truncated first message
        sentence = re.split(r"[.!?]\s+", first)[0].strip()
        if len(sentence) > 50:
            sentence = sentence[:47] + "..."
        return sentence if sentence else f"Session {datetime.now(UTC).strftime('%H:%M')}"
