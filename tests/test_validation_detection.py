import json
from pathlib import Path

import pytest

from forge.forge_core.tools import create_tool_registry
from forge.forge_core.workspace import Workspace


def test_python_detection_prefers_targeted_test_and_configured_checks(tmp_path: Path) -> None:
    # Given: Python tool configuration and a changed module with a matching test
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
        "[tool.ruff]\n"
        "line-length = 100\n"
        "[tool.pyright]\n"
        'typeCheckingMode = "standard"\n',
        encoding="utf-8",
    )
    (tmp_path / "forge").mkdir()
    (tmp_path / "forge" / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_widget.py").write_text(
        "def test_widget(): pass\n", encoding="utf-8"
    )
    from forge.validation import detect_validation

    # When: Forge detects checks for the changed module
    commands = detect_validation(tmp_path, ("forge/widget.py",))

    # Then: the smallest test runs first, followed by configured project checks
    assert [command.arguments for command in commands] == [
        ("pytest", "tests/test_widget.py"),
        ("ruff", "check", "."),
        ("ruff", "format", "--check", "."),
        ("pyright",),
    ]
    assert commands[0].targeted is True


def test_node_detection_uses_only_configured_script_names(tmp_path: Path) -> None:
    # Given: package metadata with test and lint scripts containing untrusted shell text
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": "vitest run && unexpected-command",
                    "lint": "eslint .",
                    "release": "publish-everything",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    from forge.validation import detect_validation

    # When: Forge detects Node validation commands
    commands = detect_validation(tmp_path)

    # Then: it invokes configured script names without interpreting script bodies
    assert [command.arguments for command in commands] == [
        ("npm", "test"),
        ("npm", "run", "lint"),
    ]


def test_rust_detection_returns_standard_non_installing_checks(tmp_path: Path) -> None:
    # Given: a Rust package manifest
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "sample"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    from forge.validation import detect_validation

    # When: Forge detects Rust checks
    commands = detect_validation(tmp_path)

    # Then: it suggests the roadmap checks in deterministic order
    assert [command.arguments for command in commands] == [
        ("cargo", "test"),
        ("cargo", "clippy"),
        ("cargo", "fmt", "--check"),
    ]


def test_detection_rejects_malformed_project_metadata(tmp_path: Path) -> None:
    # Given: malformed package metadata at the configuration boundary
    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")
    from forge.validation import ValidationDetectionError, detect_validation

    # When / Then: Forge reports the exact source instead of guessing commands
    with pytest.raises(ValidationDetectionError, match="package.json"):
        detect_validation(tmp_path)


def test_detection_tool_displays_commands_without_approval_or_execution(tmp_path: Path) -> None:
    # Given: a configured Python project and its primary read-only tool registry
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )
    registry = create_tool_registry(Workspace(tmp_path))

    # When: the model asks Forge which validation commands are appropriate
    output = registry.execute("detect_validation", {"changed_files": []})

    # Then: exact argument arrays are visible and no approval or execution is implied
    assert '["pytest"]' in output
    assert registry.get("detect_validation").requires_approval is False
