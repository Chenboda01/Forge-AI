from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError
from typing import Final
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from forge.version import __version__

RELEASE_SOURCE_URL: Final = "https://chenboda01.github.io/Forge-AI/releases.json"
UPDATE_TIMEOUT_SECONDS: Final = 120.0


class UpdateError(Exception):
    pass


class UpdateStatus(StrEnum):
    CURRENT = "current"
    DENIED = "denied"
    UPDATED = "updated"


@dataclass(frozen=True, slots=True)
class UpdateOutcome:
    status: UpdateStatus
    current: str
    latest: str


LatestVersionFetcher = Callable[[], str]
Reinstaller = Callable[[str], None]
Approval = Callable[[str], bool]


class UpdateService:
    def __init__(
        self,
        current_version: str = __version__,
        fetch_latest: LatestVersionFetcher | None = None,
        reinstall: Reinstaller | None = None,
    ) -> None:
        self._current_version = current_version
        self._fetch_latest = fetch_latest or fetch_latest_version
        self._reinstall = reinstall or reinstall_version

    def check(self) -> tuple[str, str]:
        try:
            current = str(Version(self._current_version))
            latest = str(Version(self._fetch_latest()))
        except InvalidVersion as error:
            raise UpdateError(
                f"The release registry returned an invalid version: {error}"
            ) from error
        return current, latest

    def reinstall(self, latest: str) -> None:
        self._reinstall(latest)


def fetch_latest_version() -> str:
    request = Request(RELEASE_SOURCE_URL, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=10.0) as response:  # noqa: S310 - fixed HTTPS URL
            payload = json.loads(response.read())
        latest = payload["forge"]["latest"]
    except (JSONDecodeError, KeyError, TypeError) as error:
        raise UpdateError(f"The release manifest is malformed: {error}") from error
    except (URLError, TimeoutError) as error:
        raise UpdateError(f"Could not reach the Forge release source: {error}") from error

    if not isinstance(latest, str):
        raise UpdateError("The Forge release source returned a non-text version.")
    return latest


def update_command(latest: str) -> tuple[str, ...]:
    if shutil.which("uv") is not None:
        return ("uv", "tool", "install", f"forge@{latest}", "--force")
    return (
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        f"forge=={latest}",
    )


def reinstall_version(latest: str) -> None:
    command = update_command(latest)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=UPDATE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise UpdateError("The selected Forge installer is no longer available.") from error
    except subprocess.TimeoutExpired as error:
        raise UpdateError("The Forge update timed out.") from error

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise UpdateError((detail or "uv could not install the Forge update.")[:2_000])


def coordinate_update(service: UpdateService, approve: Approval) -> UpdateOutcome:
    current, latest = service.check()
    if Version(latest) <= Version(current):
        return UpdateOutcome(UpdateStatus.CURRENT, current, latest)
    if not approve(latest):
        return UpdateOutcome(UpdateStatus.DENIED, current, latest)

    service.reinstall(latest)
    return UpdateOutcome(UpdateStatus.UPDATED, current, latest)
