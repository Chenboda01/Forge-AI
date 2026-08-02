from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, assert_never

from forge.forge_core.updates import (
    UpdateError,
    UpdateOutcome,
    UpdateService,
    UpdateStatus,
    coordinate_update,
    update_command,
)

if TYPE_CHECKING:
    from forge.ui.app import ForgeApp


def start_update(app: ForgeApp) -> None:
    app._set_busy(True, "Checking for Forge updates...")
    app.run_worker(
        lambda: _run_update(app),
        thread=True,
        group="forge-update",
        exclusive=True,
    )


def _run_update(app: ForgeApp) -> None:
    try:
        outcome = coordinate_update(
            UpdateService(),
            lambda latest: app.request_approval("Forge update", _approval_details(latest)),
        )
    except UpdateError as error:
        app.call_from_thread(app._append_entry, "UPDATE ERROR", str(error), "error")
    else:
        app.call_from_thread(app._append_entry, "SYSTEM", _outcome_message(outcome), "notice")
    finally:
        app.call_from_thread(app._set_busy, False)


def _approval_details(latest: str) -> str:
    return (
        f"Install Forge {latest}?\n\n"
        f"Command: {shlex.join(update_command(latest))}\n\n"
        "Forge will continue running the current version until restarted."
    )


def _outcome_message(outcome: UpdateOutcome) -> str:
    match outcome.status:
        case UpdateStatus.CURRENT:
            return f"Forge {outcome.current} is already up to date."
        case UpdateStatus.DENIED:
            return "Forge update cancelled."
        case UpdateStatus.UPDATED:
            return (
                f"Forge {outcome.latest} was installed successfully. "
                "Restart Forge to use the new version."
            )
        case unreachable:
            assert_never(unreachable)
