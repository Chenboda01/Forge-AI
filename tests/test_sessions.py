import json
from pathlib import Path

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


def test_session_save_redacts_bare_and_quoted_credentials(tmp_path: Path) -> None:
    # Given: synthetic provider credentials without a label and inside a quoted assignment
    bare_secret = "sk-proj-syntheticcredential1234567890"
    quoted_secret = "quoted-synthetic-secret"
    messages = [
        {
            "role": "user",
            "content": f'raw {bare_secret}\nOPENAI_API_KEY="{quoted_secret}"',
        }
    ]
    manager = SessionManager(tmp_path)

    # When: Forge persists the conversation
    session = manager.save(messages, "test/model")
    persisted = (manager.root / f"{session.id}.json").read_text(encoding="utf-8")

    # Then: neither credential representation reaches disk
    assert bare_secret not in persisted
    assert quoted_secret not in persisted
    data = json.loads(persisted)
    assert data["messages"][0]["content"] == ('raw [REDACTED]\nOPENAI_API_KEY="[REDACTED]"')
    assert "[REDACTED]" in data["meta"]["name"]


def test_session_identifiers_cannot_escape_session_storage(tmp_path: Path) -> None:
    # Given: valid-looking session JSON outside Forge's session directory
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "meta": {"input_tokens": 0, "output_tokens": 0},
                "messages": [{"role": "user", "content": "outside"}],
            }
        ),
        encoding="utf-8",
    )
    manager = SessionManager(tmp_path)

    # When: user-controlled session identifiers attempt path traversal
    loaded = manager.load("../../outside")
    resumed = manager.resume_data("../../outside")

    # Then: neither legacy loading path reads outside the session directory
    assert loaded is None
    assert resumed is None


def test_session_listing_ignores_external_record_symlink(tmp_path: Path) -> None:
    # Given: a session record redirected to valid-looking metadata outside Forge state
    manager = SessionManager(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "meta": {
                    "id": "external123",
                    "name": "external",
                    "created_at": "2026-09-13T00:00:00+00:00",
                    "updated_at": "2026-09-13T00:00:00+00:00",
                    "model": "test/model",
                    "message_count": 0,
                },
                "messages": [],
            }
        ),
        encoding="utf-8",
    )
    (manager.root / "external123.json").symlink_to(outside)

    # When: Forge lists persisted sessions
    sessions = manager.list_sessions()

    # Then: external metadata does not become trusted session state
    assert sessions == []


def test_session_load_rejects_symlink_replacement_after_validation(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: a persisted session replaced with an external record after containment validation
    manager = SessionManager(tmp_path)
    session = manager.save([{"role": "user", "content": "inside"}], "test/model")
    target = manager.root / f"{session.id}.json"
    outside = tmp_path / "outside-session.json"
    outside.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    original_exists = Path.exists

    def replace_before_read(path: Path) -> bool:
        if path == target:
            target.unlink()
            target.symlink_to(outside)
            return True
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", replace_before_read)

    # When / Then: the changed path produces no trusted session data
    assert manager.load(session.id) is None
