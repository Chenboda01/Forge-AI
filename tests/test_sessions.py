import json

from forge.forge_core.sessions import SessionManager


def test_session_save_redacts_secrets_before_persistence(tmp_path) -> None:
    # Given: a conversation containing synthetic credentials in nested message data
    secret = "sk-test-not-real"
    messages = [
        {
            "role": "user",
            "content": f"OPENAI_API_KEY={secret}\nAuthorization: Bearer token-test-not-real",
            "metadata": {"password": "password-test-not-real"},
        }
    ]
    manager = SessionManager(tmp_path)

    # When: Forge saves the session
    session = manager.save(messages, "test/model")
    persisted = (manager.root / f"{session.id}.json").read_text(encoding="utf-8")
    data = json.loads(persisted)

    # Then: no raw credential value reaches disk
    assert secret not in persisted
    assert "token-test-not-real" not in persisted
    assert "password-test-not-real" not in persisted
    assert "[REDACTED]" in persisted
    assert data["messages"][0]["role"] == "user"
