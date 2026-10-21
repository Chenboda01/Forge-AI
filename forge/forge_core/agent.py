from __future__ import annotations

import json
from enum import StrEnum
from threading import Event, Lock
from typing import Any, assert_never

from .agent_limits import (
    DEFAULT_MAX_REPEATED_TOOL_CALLS,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOOL_CALLS,
    AgentLimitError,
    AgentLimits,
    ToolCallState,
)
from .agent_prompt import SYSTEM_PROMPT
from .approval import render_approval_details
from .context import (
    ContextBudgetError,
    compact_agent,
    context_limit,
    count_message_tokens,
    fit_messages,
)
from .instructions import ProjectInstructions, TaskMetadata
from .presenter import AgentLifecycle, AgentPresenter, NullLifecycle, SilentPresenter
from .provider import (
    CompletionRequest,
    CompletionResponse,
    ForgeProviderError,
    ProviderClient,
    ProviderTimeoutError,
    ProviderToolCall,
)
from .redaction import redact_text
from .tools import ToolError, ToolRegistry


class AgentError(Exception):
    """Raised when the Forge agent cannot continue."""


class AgentInterruptedError(AgentError):
    pass


class AgentMode(StrEnum):
    ASK = "ask"
    ARCHITECT = "architect"
    BUILD = "build"


class ForgeAgent:
    def __init__(
        self,
        provider: ProviderClient,
        tools: ToolRegistry,
        presenter: AgentPresenter | None = None,
        *,
        mode: AgentMode = AgentMode.ASK,
        project_instructions: ProjectInstructions | None = None,
        lifecycle: AgentLifecycle | None = None,
    ):
        self.provider = provider
        self.tools = tools
        self._active_tools = self._tools_for_mode(tools, mode)
        self.mode = mode
        self.project_instructions = project_instructions or ProjectInstructions()
        self.task_metadata: TaskMetadata = self.project_instructions.task_metadata
        self.max_steps = DEFAULT_MAX_STEPS
        self.max_tool_calls = DEFAULT_MAX_TOOL_CALLS
        self.max_repeated_tool_calls = DEFAULT_MAX_REPEATED_TOOL_CALLS
        self.presenter = presenter or SilentPresenter()
        self.lifecycle = lifecycle or NullLifecycle()
        self._cancel_requested, self._cancel_lock = Event(), Lock()
        self._accepting_cancellation = False

        self.messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt()}]
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    @property
    def model_id(self) -> str:
        return self.provider.model_id

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def context_tokens(self) -> int:
        return count_message_tokens(self.model_id, self.messages)

    @property
    def context_pct(self) -> float:
        """Estimated context window usage percentage."""
        return min((self.context_tokens / context_limit(self.model_id)) * 100, 100.0)

    def cancel(self) -> None:
        with self._cancel_lock:
            if self._accepting_cancellation:
                self._cancel_requested.set()

    def _begin_operation(self) -> None:
        with self._cancel_lock:
            self._cancel_requested.clear()
            self._accepting_cancellation = True

    def _finish_operation(self) -> None:
        with self._cancel_lock:
            self._accepting_cancellation = False
            self._cancel_requested.clear()

    def _raise_if_interrupted(self) -> None:
        with self._cancel_lock:
            self._raise_if_interrupted_locked()

    def _raise_if_interrupted_locked(self) -> None:
        if not self._cancel_requested.is_set():
            return
        self._cancel_requested.clear()
        self._accepting_cancellation = False
        raise AgentInterruptedError("Operation interrupted by user.")

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self._system_prompt()}]
        self.input_tokens = 0
        self.output_tokens = 0

    def _system_prompt(self) -> str:
        return self.project_instructions.with_core_prompt(SYSTEM_PROMPT)

    def run(self, user_message: str) -> str:
        limits = AgentLimits(
            max_steps=self.max_steps,
            max_tool_calls=self.max_tool_calls,
            max_repeated_tool_calls=self.max_repeated_tool_calls,
        )
        try:
            limits.validate()
        except AgentLimitError as error:
            raise AgentError(str(error)) from error
        self._begin_operation()
        self.lifecycle.turn_started()
        try:
            return self._run(user_message, limits)
        finally:
            self._finish_operation()
            self.lifecycle.turn_finished()

    def _run(self, user_message: str, limits: AgentLimits) -> str:
        self._raise_if_interrupted()
        self.messages.append({"role": "user", "content": redact_text(user_message)})
        tool_definitions = tuple(self._active_tools.definitions())
        if tool_definitions and not self.provider.capabilities.tool_calling:
            raise AgentError(
                f"Model {self.model_id} does not support tool-calling required by the active tools."
            )
        tool_call_state = ToolCallState()

        for step in range(1, limits.max_steps + 1):
            self.presenter.step_started(step, self.max_steps)
            try:
                context = fit_messages(self.model_id, self.messages)
            except ContextBudgetError as error:
                raise AgentError(str(error)) from error
            self.messages = context.messages
            self._raise_if_interrupted()
            if context.removed_messages:
                self.presenter.context_reduced(context.tokens_before, context.tokens_after)
            try:
                response = self.provider.complete(
                    CompletionRequest(
                        messages=tuple(self.messages),
                        tools=tool_definitions,
                        tool_choice="auto",
                    )
                )
                self.input_tokens += response.input_tokens
                self.output_tokens += response.output_tokens
            except ProviderTimeoutError as error:
                self._raise_if_interrupted()
                raise AgentError(f"Model request timed out: {error}") from error
            except ForgeProviderError as error:
                self._raise_if_interrupted()
                raise AgentError(f"Model request failed: {error}") from error

            self._raise_if_interrupted()
            tool_calls = response.tool_calls

            if not tool_calls:
                content = response.content
                if content:
                    return self._commit_response(response, content)
                raise AgentError("The model returned neither text nor tool calls.")

            try:
                tool_call_state = limits.reserve_tool_calls(tool_calls, tool_call_state)
            except AgentLimitError as error:
                raise AgentError(str(error)) from error
            self._append_provider_message(response.assistant_message)
            for tool_call in tool_calls:
                self._raise_if_interrupted()
                self._execute_tool_call(tool_call)
                self._raise_if_interrupted()

        self._raise_if_interrupted()
        raise AgentError(f"Forge reached its {limits.max_steps}-step limit.")

    @staticmethod
    def _tools_for_mode(tools: ToolRegistry, mode: AgentMode) -> ToolRegistry:
        match mode:
            case AgentMode.ASK | AgentMode.ARCHITECT:
                return tools.read_only()
            case AgentMode.BUILD:
                return tools
            case unreachable:
                assert_never(unreachable)

    def _append_provider_message(self, message: dict[str, Any]) -> None:
        with self._cancel_lock:
            self._raise_if_interrupted_locked()
            self.messages.append(message)

    def _commit_response(self, response: CompletionResponse, content: str) -> str:
        safe_content = redact_text(content)
        assistant_message = response.assistant_message
        assistant_message["content"] = safe_content
        with self._cancel_lock:
            self._raise_if_interrupted_locked()
            self.messages.append(assistant_message)
            self._accepting_cancellation = False
        self.presenter.response_completed(safe_content)
        return safe_content

    def _execute_tool_call(self, tool_call: ProviderToolCall) -> None:
        tool_name = tool_call.name
        raw_arguments = tool_call.arguments or "{}"

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            result = "Tool error: the model supplied invalid JSON arguments."
        else:
            if not isinstance(arguments, dict):
                result = "Tool error: tool arguments must be a JSON object."
            else:
                result = self._run_tool(tool_name, arguments)

        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": result,
            }
        )

    def _run_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            tool = self._active_tools.get(tool_name)
        except ToolError as error:
            return f"Tool error: {error}"

        arguments_json = json.dumps(arguments, indent=2)
        self.presenter.tool_started(tool_name, arguments_json)

        working_directory = (
            None if self._active_tools.workspace is None else self._active_tools.workspace.root
        )
        approval_details = render_approval_details(tool, arguments_json, working_directory)
        if tool.requires_approval:
            self.lifecycle.waiting_for_approval(tool_name)
            try:
                approved = self.presenter.request_approval(tool_name, approval_details)
            finally:
                self.lifecycle.approval_resolved()
            if not approved:
                return "The user denied this tool request."

        try:
            result = self._active_tools.execute(tool_name, arguments)
        except ToolError as error:
            result = f"Tool error: {error}"

        self.presenter.tool_completed(tool_name, result)
        return result

    def compact(self) -> str:
        return compact_agent(self)
