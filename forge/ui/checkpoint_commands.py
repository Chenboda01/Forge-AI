from forge.checkpoints import CheckpointError

from .state import ForgeRuntime


def checkpoint_text(runtime: ForgeRuntime | None) -> str:
    if runtime is None:
        return "Checkpoints\nNo checkpoint storage is connected."
    incomplete = runtime.checkpoints.incomplete_checkpoints()
    try:
        records = runtime.checkpoints.list_checkpoints()
    except CheckpointError as error:
        return f"Checkpoints\n{error}"
    lines = ["Checkpoints"]
    if not records:
        lines.append("No checkpoints.")
    else:
        lines.extend(
            f"{record.id}  {record.created_at}  task={record.task_id}  "
            f"patch={record.patch_id}  {len(record.files)} file(s)"
            for record in records
        )
    lines.extend(f"Incomplete: {name}" for name in incomplete)
    return "\n".join(lines)


def undo_checkpoint(runtime: ForgeRuntime | None, checkpoint_id: str) -> str:
    if runtime is None:
        return "No checkpoint storage is connected."
    selected = checkpoint_id.strip()
    if not selected:
        latest = runtime.checkpoints.latest()
        if latest is None:
            return "No checkpoint is available to restore."
        selected = latest.id
    try:
        record = runtime.checkpoints.undo(selected)
    except CheckpointError as error:
        return str(error)
    return f"Restored checkpoint {record.id}."
