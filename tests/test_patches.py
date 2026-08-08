from pathlib import Path

import pytest

from forge.forge_core.tools import ToolError, create_tool_registry
from forge.forge_core.workspace import Workspace
from forge.patches import (
    MAX_PATCH_BYTES,
    PatchError,
    PatchOperation,
    parse_patch,
    render_preview,
)


def modification_patch(path: str = "example.py") -> str:
    return (
        f"--- a/{path}\n+++ b/{path}\n@@ -1,2 +1,2 @@\n value = 1\n-print('old')\n+print('new')\n"
    )


def test_parse_patch_extracts_typed_multi_file_changes(tmp_path: Path) -> None:
    # Given: current content and a proposal that modifies one file and creates another
    (tmp_path / "example.py").write_text("value = 1\nprint('old')\n", encoding="utf-8")
    raw = modification_patch() + ("--- /dev/null\n+++ b/notes.txt\n@@ -0,0 +1,1 @@\n+ready\n")

    # When: untrusted unified diff text is parsed at the patch boundary
    proposal = parse_patch(raw, Workspace(tmp_path))

    # Then: downstream code receives immutable, normalized patch data
    assert proposal.affected_files == ("example.py", "notes.txt")
    assert tuple(change.operation for change in proposal.files) == (
        PatchOperation.MODIFY,
        PatchOperation.CREATE,
    )
    assert proposal.additions == 2
    assert proposal.deletions == 1


@pytest.mark.parametrize(
    "raw",
    [
        "not a unified diff\n",
        "--- a/example.py\n+++ b/example.py\n",
        ("--- a/example.py\n+++ b/example.py\n@@ -1,1 +1,1 @@\n value = 1\n+extra\n"),
        ("--- a/example.py\n+++ b/example.py\n@@ broken @@\n value = 1\n"),
    ],
)
def test_parse_patch_rejects_malformed_input(tmp_path: Path, raw: str) -> None:
    # Given: malformed model-originated patch text
    (tmp_path / "example.py").write_text("value = 1\n", encoding="utf-8")

    # When / Then: parsing fails before a proposal reaches workflow code
    with pytest.raises(PatchError, match="malformed"):
        parse_patch(raw, Workspace(tmp_path))


@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd"])
def test_parse_patch_rejects_external_paths(tmp_path: Path, path: str) -> None:
    # Given: a patch header targeting a path outside the workspace
    raw = f"--- /dev/null\n+++ {path}\n@@ -0,0 +1,1 @@\n+blocked\n"

    # When / Then: workspace containment rejects it during parsing
    with pytest.raises(PatchError, match="path rejected"):
        parse_patch(raw, Workspace(tmp_path))


@pytest.mark.parametrize("path", [".env", "keys/signing.pem", ".forge/state.json"])
def test_parse_patch_rejects_restricted_paths(tmp_path: Path, path: str) -> None:
    # Given: a proposal targeting secret-bearing or private Forge state
    raw = f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,1 @@\n+blocked\n"

    # When / Then: the shared workspace policy rejects the proposal
    with pytest.raises(PatchError, match="path rejected"):
        parse_patch(raw, Workspace(tmp_path))


def test_parse_patch_rejects_oversized_input(tmp_path: Path) -> None:
    # Given: untrusted patch text beyond the deterministic byte limit
    raw = "x" * (MAX_PATCH_BYTES + 1)

    # When / Then: size is rejected before structural parsing
    with pytest.raises(PatchError, match="size limit"):
        parse_patch(raw, Workspace(tmp_path))


def test_parse_patch_rejects_stale_context(tmp_path: Path) -> None:
    # Given: a proposal generated against content that is no longer current
    (tmp_path / "example.py").write_text("value = 2\nprint('changed')\n", encoding="utf-8")

    # When / Then: context validation detects the stale hunk
    with pytest.raises(PatchError, match="context mismatch"):
        parse_patch(modification_patch(), Workspace(tmp_path))


def test_parse_patch_supports_git_metadata_and_file_deletion(tmp_path: Path) -> None:
    # Given: a standard Git diff deleting a file without a trailing newline
    (tmp_path / "obsolete.txt").write_text("remove me", encoding="utf-8")
    raw = (
        "diff --git a/obsolete.txt b/obsolete.txt\n"
        "deleted file mode 100644\n"
        "index 1f2a3b4..0000000\n"
        "--- a/obsolete.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-remove me\n"
        "\\ No newline at end of file\n"
    )

    # When: the Git-produced proposal is parsed
    proposal = parse_patch(raw, Workspace(tmp_path))

    # Then: deletion intent is preserved without changing the file
    assert proposal.files[0].operation is PatchOperation.DELETE
    assert proposal.affected_files == ("obsolete.txt",)
    assert (tmp_path / "obsolete.txt").read_text(encoding="utf-8") == "remove me"


def test_parse_patch_supports_no_newline_markers_inside_hunk(tmp_path: Path) -> None:
    # Given: old and new lines both lack trailing newlines
    (tmp_path / "value.txt").write_text("old", encoding="utf-8")
    raw = (
        "--- a/value.txt\n"
        "+++ b/value.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "\\ No newline at end of file\n"
        "+new\n"
        "\\ No newline at end of file\n"
    )

    # When: the valid marker placement is parsed
    proposal = parse_patch(raw, Workspace(tmp_path))

    # Then: both changed lines are represented in one modification
    assert proposal.files[0].operation is PatchOperation.MODIFY
    assert proposal.additions == 1
    assert proposal.deletions == 1


def test_parse_patch_rejects_out_of_range_insertion(tmp_path: Path) -> None:
    # Given: a zero-length hunk positioned beyond the current file
    (tmp_path / "value.txt").write_text("one\n", encoding="utf-8")
    raw = "--- a/value.txt\n+++ b/value.txt\n@@ -99,0 +100,1 @@\n+impossible\n"

    # When / Then: context validation rejects the impossible position
    with pytest.raises(PatchError, match="context mismatch"):
        parse_patch(raw, Workspace(tmp_path))


def test_patch_preview_contains_exact_intended_modification(tmp_path: Path) -> None:
    # Given: a valid proposal against current workspace content
    current = "value = 1\nprint('old')\n"
    (tmp_path / "example.py").write_text(current, encoding="utf-8")
    proposal = parse_patch(modification_patch(), Workspace(tmp_path))

    # When: a human-readable preview is rendered
    preview = render_preview(proposal)

    # Then: its summary and diff expose the exact affected content
    assert "MODIFY example.py (+1 -1)" in preview
    assert "-print('old')" in preview
    assert "+print('new')" in preview
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == current


def test_propose_patch_tool_previews_without_writing(tmp_path: Path) -> None:
    # Given: the primary registry and a valid proposal
    current = "value = 1\nprint('old')\n"
    (tmp_path / "example.py").write_text(current, encoding="utf-8")
    registry = create_tool_registry(Workspace(tmp_path))

    # When: the model-facing proposal tool handles the patch
    preview = registry.execute("propose_patch", {"patch": modification_patch()})

    # Then: preview is returned but workspace state is untouched
    assert "MODIFY example.py" in preview
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == current
    assert registry.get("propose_patch").requires_approval is False


def test_propose_patch_tool_returns_structured_tool_error(tmp_path: Path) -> None:
    # Given: the primary registry and a malformed model proposal
    registry = create_tool_registry(Workspace(tmp_path))

    # When / Then: patch rejection crosses the tool boundary as a ToolError
    with pytest.raises(ToolError, match="Patch rejected"):
        registry.execute("propose_patch", {"patch": "invalid"})
