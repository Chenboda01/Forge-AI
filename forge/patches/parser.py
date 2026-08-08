from __future__ import annotations

import re
from typing import Final, assert_never

from forge.forge_core.workspace import Workspace, WorkspaceError

from .models import (
    MAX_PATCH_BYTES,
    FilePatch,
    PatchError,
    PatchErrorCode,
    PatchHunk,
    PatchOperation,
    PatchProposal,
)

HUNK_HEADER: Final = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")
METADATA_PREFIXES: Final = (
    "diff --git ",
    "index ",
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
)


def parse_patch(raw_diff: str, workspace: Workspace) -> PatchProposal:
    encoded_size = len(raw_diff.encode("utf-8"))
    if encoded_size == 0:
        raise PatchError(PatchErrorCode.EMPTY, "patch text is empty")
    if encoded_size > MAX_PATCH_BYTES:
        raise PatchError(
            PatchErrorCode.TOO_LARGE,
            f"patch exceeds the {MAX_PATCH_BYTES}-byte size limit",
        )

    lines = raw_diff.splitlines()
    files: list[FilePatch] = []
    index = 0
    while index < len(lines):
        index = _skip_metadata(lines, index)
        if index >= len(lines):
            break
        if not lines[index].startswith("--- "):
            raise _malformed(f"expected old-file header at line {index + 1}")
        old_header = lines[index][4:]
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise _malformed(f"expected new-file header at line {index + 1}")
        new_header = lines[index][4:]
        index += 1

        hunks: list[PatchHunk] = []
        while index < len(lines) and lines[index].startswith("@@"):
            hunk, index = _parse_hunk(lines, index)
            hunks.append(hunk)
        if not hunks:
            raise _malformed("file patch contains no hunks")

        old_path = _parse_path(old_header, workspace)
        new_path = _parse_path(new_header, workspace)
        match (old_path, new_path):
            case (None, None):
                raise _malformed("both file headers use /dev/null")
            case (None, str() as created_path):
                file_patch = FilePatch(created_path, PatchOperation.CREATE, tuple(hunks))
            case (str() as deleted_path, None):
                file_patch = FilePatch(deleted_path, PatchOperation.DELETE, tuple(hunks))
            case (str() as previous_path, str() as current_path):
                if previous_path != current_path:
                    raise _malformed("renamed paths are not supported in this milestone")
                file_patch = FilePatch(current_path, PatchOperation.MODIFY, tuple(hunks))
            case unreachable:
                assert_never(unreachable)
        _validate_context(file_patch, workspace)
        files.append(file_patch)

    if not files:
        raise _malformed("patch contains no file changes")
    paths = [file.path for file in files]
    if len(paths) != len(set(paths)):
        raise _malformed("patch contains duplicate file sections")
    return PatchProposal(raw_diff=raw_diff, files=tuple(files))


def _skip_metadata(lines: list[str], index: int) -> int:
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith(METADATA_PREFIXES):
            index += 1
            continue
        break
    return index


def _parse_hunk(lines: list[str], index: int) -> tuple[PatchHunk, int]:
    header = HUNK_HEADER.fullmatch(lines[index])
    if header is None:
        raise _malformed(f"invalid hunk header at line {index + 1}")
    old_start, old_count, new_start, new_count = _hunk_coordinates(header)
    index += 1
    body: list[str] = []
    seen_old = 0
    seen_new = 0

    while index < len(lines) and (seen_old < old_count or seen_new < new_count):
        line = lines[index]
        if line == "\\ No newline at end of file":
            if not body or body[-1] == line:
                raise _malformed(f"orphaned no-newline marker at line {index + 1}")
            body.append(line)
            index += 1
            continue
        if not line or line[0] not in {" ", "+", "-"}:
            raise _malformed(f"invalid hunk line at line {index + 1}")
        body.append(line)
        if line[0] in {" ", "-"}:
            seen_old += 1
        if line[0] in {" ", "+"}:
            seen_new += 1
        if seen_old > old_count or seen_new > new_count:
            raise _malformed(f"hunk line counts exceed header at line {index + 1}")
        index += 1

    if seen_old != old_count or seen_new != new_count:
        raise _malformed("hunk line counts do not match header")
    if index < len(lines) and lines[index] == "\\ No newline at end of file":
        body.append(lines[index])
        index += 1
    return PatchHunk(old_start, old_count, new_start, new_count, tuple(body)), index


def _hunk_coordinates(header: re.Match[str]) -> tuple[int, int, int, int]:
    old_start = int(header.group(1))
    old_count = int(header.group(2)) if header.group(2) is not None else 1
    new_start = int(header.group(3))
    new_count = int(header.group(4)) if header.group(4) is not None else 1
    return old_start, old_count, new_start, new_count


def _parse_path(header: str, workspace: Workspace) -> str | None:
    value = header.split("\t", maxsplit=1)[0]
    if value == "/dev/null":
        return None
    if value.startswith(("a/", "b/")):
        value = value[2:]
    try:
        resolved = workspace.resolve(value)
    except WorkspaceError as error:
        raise PatchError(PatchErrorCode.PATH_REJECTED, str(error)) from error
    return resolved.relative_to(workspace.root).as_posix()


def _validate_context(file_patch: FilePatch, workspace: Workspace) -> None:
    path = workspace.resolve(file_patch.path)
    match file_patch.operation:
        case PatchOperation.CREATE:
            if path.exists():
                raise _context_mismatch(file_patch.path, "create target already exists")
            return
        case PatchOperation.MODIFY | PatchOperation.DELETE:
            pass
        case unreachable:
            assert_never(unreachable)
    if not path.is_file():
        raise _context_mismatch(file_patch.path, "target is not an existing file")
    try:
        current_lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise _context_mismatch(file_patch.path, "target is not UTF-8 text") from error

    previous_end = 0
    for hunk in file_patch.hunks:
        start = max(hunk.old_start - 1, 0)
        if start > len(current_lines):
            raise _context_mismatch(file_patch.path, "hunk starts beyond end of file")
        if start < previous_end:
            raise _context_mismatch(file_patch.path, "hunks overlap")
        expected = [line[1:] for line in hunk.lines if line.startswith((" ", "-"))]
        actual = current_lines[start : start + len(expected)]
        if actual != expected:
            raise _context_mismatch(file_patch.path, f"stale hunk at old line {hunk.old_start}")
        previous_end = start + hunk.old_count


def _malformed(detail: str) -> PatchError:
    return PatchError(PatchErrorCode.MALFORMED, detail)


def _context_mismatch(path: str, detail: str) -> PatchError:
    return PatchError(PatchErrorCode.CONTEXT_MISMATCH, f"{path}: {detail}")
