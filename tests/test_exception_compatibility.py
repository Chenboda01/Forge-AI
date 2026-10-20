from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from forge.checkpoints import CheckpointError
from forge.forge_core.agent_limits import AgentLimitError
from forge.forge_core.config import ConfigurationError
from forge.forge_core.safe_io import SafeReadError, SafeWriteError
from forge.patches import PatchApplicationError, PatchError, PatchErrorCode
from forge.recovery import RecoveryError
from forge.sessions import SessionStorageError
from forge.validation import (
    CommandExecutionError,
    CommandPolicyError,
    ValidationDetectionError,
)


@contextmanager
def exception_boundary() -> Iterator[None]:
    yield


@pytest.mark.parametrize(
    "error",
    (
        AgentLimitError("limit"),
        CheckpointError("checkpoint"),
        CommandExecutionError("execution"),
        CommandPolicyError("policy"),
        ConfigurationError("source", "configuration"),
        PatchApplicationError("application"),
        PatchError(PatchErrorCode.MALFORMED, "patch"),
        RecoveryError("recovery"),
        SafeReadError(Path("read")),
        SafeWriteError(Path("write")),
        SessionStorageError("session"),
        ValidationDetectionError("source", "validation"),
    ),
    ids=lambda error: type(error).__name__,
)
def test_typed_exception_survives_context_manager_propagation(error: Exception) -> None:
    # Given: a typed Forge error crossing a standard generator context-manager boundary
    expected_type = type(error)

    # When / Then: traceback restoration preserves the original exception type
    with pytest.raises(expected_type), exception_boundary():
        raise error
