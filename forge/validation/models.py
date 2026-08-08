from dataclasses import dataclass
from enum import StrEnum


class ValidationKind(StrEnum):
    TEST = "test"
    LINT = "lint"
    FORMAT = "format"
    TYPE_CHECK = "type_check"


class CommandClassification(StrEnum):
    APPROVAL_REQUIRED = "approval_required"


class NetworkPolicy(StrEnum):
    DENIED = "denied"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    NOT_RUN = "not_run"
    COULD_NOT_RUN = "could_not_run"


@dataclass(frozen=True, slots=True)
class ValidationCommand:
    arguments: tuple[str, ...]
    kind: ValidationKind
    source: str
    targeted: bool = False


@dataclass(frozen=True, slots=True)
class ValidationDetectionError(Exception):
    source: str
    detail: str

    def __str__(self) -> str:
        return f"Could not read validation configuration from {self.source}: {self.detail}"


@dataclass(frozen=True, slots=True)
class CommandPolicyError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class CommandExecutionError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class CommandRequest:
    arguments: tuple[str, ...]
    timeout_seconds: float = 60
    output_limit_bytes: int = 30_000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise CommandPolicyError("Command timeout must be positive.")
        if self.output_limit_bytes <= 0:
            raise CommandPolicyError("Command output limit must be positive.")


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    arguments: tuple[str, ...]
    classification: CommandClassification
    network_policy: NetworkPolicy
    exit_code: int
    output: str
    output_bytes: int
    truncated: bool
    timed_out: bool
    passed: bool
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    id: str
    created_at: str
    arguments: tuple[str, ...]
    status: ValidationStatus
    exit_code: int | None
    duration_seconds: float | None
    output: str
    output_bytes: int
    truncated: bool
    detail: str
