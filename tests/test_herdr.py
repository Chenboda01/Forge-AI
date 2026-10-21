from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from forge.forge_core.agent import AgentError, AgentMode, ForgeAgent
from forge.forge_core.herdr import HerdrReporter
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
from forge.forge_core.tools import Tool, ToolRegistry


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self._condition = threading.Condition()

    def __call__(self, command: Any) -> None:
        with self._condition:
            self.commands.append(list(command))
            self._condition.notify_all()

    def wait_for(self, count: int, timeout: float = 2.0) -> list[list[str]]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while len(self.commands) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f"Expected {count} commands, got {self.commands!r}")
                self._condition.wait(remaining)
            return [list(command) for command in self.commands]


def option(command: list[str], name: str) -> str | None:
    try:
        return command[command.index(name) + 1]
    except (ValueError, IndexError):
        return None


def state(command: list[str]) -> str | None:
    return option(command, "--state")


def test_reporter_is_inactive_outside_herdr(monkeypatch) -> None:
    monkeypatch.delenv("HERDR_ENV", raising=False)
    assert HerdrReporter.from_environment() is None


def test_reporter_requires_a_pane(monkeypatch) -> None:
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    assert HerdrReporter.from_environment() is None


def test_reporter_requires_a_herdr_binary(monkeypatch) -> None:
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    monkeypatch.delenv("HERDR_BIN_PATH", raising=False)
    monkeypatch.setattr("forge.forge_core.herdr.shutil.which", lambda _name: None)
    assert HerdrReporter.from_environment() is None


def test_reporter_uses_the_pane_binary_from_path(monkeypatch) -> None:
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    monkeypatch.delenv("HERDR_BIN_PATH", raising=False)
    monkeypatch.setattr("forge.forge_core.herdr.shutil.which", lambda _name: "/usr/bin/herdr")

    reporter = HerdrReporter.from_environment()

    assert reporter is not None
    assert reporter.pane_id == "w1:p1"


class RecordingLifecycle:
    def __init__(self) -> None:
        self.events: list[str] = []

    def turn_started(self) -> None:
        self.events.append("turn_started")

    def waiting_for_approval(self, tool_name: str) -> None:
        self.events.append(f"waiting:{tool_name}")

    def approval_resolved(self) -> None:
        self.events.append("approval_resolved")

    def turn_finished(self) -> None:
        self.events.append("turn_finished")


class StubProvider:
    def __init__(self, responses: list[CompletionResponse]) -> None:
        self.model_id = "test/model"
        self.capabilities = ModelCapabilities(tool_calling=True, streaming=False)
        self._responses = responses

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return self._responses.pop(0)

    def stream(self, request: CompletionRequest) -> Iterator[CompletionChunk]:
        raise AssertionError(f"Unexpected provider stream: {request}")

    def test_connection(self) -> ProviderHealth:
        return ProviderHealth(provider="Stub", model_id=self.model_id, reachable=True)


class FailingProvider(StubProvider):
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        raise ProviderTimeoutError("timed out")


class ApprovingPresenter:
    def step_started(self, step: int, maximum: int) -> None:
        return None

    def tool_started(self, name: str, arguments: str) -> None:
        return None

    def request_approval(self, name: str, arguments: str) -> bool:
        return True

    def tool_completed(self, name: str, result: str) -> None:
        return None

    def context_reduced(self, tokens_before: int, tokens_after: int) -> None:
        return None

    def response_completed(self, content: str) -> None:
        return None


def test_reporter_maps_the_forge_lifecycle_to_herdr_states() -> None:
    runner = RecordingRunner()
    reporter = HerdrReporter("/usr/bin/herdr", "w1:p1", runner=runner)

    reporter.turn_started()
    assert state(runner.wait_for(1)[0]) == "working"

    reporter.waiting_for_approval("write_file")
    blocked = runner.wait_for(2)[1]
    assert state(blocked) == "blocked"
    assert option(blocked, "--message") == "Waiting for approval: write_file"

    reporter.approval_resolved()
    assert state(runner.wait_for(3)[2]) == "working"

    reporter.turn_finished()
    assert state(runner.wait_for(4)[3]) == "idle"

    reporter.release()
    released = runner.wait_for(5)[4]
    assert released[1:3] == ["pane", "release-agent"]
    assert option(released, "--source") == "forge"
    assert option(released, "--agent") == "forge"

    commands = runner.commands
    sequences = [int(option(command, "--seq") or 0) for command in commands]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)


def test_reporter_publishes_initial_idle_state() -> None:
    runner = RecordingRunner()
    reporter = HerdrReporter("/usr/bin/herdr", "w1:p1", runner=runner)

    reporter.report_idle()

    assert state(runner.wait_for(1)[0]) == "idle"
    reporter.release()


def test_nested_turns_remain_working_until_every_turn_finishes() -> None:
    runner = RecordingRunner()
    reporter = HerdrReporter("/usr/bin/herdr", "w1:p1", runner=runner)

    reporter.turn_started()
    runner.wait_for(1)
    reporter.turn_started()
    reporter.turn_finished()

    time.sleep(0.05)
    assert len(runner.commands) == 1

    reporter.turn_finished()
    assert state(runner.wait_for(2)[1]) == "idle"

    reporter.release()


def test_reporter_ignores_failed_herdr_commands() -> None:
    def fail(_command: Any) -> None:
        raise OSError("herdr is unavailable")

    reporter = HerdrReporter("/usr/bin/herdr", "w1:p1", runner=fail)

    reporter.turn_started()
    reporter.waiting_for_approval("write_file")
    reporter.approval_resolved()
    reporter.turn_finished()
    reporter.release()


def test_agent_reports_turn_and_approval_lifecycle() -> None:
    lifecycle = RecordingLifecycle()
    registry = ToolRegistry()
    registry.register(Tool("write", "write", {}, lambda: "written", requires_approval=True))
    provider = StubProvider(
        [
            CompletionResponse(
                None,
                (ProviderToolCall("call-1", "write", "{}"),),
                TokenUsage(1, 1),
                "tool_calls",
            ),
            CompletionResponse("done", (), TokenUsage(1, 1), "stop"),
        ]
    )
    agent = ForgeAgent(
        provider,
        registry,
        presenter=ApprovingPresenter(),
        mode=AgentMode.BUILD,
        lifecycle=lifecycle,
    )

    assert agent.run("write the file") == "done"
    assert lifecycle.events == [
        "turn_started",
        "waiting:write",
        "approval_resolved",
        "turn_finished",
    ]


def test_agent_reports_turn_finished_after_a_provider_failure() -> None:
    # Given: an agent whose provider request fails
    lifecycle = RecordingLifecycle()
    agent = ForgeAgent(FailingProvider([]), ToolRegistry(), lifecycle=lifecycle)

    # When: the turn fails before producing a response
    with pytest.raises(AgentError, match="timed out"):
        agent.run("fail")

    # Then: the lifecycle returns to idle instead of staying working
    assert lifecycle.events == ["turn_started", "turn_finished"]
