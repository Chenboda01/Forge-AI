from .state import ForgeRuntime


def recovery_text(runtime: ForgeRuntime | None) -> str:
    if runtime is None:
        return "Recovery\nNo recovery service is connected."
    if not runtime.recovery.items:
        return "Recovery\nNo recovery items."
    return "Recovery\n" + "\n".join(
        f"{item.id}  {item.kind.value}  {item.detail}" for item in runtime.recovery.items
    )


def recover(runtime: ForgeRuntime | None, request: str) -> str:
    if runtime is None:
        return "No recovery service is connected."
    action, _, item_id = request.partition(" ")
    if not action or not item_id:
        return "Usage: /recover [restore|resume|discard] ID"
    if action == "restore":
        checkpoint_id = runtime.recovery.restore(item_id)
        return f"Restored checkpoint {checkpoint_id}."
    if action == "resume":
        session_id = runtime.recovery.resume(item_id)
        return f"Session {session_id} is available to resume."
    if action == "discard":
        runtime.recovery.discard(item_id)
        return f"Discarded recovery item {item_id}."
    return "Usage: /recover [restore|resume|discard] ID"
