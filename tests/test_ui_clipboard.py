from types import SimpleNamespace

import forge.ui.clipboard as clipboard


def test_copy_to_clipboard_uses_the_first_successful_tool(monkeypatch) -> None:
    # Given: a clipboard tool that fails and a fallback tool that succeeds
    monkeypatch.setattr(clipboard, "_clipboard_commands", lambda: (("wl-copy",), ("xclip",)))
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/usr/bin/{name}")
    returncodes = iter((1, 0))
    inputs: list[str] = []

    def fake_run(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        inputs.append(str(kwargs["input"]))
        return SimpleNamespace(returncode=next(returncodes))

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    # When: text is copied
    result = clipboard.copy_to_clipboard("hello")

    # Then: the fallback tool receives the text and success is reported
    assert result is True
    assert inputs == ["hello", "hello"]


def test_copy_to_clipboard_reports_failure_when_every_tool_fails(monkeypatch) -> None:
    # Given: clipboard tools that all fail
    monkeypatch.setattr(
        clipboard,
        "_clipboard_commands",
        lambda: (("wl-copy",), ("xclip", "-selection", "clipboard")),
    )
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        clipboard.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    # When: text is copied
    result = clipboard.copy_to_clipboard("hello")

    # Then: an unsuccessful copy is reported
    assert result is False


def test_copy_to_clipboard_reports_failure_without_a_supported_tool(monkeypatch) -> None:
    # Given: no clipboard tool installed
    monkeypatch.setattr(clipboard, "_clipboard_commands", lambda: (("wl-copy",),))
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: None)

    # When: text is copied
    result = clipboard.copy_to_clipboard("hello")

    # Then: an unsuccessful copy is reported
    assert result is False
