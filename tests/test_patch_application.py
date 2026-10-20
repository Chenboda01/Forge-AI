import fcntl
import json
import os
import subprocess
from pathlib import Path

import pytest

import forge.patches as patches
import forge.patches.application as application_module
from forge.checkpoints import CheckpointManager
from forge.forge_core.tools import ToolError, create_tool_registry
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
    # Given: a valid multi-file patch whose modification fails after CREATE reservation
    existing = tmp_path / "existing.txt"
    obsolete = tmp_path / "obsolete.txt"
    existing.write_text("before\n", encoding="utf-8")
    obsolete.write_text("remove\n", encoding="utf-8")
    applier = make_applier(tmp_path)
    original_replace = applier._replace

    def fail_existing_file(source: Path, target: Path) -> None:
        if target.name == "existing.txt":
            raise OSError("injected replacement failure")
        original_replace(source, target)

    monkeypatch.setattr(applier, "_replace", fail_existing_file)

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


def test_apply_rejects_parent_directory_replacement_before_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a validated patch target whose parent is replaced before commit
    nested = tmp_path / "nested"
    nested.mkdir()
    target = nested / "existing.txt"
    target.write_text("before\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-patch"
    outside.mkdir()
    external = outside / "existing.txt"
    external.write_text("external\n", encoding="utf-8")
    applier = make_applier(tmp_path)
    original_replace = applier._replace

    def replace_parent_then_commit(source: Path, destination: Path) -> None:
        if destination == target:
            target.unlink()
            nested.rmdir()
            nested.symlink_to(outside, target_is_directory=True)
        original_replace(source, destination)

    monkeypatch.setattr(applier, "_replace", replace_parent_then_commit)
    raw = "--- a/nested/existing.txt\n+++ b/nested/existing.txt\n@@ -1 +1 @@\n-before\n+after\n"

    # When / Then: commit and rollback fail closed without touching external content
    with pytest.raises(patches.PatchApplicationError, match="rollback failed"):
        applier.apply(raw, task_id="task-race", patch_id="patch-race")
    assert external.read_text(encoding="utf-8") == "external\n"


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


def test_apply_create_does_not_clobber_concurrently_created_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: another writer creates the proposed path after final validation
    target = tmp_path / "new.txt"
    applier = make_applier(tmp_path)
    raw = "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+forge content\n"
    real_parse = application_module.parse_patch
    parse_calls = 0

    def parse_then_create(raw_diff: str, workspace: Workspace):
        nonlocal parse_calls
        proposal = real_parse(raw_diff, workspace)
        parse_calls += 1
        if parse_calls == 2:
            target.write_text("concurrent content\n", encoding="utf-8")
        return proposal

    monkeypatch.setattr(application_module, "parse_patch", parse_then_create)

    # When / Then: atomic CREATE fails without overwriting or deleting the other writer
    with pytest.raises(patches.PatchApplicationError, match="already exists"):
        applier.apply(raw, task_id="task-create-race", patch_id="patch-create-race")
    assert target.read_text(encoding="utf-8") == "concurrent content\n"


def test_apply_patch_tool_requires_approval_and_returns_undo_id(tmp_path: Path) -> None:
    # Given: the primary tool registry and a valid patch
    (tmp_path / "existing.txt").write_text("before\n", encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))
    raw = "--- a/existing.txt\n+++ b/existing.txt\n@@ -1 +1 @@\n-before\n+after\n"

    # When: the approved handler applies the exact previously previewed patch arguments
    registry.execute("propose_patch", {"patch": raw})
    result = registry.execute("apply_patch", {"patch": raw})

    # Then: the tool is approval-gated and reports durable undo evidence
    assert registry.get("apply_patch").requires_approval is True
    assert "Checkpoint:" in result
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "after\n"


def test_apply_patch_tool_rejects_payload_changed_after_preview(tmp_path: Path) -> None:
    # Given: a valid patch preview followed by a different model-originated payload
    target = tmp_path / "existing.txt"
    target.write_text("before\n", encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))
    previewed = "--- a/existing.txt\n+++ b/existing.txt\n@@ -1 +1 @@\n-before\n+after\n"
    changed = "--- a/existing.txt\n+++ b/existing.txt\n@@ -1 +1 @@\n-before\n+different\n"
    registry.execute("propose_patch", {"patch": previewed})

    # When / Then: exact-preview binding rejects approval drift before workspace mutation
    with pytest.raises(ToolError, match="exactly match the most recent preview"):
        registry.execute("apply_patch", {"patch": changed})
    assert target.read_text(encoding="utf-8") == "before\n"


def test_apply_rejects_deletion_of_dirty_tracked_file(tmp_path: Path) -> None:
    # Given: a tracked file containing user changes
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "important.txt"
    target.write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "important.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Forge Test",
            "-c",
            "user.email=forge@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
    )
    target.write_text("user work\n", encoding="utf-8")
    raw = "--- a/important.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-user work\n"

    # When / Then: destructive application stops before checkpoint or deletion
    with pytest.raises(patches.PatchApplicationError, match="uncommitted"):
        make_applier(tmp_path).apply(raw, task_id="task-dirty", patch_id="patch-dirty")
    assert target.read_text(encoding="utf-8") == "user work\n"


def test_dirty_delete_check_ignores_ambient_git_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an attacker-controlled git executable appears first on ambient PATH
    attacker_bin = tmp_path / "attacker-bin"
    attacker_bin.mkdir()
    marker = tmp_path / "ambient-git-ran"
    fake_git = attacker_bin / "git"
    fake_git.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n", encoding="utf-8")
    fake_git.chmod(0o700)
    monkeypatch.setenv("PATH", str(attacker_bin))
    target = tmp_path / "obsolete.txt"
    target.write_text("remove\n", encoding="utf-8")
    raw = "--- a/obsolete.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-remove\n"

    # When: Forge checks and applies a deletion outside a Git repository
    make_applier(tmp_path).apply(raw, task_id="task-path", patch_id="patch-path")

    # Then: the project-controlled executable was never invoked
    assert not marker.exists()
    assert not target.exists()


def test_dirty_delete_check_fails_closed_when_git_inspection_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: Git cannot determine whether a destructive target has user changes
    target = tmp_path / "important.txt"
    target.write_text("remove\n", encoding="utf-8")
    raw = "--- a/important.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-remove\n"
    monkeypatch.setattr(
        "forge.patches.safety.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("git",), returncode=2, stdout="", stderr="index inspection failed"
        ),
    )

    # When / Then: uncertain Git state stops deletion before workspace mutation
    with pytest.raises(patches.PatchApplicationError, match="Could not inspect"):
        make_applier(tmp_path).apply(raw, task_id="task-git-error", patch_id="patch-git-error")
    assert target.read_text(encoding="utf-8") == "remove\n"
