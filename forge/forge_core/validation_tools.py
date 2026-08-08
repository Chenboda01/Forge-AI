from forge.validation import ValidationDetectionError, detect_validation, render_validation

from .tools import Tool, ToolError, ToolRegistry
from .workspace import Workspace


def register_validation_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    def detect(changed_files: list[str] | None = None) -> str:
        try:
            commands = detect_validation(workspace.root, tuple(changed_files or ()))
        except ValidationDetectionError as error:
            raise ToolError(str(error)) from error
        return render_validation(commands)

    registry.register(
        Tool(
            name="detect_validation",
            description=(
                "Show configured validation command argument arrays without executing them."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "changed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    }
                },
                "additionalProperties": False,
            },
            handler=detect,
        )
    )
