import subprocess
import sys
import tomllib
from io import BytesIO
from pathlib import Path
from urllib.error import URLError

import pytest

import forge.forge_core.updates as updates_module
from forge.forge_core.updates import (
    UpdateError,
    UpdateService,
    UpdateStatus,
    coordinate_update,
    fetch_latest_version,
    reinstall_version,
    update_command,
)
from forge.version import __version__


class UpdateRecorder:
    def __init__(self, latest: str) -> None:
        self.latest = latest
        self.approvals: list[str] = []
        self.installs: list[str] = []

    def fetch_latest(self) -> str:
        return self.latest

    def approve(self, latest: str) -> bool:
        self.approvals.append(latest)
        return True

    def deny(self, latest: str) -> bool:
        self.approvals.append(latest)
        return False

    def reinstall(self, latest: str) -> None:
        self.installs.append(latest)


def make_service(recorder: UpdateRecorder) -> UpdateService:
    return UpdateService("0.2.1", recorder.fetch_latest, recorder.reinstall)


def test_current_version_does_nothing_without_approval() -> None:
    # Given: the registry reports the installed release
    recorder = UpdateRecorder("0.2.1")

    # When: Forge coordinates an update check
    outcome = coordinate_update(make_service(recorder), recorder.approve)

    # Then: neither approval nor reinstallation is attempted
    assert outcome.status is UpdateStatus.CURRENT
    assert recorder.approvals == []
    assert recorder.installs == []


def test_outdated_version_requires_approval_before_reinstall() -> None:
    # Given: the registry reports a newer release
    recorder = UpdateRecorder("0.2.2")

    # When: the trusted interface denies the exact update
    outcome = coordinate_update(make_service(recorder), recorder.deny)

    # Then: Forge records denial without changing the installation
    assert outcome.status is UpdateStatus.DENIED
    assert recorder.approvals == ["0.2.2"]
    assert recorder.installs == []


def test_approved_outdated_version_reinstalls_latest_release() -> None:
    # Given: a newer release and trusted approval
    recorder = UpdateRecorder("0.2.2")

    # When: Forge coordinates the update
    outcome = coordinate_update(make_service(recorder), recorder.approve)

    # Then: the exact registry release is reinstalled once
    assert outcome.status is UpdateStatus.UPDATED
    assert recorder.approvals == ["0.2.2"]
    assert recorder.installs == ["0.2.2"]


def test_update_failure_is_reported_without_success_status() -> None:
    # Given: an approved update whose installer fails
    recorder = UpdateRecorder("0.2.2")

    def fail(_latest: str) -> None:
        raise UpdateError("installer failed")

    service = UpdateService("0.2.1", recorder.fetch_latest, fail)

    # When / Then: the failure propagates instead of becoming an updated outcome
    with pytest.raises(UpdateError, match="installer failed"):
        coordinate_update(service, recorder.approve)


def test_invalid_registry_version_is_rejected() -> None:
    # Given: malformed untrusted registry metadata
    def fetch() -> str:
        return "not-a-version"

    service = UpdateService("0.2.1", fetch, lambda _latest: None)

    # When / Then: Forge rejects it before requesting approval
    with pytest.raises(UpdateError, match="version"):
        coordinate_update(service, lambda _latest: True)


def test_fetch_latest_version_parses_official_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the official release source reports Forge's latest release
    payload = BytesIO(b'{"forge":{"latest":"0.2.2","releases":"..."}}')
    monkeypatch.setattr(updates_module, "urlopen", lambda *_args, **_kwargs: payload)

    # When: Forge checks its official release source
    latest = fetch_latest_version()

    # Then: the exact announced release is returned
    assert latest == "0.2.2"


def test_broken_manifest_json_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a release manifest with broken JSON
    payload = BytesIO(b"not json")
    monkeypatch.setattr(updates_module, "urlopen", lambda *_args, **_kwargs: payload)

    # When / Then: Forge rejects the payload before version comparison
    with pytest.raises(UpdateError, match="manifest"):
        fetch_latest_version()


def test_manifest_missing_forge_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a release manifest missing the forge top-level key
    payload = BytesIO(b'{"something":"else"}')
    monkeypatch.setattr(updates_module, "urlopen", lambda *_args, **_kwargs: payload)

    # When / Then: Forge rejects it
    with pytest.raises(UpdateError, match="manifest"):
        fetch_latest_version()


def test_manifest_network_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the official release source is unreachable
    def fail(*_args: object, **_kwargs: object) -> None:
        raise URLError("connection refused")

    monkeypatch.setattr(updates_module, "urlopen", fail)

    # When / Then: Forge reports the network error
    with pytest.raises(UpdateError, match="Could not reach"):
        fetch_latest_version()


def test_reinstall_uses_git_source_install_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an exact registry version approved for installation
    commands: list[tuple[str, ...]] = []

    def record(
        command: tuple[str, ...], **_options: bool | float
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", record)

    # When: the trusted installer boundary executes
    reinstall_version("0.2.4")

    # Then: it installs from the official GitHub repository at the tagged version
    assert commands == [
        (
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "git+https://github.com/Chenboda01/Forge-AI.git@v0.2.4",
        )
    ]


def test_update_command_always_uses_git_source() -> None:
    # Given / When: Forge selects the installer command for any version
    command = update_command("0.2.4")

    # Then: the command installs from the official Git source, never PyPI
    assert command == (
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "git+https://github.com/Chenboda01/Forge-AI.git@v0.2.4",
    )


def test_release_version_matches_project_metadata() -> None:
    # Given: runtime and package release metadata
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    # When / Then: every maintained version surface identifies this release
    assert __version__ == "0.2.4"
    assert project["project"]["version"] == __version__
