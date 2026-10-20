from threading import Lock
from uuid import uuid4

from forge.checkpoints import CheckpointManager
from forge.patches import (
    PatchApplicationError,
    PatchApplier,
    PatchError,
    parse_patch,
    render_preview,
)

from .tools import Permission, RiskLevel, Tool, ToolError, ToolRegistry
from .workspace import Workspace


def register_patch_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    applier = PatchApplier(workspace, CheckpointManager(workspace))
    preview_lock = Lock()
    previewed_patch: str | None = None

    def propose_patch(patch: str) -> str:
        nonlocal previewed_patch
        try:
            proposal = parse_patch(patch, workspace)
        except PatchError as error:
            raise ToolError(f"Patch rejected: {error}") from error
        with preview_lock:
            previewed_patch = patch
        return render_preview(proposal)

    def apply_patch(patch: str) -> str:
        nonlocal previewed_patch
        with preview_lock:
            if patch != previewed_patch:
                raise ToolError(
                    "Patch application rejected: patch must exactly match the most recent preview."
                )
            previewed_patch = None
        try:
            record = applier.apply(
                patch,
                task_id=uuid4().hex[:12],
                patch_id=uuid4().hex[:12],
            )
        except PatchApplicationError as error:
            raise ToolError(f"Patch application rejected: {error}") from error
        return (
            f"Applied {len(record.affected_files)} file(s).\n"
            f"Checkpoint: {record.checkpoint_id}\n"
            f"Transaction: {record.transaction_id}"
        )

    registry.register(
        Tool(
            name="propose_patch",
            description=(
                "Parse and preview a unified diff proposal without modifying the workspace."
            ),
            parameters={
                "type": "object",
                "properties": {"patch": {"type": "string"}},
                "required": ["patch"],
                "additionalProperties": False,
            },
            handler=propose_patch,
            permission=Permission.PROPOSE_PATCH,
            risk_level=RiskLevel.LOW,
            timeout_seconds=20,
            max_output_bytes=30_000,
        )
    )
    registry.register(
        Tool(
            name="apply_patch",
            description="Apply one exact unified diff atomically after trusted user approval.",
            parameters={
                "type": "object",
                "properties": {"patch": {"type": "string"}},
                "required": ["patch"],
                "additionalProperties": False,
            },
            handler=apply_patch,
            requires_approval=True,
            permission=Permission.APPLY_PATCH,
            risk_level=RiskLevel.MEDIUM,
            modifies_workspace=True,
            timeout_seconds=60,
            max_output_bytes=30_000,
        )
    )
