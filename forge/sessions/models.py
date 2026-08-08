from dataclasses import dataclass

from forge.validation import ValidationRecord


@dataclass(frozen=True, slots=True)
class SessionStorageError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class TaskStateRecord:
    id: str
    objective: str
    status: str


@dataclass(frozen=True, slots=True)
class SessionMessageRecord:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ToolExchangeRecord:
    name: str
    arguments: str
    result: str


@dataclass(frozen=True, slots=True)
class ApprovalDecisionRecord:
    tool_name: str
    arguments: str
    approved: bool


@dataclass(frozen=True, slots=True)
class PatchSessionRecord:
    id: str
    status: str
    affected_files: tuple[str, ...]
    checkpoint_id: str | None


@dataclass(frozen=True, slots=True)
class SubagentSessionRecord:
    agent_name: str
    status: str
    summary: str


@dataclass(frozen=True, slots=True)
class UsageRecord:
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    id: str
    created_at: str
    task: TaskStateRecord
    messages: tuple[SessionMessageRecord, ...]
    tools: tuple[ToolExchangeRecord, ...]
    approvals: tuple[ApprovalDecisionRecord, ...]
    patches: tuple[PatchSessionRecord, ...]
    validations: tuple[ValidationRecord, ...]
    subagents: tuple[SubagentSessionRecord, ...]
    usage: UsageRecord
