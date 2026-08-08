from forge.validation import ValidationStatus


def test_final_report_renders_only_recorded_evidence() -> None:
    from forge.reporting import FinalReportEvidence, PatchStatus, render_final_report

    evidence = FinalReportEvidence(
        summary="Applied the approved patch.",
        files_inspected=("forge/a.py",),
        files_changed=("forge/a.py",),
        patch_status=PatchStatus.APPLIED,
        validation=(ValidationStatus.PASSED,),
        limitations=("Legacy write_file is not recoverable.",),
        warnings=("Pre-existing changes were present.",),
        checkpoint_id="abc123def456",
    )

    report = render_final_report(evidence)

    for section in (
        "Summary",
        "Files inspected",
        "Files changed",
        "Patch status",
        "Validation performed",
        "Known limitations",
        "Warnings",
        "Undo information",
    ):
        assert section in report
    assert "abc123def456" in report
    assert "passed" in report


def test_final_report_never_converts_missing_validation_to_passed() -> None:
    from forge.reporting import FinalReportEvidence, PatchStatus, render_final_report

    evidence = FinalReportEvidence(
        summary="No change was applied.",
        files_inspected=(),
        files_changed=(),
        patch_status=PatchStatus.NOT_APPLIED,
        validation=(),
        limitations=(),
        warnings=(),
        checkpoint_id=None,
    )

    report = render_final_report(evidence)

    assert "Validation performed\n- Not run" in report
    assert "passed" not in report.lower()
