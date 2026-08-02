from collections.abc import Callable

import pytest

import forge.forge_core.agent as agent_module
import forge.forge_core.subagents as subagent_module
from forge.forge import build_runtime
from forge.forge_core.agent import AgentError, ForgeAgent
from forge.forge_core.provider import CompletionRequest, CompletionResponse
from forge.forge_core.tools import Tool, ToolRegistry


class StubProvider:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.handler: Callable[[CompletionRequest], CompletionResponse] | None = None

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self.handler is None:
            raise AssertionError("Unexpected provider request.")
        return self.handler(request)


def test_runtime_model_loops_use_the_normalized_provider(monkeypatch, tmp_path) -> None:
    # Given: a composed Forge runtime
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)

    # When / Then: both loops share the provider boundary and never own LiteLLM calls
    assert runtime.agent.provider is runtime.provider
    assert runtime.subagents.provider is runtime.provider
    assert not hasattr(agent_module, "completion")
    assert not hasattr(subagent_module, "completion")


class RecordingPresenter:
    def __init__(self, approved: bool = False) -> None:
        self.events: list[tuple[str, str]] = []
        self.approved = approved

    def step_started(self, step: int, maximum: int) -> None:
        self.events.append(("step", f"{step}/{maximum}"))

    def tool_started(self, name: str, arguments: str) -> None:
        self.events.append(("tool_started", f"{name}:{arguments}"))

    def request_approval(self, name: str, arguments: str) -> bool:
        self.events.append(("approval", f"{name}:{arguments}"))
        return self.approved

    def tool_completed(self, name: str, result: str) -> None:
        self.events.append(("tool_completed", f"{name}:{result}"))

    def context_reduced(self, tokens_before: int, tokens_after: int) -> None:
        self.events.append(("context_reduced", f"{tokens_before}:{tokens_after}"))

    def response_completed(self, content: str) -> None:
        self.events.append(("response", content))


def test_agent_denies_approval_tool_without_presenter() -> None:
    # Given: an approval-required tool and no trusted UI presenter
    executed = False

    def write() -> str:
        nonlocal executed
        executed = True
        return "written"

    registry = ToolRegistry()
    registry.register(Tool("write", "write", {}, write, requires_approval=True))
    agent = ForgeAgent(StubProvider("test/model"), registry)

    # When: the model requests that tool
    result = agent._run_tool("write", {})

    # Then: Forge denies it without executing model-originated authority
    assert result == "The user denied this tool request."
    assert executed is False


def test_agent_reports_tool_activity_to_presenter() -> None:
    # Given: a trusted presenter that explicitly approves a tool
    presenter = RecordingPresenter(approved=True)
    registry = ToolRegistry()
    registry.register(Tool("status", "status", {}, lambda: "clean", requires_approval=True))
    agent = ForgeAgent(StubProvider("test/model"), registry, presenter=presenter)

    # When: the tool runs through the agent boundary
    result = agent._run_tool("status", {})

    # Then: the UI receives request, approval, and result activity
    assert result == "clean"
    assert [kind for kind, _ in presenter.events] == [
        "tool_started",
        "approval",
        "tool_completed",
    ]


def test_compact_preserves_complete_tool_call_turns(monkeypatch) -> None:
    # Given: history whose final two user turns include consecutive tool steps
    provider = StubProvider("test/model")
    provider.handler = lambda _request: CompletionResponse("summary", (), 0, 0, "stop")
    agent = ForgeAgent(provider, ToolRegistry())
    agent.messages = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "old request"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "inspect"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-a",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-a", "content": "first"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-b",
                    "type": "function",
                    "function": {"name": "search_files", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-b", "content": "second"},
        {"role": "assistant", "content": "inspection complete"},
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "continuing"},
    ]
    # When: the conversation is compacted
    agent.compact()

    # Then: each tool result remains inside the assistant tool-call group that owns its ID
    pending_ids: set[str] = set()
    for message in agent.messages:
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            pending_ids = {call["id"] for call in tool_calls}
            continue
        if message.get("role") == "tool":
            assert message["tool_call_id"] in pending_ids
            pending_ids.remove(message["tool_call_id"])
            continue
        assert not pending_ids
    assert not pending_ids


def test_agent_prunes_old_turns_before_provider_request(monkeypatch) -> None:
    # Given: stale history larger than the active model's input budget
    provider = StubProvider("ollama/qwen2.5-coder:7b")
    agent = ForgeAgent(provider, ToolRegistry())
    agent.messages.extend(
        [
            {"role": "user", "content": f"old-marker-{'x' * 200_000}"},
            {"role": "assistant", "content": "old answer"},
        ]
    )
    captured_messages: list[dict[str, str | None]] = []

    def complete(request: CompletionRequest) -> CompletionResponse:
        captured_messages.extend(request.messages)
        return CompletionResponse("hello", (), 0, 0, "stop")

    provider.handler = complete

    # When: a small current request is sent
    result = agent.run("hello")

    # Then: Forge removes the complete stale turn before crossing the provider boundary
    assert result == "hello"
    assert all("old-marker" not in str(message.get("content")) for message in captured_messages)
    assert captured_messages[-1]["content"] == "hello"


def test_context_percentage_measures_current_messages() -> None:
    # Given: a large unsent message and no billed token usage
    agent = ForgeAgent(StubProvider("ollama/qwen2.5-coder:7b"), ToolRegistry())
    agent.messages.append({"role": "user", "content": "x" * 40_000})
    assert agent.total_tokens == 0

    # When / Then: context pressure reflects the outbound payload instead of usage totals
    assert agent.context_tokens > 0
    assert agent.context_pct > 0


def test_agent_rejects_single_request_larger_than_context(monkeypatch) -> None:
    # Given: one user request that cannot fit even after old history is removed
    provider = StubProvider("ollama/qwen2.5-coder:7b")
    agent = ForgeAgent(provider, ToolRegistry())
    called = False

    def complete(_request: CompletionRequest) -> CompletionResponse:
        nonlocal called
        called = True
        return CompletionResponse("unexpected", (), 0, 0, "stop")

    provider.handler = complete

    # When / Then: Forge stops locally with an actionable error
    with pytest.raises(AgentError, match="too large"):
        agent.run("x" * 200_000)
    assert called is False


def test_agent_discards_response_after_interrupt(monkeypatch) -> None:
    # Given: cancellation arrives while a provider request is in flight
    presenter = RecordingPresenter()
    provider = StubProvider("test/model")
    agent = ForgeAgent(provider, ToolRegistry(), presenter=presenter)

    def complete(_request: CompletionRequest) -> CompletionResponse:
        agent.cancel()
        return CompletionResponse("late response", (), 0, 0, "stop")

    provider.handler = complete

    # When / Then: the late response is neither returned nor presented
    with pytest.raises(AgentError, match="interrupted"):
        agent.run("hello")
    assert all(kind != "response" for kind, _ in presenter.events)


def test_agent_cancellation_at_final_commit_does_not_poison_next_run(monkeypatch) -> None:
    # Given: cancellation arrives immediately after the last post-provider check
    presenter = RecordingPresenter()
    provider = StubProvider("test/model")
    provider.handler = lambda _request: CompletionResponse("response", (), 0, 0, "stop")
    agent = ForgeAgent(provider, ToolRegistry(), presenter=presenter)
    original_check = agent._raise_if_interrupted
    check_count = 0

    def cancel_after_final_check() -> None:
        nonlocal check_count
        original_check()
        check_count += 1
        if check_count == 3:
            agent.cancel()

    monkeypatch.setattr(agent, "_raise_if_interrupted", cancel_after_final_check)

    # When: the response reaches the final commit boundary
    with pytest.raises(AgentError, match="interrupted"):
        agent.run("first")

    # Then: no response is presented and a later request remains usable
    assert all(kind != "response" for kind, _ in presenter.events)
    monkeypatch.setattr(agent, "_raise_if_interrupted", original_check)
    assert agent.run("second") == "response"
