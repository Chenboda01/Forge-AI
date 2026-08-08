import json
from pathlib import Path

import pytest
from textual.widgets import TextArea

from forge.checkpoints import CheckpointError, CheckpointManager
from forge.forge import build_runtime
from forge.forge_core.workspace import Workspace
from forge.patches import parse_patch
from forge.ui.app import ForgeApp
from forge.ui.commands import CommandService
from forge.ui.widgets import ConversationView


def proposal_for_existing_and_new(root: Path):
    (root / "existing.txt").write_text("before\n", encoding="utf-8")
    raw = (
        "--- a/existing.txt\n+++ b/existing.txt\n@@ -1 +1 @@\n-before\n+after\n"
        "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+created\n"
    )
    return parse_patch(raw, Workspace(root))


def test_checkpoint_persists_original_state_and_identity(tmp_path: Path) -> None:
    # Given: a proposal affecting an existing file and a future new file
    proposal = proposal_for_existing_and_new(tmp_path)
    manager = CheckpointManager(Workspace(tmp_path))

    # When: Forge checkpoints the proposal before application
    record = manager.create(proposal, task_id="task-123", patch_id="patch-456")

    # Then: task, patch, existence, and original content are durably recorded
    payload = json.loads((manager.root / f"{record.id}.json").read_text(encoding="utf-8"))
    assert payload["task_id"] == "task-123"
    assert payload["patch_id"] == "patch-456"
    assert payload["files"] == [
        {"path": "existing.txt", "existed": True, "content": "before\n"},
        {"path": "new.txt", "existed": False, "content": None},
    ]


def test_undo_restores_existing_and_removes_new_file(tmp_path: Path) -> None:
    # Given: a checkpoint followed by simulated modification and creation
    manager = CheckpointManager(Workspace(tmp_path))
    record = manager.create(
        proposal_for_existing_and_new(tmp_path), task_id="task-1", patch_id="patch-1"
    )
    (tmp_path / "existing.txt").write_text("after\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("created\n", encoding="utf-8")

    # When: the checkpoint is undone
    restored = manager.undo(record.id)

    # Then: original content returns and the newly created file is removed
    assert restored.id == record.id
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "before\n"
    assert not (tmp_path / "new.txt").exists()


def test_undo_restores_deleted_file(tmp_path: Path) -> None:
    # Given: a checkpoint for a file that is subsequently deleted
    target = tmp_path / "obsolete.txt"
    target.write_text("keep me\n", encoding="utf-8")
    proposal = parse_patch(
        "--- a/obsolete.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-keep me\n",
        Workspace(tmp_path),
    )
    manager = CheckpointManager(Workspace(tmp_path))
    record = manager.create(proposal, task_id="task-2", patch_id="patch-2")
    target.unlink()

    # When: undo runs after deletion
    manager.undo(record.id)

    # Then: deleted content is restored
    assert target.read_text(encoding="utf-8") == "keep me\n"


def test_checkpoint_survives_manager_restart(tmp_path: Path) -> None:
    # Given: a persisted checkpoint and a new manager instance
    manager = CheckpointManager(Workspace(tmp_path))
    record = manager.create(
        proposal_for_existing_and_new(tmp_path), task_id="task-3", patch_id="patch-3"
    )
    (tmp_path / "existing.txt").write_text("changed\n", encoding="utf-8")

    # When: a restarted manager loads and undoes the checkpoint
    restarted = CheckpointManager(Workspace(tmp_path))
    restarted.undo(record.id)

    # Then: persisted state remains sufficient for restoration
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "before\n"


def test_incomplete_checkpoint_is_detected(tmp_path: Path) -> None:
    # Given: a temporary checkpoint file left by an interrupted atomic write
    manager = CheckpointManager(Workspace(tmp_path))
    interrupted = manager.root / "checkpoint-deadbeef.tmp"
    interrupted.write_text("partial", encoding="utf-8")

    # When: Forge inspects checkpoint health
    incomplete = manager.incomplete_checkpoints()

    # Then: interrupted state is visible rather than silently ignored
    assert incomplete == (interrupted.name,)


def test_checkpoint_rejects_unknown_or_corrupt_record(tmp_path: Path) -> None:
    # Given: an unknown ID and a corrupt persisted checkpoint
    manager = CheckpointManager(Workspace(tmp_path))
    corrupt = manager.root / "abcdef123456.json"
    corrupt.write_text("not-json", encoding="utf-8")

    # When / Then: neither record can become restoration authority
    with pytest.raises(CheckpointError, match="not found"):
        manager.undo("000000000000")
    with pytest.raises(CheckpointError, match="corrupt"):
        manager.undo("abcdef123456")


def test_checkpoint_and_undo_commands_use_latest_record(monkeypatch, tmp_path: Path) -> None:
    # Given: a runtime with a checkpoint followed by a simulated edit
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    record = runtime.checkpoints.create(
        proposal_for_existing_and_new(tmp_path), task_id="task-ui", patch_id="patch-ui"
    )
    (tmp_path / "existing.txt").write_text("after\n", encoding="utf-8")
    service = CommandService(runtime)

    # When: trusted slash-command services inspect and undo the latest checkpoint
    summary = service.checkpoint_text()
    result = service.undo("")

    # Then: the exact checkpoint is shown and restored
    assert record.id in summary
    assert result == f"Restored checkpoint {record.id}."
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "before\n"


@pytest.mark.asyncio
async def test_undo_command_restores_latest_checkpoint_through_tui(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: a running Forge TUI with a checkpointed file changed afterward
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    record = runtime.checkpoints.create(
        proposal_for_existing_and_new(tmp_path), task_id="task-e2e", patch_id="patch-e2e"
    )
    (tmp_path / "existing.txt").write_text("after\n", encoding="utf-8")
    app = ForgeApp(runtime, skip_startup=True)

    # When: the user invokes /undo through the composer
    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "/undo"
        await pilot.press("enter")
        await pilot.pause()

        # Then: restoration and its exact checkpoint ID are visible
        assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "before\n"
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert f"Restored checkpoint {record.id}." in transcript
