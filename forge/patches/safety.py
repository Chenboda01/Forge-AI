import os
import shutil
import subprocess
from pathlib import Path
from typing import Final

from .models import PatchApplicationError, PatchOperation, PatchProposal

GIT_ENVIRONMENT: Final = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": os.defpath,
}


def reject_dirty_deletions(workspace_root: Path, proposal: PatchProposal) -> None:
    git = shutil.which("git", path=os.defpath)
    if git is None:
        raise PatchApplicationError(
            "Could not inspect destructive targets: trusted Git unavailable."
        )
    for file_patch in proposal.files:
        if file_patch.operation is not PatchOperation.DELETE:
            continue
        try:
            result = subprocess.run(
                (
                    git,
                    "--no-pager",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "core.fsmonitor=false",
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                    "--",
                    file_patch.path,
                ),
                cwd=workspace_root,
                capture_output=True,
                check=False,
                env=GIT_ENVIRONMENT,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PatchApplicationError(
                "Could not inspect destructive targets with trusted Git."
            ) from error
        if result.returncode == 128 and "not a git repository" in result.stderr:
            continue
        if result.returncode != 0:
            raise PatchApplicationError(
                f"Could not inspect destructive target with trusted Git: {file_patch.path}"
            )
        if result.stdout:
            raise PatchApplicationError(
                f"Refusing to delete file with uncommitted changes: {file_patch.path}"
            )
