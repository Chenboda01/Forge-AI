from __future__ import annotations

import json
import tomllib
from datetime import date, datetime, time
from pathlib import Path, PurePosixPath
from typing import assert_never

from forge.forge_core.safe_io import SafeReadError, is_regular_file_beneath, read_bytes_beneath

from .models import ValidationCommand, ValidationDetectionError, ValidationKind

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type TomlValue = (
    str | int | float | bool | date | datetime | time | list[TomlValue] | dict[str, TomlValue]
)
MAX_VALIDATION_CONFIG_BYTES = 1_000_000


def detect_validation(
    root: Path,
    changed_files: tuple[str, ...] = (),
) -> tuple[ValidationCommand, ...]:
    project_root = root.resolve()
    commands: list[ValidationCommand] = []
    pyproject = project_root / "pyproject.toml"
    if _is_project_file(project_root, pyproject):
        commands.extend(_python_commands(project_root, pyproject, changed_files))
    package = project_root / "package.json"
    if _is_project_file(project_root, package):
        commands.extend(_node_commands(project_root, package))
    cargo = project_root / "Cargo.toml"
    if _is_project_file(project_root, cargo):
        _load_toml(project_root, cargo)
        commands.extend(
            (
                ValidationCommand(("cargo", "test"), ValidationKind.TEST, cargo.name),
                ValidationCommand(("cargo", "clippy"), ValidationKind.LINT, cargo.name),
                ValidationCommand(("cargo", "fmt", "--check"), ValidationKind.FORMAT, cargo.name),
            )
        )
    return tuple(commands)


def render_validation(commands: tuple[ValidationCommand, ...]) -> str:
    if not commands:
        return "Validation commands\nNo configured checks detected."
    lines = ["Validation commands"]
    for command in commands:
        arguments = json.dumps(list(command.arguments))
        scope = "targeted" if command.targeted else "project"
        lines.append(f"{arguments}  [{command.kind.value}; {scope}; {command.source}]")
    return "\n".join(lines)


def _python_commands(
    root: Path,
    pyproject: Path,
    changed_files: tuple[str, ...],
) -> tuple[ValidationCommand, ...]:
    config = _load_toml(root, pyproject)
    tools = _toml_table(config.get("tool"), pyproject.name, "tool")

    commands: list[ValidationCommand] = []
    if "pytest" in tools:
        target = _targeted_python_test(root, changed_files)
        arguments = ("pytest", target) if target is not None else ("pytest",)
        commands.append(
            ValidationCommand(
                arguments,
                ValidationKind.TEST,
                pyproject.name,
                targeted=target is not None,
            )
        )
    if "ruff" in tools:
        commands.extend(
            (
                ValidationCommand(("ruff", "check", "."), ValidationKind.LINT, pyproject.name),
                ValidationCommand(
                    ("ruff", "format", "--check", "."),
                    ValidationKind.FORMAT,
                    pyproject.name,
                ),
            )
        )
    if "pyright" in tools:
        commands.append(ValidationCommand(("pyright",), ValidationKind.TYPE_CHECK, pyproject.name))
    return tuple(commands)


def _targeted_python_test(root: Path, changed_files: tuple[str, ...]) -> str | None:
    for changed in sorted(changed_files):
        path = PurePosixPath(changed)
        if path.is_absolute() or ".." in path.parts:
            continue
        if path.parts and path.parts[0] == "tests" and path.suffix == ".py":
            candidate = root.joinpath(*path.parts)
            if candidate.is_file():
                return path.as_posix()
        if path.suffix != ".py":
            continue
        test_path = PurePosixPath("tests", f"test_{path.stem}.py")
        if root.joinpath(*test_path.parts).is_file():
            return test_path.as_posix()
    return None


def _node_commands(root: Path, package: Path) -> tuple[ValidationCommand, ...]:
    try:
        payload: JsonValue = json.loads(
            read_bytes_beneath(root, package, max_bytes=MAX_VALIDATION_CONFIG_BYTES).decode("utf-8")
        )
    except (SafeReadError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationDetectionError(package.name, str(error)) from error
    configured = _node_scripts(payload, package.name)

    manager = _node_manager(root)
    commands: list[ValidationCommand] = []
    for name, kind in (
        ("test", ValidationKind.TEST),
        ("lint", ValidationKind.LINT),
        ("typecheck", ValidationKind.TYPE_CHECK),
    ):
        if name not in configured:
            continue
        arguments = (
            (manager, "test")
            if manager == "npm" and name == "test"
            else (
                manager,
                "run",
                name,
            )
        )
        commands.append(ValidationCommand(arguments, kind, package.name))
    return tuple(commands)


def _node_manager(root: Path) -> str:
    if _is_optional_project_file(root, root / "bun.lock") or _is_optional_project_file(
        root, root / "bun.lockb"
    ):
        return "bun"
    if _is_optional_project_file(root, root / "pnpm-lock.yaml"):
        return "pnpm"
    if _is_optional_project_file(root, root / "yarn.lock"):
        return "yarn"
    return "npm"


def _node_scripts(payload: JsonValue, source: str) -> frozenset[str]:
    match payload:
        case dict() as package_data:
            return _script_names(package_data.get("scripts"), source)
        case None | bool() | int() | float() | str() | list():
            raise ValidationDetectionError(source, "top-level value must be an object")
        case unreachable:
            assert_never(unreachable)


def _script_names(value: JsonValue, source: str) -> frozenset[str]:
    match value:
        case None:
            return frozenset()
        case dict() as scripts:
            return frozenset(name for name, command in scripts.items() if isinstance(command, str))
        case bool() | int() | float() | str() | list():
            raise ValidationDetectionError(source, "scripts must be an object")
        case unreachable:
            assert_never(unreachable)


def _toml_table(value: TomlValue | None, source: str, name: str) -> dict[str, TomlValue]:
    match value:
        case None:
            return {}
        case dict() as table:
            return table
        case str() | int() | float() | bool() | date() | datetime() | time() | list():
            raise ValidationDetectionError(source, f"{name} must be a table")
        case unreachable:
            assert_never(unreachable)


def _load_toml(root: Path, path: Path) -> dict[str, TomlValue]:
    try:
        return tomllib.loads(
            read_bytes_beneath(root, path, max_bytes=MAX_VALIDATION_CONFIG_BYTES).decode("utf-8")
        )
    except (SafeReadError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValidationDetectionError(path.name, str(error)) from error


def _is_project_file(root: Path, path: Path) -> bool:
    try:
        return is_regular_file_beneath(root, path)
    except SafeReadError as error:
        raise ValidationDetectionError(path.name, str(error)) from error


def _is_optional_project_file(root: Path, path: Path) -> bool:
    try:
        return is_regular_file_beneath(root, path)
    except SafeReadError:
        return False
