import json
import subprocess
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


def test_runner_closes_captured_output_pipe(monkeypatch, tmp_path: Path) -> None:
    # Given: a permitted executable and an observable subprocess instance
    write_fake_pytest(tmp_path, "print('validated')\n")
    processes: list[subprocess.Popen[str]] = []
    real_popen = subprocess.Popen

    def record_process(*args, **kwargs) -> subprocess.Popen[str]:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr("forge.validation.execution.subprocess.Popen", record_process)
    from forge.validation import CommandRequest, RestrictedCommandRunner

    # When: Forge captures the command output
    RestrictedCommandRunner(tmp_path).run(CommandRequest(("pytest",)))

    # Then: ownership of the output pipe has been released
    assert processes[0].stdout is not None
    assert processes[0].stdout.closed is True


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


def test_runner_timeout_kills_descendants_holding_output_pipe(tmp_path: Path) -> None:
    # Given: a command exits after spawning a descendant that retains stdout
    write_fake_pytest(
        tmp_path,
        "import subprocess\n"
        "import sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
        "print('parent exited')\n",
    )
    from forge.validation import CommandRequest, RestrictedCommandRunner

    # When: the descendant keeps the capture pipe open beyond the timeout
    result = RestrictedCommandRunner(tmp_path).run(CommandRequest(("pytest",), timeout_seconds=0.1))

    # Then: Forge kills the process group and returns promptly
    assert result.timed_out is True
    assert result.passed is False
    assert result.duration_seconds < 2


def test_runner_rejects_state_parent_replacement_before_environment_setup(tmp_path: Path) -> None:
    # Given: initialized runtime state replaced with an external directory before execution
    from forge.validation import CommandExecutionError, RestrictedCommandRunner

    runner = RestrictedCommandRunner(tmp_path)
    state = tmp_path / ".forge"
    state.rename(tmp_path / ".forge-original")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-runtime"
    (outside / "runtime-home").mkdir(parents=True)
    state.symlink_to(outside, target_is_directory=True)

    # When / Then: environment setup fails closed without creating an external cache
    with pytest.raises(CommandExecutionError, match="state changed"):
        runner._environment()
    assert not (outside / "runtime-home" / "cache").exists()


def test_runner_does_not_resolve_executables_from_ambient_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an attacker-controlled executable appears first on ambient PATH
    attacker_bin = tmp_path / "attacker-bin"
    attacker_bin.mkdir()
    executable = attacker_bin / "forge-test-runner"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(attacker_bin))
    from forge.validation import CommandExecutionError, RestrictedCommandRunner

    # When / Then: executable resolution ignores ambient PATH and fails closed
    with pytest.raises(CommandExecutionError, match="trusted locations"):
        RestrictedCommandRunner(tmp_path)._resolve_executable("forge-test-runner")


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
