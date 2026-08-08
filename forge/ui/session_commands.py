from forge.forge_core.redaction import redact_text

from .state import ForgeRuntime


def sessions_text(runtime: ForgeRuntime | None) -> str:
    if runtime is None:
        return "Sessions\nNo session storage is connected."
    sessions = runtime.sessions.list_sessions()
    if not sessions:
        return "Sessions\nNo saved sessions."
    return "Sessions\n" + "\n".join(
        f"{session.id}  {session.name}  {session.total_tokens:,} tokens" for session in sessions
    )


def resume_session(runtime: ForgeRuntime | None, session_id: str) -> str:
    if runtime is None:
        return "No session storage is connected."
    if not session_id:
        return "Usage: /resume SESSION_ID"
    data = runtime.sessions.resume_data(session_id)
    if data is None:
        return f"Session not found or corrupt: {session_id}"
    runtime.agent.reset()
    runtime.agent.messages.extend(
        {"role": message.role, "content": message.content} for message in data.messages
    )
    runtime.agent.input_tokens = data.input_tokens
    runtime.agent.output_tokens = data.output_tokens
    return f"Resumed session {session_id}."


def history_text(runtime: ForgeRuntime | None) -> str:
    if runtime is None:
        return "History\nNo model runtime is connected."
    entries = [
        f"{message['role']}: {redact_text(message['content'])}"
        for message in runtime.agent.messages
        if message.get("role") in {"user", "assistant"}
        and isinstance(message.get("content"), str)
        and message["content"]
    ]
    return "History\n" + ("\n".join(entries) if entries else "No conversation history.")
