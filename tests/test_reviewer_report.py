import json

import pytest

from forge.forge_core.reviewer_report import (
    ReviewerReport,
    ReviewerReportError,
    ReviewerVerdict,
    parse_reviewer_report,
    render_reviewer_report,
)


def valid_payload(**overrides: object) -> str:
    payload: dict[str, object] = {
        "critical_issues": [],
        "warnings": [],
        "suggestions": [],
        "missing_tests": [],
        "verdict": "approve",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_parse_reviewer_report_returns_typed_sections() -> None:
    # Given: a complete reviewer report with padded findings
    content = valid_payload(
        critical_issues=[" forge/a.py: drops the workspace check "],
        warnings=["forge/b.py: swallows the error"],
        suggestions=["forge/c.py: split the parser"],
        missing_tests=["reject a path outside the workspace"],
        verdict="request_changes",
    )

    # When: the runtime parses the reviewer message
    report = parse_reviewer_report(content)

    # Then: every section and verdict is typed and trimmed
    assert report == ReviewerReport(
        critical_issues=("forge/a.py: drops the workspace check",),
        warnings=("forge/b.py: swallows the error",),
        suggestions=("forge/c.py: split the parser",),
        missing_tests=("reject a path outside the workspace",),
        verdict=ReviewerVerdict.REQUEST_CHANGES,
    )


def test_parse_reviewer_report_accepts_a_json_fence() -> None:
    # Given: a provider that wrapped the report in a Markdown fence
    content = f"```json\n{valid_payload(verdict='approve')}\n```"

    # When / Then: the fenced object is still validated
    assert parse_reviewer_report(content).verdict is ReviewerVerdict.APPROVE


def test_parse_reviewer_report_rejects_malformed_json_without_echoing_content() -> None:
    # Given: invalid JSON containing a credential-shaped value
    secret = "sk-proj-syntheticcredential1234567890"
    content = '{"verdict": "approve", "warnings": ["' + secret + '"]'

    # When / Then: the failure is reported without repeating the content
    with pytest.raises(ReviewerReportError, match="not valid JSON") as captured:
        parse_reviewer_report(content)
    assert secret not in str(captured.value)


def test_parse_reviewer_report_rejects_missing_sections() -> None:
    # Given: a report without the missing-tests section
    payload = json.loads(valid_payload())
    del payload["missing_tests"]

    # When / Then: the report is rejected and the missing field is named
    with pytest.raises(ReviewerReportError, match="missing_tests"):
        parse_reviewer_report(json.dumps(payload))


def test_parse_reviewer_report_rejects_unknown_fields() -> None:
    # Given: a report carrying a field outside the fixed schema
    content = valid_payload(severity="critical")

    # When / Then: additional fields are rejected instead of ignored
    with pytest.raises(ReviewerReportError, match="unknown fields"):
        parse_reviewer_report(content)


def test_parse_reviewer_report_rejects_non_object_json() -> None:
    # Given: a JSON array instead of the required object
    # When / Then: the shape is rejected
    with pytest.raises(ReviewerReportError, match="JSON object"):
        parse_reviewer_report("[]")


@pytest.mark.parametrize("verdict", ["maybe", "", 1, None])
def test_parse_reviewer_report_rejects_invalid_verdict(verdict: object) -> None:
    # Given: a verdict outside the two allowed values
    content = valid_payload(verdict=verdict)

    # When / Then: the verdict is rejected
    with pytest.raises(ReviewerReportError, match="approve"):
        parse_reviewer_report(content)


def test_parse_reviewer_report_rejects_non_array_findings() -> None:
    # Given: a findings section that is not a list
    content = valid_payload(warnings="forge/a.py: issue")

    # When / Then: the section is rejected
    with pytest.raises(ReviewerReportError, match="'warnings' must be an array"):
        parse_reviewer_report(content)


@pytest.mark.parametrize("item", ["  ", 7, None])
def test_parse_reviewer_report_rejects_invalid_findings(item: object) -> None:
    # Given: a findings section containing an empty or non-string entry
    content = valid_payload(critical_issues=[item])

    # When / Then: the entry is rejected
    with pytest.raises(ReviewerReportError, match="field 'critical_issues'"):
        parse_reviewer_report(content)


def test_parse_reviewer_report_rejects_unclosed_fence() -> None:
    # Given: a fenced message without a closing fence
    content = "```json\n{}"

    # When / Then: the fence is rejected
    with pytest.raises(ReviewerReportError, match="not closed"):
        parse_reviewer_report(content)


def test_render_reviewer_report_lists_every_required_section() -> None:
    # Given: a validated report with some empty sections
    report = ReviewerReport(
        critical_issues=("forge/a.py: missing check",),
        warnings=(),
        suggestions=("forge/b.py: rename",),
        missing_tests=(),
        verdict=ReviewerVerdict.REQUEST_CHANGES,
    )

    # When: Forge renders the validated report for the conversation
    rendered = render_reviewer_report(report)

    # Then: the fixed section order is preserved and empty sections are explicit
    assert rendered == (
        "Critical issues\n- forge/a.py: missing check\n\n"
        "Warnings\n- None recorded\n\n"
        "Suggestions\n- forge/b.py: rename\n\n"
        "Missing tests\n- None recorded\n\n"
        "Verdict\n- request_changes"
    )
