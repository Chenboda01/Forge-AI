from pathlib import Path

from .tools import Tool


def render_approval_details(tool: Tool, arguments_json: str, working_directory: Path | None) -> str:
    directory = "unavailable" if working_directory is None else str(working_directory)
    network = "allowed" if tool.network_access else "denied"
    modifies_workspace = "yes" if tool.modifies_workspace else "no"
    return (
        f"Arguments:\n{arguments_json}\n\n"
        f"Reason: {tool.description}\n"
        f"Working directory: {directory}\n"
        f"Network: {network}\n"
        f"Timeout: {tool.timeout_seconds:g} seconds\n"
        f"Risk: {tool.risk_level.value}\n"
        f"Modifies workspace: {modifies_workspace}"
    )
