from __future__ import annotations

import os
import stat
from contextlib import ExitStack, suppress
from pathlib import Path
from uuid import uuid4


class SafeReadError(Exception):
    def __init__(self, path: Path, missing: bool = False, too_large: bool = False) -> None:
        self.path = path
        self.missing = missing
        self.too_large = too_large
        super().__init__(path, missing, too_large)

    def __str__(self) -> str:
        return f"Path changed during access: {self.path}"


class SafeWriteError(OSError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(path)

    def __str__(self) -> str:
        return f"Path changed during access: {self.path}"


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW


def read_bytes_beneath(root: Path, path: Path, *, max_bytes: int | None = None) -> bytes:
    try:
        with ExitStack() as stack:
            directory, name = _open_parent(root, path, stack)
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise OSError
            with os.fdopen(descriptor, "rb") as stream:
                content = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
            if max_bytes is not None and len(content) > max_bytes:
                raise SafeReadError(path, too_large=True)
            return content
    except (OSError, ValueError) as error:
        raise SafeReadError(path, isinstance(error, FileNotFoundError)) from error


def is_regular_file_beneath(root: Path, path: Path) -> bool:
    try:
        with ExitStack() as stack:
            directory, name = _open_parent(root, path, stack)
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory)
            stack.callback(os.close, descriptor)
            return stat.S_ISREG(os.fstat(descriptor).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError) as error:
        raise SafeReadError(path) from error


def regular_file_mode_beneath(root: Path, path: Path) -> int:
    try:
        with ExitStack() as stack:
            directory, name = _open_parent(root, path, stack)
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory)
            stack.callback(os.close, descriptor)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError
            return stat.S_IMODE(metadata.st_mode)
    except (OSError, ValueError) as error:
        raise SafeReadError(path) from error


def ensure_directory_beneath(root: Path, path: Path, *, mode: int = 0o700) -> None:
    try:
        with ExitStack() as stack:
            relative = _relative_path(root, path)
            directory = _open_absolute_directory(root, stack)
            for part in relative.parts:
                with suppress(FileExistsError):
                    os.mkdir(part, mode=mode, dir_fd=directory)
                directory = _open_child_directory(directory, part, stack)
            os.fchmod(directory, mode)
    except (OSError, ValueError) as error:
        raise SafeWriteError(path) from error


def atomic_write_text_beneath(
    root: Path,
    path: Path,
    content: str,
    *,
    mode: int = 0o600,
    create_parents: bool = False,
) -> None:
    temporary_name = f".{path.name}.{uuid4().hex}.tmp"
    directory: int | None = None
    try:
        with ExitStack() as stack:
            directory, name = _open_parent(
                root,
                path,
                stack,
                create=create_parents,
            )
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                mode,
                dir_fd=directory,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
    except (OSError, ValueError) as error:
        if directory is not None:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=directory)
        raise SafeWriteError(path) from error


def replace_file_beneath(
    source_root: Path,
    source: Path,
    target_root: Path,
    target: Path,
) -> None:
    try:
        with ExitStack() as stack:
            source_directory, source_name = _open_parent(source_root, source, stack)
            target_directory, target_name = _open_parent(
                target_root,
                target,
                stack,
                create=True,
            )
            metadata = os.stat(source_name, dir_fd=source_directory, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError
            os.replace(
                source_name,
                target_name,
                src_dir_fd=source_directory,
                dst_dir_fd=target_directory,
            )
            os.fsync(target_directory)
    except (OSError, ValueError) as error:
        raise SafeWriteError(target) from error


def link_file_beneath(
    source_root: Path,
    source: Path,
    target_root: Path,
    target: Path,
) -> None:
    try:
        with ExitStack() as stack:
            source_directory, source_name = _open_parent(source_root, source, stack)
            target_directory, target_name = _open_parent(
                target_root,
                target,
                stack,
                create=True,
            )
            metadata = os.stat(source_name, dir_fd=source_directory, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError
            os.link(
                source_name,
                target_name,
                src_dir_fd=source_directory,
                dst_dir_fd=target_directory,
                follow_symlinks=False,
            )
            os.fsync(target_directory)
    except (OSError, ValueError) as error:
        raise SafeWriteError(target) from error


def unlink_file_beneath(root: Path, path: Path) -> None:
    try:
        with ExitStack() as stack:
            directory, name = _open_parent(root, path, stack)
            metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                raise OSError
            os.unlink(name, dir_fd=directory)
            os.fsync(directory)
    except (OSError, ValueError) as error:
        raise SafeWriteError(path) from error


def open_file_beneath(root: Path, path: Path, flags: int, mode: int = 0o600) -> int:
    try:
        with ExitStack() as stack:
            directory, name = _open_parent(root, path, stack)
            return os.open(name, flags | os.O_CLOEXEC | os.O_NOFOLLOW, mode, dir_fd=directory)
    except (OSError, ValueError) as error:
        raise SafeWriteError(path) from error


def open_read_file_beneath(root: Path, path: Path) -> int:
    try:
        with ExitStack() as stack:
            directory, name = _open_parent(root, path, stack)
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise OSError
            return descriptor
    except (OSError, ValueError) as error:
        raise SafeReadError(path, isinstance(error, FileNotFoundError)) from error


def _open_parent(
    root: Path,
    path: Path,
    stack: ExitStack,
    *,
    create: bool = False,
) -> tuple[int, str]:
    relative = _relative_path(root, path)
    directory = _open_absolute_directory(root, stack)
    for part in relative.parts[:-1]:
        if create:
            with suppress(FileExistsError):
                os.mkdir(part, mode=0o700, dir_fd=directory)
        directory = _open_child_directory(directory, part, stack)
    return directory, relative.name


def _open_absolute_directory(path: Path, stack: ExitStack) -> int:
    absolute = path.absolute()
    if not absolute.is_absolute() or ".." in absolute.parts:
        raise ValueError
    directory = os.open(absolute.anchor, _DIRECTORY_FLAGS)
    stack.callback(os.close, directory)
    for part in absolute.parts[1:]:
        directory = _open_child_directory(directory, part, stack)
    return directory


def _open_child_directory(directory: int, name: str, stack: ExitStack) -> int:
    child = os.open(name, _DIRECTORY_FLAGS, dir_fd=directory)
    stack.callback(os.close, child)
    return child


def _relative_path(root: Path, path: Path) -> Path:
    relative = path.absolute().relative_to(root.absolute())
    if not relative.parts or ".." in relative.parts:
        raise ValueError
    return relative
