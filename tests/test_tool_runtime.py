import logging
import subprocess
from pathlib import Path

import pytest

from forge.forge_core.tools import (
    Permission,
    RiskLevel,
    Tool,
    ToolError,
    ToolRegistry,
    ToolResult,
    ToolStatus,
    create_tool_registry,
)
from forge.forge_core.workspace import Workspace


def test_initial_tools_have_read_only_permission_metadata(tmp_path: Path) -> None:
    # Given: the primary workspace tool registry
    registry = create_tool_registry(Workspace(tmp_path))
    expected_tools = {
        "list_files",
        "read_file",
        "search_files",
        "git_status",
        "git_diff",
        "git_log",
    }

    # When: the initial repository-inspection tools are inspected
    actual_tools = {definition["function"]["name"] for definition in registry.definitions()}

    # Then: every required read-only tool is explicitly bounded and non-mutating
    assert expected_tools <= actual_tools
    for name in expected_tools:
        tool = registry.get(name)
        assert tool.permission in {
            Permission.READ_FILES,
            Permission.SEARCH_FILES,
            Permission.GIT_READ,
        }
        assert tool.risk_level is RiskLevel.READ_ONLY
        assert tool.requires_approval is False
        assert tool.modifies_workspace is False
        assert tool.network_access is False
        assert tool.timeout_seconds > 0
        assert tool.max_output_bytes > 0


def test_tool_registry_rejects_invalid_json_schema_arguments() -> None:
    # Given: a tool registry with strict object schemas
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="strict",
            description="strict test tool",
            parameters={
                "type": "object",
                "properties": {"count": {"type": "integer", "minimum": 1}},
                "required": ["count"],
                "additionalProperties": False,
            },
            handler=lambda count: str(count),
        )
    )

    # When / Then: missing, mistyped, and unknown arguments are rejected before execution
    for arguments in ({}, {"count": "1"}, {"count": 1, "extra": True}):
        with pytest.raises(ToolError, match="Invalid arguments"):
            registry.execute("strict", arguments)


def test_tool_result_bounds_and_redacts_success_output() -> None:
    # Given: a tool that returns more output than its runtime limit
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="long_output",
            description="bounded test tool",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda: "API_KEY=sk-test-not-real " + ("x" * 100),
            max_output_bytes=32,
        )
    )

    # When: the tool executes through the structured runtime boundary
    result = registry.execute_result("long_output", {})

    # Then: the result is redacted, bounded, and carries truncation metadata
    assert isinstance(result, ToolResult)
    assert result.status is ToolStatus.SUCCEEDED
    assert "sk-test-not-real" not in result.output
    assert "[REDACTED]" in result.output
    assert result.truncated is True
    assert result.output_bytes > 32
    assert len(result.output.encode("utf-8")) <= 32
    assert "truncated" in registry.execute("long_output", {}).lower()


def test_tool_failure_is_structured_and_redacted() -> None:
    # Given: a tool handler that reports a secret-bearing failure
    def fail() -> str:
        raise ToolError("API_KEY=sk-test-not-real")

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="failing",
            description="failure test tool",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=fail,
        )
    )

    # When: the tool executes through the structured runtime boundary
    result = registry.execute_result("failing", {})

    # Then: failure status and safe error text are returned without raising internally
    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert "sk-test-not-real" not in result.error
    assert "[REDACTED]" in result.error
    with pytest.raises(ToolError, match="REDACTED"):
        registry.execute("failing", {})


def test_permission_filter_rejects_tools_outside_allowed_scope() -> None:
    # Given: a registry containing a Git-read tool and a read-files-only view
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="git_read",
            description="git read test tool",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda: "ok",
            permission=Permission.GIT_READ,
            risk_level=RiskLevel.READ_ONLY,
        )
    )
    read_only_files = registry.for_permissions(frozenset({Permission.READ_FILES}))

    # When: the restricted registry receives a Git-read request
    result = read_only_files.execute_result("git_read", {})

    # Then: runtime permission validation rejects the request before the handler runs
    assert result.status is ToolStatus.PERMISSION_DENIED
    assert result.error == "Permission denied for tool: git_read"


def test_tool_execution_is_logged_without_output_content(caplog: pytest.LogCaptureFixture) -> None:
    # Given: a successful tool that returns private content
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="logged",
            description="logging test tool",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda: "private tool output",
        )
    )

    # When: execution logging is enabled at the tool boundary
    with caplog.at_level(logging.INFO, logger="forge.tools"):
        registry.execute_result("logged", {})

    # Then: the event has metadata but not the tool output
    record = next(record for record in caplog.records if record.name == "forge.tools")
    assert record.getMessage() == "tool execution completed"
    assert record.forge_tool_name == "logged"
    assert record.forge_tool_status == "succeeded"
    assert "private tool output" not in record.getMessage()


def test_git_log_is_read_only_and_returns_recent_commit(tmp_path: Path) -> None:
    # Given: a temporary Git repository with one committed file
    (tmp_path / "tracked.txt").write_text("unchanged\n", encoding="utf-8")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "forge-test@example.invalid"],
        ["git", "config", "user.name", "Forge Test"],
        ["git", "add", "tracked.txt"],
        ["git", "commit", "--quiet", "-m", "initial test commit"],
    ):
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
    before = (tmp_path / "tracked.txt").read_bytes()
    registry = create_tool_registry(Workspace(tmp_path))

    # When: Forge requests the recent Git history
    result = registry.execute_result("git_log", {"max_count": 1})

    # Then: the read-only tool returns history without changing tracked content
    assert result.status is ToolStatus.SUCCEEDED
    assert "initial test commit" in result.output
    assert (tmp_path / "tracked.txt").read_bytes() == before
