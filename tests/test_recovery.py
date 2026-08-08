import json
from pathlib import Path

import pytest

from forge.checkpoints import CheckpointManager
from forge.forge import build_runtime
from forge.forge_core.workspace import Workspace
from forge.patches import PatchApplier
from forge.sessions import SessionSnapshot, SessionStore, TaskStateRecord, UsageRecord
from forge.ui.commands import CommandService


def two_file_patch() -> str:
    return (
        "--- a/one.txt\n+++ b/one.txt\n@@ -1 +1 @@\n-before one\n+after one\n"
        "--- a/two.txt\n+++ b/two.txt\n@@ -1 +1 @@\n-before two\n+after two\n"
    )


def test_restart_detects_partial_patch_and_restores_checkpoint(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_text("before one\n", encoding="utf-8")
    (tmp_path / "two.txt").write_text("before two\n", encoding="utf-8")
    workspace = Workspace(tmp_path)
    applier = PatchApplier(workspace, CheckpointManager(workspace))
    original_replace = applier._replace
    replacements = 0

    def interrupt_second_replace(source: Path, target: Path) -> None:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise KeyboardInterrupt
        original_replace(source, target)

    monkeypatch.setattr(applier, "_replace", interrupt_second_replace)
    with pytest.raises(KeyboardInterrupt):
        applier.apply(two_file_patch(), "task-crash", "patch-crash")
    assert (tmp_path / "one.txt").read_text(encoding="utf-8") == "after one\n"

    from forge.recovery import RecoveryKind, RecoveryManager

    recovery = RecoveryManager(tmp_path)
    partial = next(item for item in recovery.items if item.kind is RecoveryKind.PARTIAL_PATCH)
    recovery.restore(partial.id)

    assert (tmp_path / "one.txt").read_text(encoding="utf-8") == "before one\n"
    assert (tmp_path / "two.txt").read_text(encoding="utf-8") == "before two\n"


def test_startup_detects_corrupt_session_and_temporary_persistence(tmp_path: Path) -> None:
    session_root = tmp_path / ".forge" / "sessions"
    session_root.mkdir(parents=True)
    (session_root / "broken123.json").write_text("not-json", encoding="utf-8")
    validation_root = tmp_path / ".forge" / "validation"
    validation_root.mkdir()
    temporary = validation_root / ".interrupted.tmp"
    temporary.write_text("partial", encoding="utf-8")

    from forge.recovery import RecoveryKind, RecoveryManager

    recovery = RecoveryManager(tmp_path)
    kinds = {item.kind for item in recovery.items}
    assert RecoveryKind.CORRUPT_SESSION in kinds
    assert RecoveryKind.TEMPORARY_FILE in kinds
    temp_item = next(item for item in recovery.items if item.path == temporary)
    recovery.discard(temp_item.id)
    assert not temporary.exists()


def test_interrupted_task_resume_returns_snapshot_without_executing(tmp_path: Path) -> None:
    snapshot = SessionSnapshot(
        id="running123",
        created_at="2026-08-08T12:00:00+00:00",
        task=TaskStateRecord("task-running", "Continue safely", "running"),
        messages=(),
        tools=(),
        approvals=(),
        patches=(),
        validations=(),
        subagents=(),
        usage=UsageRecord("test/model", 0, 0),
    )
    SessionStore(tmp_path).save(snapshot)

    from forge.recovery import RecoveryKind, RecoveryManager

    recovery = RecoveryManager(tmp_path)
    interrupted = next(
        item for item in recovery.items if item.kind is RecoveryKind.INTERRUPTED_TASK
    )
    resumed = recovery.resume(interrupted.id)

    assert resumed == snapshot.id
    persisted = json.loads(
        (tmp_path / ".forge" / "sessions" / f"{snapshot.id}.json").read_text(encoding="utf-8")
    )
    assert persisted["task"]["status"] == "running"


def test_runtime_detects_and_displays_recovery_items_at_startup(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    checkpoint_root = tmp_path / ".forge" / "checkpoints"
    checkpoint_root.mkdir(parents=True)
    (checkpoint_root / "interrupted.tmp").write_text("partial", encoding="utf-8")

    runtime = build_runtime(tmp_path)
    output = CommandService(runtime).recovery_text()

    assert runtime.recovery.items
    assert "incomplete_checkpoint" in output
