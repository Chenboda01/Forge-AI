from __future__ import annotations

import json
import tomllib
from datetime import date, datetime, time
from pathlib import Path
from typing import Final, assert_never

from .safe_io import SafeReadError, is_regular_file_beneath, read_bytes_beneath

MAX_METADATA_BYTES: Final = 1_000_000
INSTRUCTION_FILENAMES: Final = ("FORGE.md",)
DISCOVERY_FILENAMES: Final = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "pytest.ini",
    "tox.ini",
    "noxfile.py",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "Cargo.toml",
    "Cargo.lock",
    "rustfmt.toml",
    "go.mod",
    "go.sum",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "Makefile",
    "Dockerfile",
    "FORGE.md",
)
PYTHON_MARKERS: Final = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "requirements-dev.txt",
        "pytest.ini",
        "tox.ini",
        "noxfile.py",
    }
)
NODE_MARKERS: Final = frozenset({"package.json"})
RUST_MARKERS: Final = frozenset({"Cargo.toml"})
GO_MARKERS: Final = frozenset({"go.mod"})
JAVA_MARKERS: Final = frozenset(
    {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
)

type MetadataValue = (
    None
    | bool
    | int
    | float
    | str
    | date
    | datetime
    | time
    | list[MetadataValue]
    | dict[str, MetadataValue]
)


def _discoverable_files(root: Path) -> frozenset[str]:
    files: set[str] = set()
    for name in DISCOVERY_FILENAMES:
        try:
            if is_regular_file_beneath(root, root / name):
                files.add(name)
        except SafeReadError:
            continue
    return frozenset(files)


def _metadata_tokens(root: Path, present: frozenset[str]) -> frozenset[str]:
    tokens: set[str] = set()
    for filename in ("pyproject.toml", "package.json"):
        if filename not in present:
            continue
        content = _read_metadata(root / filename)
        if content is None:
            continue
        parsed = _parse_metadata(filename, content)
        if parsed is not None:
            tokens.update(_value_tokens(parsed))
    for filename in present:
        if filename in {"pom.xml", "build.gradle", "build.gradle.kts"}:
            content = _read_metadata(root / filename)
            if content is not None:
                tokens.update(content.casefold().split())
    return frozenset(tokens)


def _parse_metadata(filename: str, content: str) -> MetadataValue | None:
    try:
        if filename == "pyproject.toml":
            return tomllib.loads(content)
        return json.loads(content)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError):
        return None


def _value_tokens(value: MetadataValue) -> frozenset[str]:
    match value:
        case None | bool() | int() | float() | date() | datetime() | time():
            return frozenset()
        case str():
            return frozenset({value.casefold()})
        case list() as values:
            return frozenset(token for item in values for token in _value_tokens(item))
        case dict() as values:
            return frozenset(key.casefold() for key in values) | frozenset(
                token for item in values.values() for token in _value_tokens(item)
            )
        case unreachable:
            assert_never(unreachable)


def _project_types(present: frozenset[str]) -> tuple[str, ...]:
    markers = (
        ("python", PYTHON_MARKERS),
        ("node", NODE_MARKERS),
        ("rust", RUST_MARKERS),
        ("go", GO_MARKERS),
        ("java", JAVA_MARKERS),
    )
    return tuple(name for name, candidates in markers if present & candidates)


def _test_frameworks(present: frozenset[str], tokens: frozenset[str]) -> tuple[str, ...]:
    frameworks: list[str] = []
    if {"pytest.ini", "tox.ini", "noxfile.py"} & present or _has(tokens, "pytest"):
        frameworks.append("pytest")
    if _has(tokens, "unittest"):
        frameworks.append("unittest")
    for name in ("jest", "vitest", "mocha", "ava", "tap", "playwright", "cypress"):
        if _has(tokens, name):
            frameworks.append(name)
    if "Cargo.toml" in present:
        frameworks.append("cargo test")
    if "go.mod" in present:
        frameworks.append("go test")
    if JAVA_MARKERS & present:
        for name in ("junit", "testng"):
            if _has(tokens, name):
                frameworks.append(name)
    return tuple(frameworks)


def _formatters(present: frozenset[str], tokens: frozenset[str]) -> tuple[str, ...]:
    formatters: list[str] = []
    for name in ("ruff", "black", "yapf", "autopep8", "isort"):
        if _has(tokens, name):
            formatters.append(name)
    for name in ("prettier", "biome"):
        if _has(tokens, name):
            formatters.append(name)
    if "Cargo.toml" in present or "rustfmt.toml" in present:
        formatters.append("rustfmt")
    if "go.mod" in present:
        formatters.append("gofmt")
    for name in ("google-java-format", "spotless", "checkstyle"):
        if _has(tokens, name):
            formatters.append(name)
    return tuple(formatters)


def _type_checkers(present: frozenset[str], tokens: frozenset[str]) -> tuple[str, ...]:
    checkers: list[str] = []
    if _has(tokens, "basedpyright"):
        checkers.append("basedpyright")
    elif _has(tokens, "pyright"):
        checkers.append("pyright")
    if _has(tokens, "mypy"):
        checkers.append("mypy")
    if _has(tokens, "typescript") or _has(tokens, "tsc"):
        checkers.append("typescript")
    if _has(tokens, "flow"):
        checkers.append("flow")
    if "Cargo.toml" in present:
        checkers.append("rustc")
    if "go.mod" in present:
        checkers.append("go vet")
    if JAVA_MARKERS & present:
        checkers.append("javac")
    return tuple(checkers)


def _has(tokens: frozenset[str], value: str) -> bool:
    separators = "-_.:/@<>=!~[],"
    translation = str.maketrans(separators, "-" * len(separators))
    normalized_value = value.casefold()
    return any(
        f"-{normalized_value}-" in f"-{token.casefold().translate(translation)}-"
        for token in tokens
    )


def _read_metadata(path: Path) -> str | None:
    try:
        content = read_bytes_beneath(path.parent, path, max_bytes=MAX_METADATA_BYTES)
    except (SafeReadError, UnicodeError):
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None
