from collections.abc import Callable, Iterator

import pytest

import forge.forge_core.agent as agent_module
import forge.forge_core.subagents as subagent_module
from forge.forge import build_runtime
from forge.forge_core.agent import AgentError, AgentMode, ForgeAgent
from forge.forge_core.models import ModelCapabilities
from forge.forge_core.provider import (
    CompletionChunk,
    CompletionRequest,
    CompletionResponse,
    ProviderHealth,
    ProviderTimeoutError,
    ProviderToolCall,
    TokenUsage,
)
from forge.forge_core.tools import RiskLevel, Tool, ToolRegistry
from forge.forge_core.workspace import Workspace


class StubProvider:
    def __init__(self, model_id: str, *, tool_calling: bool = True) -> None:
        self.model_id = model_id
        self.capabilities = ModelCapabilities(tool_calling=tool_calling, streaming=True)
        self.handler: Callable[[CompletionRequest], CompletionResponse] | None = None

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self.handler is None:
            raise AssertionError("Unexpected provider request.")
        return self.handler(request)

    def stream(self, request: CompletionRequest) -> Iterator[CompletionChunk]:
        raise AssertionError(f"Unexpected provider stream: {request}")

    def test_connection(self) -> ProviderHealth:
        return ProviderHealth(provider="Stub", model_id=self.model_id, reachable=True)


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
    agent = ForgeAgent(
        StubProvider("test/model"), registry, presenter=presenter, mode=AgentMode.BUILD
    )

    # When: the tool runs through the agent boundary
    result = agent._run_tool("status", {})

    # Then: the UI receives request, approval, and result activity
    assert result == "clean"
    assert [kind for kind, _ in presenter.events] == [
        "tool_started",
        "approval",
        "tool_completed",
    ]


def test_agent_redacts_provider_text_before_rendering_or_history() -> None:
    # Given: an untrusted provider response containing a credential-shaped value
    secret = "sk-proj-syntheticcredential1234567890"
    provider = StubProvider("test/model")
    provider.handler = lambda _request: CompletionResponse(
        f"result {secret}", (), TokenUsage(1, 1), "stop"
    )
    presenter = RecordingPresenter()
    agent = ForgeAgent(provider, ToolRegistry(), presenter=presenter)

    # When: the final response crosses the workflow boundary
    result = agent.run("hello")

    # Then: return, rendering, and retained conversation all contain only redacted text
    assert secret not in result
    assert "[REDACTED]" in result
    assert secret not in presenter.events[-1][1]
    assert secret not in str(agent.messages)


def test_agent_redacts_user_credentials_before_provider_request() -> None:
    # Given: a user message containing a credential-shaped value
    secret = "sk-proj-syntheticcredential1234567890"
    requests: list[CompletionRequest] = []
    provider = StubProvider("test/model")

    def complete(request: CompletionRequest) -> CompletionResponse:
        requests.append(request)
        return CompletionResponse("done", (), TokenUsage(1, 1), "stop")

    provider.handler = complete
    agent = ForgeAgent(provider, ToolRegistry())

    # When: Forge sends the request through the provider boundary
    agent.run(f"inspect this credential {secret}")

    # Then: provider context and retained conversation contain only redacted text
    assert secret not in str(requests[0].messages)
    assert "[REDACTED]" in str(requests[0].messages)
    assert secret not in str(agent.messages)


def test_compact_preserves_complete_tool_call_turns(monkeypatch) -> None:
    # Given: history whose final two user turns include consecutive tool steps
    provider = StubProvider("test/model")
    provider.handler = lambda _request: CompletionResponse("summary", (), TokenUsage(0, 0), "stop")
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
        return CompletionResponse("hello", (), TokenUsage(0, 0), "stop")

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
        return CompletionResponse("unexpected", (), TokenUsage(0, 0), "stop")

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
        return CompletionResponse("late response", (), TokenUsage(0, 0), "stop")

    provider.handler = complete

    # When / Then: the late response is neither returned nor presented
    with pytest.raises(AgentError, match="interrupted"):
        agent.run("hello")
    assert all(kind != "response" for kind, _ in presenter.events)


def test_agent_cancellation_at_final_commit_does_not_poison_next_run(monkeypatch) -> None:
    # Given: cancellation arrives immediately after the last post-provider check
    presenter = RecordingPresenter()
    provider = StubProvider("test/model")
    provider.handler = lambda _request: CompletionResponse("response", (), TokenUsage(0, 0), "stop")
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


def test_agent_defaults_to_twenty_model_steps() -> None:
    # Given: a newly created primary agent
    agent = ForgeAgent(StubProvider("test/model"), ToolRegistry())

    # When / Then: the deterministic primary-loop default is architecture bounded
    assert agent.max_steps == 20


def test_agent_rejects_model_step_limit_above_hard_maximum() -> None:
    # Given: a primary agent configured beyond the runtime hard maximum
    provider = StubProvider("test/model")
    agent = ForgeAgent(provider, ToolRegistry())
    agent.max_steps = 301
    called = False

    def complete(_request: CompletionRequest) -> CompletionResponse:
        nonlocal called
        called = True
        return CompletionResponse("unexpected", (), TokenUsage(0, 0), "stop")

    provider.handler = complete

    # When / Then: Forge rejects the unsafe limit before contacting the provider
    with pytest.raises(AgentError, match="max_steps must be between 1 and 300"):
        agent.run("hello")
    assert called is False


def test_agent_stops_cleanly_at_model_step_limit() -> None:
    # Given: a model that keeps requesting the same harmless read-only tool
    provider = StubProvider("test/model")
    registry = ToolRegistry()
    registry.register(Tool("read", "read", {}, lambda: "ok"))
    provider.handler = lambda _request: CompletionResponse(
        None,
        (ProviderToolCall("call-1", "read", "{}"),),
        TokenUsage(0, 0),
        "tool_calls",
    )
    agent = ForgeAgent(provider, registry)
    agent.max_steps = 1

    # When / Then: the workflow stops at the configured step boundary
    with pytest.raises(AgentError, match="1-step limit"):
        agent.run("inspect")


def test_agent_rejects_tool_batch_over_total_limit_without_execution() -> None:
    # Given: a response whose complete tool-call batch exceeds the run limit
    provider = StubProvider("test/model")
    executed = 0

    def read() -> str:
        nonlocal executed
        executed += 1
        return "ok"

    registry = ToolRegistry()
    registry.register(Tool("read", "read", {}, read))
    provider.handler = lambda _request: CompletionResponse(
        None,
        (
            ProviderToolCall("call-1", "read", "{}"),
            ProviderToolCall("call-2", "read", "{}"),
        ),
        TokenUsage(0, 0),
        "tool_calls",
    )
    agent = ForgeAgent(provider, registry)
    agent.max_tool_calls = 1

    # When / Then: Forge rejects the batch before appending or executing it
    with pytest.raises(AgentError, match="tool-call limit"):
        agent.run("inspect")
    assert executed == 0
    assert not any(message.get("role") == "assistant" for message in agent.messages)


def test_agent_stops_before_fourth_identical_tool_call() -> None:
    # Given: a model that repeats one canonical tool request indefinitely
    provider = StubProvider("test/model")
    executed = 0
    registry = ToolRegistry()

    def read() -> str:
        nonlocal executed
        executed += 1
        return "ok"

    registry.register(Tool("read", "read", {}, read))
    provider.handler = lambda _request: CompletionResponse(
        None,
        (ProviderToolCall(f"call-{executed + 1}", "read", "{}"),),
        TokenUsage(0, 0),
        "tool_calls",
    )
    agent = ForgeAgent(provider, registry)
    agent.max_steps = 10

    # When / Then: three identical calls may run, but the fourth is rejected
    with pytest.raises(AgentError, match="repeated tool-call limit"):
        agent.run("inspect")
    assert executed == 3


def test_agent_canonicalizes_json_when_comparing_identical_calls() -> None:
    # Given: equivalent arguments with different JSON key ordering
    provider = StubProvider("test/model")
    executed = 0
    arguments = (
        '{"path":"a","start_line":1}',
        '{"start_line":1,"path":"a"}',
    )
    registry = ToolRegistry()

    def read(path: str, start_line: int) -> str:
        nonlocal executed
        executed += 1
        return f"{path}:{start_line}"

    registry.register(
        Tool(
            "read",
            "read",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                },
                "required": ["path", "start_line"],
                "additionalProperties": False,
            },
            read,
        )
    )

    def complete(_request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            None,
            (ProviderToolCall(f"call-{executed + 1}", "read", arguments[executed]),),
            TokenUsage(0, 0),
            "tool_calls",
        )

    provider.handler = complete
    agent = ForgeAgent(provider, registry)
    agent.max_repeated_tool_calls = 1
    agent.max_steps = 3

    # When / Then: semantically identical calls share one repetition counter
    with pytest.raises(AgentError, match="repeated tool-call limit"):
        agent.run("inspect")
    assert executed == 1


def test_agent_tool_call_limits_reset_between_runs() -> None:
    # Given: each user request makes one repeated-call-limited tool request, then completes
    provider = StubProvider("test/model")
    executed = 0
    provider_calls = 0
    registry = ToolRegistry()

    def read() -> str:
        nonlocal executed
        executed += 1
        return "ok"

    registry.register(Tool("read", "read", {}, read))

    def complete(_request: CompletionRequest) -> CompletionResponse:
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls in {1, 3}:
            return CompletionResponse(
                None,
                (ProviderToolCall(f"call-{provider_calls}", "read", "{}"),),
                TokenUsage(0, 0),
                "tool_calls",
            )
        return CompletionResponse("done", (), TokenUsage(0, 0), "stop")

    provider.handler = complete
    agent = ForgeAgent(provider, registry)
    agent.max_repeated_tool_calls = 1

    # When: two separate user runs request the same tool
    assert agent.run("first") == "done"
    assert agent.run("second") == "done"

    # Then: each run had its own repetition budget
    assert executed == 2


@pytest.mark.parametrize("mode", (AgentMode.ASK, AgentMode.ARCHITECT))
def test_read_only_modes_expose_only_read_only_tools(monkeypatch, tmp_path, mode) -> None:
    # Given: a runtime in one of the initial read-only modes
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path, mode=mode)
    names = {
        definition["function"]["name"] for definition in runtime.agent._active_tools.definitions()
    }

    # When / Then: only the read-only inspection surface reaches the model
    assert {"list_files", "read_file", "search_files", "git_status", "git_diff", "git_log"} <= names
    assert {"propose_patch", "apply_patch", "run_command", "delegate_task"}.isdisjoint(names)


@pytest.mark.parametrize("mode", (AgentMode.ASK, AgentMode.ARCHITECT))
def test_read_only_modes_reject_hidden_write_tool_without_approval_or_execution(mode) -> None:
    # Given: a write tool that is hidden by the active read-only mode
    presenter = RecordingPresenter(approved=True)
    executed = False

    def write() -> str:
        nonlocal executed
        executed = True
        return "written"

    registry = ToolRegistry()
    registry.register(
        Tool(
            "write",
            "write",
            {},
            write,
            requires_approval=True,
            risk_level=RiskLevel.MEDIUM,
            modifies_workspace=True,
        )
    )
    agent = ForgeAgent(StubProvider("test/model"), registry, presenter=presenter, mode=mode)

    # When: the model names the hidden write tool directly
    result = agent._run_tool("write", {})

    # Then: runtime filtering denies it before approval or handler execution
    assert result == "Tool error: Unknown tool: write"
    assert executed is False
    assert presenter.events == []


def test_agent_reports_missing_tool_calling_capability_before_provider_request() -> None:
    # Given: a selected model that cannot call tools and a visible read-only tool
    provider = StubProvider("test/no-tools", tool_calling=False)
    registry = ToolRegistry()
    registry.register(Tool("read", "read", {}, lambda: "ok"))
    called = False

    def complete(_request: CompletionRequest) -> CompletionResponse:
        nonlocal called
        called = True
        return CompletionResponse("unexpected", (), TokenUsage(0, 0), "stop")

    provider.handler = complete
    agent = ForgeAgent(provider, registry)

    # When / Then: Forge reports the capability mismatch locally
    with pytest.raises(AgentError, match="test/no-tools.*tool-calling"):
        agent.run("inspect")
    assert called is False


def test_build_runtime_defaults_to_ask_mode(monkeypatch, tmp_path) -> None:
    # Given: the default runtime composition
    monkeypatch.setenv("FORGE_MODEL", "ollama")

    # When / Then: Forge starts in the safer read-only mode
    assert build_runtime(tmp_path).agent.mode is AgentMode.ASK


def test_build_mode_exposes_approved_patch_and_validation_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Given: a runtime explicitly started for code-editing work
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path, mode=AgentMode.BUILD)

    # When: the active model tool set is inspected
    names = {
        definition["function"]["name"] for definition in runtime.agent._active_tools.definitions()
    }

    # Then: writes and commands are available only through approval-gated capabilities
    assert {"propose_patch", "apply_patch", "detect_validation", "run_command"} <= names
    assert runtime.agent._active_tools.get("apply_patch").requires_approval is True
    assert runtime.agent._active_tools.get("run_command").requires_approval is True


def test_approval_is_requested_again_when_operation_changes() -> None:
    # Given: a presenter that approves only the first exact request
    presenter = RecordingPresenter(approved=True)
    registry = ToolRegistry()
    executed: list[str] = []
    registry.register(
        Tool(
            "write",
            "write",
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            lambda value: executed.append(value) or value,
            requires_approval=True,
        )
    )
    agent = ForgeAgent(StubProvider("test/model"), registry, presenter=presenter)

    # When: two different operations are requested
    assert agent._run_tool("write", {"value": "first"}) == "first"
    presenter.approved = False
    assert agent._run_tool("write", {"value": "second"}) == "The user denied this tool request."

    # Then: the first approval is not reusable for changed arguments
    assert executed == ["first"]
    approvals = [event for event in presenter.events if event[0] == "approval"]
    assert len(approvals) == 2
    assert "first" in approvals[0][1]
    assert "second" in approvals[1][1]


def test_approval_displays_runtime_policy_metadata(tmp_path) -> None:
    # Given: an approval-required command with explicit runtime policy metadata
    presenter = RecordingPresenter(approved=False)
    registry = ToolRegistry(workspace=Workspace(tmp_path))
    registry.register(
        Tool(
            "validate",
            "Run the selected validation command.",
            {
                "type": "object",
                "properties": {"arguments": {"type": "array", "items": {"type": "string"}}},
                "required": ["arguments"],
                "additionalProperties": False,
            },
            lambda arguments: "unexpected",
            requires_approval=True,
            risk_level=RiskLevel.MEDIUM,
            modifies_workspace=True,
            network_access=False,
            timeout_seconds=60,
        )
    )
    agent = ForgeAgent(
        StubProvider("test/model"), registry, presenter=presenter, mode=AgentMode.BUILD
    )

    # When: the model requests the command
    agent._run_tool("validate", {"arguments": ["pytest"]})

    # Then: the trusted approval surface receives the exact action and policy context
    approval = next(value for kind, value in presenter.events if kind == "approval")
    assert '"pytest"' in approval
    assert "Reason: Run the selected validation command." in approval
    assert f"Working directory: {tmp_path}" in approval
    assert "Risk: medium" in approval
    assert "Network: denied" in approval
    assert "Timeout: 60 seconds" in approval
    assert "Modifies workspace: yes" in approval


def test_agent_recovers_after_malformed_tool_call_json() -> None:
    # Given: malformed arguments followed by a valid final response
    provider = StubProvider("test/model")
    provider_calls = 0
    executed = False

    def read() -> str:
        nonlocal executed
        executed = True
        return "unexpected"

    registry = ToolRegistry()
    registry.register(Tool("read", "read", {}, read))

    def complete(_request: CompletionRequest) -> CompletionResponse:
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls == 1:
            return CompletionResponse(
                None,
                (ProviderToolCall("call-1", "read", "{invalid"),),
                TokenUsage(0, 0),
                "tool_calls",
            )
        return CompletionResponse("recovered", (), TokenUsage(0, 0), "stop")

    provider.handler = complete
    agent = ForgeAgent(provider, registry)

    # When: Forge receives the malformed request
    result = agent.run("inspect")

    # Then: the handler is bypassed and the next model response can complete
    assert result == "recovered"
    assert executed is False
    tool_result = next(message for message in agent.messages if message.get("role") == "tool")
    assert "{invalid" not in str(tool_result["content"])


def test_agent_reports_provider_timeout() -> None:
    # Given: the normalized provider timeout error
    provider = StubProvider("test/model")
    provider.handler = lambda _request: (_ for _ in ()).throw(
        ProviderTimeoutError("provider deadline")
    )
    agent = ForgeAgent(provider, ToolRegistry())

    # When / Then: the workflow preserves the timeout meaning at its boundary
    with pytest.raises(AgentError, match="timed out"):
        agent.run("hello")
