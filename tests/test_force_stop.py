from pathlib import Path
from threading import Event

import pytest
from textual.widgets import Static, TextArea

from forge.forge import build_runtime
from forge.forge_core.workspace import Workspace
from forge.patches import parse_patch
from forge.ui.app import ForgeApp
from forge.ui.force_stop import (
    CHOICE_ALL,
    CHOICE_CURRENT,
    CHOICE_KEEP,
    ForceStopScreen,
    checkpoint_baseline,
    revert_force_stop,
    turn_checkpoint_ids,
)
from forge.ui.widgets import ConversationView


def _create_checkpoint(
    runtime,
    root: Path,
    path: str,
    before: str,
    after: str,
):
    (root / path).write_text(f"{before}\n", encoding="utf-8")
    raw = f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{before}\n+{after}\n"
    proposal = parse_patch(raw, Workspace(root))
    record = runtime.checkpoints.create(proposal, task_id="task-1", patch_id=f"patch-{path}")
    (root / path).write_text(f"{after}\n", encoding="utf-8")
    return record


def _text(app: ForgeApp) -> str:
    return app.query_one("#conversation", ConversationView).transcript


def test_checkpoint_baseline_marks_existing_work_before_the_task(tmp_path: Path) -> None:
    # Given: a checkpoint created before the current task starts
    runtime = build_runtime(tmp_path)
    earlier = _create_checkpoint(runtime, tmp_path, "earlier.md", "old", "edited")

    # When: Forge captures the task baseline and a new edit is checkpointed
    baseline = checkpoint_baseline(runtime)
    assert baseline is not None
    current = _create_checkpoint(runtime, tmp_path, "current.md", "before", "after")

    # Then: only the new edit belongs to the task
    assert baseline == frozenset({earlier.id})
    assert turn_checkpoint_ids(runtime, baseline) == (current.id,)


def test_revert_current_restores_only_the_newest_edit(tmp_path: Path) -> None:
    # Given: earlier work that predates this task and one edit in progress
    runtime = build_runtime(tmp_path)
    _create_checkpoint(runtime, tmp_path, "earlier.md", "earlier before", "earlier after")
    baseline = checkpoint_baseline(runtime)
    assert baseline is not None
    current = _create_checkpoint(runtime, tmp_path, "current.md", "current before", "current after")

    # When: the user force-stops and reverts the current edit
    message = revert_force_stop(runtime, turn_checkpoint_ids(runtime, baseline), CHOICE_CURRENT)

    # Then: only the current file returns to its pre-edit content
    assert (tmp_path / "current.md").read_text(encoding="utf-8") == "current before\n"
    assert (tmp_path / "earlier.md").read_text(encoding="utf-8") == "earlier after\n"
    assert current.id in message
    assert "Earlier changes were kept" in message


def test_revert_all_restores_every_edit_from_the_task(tmp_path: Path) -> None:
    # Given: two edits applied during the same task
    runtime = build_runtime(tmp_path)
    baseline = checkpoint_baseline(runtime)
    assert baseline is not None
    _create_checkpoint(runtime, tmp_path, "first.md", "first before", "first after")
    _create_checkpoint(runtime, tmp_path, "second.md", "second before", "second after")

    # When: the user force-stops and reverts every change
    message = revert_force_stop(runtime, turn_checkpoint_ids(runtime, baseline), CHOICE_ALL)

    # Then: both files return to the content captured before their edits
    assert (tmp_path / "first.md").read_text(encoding="utf-8") == "first before\n"
    assert (tmp_path / "second.md").read_text(encoding="utf-8") == "second before\n"
    assert "2 edit(s)" in message


def test_revert_reports_when_the_task_made_no_edits(tmp_path: Path) -> None:
    # Given: a checkpoint that predates the task and no new edits
    runtime = build_runtime(tmp_path)
    _create_checkpoint(runtime, tmp_path, "old.md", "old before", "old after")

    # When: the user asks to revert the current edit
    message = revert_force_stop(runtime, (), CHOICE_CURRENT)

    # Then: nothing is touched and the empty scope is reported
    assert "nothing to revert" in message
    assert (tmp_path / "old.md").read_text(encoding="utf-8") == "old after\n"


def test_keep_choice_leaves_every_file_untouched(tmp_path: Path) -> None:
    # Given: a task edit already applied to the workspace
    runtime = build_runtime(tmp_path)
    _create_checkpoint(runtime, tmp_path, "kept.md", "kept before", "kept after")

    # When: the user force-stops but keeps the changes
    message = revert_force_stop(runtime, (), CHOICE_KEEP)

    # Then: the edit stays exactly as applied
    assert "changes kept" in message
    assert (tmp_path / "kept.md").read_text(encoding="utf-8") == "kept after\n"


def test_revert_without_checkpoint_storage_is_reported_safely() -> None:
    # Given: no runtime or checkpoint baseline is available
    assert checkpoint_baseline(None) is None

    # When: a revert is requested anyway
    message = revert_force_stop(None, None, CHOICE_CURRENT)

    # Then: Forge refuses instead of guessing
    assert "checkpoint storage is unavailable" in message


@pytest.mark.asyncio
async def test_force_stop_screen_navigates_three_answers_with_arrows() -> None:
    # Given: the force-stop dialog opened on its safest answer
    app = ForgeApp(skip_startup=True)
    async with app.run_test(size=(100, 32)) as pilot:
        await app.push_screen(ForceStopScreen())
        await pilot.pause()
        question = app.screen.query_one("#force-question", Static)

        # When: the user moves across the row with the arrow keys
        assert app.screen.focused is not None
        assert app.screen.focused.id == "force-keep"
        assert "keep" in str(question.content)
        await pilot.press("right")

        # Then: the highlighted answer and its explanation advance together
        assert app.screen.focused.id == "force-current"
        assert "edit in progress" in str(question.content)
        await pilot.press("right")
        assert app.screen.focused.id == "force-all"
        assert "every change" in str(question.content)

        # When: navigation wraps past either end
        await pilot.press("right")
        assert app.screen.focused.id == "force-keep"
        await pilot.press("left")

        # Then: the row wraps back to the final answer
        assert app.screen.focused.id == "force-all"


@pytest.mark.asyncio
async def test_force_stop_screen_enter_returns_the_focused_answer() -> None:
    # Given: an open force-stop dialog
    app = ForgeApp(skip_startup=True)
    results: list[str | None] = []
    async with app.run_test(size=(100, 32)) as pilot:
        await app.push_screen(ForceStopScreen(), callback=results.append)
        await pilot.pause()

        # When: the user selects the second answer
        await pilot.press("right", "enter")
        await pilot.pause()

        # Then: the choice is returned to the caller
        assert results == ["current"]


@pytest.mark.asyncio
async def test_force_stop_screen_escape_cancels_without_a_choice() -> None:
    # Given: an open force-stop dialog
    app = ForgeApp(skip_startup=True)
    results: list[str | None] = []
    async with app.run_test(size=(100, 32)) as pilot:
        await app.push_screen(ForceStopScreen(), callback=results.append)
        await pilot.pause()

        # When: the user cancels the dialog
        await pilot.press("escape")
        await pilot.pause()

        # Then: no revert choice is returned
        assert results == [None]


@pytest.mark.asyncio
async def test_force_stop_while_idle_reports_without_a_dialog() -> None:
    # Given: an idle Forge application
    app = ForgeApp(skip_startup=True)
    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user requests a force stop anyway
        composer.text = "/force-stop"
        await pilot.press("enter")
        await pilot.pause()

        # Then: Forge explains that no work is running
        assert "Forge is not working." in _text(app)
        assert app.screen is app.screen_stack[0]


@pytest.mark.asyncio
async def test_force_stop_reverts_current_edit_and_keeps_earlier_work(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: earlier work and a task that is editing a file right now
    runtime = build_runtime(tmp_path)
    release = Event()
    _create_checkpoint(runtime, tmp_path, "earlier.md", "earlier before", "earlier after")

    def fake_run(message: str) -> None:
        _create_checkpoint(runtime, tmp_path, "current.md", "current before", "current after")
        release.wait(timeout=5)

    monkeypatch.setattr(runtime.agent, "run", fake_run)
    monkeypatch.setattr(runtime.agent, "cancel", release.set)
    app = ForgeApp(runtime, skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "edit the docs"
        await pilot.press("enter")
        for _ in range(100):
            await pilot.pause()
            if (tmp_path / "current.md").read_text(encoding="utf-8") == "current after\n":
                break
        assert app._busy

        # When: the user force-stops and reverts only the edit in progress
        composer.text = "/force-stop"
        await pilot.press("enter")
        for _ in range(100):
            await pilot.pause()
            if isinstance(app.screen, ForceStopScreen):
                break
        assert isinstance(app.screen, ForceStopScreen)
        assert composer.disabled
        await pilot.press("right", "enter")
        for _ in range(100):
            await pilot.pause()
            if "Earlier changes were kept" in _text(app):
                break

        # Then: the current file is restored while earlier work is preserved
        assert "reverted the current edit" in _text(app)
        assert (tmp_path / "current.md").read_text(encoding="utf-8") == "current before\n"
        assert (tmp_path / "earlier.md").read_text(encoding="utf-8") == "earlier after\n"
        assert not app._busy
        assert not composer.disabled
