from .subagents import SUBAGENTS, SubagentError, SubagentRunner
from .tools import Tool, ToolRegistry


def register_delegation_tool(registry: ToolRegistry, runner: SubagentRunner) -> None:
    """Expose read-only subagent delegation only to the primary agent registry."""

    def delegate_task(
        agent: str,
        objective: str,
        context_files: list[str] | None = None,
        constraints: list[str] | None = None,
    ) -> str:
        try:
            report = runner.run(
                agent_name=agent,
                objective=objective,
                context_files=context_files,
                constraints=constraints,
            )
        except SubagentError as error:
            return f"Subagent failed: {error}"
        return f"Subagent: {agent}\nStatus: completed\n\n{report}"

    registry.register(
        Tool(
            name="delegate_task",
            description=(
                "Delegate a focused read-only investigation or review "
                "to a specialized Forge subagent."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "enum": sorted(SUBAGENTS)},
                    "objective": {"type": "string"},
                    "context_files": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["agent", "objective"],
                "additionalProperties": False,
            },
            handler=delegate_task,
            requires_approval=False,
        )
    )
