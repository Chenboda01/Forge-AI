import fcntl
import json
import os
from pathlib import Path

import pytest

import forge.patches as patches
from forge.checkpoints import CheckpointManager
from forge.forge_core.tools import create_tool_registry
from forge.forge_core.workspace import Workspace


def multi_file_patch() -> str:
    return (
        "--- a/existing.txt\n"
        "+++ b/existing.txt\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n"
        "--- /dev/null\n"
        "+++ b/new.txt\n"
        "@@ -0,0 +1 @@\n"
        "+created\n"
        "--- a/obsolete.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-remove\n"
    )


def make_applier(root: Path) -> patches.PatchApplier:
    workspace = Workspace(root)
    return patches.PatchApplier(workspace, CheckpointManager(workspace))


def test_apply_commits_multi_file_patch_and_records_success(tmp_path: Path) -> None:
    # Given: one approved patch that modifies, creates, and deletes files
    (tmp_path / "existing.txt").write_text("before\n", encoding="utf-8")
    (tmp_path / "obsolete.txt").write_text("remove\n", encoding="utf-8")
    applier = make_applier(tmp_path)

    # When: the patch boundary applies the complete proposal
    result = applier.apply(multi_file_patch(), task_id="task-1", patch_id="patch-1")

    # Then: every intended file and durable transaction evidence agree
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "after\n"
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "created\n"
    assert not (tmp_path / "obsolete.txt").exists()
    assert result.status is patches.PatchApplicationStatus.SUCCEEDED
    assert result.affected_files == ("existing.txt", "new.txt", "obsolete.txt")
    record = json.loads(
        (tmp_path / ".forge" / "patches" / f"{result.transaction_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["status"] == "succeeded"
    assert record["checkpoint_id"] == result.checkpoint_id


def test_apply_rechecks_current_content_before_commit(monkeypatch, tmp_path: Path) -> None:
    # Given: content changes after Forge creates its checkpoint but before commit
    target = tmp_path / "existing.txt"
    target.write_text("before\n", encoding="utf-8")
    applier = make_applier(tmp_path)
    original_create = applier.checkpoints.create

    def create_then_change(proposal, task_id: str, patch_id: str):
        record = original_create(proposal, task_id, patch_id)
        target.write_text("concurrent\n", encoding="utf-8")
        return record

    monkeypatch.setattr(applier.checkpoints, "create", create_then_change)
    raw = "--- a/existing.txt\n+++ b/existing.txt\n@@ -1 +1 @@\n-before\n+after\n"

    # When / Then: stale content stops application without overwriting the other writer
    with pytest.raises(patches.PatchApplicationError, match="current content changed"):
        applier.apply(raw, task_id="task-2", patch_id="patch-2")
    assert target.read_text(encoding="utf-8") == "concurrent\n"


def test_apply_rolls_back_all_files_after_mid_commit_failure(monkeypatch, tmp_path: Path) -> None:
    # Given: a valid multi-file patch whose second replacement fails
    existing = tmp_path / "existing.txt"
    obsolete = tmp_path / "obsolete.txt"
    existing.write_text("before\n", encoding="utf-8")
    obsolete.write_text("remove\n", encoding="utf-8")
    applier = make_applier(tmp_path)
    original_replace = applier._replace

    def fail_new_file(source: Path, target: Path) -> None:
        if target.name == "new.txt":
            raise OSError("injected replacement failure")
        original_replace(source, target)

    monkeypatch.setattr(applier, "_replace", fail_new_file)

    # When: commit fails after the first file was replaced
    with pytest.raises(patches.PatchApplicationError, match="restored checkpoint"):
        applier.apply(multi_file_patch(), task_id="task-3", patch_id="patch-3")

    # Then: the checkpoint restores the complete pre-application file state
    assert existing.read_text(encoding="utf-8") == "before\n"
    assert obsolete.read_text(encoding="utf-8") == "remove\n"
    assert not (tmp_path / "new.txt").exists()
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / ".forge" / "patches").glob("*.json")
    ]
    assert [record["status"] for record in records] == ["failed"]


def test_apply_rejects_concurrent_writer(tmp_path: Path) -> None:
    # Given: another writer holds Forge's project-local patch lock
    target = tmp_path / "existing.txt"
    target.write_text("before\n", encoding="utf-8")
    applier = make_applier(tmp_path)
    lock_path = tmp_path / ".forge" / "patch-application.lock"
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    raw = "--- a/existing.txt\n+++ b/existing.txt\n@@ -1 +1 @@\n-before\n+after\n"

    try:
        # When / Then: a second application is rejected before workspace mutation
        with pytest.raises(patches.PatchApplicationError, match="already in progress"):
            applier.apply(raw, task_id="task-4", patch_id="patch-4")
        assert target.read_text(encoding="utf-8") == "before\n"
    finally:
        os.close(descriptor)


def test_apply_patch_tool_requires_approval_and_returns_undo_id(tmp_path: Path) -> None:
    # Given: the primary tool registry and a valid patch
    (tmp_path / "existing.txt").write_text("before\n", encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))
    raw = "--- a/existing.txt\n+++ b/existing.txt\n@@ -1 +1 @@\n-before\n+after\n"

    # When: the approved handler applies the exact patch arguments
    result = registry.execute("apply_patch", {"patch": raw})

    # Then: the tool is approval-gated and reports durable undo evidence
    assert registry.get("apply_patch").requires_approval is True
    assert "Checkpoint:" in result
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "after\n"
