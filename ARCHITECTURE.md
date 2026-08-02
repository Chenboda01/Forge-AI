# Forge Architecture

## 1. Purpose

This document defines the intended architecture of Forge.

Forge is a terminal-based AI coding agent that can inspect repositories, plan changes, delegate focused tasks, propose patches, request approval, run validation, and report evidence.

This document is authoritative for implementation decisions unless a later Architecture Decision Record explicitly changes a section.

The primary implementation goals are:

* Predictable behavior
* Safe execution
* Clear module boundaries
* Provider independence
* Testability
* Recoverable edits
* Limited and observable agent autonomy
* Support for future plugins without destabilizing the core

Forge should not be designed as one large agent class. It should be built as a collection of small systems coordinated by a workflow engine.

---

## 2. Architectural Principles

### 2.1 Workflow First

The workflow engine controls the lifecycle of a task.

The model may recommend actions, select tools, and produce patches, but it must not control permissions, safety boundaries, retries, task limits, or recovery.

The intended flow is:

```text
User Request
    ↓
Task Creation
    ↓
Context Discovery
    ↓
Planning
    ↓
Optional Delegation
    ↓
Patch Proposal
    ↓
Review
    ↓
User Approval
    ↓
Patch Application
    ↓
Validation
    ↓
Final Report
```

Not every request needs every stage.

Read-only questions may stop after inspection and explanation.

Small edits may use a shortened flow:

```text
Inspect → Propose → Approve → Apply → Validate
```

### 2.2 Models Are Untrusted Components

Model responses must be treated as untrusted input.

A model may:

* Produce invalid JSON
* Request unavailable tools
* Use incorrect paths
* Suggest dangerous commands
* Hallucinate successful results
* Ignore project instructions
* Misinterpret tool output
* Attempt unnecessary edits
* Request access to secrets
* Continue indefinitely

Forge must validate every model-originated action before execution.

### 2.3 Evidence Over Confidence

Forge must not consider a task complete merely because a model says it is complete.

Completion should be supported by available evidence, such as:

* Applied patch
* Git diff
* Successful test output
* Lint results
* Type-check results
* File existence
* Command exit codes
* Reviewer report
* Explicitly documented limitations

### 2.4 Least Privilege

Every agent and tool receives only the permissions needed for its role.

Read-only agents must not receive write or shell tools.

Subagents must not receive delegation capability by default.

Shell execution must be restricted by policy and approval.

### 2.5 Reversible Changes

Every file modification must be recoverable.

Forge should create a checkpoint before applying edits.

A failed or interrupted patch must not leave the workspace in an unknown state.

### 2.6 Small Stable Core

The core should include only the systems required for safe coding-agent behavior.

Optional systems such as themes, plugins, language servers, semantic indexing, and external integrations must remain outside the critical execution path.

---

## 3. High-Level System

```text
┌────────────────────────────────────────────────────────────┐
│                         Forge CLI                          │
│                                                            │
│  User Input                                                │
│      ↓                                                     │
│  Terminal UI                                               │
│      ↓                                                     │
│  Session Controller                                        │
│      ↓                                                     │
│  Workflow Engine                                           │
│      ├── Context Manager                                   │
│      ├── Primary Agent                                     │
│      ├── Subagent Manager                                  │
│      ├── Approval Manager                                  │
│      ├── Tool Runtime                                      │
│      ├── Patch Manager                                     │
│      ├── Validation Manager                                │
│      └── Reporting                                         │
│                                                            │
│  Supporting Systems                                        │
│      ├── Provider Layer                                    │
│      ├── Workspace Guard                                   │
│      ├── Git Adapter                                       │
│      ├── Secret Redaction                                  │
│      ├── Configuration                                     │
│      ├── Event Bus                                         │
│      ├── Logging                                           │
│      └── Persistence                                       │
└────────────────────────────────────────────────────────────┘
```

---

## 4. Recommended Package Structure

Forge should use a Python `src` layout.

```text
forge/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── SECURITY.md
├── CONTRIBUTING.md
├── AGENTS.md
├── src/
│   └── forge/
│       ├── __init__.py
│       ├── cli.py
│       ├── app.py
│       │
│       ├── agents/
│       │   ├── base.py
│       │   ├── primary.py
│       │   ├── subagent.py
│       │   ├── registry.py
│       │   ├── manager.py
│       │   └── prompts.py
│       │
│       ├── providers/
│       │   ├── base.py
│       │   ├── client.py
│       │   ├── registry.py
│       │   ├── models.py
│       │   └── errors.py
│       │
│       ├── workflow/
│       │   ├── engine.py
│       │   ├── stages.py
│       │   ├── task.py
│       │   ├── policies.py
│       │   └── results.py
│       │
│       ├── context/
│       │   ├── manager.py
│       │   ├── project.py
│       │   ├── selection.py
│       │   ├── compression.py
│       │   └── instructions.py
│       │
│       ├── tools/
│       │   ├── base.py
│       │   ├── registry.py
│       │   ├── runtime.py
│       │   ├── filesystem.py
│       │   ├── search.py
│       │   ├── shell.py
│       │   ├── git.py
│       │   └── delegation.py
│       │
│       ├── workspace/
│       │   ├── guard.py
│       │   ├── ignore.py
│       │   ├── secrets.py
│       │   └── files.py
│       │
│       ├── patches/
│       │   ├── parser.py
│       │   ├── preview.py
│       │   ├── apply.py
│       │   ├── checkpoint.py
│       │   └── recovery.py
│       │
│       ├── approvals/
│       │   ├── manager.py
│       │   ├── policy.py
│       │   └── models.py
│       │
│       ├── validation/
│       │   ├── manager.py
│       │   ├── commands.py
│       │   ├── results.py
│       │   └── detection.py
│       │
│       ├── sessions/
│       │   ├── manager.py
│       │   ├── storage.py
│       │   ├── history.py
│       │   └── models.py
│       │
│       ├── ui/
│       │   ├── app.py
│       │   ├── events.py
│       │   ├── state.py
│       │   ├── commands.py
│       │   └── widgets/
│       │
│       ├── config/
│       │   ├── loader.py
│       │   ├── models.py
│       │   └── defaults.py
│       │
│       └── diagnostics/
│           ├── doctor.py
│           ├── logging.py
│           └── telemetry.py
│
└── tests/
    ├── unit/
    ├── integration/
    ├── security/
    ├── benchmarks/
    └── fixtures/
```

This structure may evolve, but the separation between workflow, models, tools, workspace safety, patches, approvals, and UI should remain.

---

## 5. Core Data Models

Forge should use explicit typed models rather than passing unstructured dictionaries throughout the codebase.

Dataclasses or Pydantic models may be used.

### 5.1 Task

A task represents one user request.

```python
@dataclass
class Task:
    id: str
    objective: str
    status: TaskStatus
    stage: WorkflowStage
    created_at: datetime
    updated_at: datetime

    mode: AgentMode
    model_profile: str

    plan: list[PlanStep]
    context_files: list[str]
    delegated_tasks: list[str]
    proposed_patches: list[str]
    validation_runs: list[str]

    parent_task_id: str | None = None
```

### 5.2 Tool Request

```python
@dataclass
class ToolRequest:
    id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any]
    requires_approval: bool
```

### 5.3 Tool Result

```python
@dataclass
class ToolResult:
    request_id: str
    status: ToolStatus
    output: str
    exit_code: int | None
    truncated: bool
    started_at: datetime
    completed_at: datetime
```

### 5.4 Patch Proposal

```python
@dataclass
class PatchProposal:
    id: str
    task_id: str
    author_agent: str
    diff: str
    affected_files: list[str]
    summary: str
    approved: bool | None
    applied: bool
```

### 5.5 Validation Result

```python
@dataclass
class ValidationResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    duration_seconds: float
```

### 5.6 Subagent Report

```python
@dataclass
class SubagentReport:
    task_id: str
    agent_name: str
    status: TaskStatus
    summary: str
    findings: list[str]
    files_examined: list[str]
    warnings: list[str]
    token_usage: TokenUsage
```

---

## 6. Workflow Engine

The workflow engine is the central coordinator.

It must not contain provider-specific logic or direct terminal rendering.

Its responsibilities are:

* Create tasks
* Track workflow stages
* Request context discovery
* Invoke the primary agent
* Handle model tool requests
* Delegate focused tasks
* Request approval
* Apply approved patches
* Trigger validation
* Collect evidence
* Decide whether the task is complete
* Produce a final structured result

### 6.1 Workflow Stages

```python
class WorkflowStage(str, Enum):
    CREATED = "created"
    UNDERSTANDING = "understanding"
    INSPECTING = "inspecting"
    PLANNING = "planning"
    DELEGATING = "delegating"
    PROPOSING = "proposing"
    REVIEWING = "reviewing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPLYING = "applying"
    VALIDATING = "validating"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

A task does not have to visit every stage.

### 6.2 Deterministic Responsibilities

The workflow engine, not the model, decides:

* Whether a tool is registered
* Whether a tool call is valid
* Whether approval is required
* Whether a path is allowed
* Whether a command is blocked
* Whether a patch can be applied
* Whether the maximum step count has been reached
* Whether delegation depth is permitted
* Whether validation is required
* Whether a failed task should stop or retry
* Whether a task is eligible for completion

### 6.3 Agent Step Limits

Every model loop must have a hard step limit.

Recommended defaults:

```text
Primary agent: 20 steps
Explore agent: 10 steps
Reviewer agent: 8 steps
Tester agent: 8 steps
Coder agent: 12 steps
Delegation depth: 1
Parallel read-only agents: 3
Parallel writing agents: 0 initially
```

The limits should be configurable but bounded.

---

## 7. Provider Layer

The provider layer normalizes model access.

Forge should initially use a provider abstraction such as LiteLLM, but internal code must not depend directly on provider-specific response objects.

### 7.1 Provider Interface

```python
class ProviderClient(Protocol):
    def complete(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        ...

    def stream(
        self,
        request: CompletionRequest,
    ) -> Iterator[CompletionChunk]:
        ...

    def test_connection(
        self,
        model: ModelConfig,
    ) -> ProviderHealth:
        ...
```

### 7.2 Normalized Response

The provider layer should normalize:

* Assistant text
* Tool calls
* Token usage
* Finish reason
* Provider errors
* Rate limits
* Authentication failures
* Unsupported capabilities

### 7.3 Model Capabilities

Each model should declare capabilities.

```python
@dataclass(frozen=True)
class ModelCapabilities:
    tool_calling: bool
    streaming: bool
    vision: bool
    reasoning: bool
    structured_output: bool
    local: bool
```

Forge must not assume that every model supports every feature.

### 7.4 Provider Failures

Provider errors must be classified.

Examples:

```text
AuthenticationError
RateLimitError
ConnectionError
TimeoutError
UnsupportedFeatureError
InvalidResponseError
ContextLimitError
ProviderUnavailableError
```

Forge should never silently switch providers when a request may change privacy, quality, or cost.

---

## 8. Agent Architecture

### 8.1 Primary Agent

The primary agent:

* Interprets the user request
* Requests relevant context
* Creates or refines the plan
* Delegates focused tasks
* Proposes changes
* Interprets validation results
* Produces the final explanation

It is the only agent that communicates directly with the user during ordinary workflow execution.

### 8.2 Subagents

Initial subagents:

* Explore
* Reviewer
* Tester
* Coder

The initial implementation should enable only Explore and Reviewer.

### 8.3 Isolation

Every subagent receives:

* Its own system prompt
* A focused objective
* Explicit constraints
* Selected context
* A filtered tool registry
* Its own model message history
* A step limit
* A delegation depth

It must not automatically receive:

* The complete parent conversation
* Unrelated files
* Write access
* Shell access
* Secret files
* Delegation tools

### 8.4 Delegation

Delegation should use structured tasks.

```python
@dataclass
class DelegatedTask:
    id: str
    parent_task_id: str
    agent_name: str
    objective: str
    context_files: list[str]
    constraints: list[str]
    expected_output: list[str]
    depth: int
```

Subagent reports are evidence, not unquestionable truth.

The primary agent may disagree with a subagent report when other evidence supports a different conclusion.

### 8.5 Parallelism

Read-only subagents may run concurrently.

Writing agents must not run concurrently against the same workspace.

The first stable version should use synchronous delegation.

Parallel execution may be added only after task isolation and event handling are tested.

---

## 9. Tool System

Tools are controlled capabilities exposed to models.

A tool definition must include:

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    permission: Permission
    risk_level: RiskLevel
    requires_approval: bool
    handler: ToolHandler
```

### 9.1 Initial Tools

Read-only:

```text
list_files
read_file
search_files
git_status
git_diff
git_log
```

Write or execution:

```text
propose_patch
apply_patch
run_command
run_validation
```

Delegation:

```text
delegate_task
```

### 9.2 Tool Runtime

The tool runtime must:

* Validate the tool name
* Validate arguments against schema
* Check agent permissions
* Check approval policy
* Enforce workspace boundaries
* Apply timeouts
* Limit output size
* Redact secrets
* Record execution metadata
* Return structured results
* Emit UI events

### 9.3 Tool Output

Tool output should be size-limited.

Large outputs should be truncated with metadata:

```python
ToolResult(
    output=truncated_text,
    truncated=True,
)
```

The model should be told that truncation occurred.

---

## 10. Workspace Safety

Forge operates inside a workspace root.

Every path must be resolved relative to that root.

### 10.1 Path Rules

Forge must reject:

* Paths outside the workspace
* `..` traversal escaping the root
* Absolute paths outside the root
* Symlink targets outside the root
* Restricted files
* Ignored directories

A safe path check must resolve symlinks before confirming containment.

### 10.2 Ignore Rules

Forge should combine:

* Built-in exclusions
* `.gitignore`
* `.forgeignore`
* Secret-file exclusions

Common exclusions:

```text
.git/
.venv/
node_modules/
dist/
build/
.env
*.pem
*.key
credentials.json
```

Ignored files must not be sent to cloud models unless the user explicitly overrides the policy.

### 10.3 File Limits

Forge should enforce:

* Maximum file size
* Maximum total context size
* Binary-file detection
* UTF-8 decoding rules
* Maximum recursive search output

---

## 11. Context Management

Context selection is a core subsystem.

Forge must not load the entire repository into the model.

### 11.1 Context Sources

Possible sources:

* User-mentioned files
* `FORGE.md`
* Project tree
* Search results
* Symbol references
* Git diff
* Test failures
* Provider configuration
* Previous tool results
* Subagent reports

### 11.2 Selection Strategy

Initial selection should use:

1. Explicit user file mentions
2. Project instructions
3. File-name search
4. Text search
5. Import relationships
6. Files referenced by errors
7. Files changed in Git

Semantic indexing may be added later.

### 11.3 Context Visibility

Users should be able to inspect what Forge is sending to the model.

Planned commands:

```text
/context
/context add PATH
/context remove PATH
/context clear
/context auto
```

### 11.4 Compression

When context grows, Forge may summarize older conversation and tool output.

Compression must preserve:

* User objective
* User constraints
* Current plan
* Pending approvals
* Files changed
* Test failures
* Subagent conclusions
* Unresolved problems

---

## 12. Patch System

Forge should prefer patches over complete file replacement.

### 12.1 Patch Lifecycle

```text
Generate
    ↓
Parse
    ↓
Validate
    ↓
Preview
    ↓
Approve
    ↓
Checkpoint
    ↓
Apply
    ↓
Verify
```

### 12.2 Patch Validation

Before applying a patch, Forge must verify:

* All paths are inside the workspace
* All target files exist when required
* Patch context matches current files
* No restricted files are affected
* The patch is syntactically parseable
* The patch does not exceed configured limits

### 12.3 Atomicity

A multi-file patch should be applied atomically when practical.

If any part fails:

* Restore all affected files from checkpoint
* Mark the patch as failed
* Record the reason
* Display the recovered state

### 12.4 Checkpoints

A checkpoint must be created before every approved edit.

Checkpoint data may contain:

* Original file contents
* File metadata
* Patch ID
* Task ID
* Timestamp
* Git status
* Workspace hash

Commands:

```text
/checkpoint
/undo
/redo
```

---

## 13. Approval System

Approval is a runtime policy, not a model decision.

### 13.1 Approval Scopes

Potential scopes:

```text
Once
For this task
For this session
Always for this project
Deny
```

Permanent approval must not be offered for high-risk operations.

### 13.2 Risk Levels

```python
class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"
```

Examples:

```text
read_file                 READ_ONLY
git_diff                  READ_ONLY
apply_patch               MEDIUM
pytest                    MEDIUM
package installation      HIGH
sudo                      BLOCKED
disk formatting           BLOCKED
```

### 13.3 Modes

Forge should support:

```text
ASK
BUILD
AUTO
ARCHITECT
```

`ASK`:

* Read-only
* No edits
* No command execution

`BUILD`:

* Edits and commands require approval

`AUTO`:

* Low-risk actions may run automatically
* Medium- and high-risk actions still require approval

`ARCHITECT`:

* Analysis and planning only
* No modifications

Default mode should be `BUILD` or `ASK` until safety is mature.

---

## 14. Command Execution

Shell execution is one of the highest-risk systems.

### 14.1 Initial Design

The initial implementation should avoid arbitrary shell strings when possible.

Prefer predefined command arrays:

```python
["pytest", "tests/test_provider.py"]
```

instead of:

```python
"pytest tests/test_provider.py"
```

Avoid shell execution through:

```text
sh -c
bash -c
eval
exec
```

unless explicitly supported and heavily restricted.

### 14.2 Command Policies

Commands should be categorized as:

* Allowed read-only
* Approval required
* High-risk approval required
* Blocked

Blocked examples:

```text
sudo
su
shutdown
reboot
mkfs
fdisk
parted
dd
mount
umount
```

Simple prefix matching is not sufficient for long-term security.

### 14.3 Execution Limits

Every command must have:

* Working directory
* Timeout
* Output limit
* Environment allowlist
* Network policy
* Captured exit code
* Captured stdout
* Captured stderr

---

## 15. Validation System

Validation is separate from generic shell execution.

Forge should detect project type and suggest appropriate checks.

Examples:

Python:

```text
pytest
ruff check .
ruff format --check .
pyright
```

JavaScript or TypeScript:

```text
npm test
npm run lint
npm run typecheck
```

Rust:

```text
cargo test
cargo clippy
cargo fmt --check
```

Validation commands should be explicit, visible, and recorded.

Forge should prefer the smallest relevant test set before running the entire suite.

---

## 16. Git Integration

Forge should use Git when available but must remain usable outside Git repositories.

Initial Git features:

```text
git status
git diff
git diff --cached
git log
git branch
```

Forge must not automatically:

* Commit
* Push
* Force-push
* Reset
* Rebase
* Delete branches

These actions require explicit user requests and approval.

Forge should warn before editing protected branches such as:

```text
main
master
production
```

---

## 17. Session and Persistence

Forge should preserve useful task history.

Recommended project-local structure:

```text
.forge/
├── config.toml
├── sessions/
├── checkpoints/
├── logs/
├── recovery/
└── index/
```

Project-local storage should be ignored by Git by default unless the user chooses otherwise.

### 17.1 Session Data

A session may store:

* Conversation history
* Task states
* Model choices
* Tool calls
* Approvals
* Subagent reports
* Patch proposals
* Validation results
* Usage totals

Secrets must never be stored in session history.

### 17.2 Atomic Writes

Persistence should use atomic writes:

```text
write temporary file
flush
rename temporary file to final file
```

This reduces corruption risk.

---

## 18. Event System

The workflow engine and agents must not directly manipulate terminal widgets.

They should emit structured events.

Example event types:

```text
TASK_STARTED
STAGE_CHANGED
AGENT_STARTED
AGENT_COMPLETED
TOOL_REQUESTED
TOOL_STARTED
TOOL_COMPLETED
APPROVAL_REQUIRED
PATCH_PROPOSED
PATCH_APPLIED
VALIDATION_STARTED
VALIDATION_COMPLETED
TASK_COMPLETED
TASK_FAILED
```

The UI subscribes to these events and updates the display.

This separation allows Forge to support:

* Rich terminal output
* Textual UI
* JSON mode
* CI mode
* Future web interfaces

---

## 19. Terminal Interface

The first interface may use Rich.

The full interactive interface should use Textual.

The UI should emphasize activity rather than empty panels.

Recommended main stream:

```text
User request

◆ Inspecting project
  ├─ Read provider.py
  ├─ Searched for API_KEY
  └─ Found 3 relevant files

◆ Delegated to Explore
  ├─ 4 tool calls
  └─ Completed

◆ Proposed patch
  └─ 2 files changed

◇ Awaiting approval
```

Persistent information may include:

```text
Project
Branch
Mode
Model
Context usage
Active task
Subagent count
Token usage
Estimated cost
```

The UI must remain usable without Nerd Fonts or animations.

---

## 20. Configuration

Configuration precedence should be:

```text
Command-line arguments
    ↓
Project .forge/config.toml
    ↓
User configuration
    ↓
Environment variables
    ↓
Built-in defaults
```

Example user configuration location:

```text
~/.config/forge/config.toml
```

Project instructions should be stored in:

```text
FORGE.md
```

Forge should search from the current directory upward to the repository root for project instructions.

---

## 21. Logging and Diagnostics

Logging must be separate from user-facing output.

Recommended logs:

```text
forge.log
tools.jsonl
provider-errors.log
```

Logs must redact:

* API keys
* Tokens
* Passwords
* Private keys
* Authorization headers
* Secret environment values

The `/doctor` command should check:

* Python version
* Forge version
* Git availability
* Ripgrep availability
* Provider configuration
* Model connectivity
* Ollama availability
* Workspace permissions
* Project configuration
* Recovery state

---

## 22. Testing Strategy

Forge requires strong automated testing.

### 22.1 Unit Tests

Cover:

* Path validation
* Symlink containment
* Tool schemas
* Permission checks
* Command classification
* Secret redaction
* Patch parsing
* Patch rollback
* Configuration loading
* Provider normalization
* Context truncation

### 22.2 Integration Tests

Cover:

* Complete read-only agent loop
* Tool-call execution
* Patch proposal and approval
* Patch application and rollback
* Provider failure handling
* Subagent delegation
* Session recovery

### 22.3 Security Tests

Cover:

* Workspace traversal
* Symlink escape
* Prompt injection inside files
* Restricted file access
* Dangerous command obfuscation
* Secret leakage
* Recursive delegation
* Malformed tool calls
* Excessive output
* Infinite agent loops

### 22.4 Benchmark Tasks

Benchmark fixtures should contain known software tasks.

Examples:

```text
simple arithmetic bug
broken import
missing null check
path traversal vulnerability
failing test
incorrect provider configuration
unsafe command request
multi-file refactor
```

Forge should measure:

* Correct file selection
* Correct tool usage
* Patch correctness
* Test success
* Safety-policy compliance
* Number of model steps
* Token usage
* Task completion rate

---

## 23. Dependency Policy

Forge should avoid unnecessary dependencies.

Dependencies should be chosen for mature functionality that Forge should not recreate.

Likely dependencies:

* Rich
* Textual
* LiteLLM
* Pydantic
* TOML parser
* Git library or Git subprocess adapter
* Diff parser
* Testing tools

Every dependency must be:

* Actively maintained
* Justified
* Version constrained
* Covered by automated tests
* Reviewed for security implications

---

## 24. Initial Implementation Boundary

The first stable implementation should include:

* Python package and CLI
* Rich terminal output
* Provider abstraction
* OpenAI-compatible provider support
* Ollama support
* Read-only tools
* Workspace guard
* Primary agent loop
* Structured tool calls
* Git status and diff
* Basic session state
* Unit tests

The next implementation should add:

* Patch proposals
* Approval flow
* Checkpoints
* Patch application
* Recovery
* Validation

Subagents and Textual should come after the single-agent workflow is reliable.

---

## 25. Explicit Non-Goals for Early Versions

Early Forge versions should not attempt to provide:

* Hundreds of model providers
* Autonomous repository-wide rewrites
* Unrestricted shell access
* Automatic Git pushing
* Deep recursive subagent trees
* Concurrent editing agents
* Full IDE replacement
* Production-grade container sandboxing
* Complete language-server integration
* Cloud-hosted collaboration
* Automatic package installation
* Self-modifying Forge code

These may be reconsidered after the core workflow is stable.

---

## 26. Success Criteria

Forge architecture is successful when it can reliably perform this workflow:

```text
1. Receive a small real coding task.
2. Inspect only relevant project files.
3. Explain the intended change.
4. Produce a valid minimal patch.
5. Show the patch to the user.
6. Apply it only after approval.
7. Run relevant validation.
8. Show exact evidence.
9. Undo the change reliably.
10. Recover cleanly from failure.
```

A beautiful interface, many providers, and advanced subagents are secondary.

The core measure is whether Forge can complete real tasks safely, predictably, and transparently.

---

## 27. Architectural Rule

When implementation choices conflict, use this priority order:

```text
Safety
Correctness
Recoverability
Clarity
Testability
Performance
Convenience
Visual polish
Feature count
```

Forge should remain useful even when the selected model behaves poorly.

The system—not the model—must remain in control.

