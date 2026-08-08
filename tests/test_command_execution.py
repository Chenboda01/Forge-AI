import json
from pathlib import Path

import pytest

from forge.forge_core.tools import create_tool_registry
from forge.forge_core.workspace import Workspace


def write_fake_pytest(root: Path, body: str) -> None:
    executable = root / ".venv" / "bin" / "pytest"
    executable.parent.mkdir(parents=True)
    executable.write_text(f"#!/usr/bin/python3\n{body}", encoding="utf-8")
    executable.chmod(0o700)


def test_command_classification_accepts_only_contained_validation_shape(tmp_path: Path) -> None:
    # Given: an existing targeted test and the restricted command policy
    test_file = tmp_path / "tests" / "test_widget.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_widget(): pass\n", encoding="utf-8")
    from forge.validation import CommandClassification, CommandPolicyError, classify_command

    # When: Forge classifies an exact targeted pytest invocation
    classification = classify_command(("pytest", "tests/test_widget.py"), tmp_path)

    # Then: validation requires approval while wrappers and escapes remain blocked
    assert classification is CommandClassification.APPROVAL_REQUIRED
    with pytest.raises(CommandPolicyError, match="not permitted"):
        classify_command(("bash", "-c", "pytest"), tmp_path)
    with pytest.raises(CommandPolicyError, match="workspace"):
        classify_command(("pytest", "../outside.py"), tmp_path)


def test_runner_isolates_environment_and_blocks_network(monkeypatch, tmp_path: Path) -> None:
    # Given: a validation executable that inspects one secret and attempts network access
    write_fake_pytest(
        tmp_path,
        "import os\n"
        "import socket\n"
        "print('secret=' + os.environ.get('OPENAI_API_KEY', 'missing'))\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=0.2)\n"
        "except OSError:\n"
        "    print('network=blocked')\n"
        "else:\n"
        "    print('network=available')\n",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    from forge.validation import CommandRequest, NetworkPolicy, RestrictedCommandRunner

    # When: the approved command runs through the restricted process boundary
    result = RestrictedCommandRunner(tmp_path).run(CommandRequest(("pytest",)))

    # Then: secrets are absent, networking is unavailable, and policy is recorded
    assert "secret=missing" in result.output
    assert "network=blocked" in result.output
    assert "network=available" not in result.output
    assert result.network_policy is NetworkPolicy.DENIED
    assert result.exit_code == 0


def test_runner_bounds_output_and_reports_truncation(tmp_path: Path) -> None:
    # Given: a permitted executable that emits more bytes than the request allows
    write_fake_pytest(tmp_path, "print('x' * 200)\n")
    from forge.validation import CommandRequest, RestrictedCommandRunner

    # When: Forge captures the command with a small output limit
    result = RestrictedCommandRunner(tmp_path).run(
        CommandRequest(("pytest",), output_limit_bytes=32)
    )

    # Then: retained output is bounded and the original byte count remains visible
    assert len(result.output.encode("utf-8")) <= 32
    assert result.output_bytes > 32
    assert result.truncated is True


def test_runner_terminates_process_group_at_timeout(tmp_path: Path) -> None:
    # Given: a permitted executable that cannot finish within its time budget
    write_fake_pytest(tmp_path, "import time\ntime.sleep(5)\n")
    from forge.validation import CommandRequest, RestrictedCommandRunner

    # When: the command reaches its timeout
    result = RestrictedCommandRunner(tmp_path).run(CommandRequest(("pytest",), timeout_seconds=0.1))

    # Then: Forge kills the process group and reports that execution did not pass
    assert result.timed_out is True
    assert result.passed is False
    assert result.duration_seconds < 2


def test_run_command_tool_accepts_arrays_and_returns_policy_evidence(tmp_path: Path) -> None:
    # Given: an executable validation command and the primary tool registry
    write_fake_pytest(tmp_path, "print('validated')\n")
    registry = create_tool_registry(Workspace(tmp_path))

    # When: the approved handler receives an argument array
    output = registry.execute("run_command", {"arguments": ["pytest"]})
    result = json.loads(output)

    # Then: exact execution and restriction metadata are returned
    assert registry.get("run_command").requires_approval is True
    assert result["arguments"] == ["pytest"]
    assert result["exit_code"] == 0
    assert result["network_policy"] == "denied"
    assert result["truncated"] is False
