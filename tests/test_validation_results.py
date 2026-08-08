import json
from pathlib import Path

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
