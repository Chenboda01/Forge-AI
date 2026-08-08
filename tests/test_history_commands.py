from pathlib import Path

from forge.forge import build_runtime
from forge.sessions import SessionSnapshot, TaskStateRecord, UsageRecord
from forge.ui.commands import CommandService


def test_resume_restores_only_text_history_without_replaying_tools(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    saved = runtime.sessions.save(
        [
            {"role": "system", "content": "old system"},
            {"role": "user", "content": "Inspect files"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call-1", "function": {"name": "read_file"}}],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "untrusted result"},
            {"role": "assistant", "content": "Inspection finished."},
        ],
        "old/model",
        input_tokens=12,
        output_tokens=4,
    )

    resumed_runtime = build_runtime(tmp_path)
    result = CommandService(resumed_runtime).resume_session(saved.id)

    assert result == f"Resumed session {saved.id}."
    assert [message["role"] for message in resumed_runtime.agent.messages] == [
        "system",
        "user",
        "assistant",
    ]
    assert resumed_runtime.agent.messages[-1]["content"] == "Inspection finished."
    assert resumed_runtime.agent.input_tokens == 12
    assert resumed_runtime.agent.output_tokens == 4


def test_history_redacts_current_conversation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    runtime.agent.messages.append(
        {
            "role": "user",
            "content": "Authorization: Bearer token-test-not-real",
        }
    )

    history = CommandService(runtime).history_text()

    assert "token-test-not-real" not in history
    assert "[REDACTED]" in history


def test_sessions_lists_typed_and_legacy_records_while_skipping_corruption(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    legacy = runtime.sessions.save([{"role": "user", "content": "Legacy task"}], "test/model")
    typed = SessionSnapshot(
        id="typed123456",
        created_at="2026-08-08T12:00:00+00:00",
        task=TaskStateRecord("task-typed", "Typed task", "completed"),
        messages=(),
        tools=(),
        approvals=(),
        patches=(),
        validations=(),
        subagents=(),
        usage=UsageRecord("test/model", 3, 2),
    )
    runtime.sessions.save_snapshot(typed)
    (runtime.sessions.root / "corrupt123.json").write_text("not-json", encoding="utf-8")

    listing = CommandService(runtime).sessions_text()

    assert legacy.id in listing
    assert typed.id in listing
    assert "corrupt123" not in listing
