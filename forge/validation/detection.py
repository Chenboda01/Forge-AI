from __future__ import annotations

import json
import tomllib
from datetime import date, datetime, time
from pathlib import Path, PurePosixPath
from typing import assert_never

from .models import ValidationCommand, ValidationDetectionError, ValidationKind

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type TomlValue = (
    str | int | float | bool | date | datetime | time | list[TomlValue] | dict[str, TomlValue]
)


def detect_validation(
    root: Path,
    changed_files: tuple[str, ...] = (),
) -> tuple[ValidationCommand, ...]:
    project_root = root.resolve()
    commands: list[ValidationCommand] = []
    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file():
        commands.extend(_python_commands(project_root, pyproject, changed_files))
    package = project_root / "package.json"
    if package.is_file():
        commands.extend(_node_commands(project_root, package))
    cargo = project_root / "Cargo.toml"
    if cargo.is_file():
        _load_toml(cargo)
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
    config = _load_toml(pyproject)
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
        payload: JsonValue = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
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
    if (root / "bun.lock").is_file() or (root / "bun.lockb").is_file():
        return "bun"
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
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


def _load_toml(path: Path) -> dict[str, TomlValue]:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValidationDetectionError(path.name, str(error)) from error
