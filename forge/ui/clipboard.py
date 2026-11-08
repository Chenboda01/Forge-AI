from __future__ import annotations

import os
import shutil
import subprocess
import sys


def copy_to_clipboard(text: str) -> bool:
    for command in _clipboard_commands():
        if shutil.which(command[0]) is None:
            continue
        try:
            completed = subprocess.run(
                command,
                input=text,
                text=True,
                capture_output=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0:
            return True
    return False


def _clipboard_commands() -> tuple[tuple[str, ...], ...]:
    if sys.platform == "darwin":
        return (("pbcopy",),)
    if sys.platform.startswith("win"):
        return (("clip.exe",),)
    wayland = (("wl-copy",),)
    x11 = (
        ("xclip", "-selection", "clipboard"),
        ("xsel", "--clipboard", "--input"),
    )
    if os.environ.get("WAYLAND_DISPLAY"):
        return (*wayland, *x11)
    if os.environ.get("DISPLAY"):
        return (*x11, *wayland)
    return (*wayland, *x11)
