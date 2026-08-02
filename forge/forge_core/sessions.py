from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .redaction import redact_text


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


class SessionManager:
    def __init__(self, root: Path | None = None):
        self.root = (root or Path.cwd()) / ".forge" / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)

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
        filepath.write_text(redact_text(json.dumps(data, indent=2)), encoding="utf-8")

        return meta

    def load(self, session_id: str) -> dict[str, Any] | None:
        filepath = self.root / f"{session_id}.json"
        if not filepath.exists():
            return None
        return json.loads(filepath.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[SessionMeta]:
        sessions: list[SessionMeta] = []
        for fp in sorted(self.root.glob("*.json"), reverse=True):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
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
            except (json.JSONDecodeError, KeyError):
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
