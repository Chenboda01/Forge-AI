import pytest

from forge.forge import build_runtime
from forge.forge_core.provider import CompletionRequest, CompletionResponse
from forge.forge_core.subagents import SUBAGENTS, SubagentError
from forge.ui.commands import CommandService


def test_runtime_exposes_delegate_task(monkeypatch, tmp_path) -> None:
    # Given: a local provider and isolated workspace
    monkeypatch.setenv("FORGE_MODEL", "ollama")

    # When: the primary Forge runtime is composed
    runtime = build_runtime(tmp_path)
    tool_names = [
        definition["function"]["name"] for definition in runtime.agent.tools.definitions()
    ]

    # Then: only the primary agent receives the delegation tool
    assert "delegate_task" in tool_names


def test_subagent_tool_sets_remain_read_only(monkeypatch, tmp_path) -> None:
    # Given: the restored isolated subagent runtime
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)

    # When: each role's filtered registry is inspected
    role_tools = {
        name: {
            definition["function"]["name"]
            for definition in runtime.subagents.tool_registry.only(spec.allowed_tools).definitions()
        }
        for name, spec in SUBAGENTS.items()
    }

    # Then: no subagent can write, execute commands, or delegate recursively
    forbidden = {"write_file", "run_command", "delegate_task"}
    assert all(tools.isdisjoint(forbidden) for tools in role_tools.values())


def test_subagents_follow_primary_model_switches(monkeypatch, tmp_path) -> None:
    # Given: a runtime configured with one local model
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    assert runtime.subagents.model_id == runtime.agent.model_id

    # When: the user switches the active model
    CommandService(runtime).switch_model("ollama-qwen")

    # Then: future subagent requests use that same explicitly selected model
    assert runtime.subagents.model_id == runtime.agent.model_id


def test_subagent_discards_report_after_interrupt(monkeypatch, tmp_path) -> None:
    # Given: cancellation arrives during a read-only subagent request
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runner = build_runtime(tmp_path).subagents

    def complete(_request: CompletionRequest) -> CompletionResponse:
        runner.cancel()
        return CompletionResponse("late report", (), 0, 0, "stop")

    monkeypatch.setattr(runner.provider, "complete", complete)

    # When / Then: the late report is rejected as interrupted
    with pytest.raises(SubagentError, match="interrupted"):
        runner.run("explore", "inspect")


def test_subagent_cancellation_at_report_commit_does_not_poison_next_run(
    monkeypatch, tmp_path
) -> None:
    # Given: cancellation arrives immediately after the last post-provider check
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runner = build_runtime(tmp_path).subagents
    monkeypatch.setattr(
        runner.provider,
        "complete",
        lambda _request: CompletionResponse("report", (), 0, 0, "stop"),
    )
    original_check = runner._raise_if_interrupted
    check_count = 0

    def cancel_after_final_check() -> None:
        nonlocal check_count
        original_check()
        check_count += 1
        if check_count == 2:
            runner.cancel()

    monkeypatch.setattr(runner, "_raise_if_interrupted", cancel_after_final_check)

    # When: the report reaches the final commit boundary
    with pytest.raises(SubagentError, match="interrupted"):
        runner.run("explore", "first")

    # Then: a later subagent request remains usable
    monkeypatch.setattr(runner, "_raise_if_interrupted", original_check)
    assert runner.run("explore", "second") == "report"
