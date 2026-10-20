from pathlib import Path

from forge.forge_core.redaction import redact_text, register_secret
from forge.forge_core.sessions import SessionManager
from forge.forge_core.tools import Tool, ToolRegistry


def test_registered_arbitrary_credential_is_redacted_from_text() -> None:
    # Given: a configured credential with no provider-specific prefix
    secret = "synthetic-arbitrary-credential-49281"
    register_secret(secret)

    # When: the value appears inside user-visible diagnostic text
    result = redact_text(f"request failed with credential {secret}")

    # Then: centralized value-based redaction removes it
    assert secret not in result
    assert "[REDACTED]" in result


def test_registered_credential_is_redacted_from_tool_output() -> None:
    # Given: a tool returns a configured arbitrary credential
    secret = "synthetic-tool-credential-71529"
    register_secret(secret)
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="credential_output",
            description="synthetic credential output",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda: f"diagnostic={secret}",
        )
    )

    # When: the result crosses the tool runtime boundary
    output = registry.execute("credential_output", {})

    # Then: the configured value is absent
    assert secret not in output
    assert "[REDACTED]" in output


def test_registered_credential_is_redacted_from_saved_session(tmp_path: Path) -> None:
    # Given: a conversation contains a configured arbitrary credential
    secret = "synthetic-session-credential-83014"
    register_secret(secret)
    manager = SessionManager(tmp_path)

    # When: Forge saves the session
    meta = manager.save(
        messages=[{"role": "user", "content": f"credential {secret}"}],
        model="test/model",
    )

    # Then: neither serialized nor restored state contains the value
    persisted = (manager.root / f"{meta.id}.json").read_text(encoding="utf-8")
    assert secret not in persisted
    loaded = manager.load(meta.id)
    assert loaded is not None
    assert secret not in str(loaded)
