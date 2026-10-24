from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _disable_herdr_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reporting into a developer's live Herdr pane."""
    for variable in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_BIN_PATH", "HERDR_SOCKET_PATH"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(autouse=True)
def _isolate_user_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep user preferences and provider configuration out of the real home."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
