import os
from pathlib import Path

from dotenv import load_dotenv

from .models import DEFAULT_MODEL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


def reload_env() -> None:
    """Re-read .env file — picks up changes made after startup."""
    load_dotenv(ENV_FILE, override=True)


def get_api_key(variable_name: str | None) -> str | None:
    if variable_name is None:
        return None

    value = os.getenv(variable_name)

    if value:
        return value.strip()

    return None


def get_default_model() -> str:
    return os.getenv("FORGE_MODEL", DEFAULT_MODEL)
