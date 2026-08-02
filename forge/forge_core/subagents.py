from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Event, Lock
from typing import Any

from .provider import CompletionRequest, ForgeProviderError, ProviderClient
from .tools import ToolError, ToolRegistry


@dataclass(frozen=True, slots=True)
class SubagentSpec:
    name: str
    description: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    max_steps: int = 8


SUBAGENTS: dict[str, SubagentSpec] = {
    "explore": SubagentSpec(
        name="explore",
        description=(
            "Investigates the repository and locates relevant code. "
            "It cannot edit files or run commands."
        ),
        system_prompt="""
You are Forge Explore, a read-only repository investigator.

Your job is to:
- Locate relevant files and symbols.
- Read only what is needed.
- Explain how the relevant code works.
- Clearly separate facts from hypotheses.
- Return useful file paths and line numbers.

Never edit files.
Never run commands.
Never request secrets.
Return a concise report to the parent agent.
""".strip(),
        allowed_tools=(
            "list_files",
            "read_file",
            "search_files",
            "git_status",
            "git_diff",
        ),
    ),
    "reviewer": SubagentSpec(
        name="reviewer",
        description=(
            "Reviews existing changes for correctness, regressions, "
            "security issues, and missing tests."
        ),
        system_prompt="""
You are Forge Reviewer.

Review the repository or current Git diff without editing anything.

Return:
1. Critical issues
2. Warnings
3. Suggestions
4. Missing tests
5. Verdict: approve or request_changes

Every finding should mention the relevant file when possible.
""".strip(),
        allowed_tools=(
            "read_file",
            "search_files",
            "git_status",
            "git_diff",
        ),
    ),
}


class SubagentError(Exception):
    """Raised when a Forge subagent cannot complete its task."""


class SubagentInterruptedError(SubagentError):
    pass


class SubagentRunner:
    """Runs one isolated read-only subagent and returns its final report."""

    def __init__(self, tool_registry: ToolRegistry, provider: ProviderClient) -> None:
        self.tool_registry = tool_registry
        self.provider = provider
        self._cancel_requested = Event()
        self._cancel_lock = Lock()
        self._accepting_cancellation = False

    @property
    def model_id(self) -> str:
        return self.provider.model_id

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
        raise SubagentInterruptedError("Subagent interrupted by user.")

    def run(
        self,
        agent_name: str,
        objective: str,
        context_files: list[str] | None = None,
        constraints: list[str] | None = None,
    ) -> str:
        self._begin_operation()
        try:
            return self._run(agent_name, objective, context_files, constraints)
        finally:
            self._finish_operation()

    def _run(
        self,
        agent_name: str,
        objective: str,
        context_files: list[str] | None,
        constraints: list[str] | None,
    ) -> str:
        self._raise_if_interrupted()
        spec = SUBAGENTS.get(agent_name)
        if spec is None:
            available = ", ".join(sorted(SUBAGENTS))
            raise SubagentError(
                f"Unknown subagent '{agent_name}'. Available subagents: {available}"
            )

        tools = self.tool_registry.only(spec.allowed_tools)
        prompt = self._build_prompt(
            objective=objective,
            context_files=context_files or [],
            constraints=constraints or [],
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": spec.system_prompt},
            {"role": "user", "content": prompt},
        ]

        for _ in range(spec.max_steps):
            try:
                response = self.provider.complete(
                    CompletionRequest(
                        messages=tuple(messages),
                        tools=tuple(tools.definitions()),
                        tool_choice="auto",
                    )
                )
            except ForgeProviderError as error:
                self._raise_if_interrupted()
                raise SubagentError(f"{agent_name} request failed: {error}") from error

            self._raise_if_interrupted()
            tool_calls = response.tool_calls
            if not tool_calls:
                content = response.content
                if not content:
                    raise SubagentError(f"{agent_name} returned no report.")
                return self._commit_report(content)

            self._append_provider_message(messages, response.assistant_message)
            for tool_call in tool_calls:
                self._raise_if_interrupted()
                tool_name = tool_call.name
                raw_arguments = tool_call.arguments or "{}"
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    result = "Tool error: invalid JSON arguments."
                else:
                    try:
                        result = tools.execute(tool_name, arguments)
                    except ToolError as error:
                        result = f"Tool error: {error}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result,
                    }
                )
                self._raise_if_interrupted()

        self._raise_if_interrupted()
        raise SubagentError(f"{agent_name} reached its step limit.")

    def _append_provider_message(
        self, messages: list[dict[str, Any]], message: dict[str, Any]
    ) -> None:
        with self._cancel_lock:
            self._raise_if_interrupted_locked()
            messages.append(message)

    def _commit_report(self, content: str) -> str:
        with self._cancel_lock:
            self._raise_if_interrupted_locked()
            self._accepting_cancellation = False
        return content

    @staticmethod
    def _build_prompt(
        objective: str,
        context_files: list[str],
        constraints: list[str],
    ) -> str:
        files_text = "\n".join(f"- {path}" for path in context_files)
        constraints_text = "\n".join(f"- {constraint}" for constraint in constraints)
        return f"""
Delegated objective:
{objective}

Suggested files:
{files_text or "- Discover relevant files using your tools."}

Constraints:
{constraints_text or "- Stay narrowly focused on the objective."}

Return a concise evidence-based report to the parent Forge agent.
Do not speak as though you are responding directly to the end user.
""".strip()
