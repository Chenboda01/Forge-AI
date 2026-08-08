from .models import FinalReportEvidence


def render_final_report(evidence: FinalReportEvidence) -> str:
    validation = (
        tuple(status.value for status in evidence.validation)
        if evidence.validation
        else ("Not run",)
    )
    undo = (
        (f"/undo {evidence.checkpoint_id}",)
        if evidence.checkpoint_id is not None
        else ("Unavailable",)
    )
    sections = (
        ("Summary", (evidence.summary,)),
        ("Files inspected", evidence.files_inspected or ("None recorded",)),
        ("Files changed", evidence.files_changed or ("None recorded",)),
        ("Patch status", (evidence.patch_status.value,)),
        ("Validation performed", validation),
        ("Known limitations", evidence.limitations or ("None recorded",)),
        ("Warnings", evidence.warnings or ("None recorded",)),
        ("Undo information", undo),
    )
    return "\n\n".join(
        f"{title}\n" + "\n".join(f"- {item}" for item in items) for title, items in sections
    )
