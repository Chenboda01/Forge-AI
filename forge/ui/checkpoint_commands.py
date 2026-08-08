from forge.checkpoints import CheckpointError

from .state import ForgeRuntime


def checkpoint_text(runtime: ForgeRuntime | None) -> str:
    if runtime is None:
        return "Checkpoints\nNo checkpoint storage is connected."
    incomplete = runtime.checkpoints.incomplete_checkpoints()
    latest = runtime.checkpoints.latest()
    lines = ["Checkpoints"]
    if latest is None:
        lines.append("No checkpoints.")
    else:
        lines.append(f"Latest: {latest.id}  task={latest.task_id}  patch={latest.patch_id}")
        lines.extend(f"- {file.path}" for file in latest.files)
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
