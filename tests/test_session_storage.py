import stat
from pathlib import Path

import pytest


def complete_snapshot():
    from forge.sessions import (
        ApprovalDecisionRecord,
        PatchSessionRecord,
        SessionMessageRecord,
        SessionSnapshot,
        SubagentSessionRecord,
        TaskStateRecord,
        ToolExchangeRecord,
        UsageRecord,
    )
    from forge.validation import ValidationRecord, ValidationStatus

    return SessionSnapshot(
        id="session123456",
        created_at="2026-08-08T12:00:00+00:00",
        task=TaskStateRecord("task-1", "Fix validation", "completed"),
        messages=(SessionMessageRecord("user", "OPENAI_API_KEY=sk-test-not-real"),),
        tools=(ToolExchangeRecord("read_file", "{}", "Authorization: Bearer token-test-not-real"),),
        approvals=(ApprovalDecisionRecord("apply_patch", "{}", True),),
        patches=(PatchSessionRecord("patch-1", "succeeded", ("forge/a.py",), "check-1"),),
        validations=(
            ValidationRecord(
                "validation1",
                "2026-08-08T12:01:00+00:00",
                ("pytest",),
                ValidationStatus.PASSED,
                0,
                1.5,
                "1 passed",
                8,
                False,
                "Command completed.",
            ),
        ),
        subagents=(SubagentSessionRecord("explore", "completed", "Found one file."),),
        usage=UsageRecord("test/model", 100, 25),
    )


def test_complete_session_snapshot_survives_restart_with_restrictive_permissions(
    tmp_path: Path,
) -> None:
    from forge.sessions import SessionStore

    store = SessionStore(tmp_path)
    snapshot = complete_snapshot()

    store.save(snapshot)
    restarted = SessionStore(tmp_path)
    loaded = restarted.load(snapshot.id)

    assert loaded is not None
    assert loaded.task == snapshot.task
    assert loaded.patches == snapshot.patches
    assert loaded.validations == snapshot.validations
    assert loaded.subagents == snapshot.subagents
    assert loaded.usage == snapshot.usage
    assert "sk-test-not-real" not in loaded.messages[0].content
    assert "token-test-not-real" not in loaded.tools[0].result
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE((store.root / f"{snapshot.id}.json").stat().st_mode) == 0o600
    assert not tuple(store.root.glob("*.tmp"))


def test_corrupt_session_is_rejected_without_becoming_runtime_state(tmp_path: Path) -> None:
    from forge.sessions import SessionStorageError, SessionStore

    store = SessionStore(tmp_path)
    (store.root / "broken123456.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(SessionStorageError, match="corrupt"):
        store.load("broken123456")


def test_runtime_session_manager_reopens_typed_snapshot(tmp_path: Path) -> None:
    from forge.forge_core.sessions import SessionManager

    manager = SessionManager(tmp_path)
    snapshot = complete_snapshot()

    manager.save_snapshot(snapshot)
    loaded = SessionManager(tmp_path).load_snapshot(snapshot.id)

    assert loaded is not None
    assert loaded.task == snapshot.task
    assert loaded.usage == snapshot.usage


def test_session_store_rejects_external_session_symlink(tmp_path: Path) -> None:
    # Given: a valid session identifier redirected to JSON outside Forge state
    from forge.sessions import SessionStorageError, SessionStore

    store = SessionStore(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (store.root / "session123456.json").symlink_to(outside)

    # When / Then: the persistence boundary rejects the external symlink before reading it
    with pytest.raises(SessionStorageError, match="outside Forge session storage"):
        store.load("session123456")


def test_session_store_rejects_symlink_replacement_before_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a valid stored session replaced with an external record after path validation
    from forge.sessions import SessionStorageError, SessionStore

    store = SessionStore(tmp_path)
    snapshot = complete_snapshot()
    store.save(snapshot)
    target = store.root / f"{snapshot.id}.json"
    outside = tmp_path / "outside.json"
    outside.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    original_is_file = Path.is_file

    def replace_before_read(path: Path) -> bool:
        if path == target:
            target.unlink()
            target.symlink_to(outside)
            return True
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", replace_before_read)

    # When / Then: external session content is rejected at the persistence boundary
    with pytest.raises(SessionStorageError, match="changed during access"):
        store.load(snapshot.id)


def test_session_store_rejects_external_state_directory_symlink(tmp_path: Path) -> None:
    # Given: project-local Forge state redirected to an external directory
    from forge.sessions import SessionStorageError, SessionStore

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / ".forge").symlink_to(outside, target_is_directory=True)

    # When / Then: initialization fails closed without creating external state
    with pytest.raises(SessionStorageError, match="state directory"):
        SessionStore(workspace)
    assert not (outside / "sessions").exists()
