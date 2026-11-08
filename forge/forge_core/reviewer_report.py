"""Schema validation and deterministic rendering for reviewer subagent reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ReviewerReportError(ValueError):
    """Raised when reviewer output does not match the required report schema."""


class ReviewerVerdict(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"


@dataclass(frozen=True, slots=True)
class ReviewerReport:
    critical_issues: tuple[str, ...]
    warnings: tuple[str, ...]
    suggestions: tuple[str, ...]
    missing_tests: tuple[str, ...]
    verdict: ReviewerVerdict


_FINDING_FIELDS = ("critical_issues", "warnings", "suggestions", "missing_tests")
_REQUIRED_FIELDS = frozenset((*_FINDING_FIELDS, "verdict"))
_FENCE_LANGUAGES = frozenset({"", "json"})
_VERDICT_ERROR = "Reviewer report verdict must be 'approve' or 'request_changes'."


def parse_reviewer_report(content: str) -> ReviewerReport:
    """Parse one reviewer message into a validated report or raise."""
    body = _unwrap_fence(content)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise ReviewerReportError("Reviewer report is not valid JSON.") from None
    if not isinstance(payload, dict):
        raise ReviewerReportError("Reviewer report must be a JSON object.")
    missing = sorted(_REQUIRED_FIELDS.difference(payload))
    if missing:
        raise ReviewerReportError(
            "Reviewer report is missing required fields: " + ", ".join(missing) + "."
        )
    if set(payload).difference(_REQUIRED_FIELDS):
        raise ReviewerReportError("Reviewer report contains unknown fields.")
    return ReviewerReport(
        critical_issues=_findings(payload, "critical_issues"),
        warnings=_findings(payload, "warnings"),
        suggestions=_findings(payload, "suggestions"),
        missing_tests=_findings(payload, "missing_tests"),
        verdict=_verdict(payload["verdict"]),
    )


def render_reviewer_report(report: ReviewerReport) -> str:
    """Render a validated report in the fixed reviewer section order."""
    sections = (
        ("Critical issues", report.critical_issues),
        ("Warnings", report.warnings),
        ("Suggestions", report.suggestions),
        ("Missing tests", report.missing_tests),
        ("Verdict", (report.verdict.value,)),
    )
    return "\n\n".join(
        f"{title}\n" + "\n".join(f"- {item}" for item in items or ("None recorded",))
        for title, items in sections
    )


def _unwrap_fence(content: str) -> str:
    body = content.strip()
    if not body.startswith("```"):
        return body
    lines = body.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        raise ReviewerReportError("Reviewer report code fence is not closed.")
    language = lines[0].strip().removeprefix("```").strip().lower()
    if language not in _FENCE_LANGUAGES:
        raise ReviewerReportError("Reviewer report code fence must be JSON.")
    return "\n".join(lines[1:-1]).strip()


def _findings(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value = payload[field]
    if not isinstance(value, list):
        raise ReviewerReportError(f"Reviewer report field '{field}' must be an array.")
    findings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ReviewerReportError(f"Reviewer report field '{field}' must contain only strings.")
        cleaned = item.strip()
        if not cleaned:
            raise ReviewerReportError(
                f"Reviewer report field '{field}' must not contain empty strings."
            )
        findings.append(cleaned)
    return tuple(findings)


def _verdict(value: object) -> ReviewerVerdict:
    if not isinstance(value, str):
        raise ReviewerReportError(_VERDICT_ERROR)
    try:
        return ReviewerVerdict(value)
    except ValueError:
        raise ReviewerReportError(_VERDICT_ERROR) from None
