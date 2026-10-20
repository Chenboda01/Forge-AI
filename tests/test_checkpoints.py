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


def test_checkpoint_rejects_external_record_symlink(tmp_path: Path) -> None:
    # Given: a valid checkpoint identifier redirected to JSON outside Forge state
    manager = CheckpointManager(Workspace(tmp_path))
    checkpoint_id = "abcdef123456"
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "id": checkpoint_id,
                "task_id": "task",
                "patch_id": "patch",
                "created_at": "2026-09-13T00:00:00+00:00",
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    (manager.root / f"{checkpoint_id}.json").symlink_to(outside)

    # When / Then: external checkpoint content cannot become restoration authority
    with pytest.raises(CheckpointError, match="outside Forge checkpoint storage"):
        manager.load(checkpoint_id)


def test_checkpoint_rejects_symlink_replacement_before_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a checkpoint replaced with an external record after path validation
    manager = CheckpointManager(Workspace(tmp_path))
    checkpoint_id = "abcdef123456"
    target = manager.root / f"{checkpoint_id}.json"
    payload = json.dumps(
        {
            "id": checkpoint_id,
            "task_id": "task",
            "patch_id": "patch",
            "created_at": "2026-09-23T00:00:00+00:00",
            "files": [],
        }
    )
    target.write_text(payload, encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text(payload, encoding="utf-8")
    original_is_file = Path.is_file

    def replace_before_read(path: Path) -> bool:
        if path == target:
            target.unlink()
            target.symlink_to(outside)
            return True
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", replace_before_read)

    # When / Then: external checkpoint content cannot become restoration authority
    with pytest.raises(CheckpointError, match="changed during access"):
        manager.load(checkpoint_id)


def test_checkpoint_creation_rejects_symlink_replacement_before_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an approved target replaced with an external symlink before checkpoint capture
    proposal = proposal_for_existing_and_new(tmp_path)
    manager = CheckpointManager(Workspace(tmp_path))
    target = tmp_path / "existing.txt"
    outside = tmp_path.parent / "outside-checkpoint.txt"
    outside.write_text("outside\n", encoding="utf-8")
    original_is_file = Path.is_file

    def replace_before_capture(path: Path) -> bool:
        if path == target:
            target.unlink()
            target.symlink_to(outside)
            return True
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", replace_before_capture)

    # When / Then: external content cannot become rollback authority
    with pytest.raises(CheckpointError, match="workspace|changed during access"):
        manager.create(proposal, task_id="task", patch_id="patch")
    assert not tuple(manager.root.glob("*.json"))


def test_undo_rejects_parent_directory_replacement_before_restore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a checkpoint target whose parent is replaced before restoration
    nested = tmp_path / "nested"
    nested.mkdir()
    target = nested / "existing.txt"
    target.write_text("before\n", encoding="utf-8")
    proposal = parse_patch(
        "--- a/nested/existing.txt\n+++ b/nested/existing.txt\n@@ -1 +1 @@\n-before\n+after\n",
        Workspace(tmp_path),
    )
    manager = CheckpointManager(Workspace(tmp_path))
    record = manager.create(proposal, task_id="task-race", patch_id="patch-race")
    target.write_text("after\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-undo"
    outside.mkdir()
    external = outside / "existing.txt"
    external.write_text("external\n", encoding="utf-8")
    original_atomic_write = manager._atomic_write

    def replace_parent_then_write(path: Path, content: str) -> None:
        if path == target:
            target.unlink()
            nested.rmdir()
            nested.symlink_to(outside, target_is_directory=True)
        original_atomic_write(path, content)

    monkeypatch.setattr(manager, "_atomic_write", replace_parent_then_write)

    # When / Then: restoration fails closed without modifying the external file
    with pytest.raises(CheckpointError, match="changed during access"):
        manager.undo(record.id)
    assert external.read_text(encoding="utf-8") == "external\n"


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
