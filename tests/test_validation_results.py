import json
from pathlib import Path

import pytest

from forge.validation import (
    CommandClassification,
    CommandExecutionResult,
    NetworkPolicy,
)


def execution(*, passed: bool, truncated: bool = False) -> CommandExecutionResult:
    return CommandExecutionResult(
        arguments=("pytest",),
        classification=CommandClassification.APPROVAL_REQUIRED,
        network_policy=NetworkPolicy.DENIED,
        exit_code=0 if passed else 1,
        output="tests passed" if passed else "tests failed",
        output_bytes=12,
        truncated=truncated,
        timed_out=False,
        passed=passed,
        duration_seconds=0.25,
    )


def test_store_persists_passed_execution_atomically(tmp_path: Path) -> None:
    # Given: completed validation evidence
    from forge.validation import ValidationResultStore, ValidationStatus

    store = ValidationResultStore(tmp_path)

    # When: Forge records the execution
    record = store.record_execution(execution(passed=True))

    # Then: exact evidence is durable and remains classified as passed
    assert record.status is ValidationStatus.PASSED
    payload = json.loads((store.root / f"{record.id}.json").read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["duration_seconds"] == 0.25
    assert not tuple(store.root.glob("*.tmp"))


def test_store_distinguishes_failed_incomplete_and_nonexecuted_states(tmp_path: Path) -> None:
    # Given: a validation evidence store
    from forge.validation import ValidationResultStore, ValidationStatus

    store = ValidationResultStore(tmp_path)

    # When: Forge records each materially different outcome
    failed = store.record_execution(execution(passed=False))
    incomplete = store.record_execution(execution(passed=True, truncated=True))
    not_run = store.record_not_run(("pytest",), "User declined approval.")
    unavailable = store.record_unavailable(("pytest",), "Executable missing.")

    # Then: no outcome is converted into passed evidence
    assert [failed.status, incomplete.status, not_run.status, unavailable.status] == [
        ValidationStatus.FAILED,
        ValidationStatus.INCOMPLETE,
        ValidationStatus.NOT_RUN,
        ValidationStatus.COULD_NOT_RUN,
    ]


def test_rendered_result_exposes_required_evidence(tmp_path: Path) -> None:
    # Given: persisted failed validation evidence
    from forge.validation import ValidationResultStore, render_validation_result

    record = ValidationResultStore(tmp_path).record_execution(execution(passed=False))

    # When: Forge renders the evidence for a report
    rendered = render_validation_result(record)

    # Then: command, status, exit, duration, output, and truncation are explicit
    assert "pytest" in rendered
    assert "Status: failed" in rendered
    assert "Exit code: 1" in rendered
    assert "Duration: 0.250s" in rendered
    assert "Truncated: no" in rendered
    assert "tests failed" in rendered


def test_validation_result_store_redacts_configured_secret_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: command output contains an arbitrary configured credential value
    from forge.forge_core.config import get_api_key
    from forge.validation import ValidationResultStore

    secret = "opaque-validation-secret-value"
    monkeypatch.setenv("TEST_API_KEY", secret)
    assert get_api_key("TEST_API_KEY") == secret
    store = ValidationResultStore(tmp_path)

    # When: validation evidence is persisted
    result = execution(passed=False)
    result = CommandExecutionResult(
        arguments=result.arguments,
        classification=result.classification,
        network_policy=result.network_policy,
        exit_code=result.exit_code,
        output=f"failure included {secret}",
        output_bytes=32,
        truncated=result.truncated,
        timed_out=result.timed_out,
        passed=result.passed,
        duration_seconds=result.duration_seconds,
    )
    record = store.record_execution(result)

    # Then: neither the typed record nor its file contains the credential
    persisted = (store.root / f"{record.id}.json").read_text(encoding="utf-8")
    assert secret not in record.output
    assert secret not in persisted


def test_validation_result_store_redacts_unavailable_detail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a command-boundary failure containing an arbitrary configured credential
    from forge.forge_core.config import get_api_key
    from forge.validation import ValidationResultStore

    secret = "opaque-unavailable-detail-secret"
    monkeypatch.setenv("TEST_API_KEY", secret)
    assert get_api_key("TEST_API_KEY") == secret
    store = ValidationResultStore(tmp_path)

    # When: Forge persists the unavailable validation result
    record = store.record_unavailable(("pytest",), f"runner rejected {secret}")

    # Then: neither the typed result nor durable evidence contains the credential
    persisted = (store.root / f"{record.id}.json").read_text(encoding="utf-8")
    assert secret not in record.detail
    assert secret not in persisted
