# Forge Roadmap

## 1. Purpose

This roadmap defines the planned development sequence for Forge.

Forge should be built through small, testable milestones. Each phase must leave the project in a working state.

The roadmap is intentionally conservative. Safety, correctness, recoverability, and test coverage take priority over feature count.

A phase is complete only when:

* Its required behavior is implemented.
* Automated tests pass.
* Documentation is updated.
* No placeholder implementations remain in the completed scope.
* The application starts and exits cleanly.
* Existing stable behavior has not regressed.

DeepSeek or any other implementation agent must work on one milestone at a time unless explicitly instructed otherwise.

---

## 2. Development Rules

Every milestone must follow this workflow:

```text
Read requirements
    ↓
Inspect existing implementation
    ↓
Create a focused plan
    ↓
Implement only the milestone
    ↓
Add or update tests
    ↓
Run validation
    ↓
Review the diff
    ↓
Report exact results
```

Implementation agents must not:

* Implement future milestones early.
* Rewrite unrelated modules.
* Introduce duplicate abstractions.
* Leave dead code or commented-out alternatives.
* Claim success without running tests.
* Add dependencies without justification.
* Replace working architecture without documenting the decision.
* Store secrets in source code, fixtures, logs, or snapshots.

Each milestone should preferably result in one focused pull request or commit series.

---

# Phase 0 — Project Foundation

## Milestone 0.1 — Repository Structure

### Goal

Create a clean Python project foundation.

### Required Work

* Use Python 3.12 or newer.
* Use a `src` package layout.
* Add `pyproject.toml`.
* Add the `forge` package.
* Add the `forge` command-line entry point.
* Add unit-test structure.
* Add development-tool configuration.
* Add a license.
* Add `.gitignore`.
* Add package metadata.

### Initial Dependencies

Keep runtime dependencies minimal.

Suggested development tools:

* pytest
* pytest-cov
* Ruff
* Pyright

### Acceptance Criteria

```bash
forge --help
```

must run successfully.

```bash
pytest
ruff check .
pyright
```

must pass.

### Non-Goals

* Providers
* AI model calls
* File tools
* Agents
* Patches
* Textual interface

---

## Milestone 0.2 — Basic CLI

### Goal

Create a stable command-line shell for Forge.

### Required Commands

```text
forge --help
forge --version
forge doctor
forge chat
```

At this stage, `forge chat` may display a placeholder interface without contacting a model.

### Required Behavior

* Clean startup banner
* Project-directory detection
* Graceful Ctrl+C handling
* Useful error messages
* No stack trace for expected user errors
* Plain-text fallback for unsupported terminals

### Acceptance Criteria

* Commands return appropriate exit codes.
* CLI parsing has unit tests.
* Ctrl+C exits without corrupt output.
* The package works after installation into a fresh virtual environment.

---

# Phase 1 — Configuration and Providers

## Milestone 1.1 — Typed Configuration

### Goal

Create a predictable configuration system.

### Configuration Sources

Use this precedence order:

```text
Command-line options
Project configuration
User configuration
Environment variables
Built-in defaults
```

### Required Features

* Typed configuration models
* TOML loading
* Environment-variable loading
* Validation errors with clear messages
* User configuration directory support
* Project `.forge/config.toml`
* No secret values displayed in diagnostics

### Planned User Configuration

```text
~/.config/forge/config.toml
```

### Acceptance Criteria

* Precedence rules are tested.
* Invalid configuration fails clearly.
* Unknown keys produce warnings or validation errors.
* Secret values are redacted in representations and logs.

---

## Milestone 1.2 — Provider Abstraction

### Goal

Define Forge’s internal provider interface.

### Required Components

* Completion request model
* Completion response model
* Streaming chunk model
* Tool-call model
* Token-usage model
* Provider health model
* Normalized provider exceptions
* Model-capability declaration

### Required Error Types

```text
AuthenticationError
RateLimitError
ProviderConnectionError
ProviderTimeoutError
UnsupportedFeatureError
InvalidProviderResponseError
ContextLimitError
ProviderUnavailableError
```

### Acceptance Criteria

* Core code does not depend on provider-specific response objects.
* Provider responses can be mocked in tests.
* Invalid and partial provider responses are handled safely.

---

## Milestone 1.3 — Initial Providers

### Goal

Connect Forge to real models.

### Initial Provider Support

* OpenAI-compatible endpoints
* DeepSeek
* OpenAI
* Ollama

DeepSeek and OpenAI may share an OpenAI-compatible adapter where appropriate, while preserving provider-specific configuration and errors.

### Required Features

* API keys from environment variables
* Configurable base URL
* Configurable model name
* Streaming responses
* Connection test
* Timeout handling
* Retry limits
* Model capability checks

### Required Commands

```text
forge providers
forge provider test PROVIDER
forge models
```

### Acceptance Criteria

* Every provider has mocked integration tests.
* Missing API keys produce a clear error.
* Invalid authentication is distinguishable from network failure.
* Ollama connection failure is reported without crashing.
* Forge never prints an API key.

---

# Phase 2 — Read-Only Coding Assistant

## Milestone 2.1 — Workspace Guard

### Goal

Confine Forge to the active project.

### Required Features

* Workspace-root detection
* Safe relative path resolution
* Traversal protection
* Absolute-path protection
* Symlink escape protection
* Restricted-file policy
* Maximum file-size limits
* Binary-file detection

### Security Tests

Test at least:

```text
../ escape
nested ../ escape
absolute external path
symlink to external file
symlink to external directory
restricted .env access
large file
binary file
```

### Acceptance Criteria

No tool can read outside the configured workspace through a supported path operation.

---

## Milestone 2.2 — Ignore System

### Goal

Prevent irrelevant or sensitive files from entering context.

### Required Sources

* Built-in exclusions
* `.gitignore`
* `.forgeignore`
* Secret-file rules

### Default Exclusions

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

### Acceptance Criteria

* Ignored files do not appear in normal file listing or search.
* Explicit override behavior is documented.
* Cloud-model context does not silently include restricted files.

---

## Milestone 2.3 — Read-Only Tools

### Goal

Give the model controlled repository-inspection capabilities.

### Initial Tools

```text
list_files
read_file
search_files
git_status
git_diff
git_log
```

### Tool Runtime Requirements

* JSON-schema argument validation
* Permission validation
* Timeouts
* Output-size limits
* Truncation metadata
* Secret redaction
* Structured results
* Execution logging

### Acceptance Criteria

* Unknown tools are rejected.
* Invalid arguments are rejected.
* Tool output is bounded.
* Tool failures return structured errors.
* Read-only tools cannot modify files.

---

## Milestone 2.4 — Primary Agent Loop

### Goal

Create the first functional coding assistant.

### Required Flow

```text
User message
    ↓
Provider completion
    ↓
Optional tool request
    ↓
Validated tool execution
    ↓
Tool result returned to model
    ↓
Final response
```

### Required Limits

* Maximum model steps
* Maximum tool calls
* Maximum repeated identical tool calls
* Cancellation support
* Provider timeout
* Context-size guard

### Required Modes

Initially:

```text
ASK
ARCHITECT
```

Both modes are read-only.

### Acceptance Criteria

Forge can:

* Answer a question about a small repository.
* Find and read relevant files.
* Explain a bug without editing anything.
* Stop cleanly at its step limit.
* Recover from malformed tool-call JSON.
* Report when a model lacks tool-calling support.

---

# Phase 3 — Context Management

## Milestone 3.1 — Project Discovery

### Goal

Identify repository type and useful project metadata.

### Detect

* Git repository
* Current branch
* Python project
* Node project
* Rust project
* Go project
* Java project
* Common test frameworks
* Common formatters
* Common type checkers
* Existing project instructions

### Relevant Files

```text
pyproject.toml
package.json
Cargo.toml
go.mod
pom.xml
Makefile
Dockerfile
FORGE.md
```

### Acceptance Criteria

* Detection is deterministic.
* Detection does not execute project code.
* Results are visible through diagnostics.

---

## Milestone 3.2 — `FORGE.md` Instructions

### Goal

Support repository-specific agent guidance.

### Required Behavior

* Search from working directory toward repository root.
* Load the closest applicable `FORGE.md`.
* Clearly distinguish project instructions from user instructions.
* Treat instructions in arbitrary source files as untrusted content.
* Include loaded instruction paths in task metadata.

### Acceptance Criteria

* Project instructions affect agent behavior.
* Conflicting instructions are resolved using documented precedence.
* `FORGE.md` cannot override core safety policies.

---

## Milestone 3.3 — Context Controls

### Goal

Make model context visible and controllable.

### Planned Commands

```text
/context
/context add PATH
/context remove PATH
/context clear
/context auto
```

### Required Features

* Token estimate
* File list
* Reason each file was selected
* Context-size limits
* Truncated-file indicators
* Manual pinning

### Acceptance Criteria

Users can determine which files Forge intends to send to a model.

---

## Milestone 3.4 — Context Compression

### Goal

Prevent long tasks from exceeding model limits.

### Preserve

* User objective
* User constraints
* Current plan
* Files inspected
* Pending approvals
* Proposed changes
* Tool failures
* Validation failures
* Unresolved questions

### Acceptance Criteria

* Compression is tested.
* Critical task state is retained.
* The user can see when compression occurred.
* Compression never stores or reveals secrets.

---

# Phase 4 — Safe Editing

## Milestone 4.1 — Patch Proposal Format

### Goal

Allow models to propose changes without directly writing files.

### Required Features

* Unified diff support
* Patch parser
* Affected-file extraction
* Patch-size limits
* Path validation
* Context validation
* Human-readable preview

### Acceptance Criteria

* Malformed patches are rejected.
* External paths are rejected.
* Restricted files are rejected.
* Patch previews match intended modifications.

---

## Milestone 4.2 — Approval System

### Goal

Require runtime approval for modifications.

### Initial Approval Choices

```text
Approve once
Reject
Cancel task
```

Later versions may add task and session scopes.

### Required Modes

```text
ASK
BUILD
ARCHITECT
```

`BUILD` allows proposed edits but requires approval.

### Acceptance Criteria

* Models cannot grant approval.
* Approval requests show exact affected files.
* Rejection does not modify the workspace.
* Approval decisions are recorded without storing secrets.

---

## Milestone 4.3 — Checkpoints

### Goal

Make every edit reversible.

### Required Behavior

Before applying a patch:

* Capture affected file contents.
* Capture whether each file existed.
* Capture task ID and patch ID.
* Write checkpoint data atomically.

### Required Commands

```text
/checkpoint
/undo
```

### Acceptance Criteria

* Existing files can be restored.
* Newly created files can be removed during undo.
* Deleted files can be restored.
* Checkpoints survive a process restart.
* Incomplete checkpoints are detected.

---

## Milestone 4.4 — Atomic Patch Application

### Goal

Apply approved patches without leaving partial changes.

### Required Flow

```text
Validate patch
Create checkpoint
Apply in temporary state
Verify results
Commit file replacements atomically
Record success
```

On failure:

```text
Restore checkpoint
Record failure
Report recovered state
```

### Acceptance Criteria

* Multi-file patch failure restores all files.
* Concurrent writes are prevented.
* Current file content is rechecked immediately before applying.
* Patch application has integration tests.

---

## Milestone 4.5 — Git Diff Review

### Goal

Show evidence of the applied change.

### Required Output

* Files changed
* Lines added and removed
* Full or summarized Git diff
* Checkpoint ID
* Whether unrelated pre-existing changes were present

### Acceptance Criteria

Forge never claims that only its files changed unless verified.

---

# Phase 5 — Validation and Reporting

## Milestone 5.1 — Validation Detection

### Goal

Identify appropriate project checks.

### Examples

Python:

```text
pytest
ruff check .
pyright
```

Node:

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

### Required Behavior

* Detect commands from project configuration.
* Do not install missing tools automatically.
* Prefer targeted tests when possible.
* Show commands before execution.

---

## Milestone 5.2 — Restricted Command Execution

### Goal

Run approved validation commands safely.

### Required Controls

* Argument-array execution
* No shell by default
* Working-directory lock
* Timeout
* Output limits
* Environment allowlist
* Exit-code capture
* Network policy
* Command classification

### Block Initially

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
sh -c
bash -c
```

### Acceptance Criteria

* Blocked commands cannot be invoked through the model tool interface.
* Timeout terminates the process.
* Output truncation is reported.
* Command failures do not crash Forge.

---

## Milestone 5.3 — Validation Results

### Goal

Present exact evidence after an edit.

### Required Report

```text
Command
Exit code
Duration
Passed or failed
Important output
Truncation status
```

### Acceptance Criteria

Forge distinguishes:

* Tests passed.
* Tests failed.
* Tests were not run.
* Tests could not run.
* Test output was incomplete.

Forge must never convert “not run” into “passed.”

---

## Milestone 5.4 — Final Task Report

### Goal

Produce a reliable completion summary.

### Required Sections

```text
Summary
Files inspected
Files changed
Patch status
Validation performed
Known limitations
Warnings
Undo information
```

### Acceptance Criteria

Every factual claim in the report is supported by recorded runtime state.

---

# Phase 6 — Sessions and Recovery

## Milestone 6.1 — Session Storage

### Goal

Persist conversations and task state.

### Store

* Task metadata
* User messages
* Normalized model responses
* Tool requests and results
* Approval decisions
* Patch metadata
* Validation results
* Subagent reports
* Usage totals

### Do Not Store

* API keys
* Authorization headers
* Unredacted secrets
* Hidden provider credentials

### Acceptance Criteria

Sessions can be reopened after restart.

---

## Milestone 6.2 — Recovery

### Goal

Recover safely after crashes or interrupted edits.

### Required Behavior

On startup, detect:

* Interrupted task
* Incomplete checkpoint
* Partial patch transaction
* Corrupted session file
* Temporary persistence files

### Recovery Options

```text
Inspect
Restore
Resume
Discard recovery data
```

### Acceptance Criteria

A simulated crash during patch application does not permanently corrupt the workspace.

---

## Milestone 6.3 — History Commands

### Planned Commands

```text
/sessions
/resume SESSION_ID
/history
```

### Acceptance Criteria

* Session listing is fast.
* Corrupted sessions do not prevent startup.
* History output is redacted.

---

# Phase 7 — Subagents

Subagents should not be implemented until the single-agent workflow is reliable.

## Milestone 7.1 — Explore Subagent

### Goal

Add focused read-only delegation.

### Permissions

```text
list_files
read_file
search_files
git_status
git_diff
git_log
```

### Restrictions

* No editing
* No shell
* No delegation
* Separate message history
* Fixed step limit
* Focused objective

### Acceptance Criteria

The primary agent can delegate a repository investigation and receive a concise structured report.

---

## Milestone 7.2 — Reviewer Subagent

### Goal

Review a proposed or applied diff independently.

### Required Output

```text
Critical issues
Warnings
Suggestions
Missing tests
Verdict
```

### Restrictions

* Read-only
* No direct user communication
* No delegation
* No patch application

### Acceptance Criteria

The reviewer can inspect current code and the patch without changing files.

---

## Milestone 7.3 — Visible Delegation

### Goal

Show subagent activity in the terminal stream.

### Example

```text
◆ Delegated to Explore
  ├─ Searching authentication code
  ├─ Read 4 files
  └─ Completed with 3 findings
```

### Acceptance Criteria

* Users can see when delegation begins and ends.
* Users can inspect the final subagent report.
* Internal reasoning transcripts are not required for normal display.

---

## Milestone 7.4 — Tester Subagent

### Goal

Separate test selection and diagnosis from the primary agent.

### Permissions

* Read-only repository tools
* Restricted validation tool

### Acceptance Criteria

The tester reports exact commands, exit codes, failures, and likely causes.

---

## Milestone 7.5 — Coder Subagent

### Goal

Allow narrowly scoped implementation delegation.

### Initial Restriction

The coder should propose a patch rather than directly write files.

### Required Flow

```text
Coder proposes patch
Reviewer inspects patch
Primary agent presents patch
User approves
Runtime applies patch
Tester validates
```

### Acceptance Criteria

* No concurrent writer agents.
* The primary workflow remains responsible for approval and application.
* The coder cannot bypass workspace or patch validation.

---

# Phase 8 — Textual Interface

## Milestone 8.1 — Event System

### Goal

Separate core logic from rendering.

### Required Events

```text
TASK_STARTED
STAGE_CHANGED
AGENT_STARTED
TOOL_STARTED
TOOL_COMPLETED
PATCH_PROPOSED
APPROVAL_REQUIRED
VALIDATION_COMPLETED
TASK_COMPLETED
TASK_FAILED
```

### Acceptance Criteria

The existing CLI can render events without importing workflow internals.

---

## Milestone 8.2 — Textual Application

### Goal

Create a richer interactive terminal interface.

### Recommended Areas

* Main activity stream
* Input box
* Project and branch status
* Current mode and model
* Active task
* Agent activity
* Context usage
* Token and cost usage

Avoid filling the screen with permanently empty panels.

### Acceptance Criteria

* The interface remains responsive during model streaming.
* Ctrl+C and cancellation work.
* It degrades gracefully in small terminals.
* Core behavior remains usable through the simpler CLI.

---

## Milestone 8.3 — Autocomplete and Mentions

### Planned Features

```text
Slash-command completion
File-path completion
Model completion
@explore
@reviewer
@tester
```

### Acceptance Criteria

Invalid commands and agent names produce useful suggestions.

---

# Phase 9 — Hardening

## Milestone 9.1 — Security Audit

### Review

* Path handling
* Symlinks
* Command policies
* Secret redaction
* Logging
* Session storage
* Tool schemas
* Prompt injection
* Patch application
* Subagent permissions
* Provider errors

### Acceptance Criteria

All documented security tests pass.

---

## Milestone 9.2 — Benchmarks

### Goal

Measure actual coding-agent performance.

### Initial Benchmark Cases

```text
Simple arithmetic bug
Broken import
Missing null check
Incorrect configuration
Path traversal vulnerability
Failing unit test
Unsafe command request
Small multi-file change
```

### Metrics

* Task completion
* Correct file selection
* Correct patch
* Tests passed
* Safety violations
* Model steps
* Tool calls
* Token usage
* Duration

### Acceptance Criteria

Benchmark results are reproducible and stored without including provider secrets.

---

## Milestone 9.3 — Cross-Platform Testing

### Initial Support Target

* Linux

### Later Targets

* macOS
* Windows

### Acceptance Criteria

Platform support is documented accurately. Unsupported systems must not be presented as fully supported.

---

## Milestone 9.4 — Packaging and Release

### Required Work

* Versioning policy
* Changelog
* Build validation
* Package publishing workflow
* Release artifacts
* Installation documentation
* Upgrade documentation

### Acceptance Criteria

Forge installs into a clean environment and runs its smoke tests.

---

# Phase 10 — Forge 1.0

Forge 1.0 should not be declared merely because many features exist.

## Required 1.0 Capabilities

Forge must reliably:

1. Start and configure itself.
2. Connect to supported providers.
3. Inspect a repository safely.
4. Follow project instructions.
5. Select relevant context.
6. Propose a valid minimal patch.
7. Show the patch clearly.
8. Require approval.
9. Create a checkpoint.
10. Apply the patch atomically.
11. Run appropriate validation.
12. Report exact evidence.
13. Undo the change.
14. Recover after interruption.
15. Delegate read-only exploration and review safely.

## Reliability Requirements

Before 1.0:

* Security tests pass.
* Integration tests pass.
* Benchmark regressions are tracked.
* No known data-loss bug remains open.
* No known workspace-escape bug remains open.
* Secrets are redacted from logs and sessions.
* Documentation matches actual behavior.
* Provider failures are handled gracefully.
* Unsupported features are clearly labeled.

---

# Future Work After 1.0

These features are intentionally deferred.

## Possible Future Features

* Additional providers
* Language-server integration
* Symbol indexing
* Semantic repository search
* Git worktrees
* Plugin system
* Reusable skills
* Project hooks
* CI review mode
* Image and screenshot context
* Remote development support
* Container sandboxing
* Network permission controls
* Multi-user collaboration
* Web interface
* Parallel read-only agents
* Advanced cost budgeting

Each future feature must justify its complexity and security impact.

---

# Version Targets

The version numbers below are directional rather than strict promises.

## Forge 0.1

```text
Project foundation
CLI
Configuration
Provider abstraction
OpenAI-compatible API
DeepSeek
OpenAI
Ollama
```

## Forge 0.2

```text
Workspace guard
Ignore rules
Read-only tools
Primary agent loop
ASK and ARCHITECT modes
```

## Forge 0.3

```text
Project discovery
FORGE.md
Context controls
Context limits
```

## Forge 0.4

```text
Patch proposals
Approval
Checkpoints
Atomic application
Undo
```

## Forge 0.5

```text
Validation detection
Restricted commands
Final reports
Git evidence
```

## Forge 0.6

```text
Sessions
Recovery
History
Diagnostics
```

## Forge 0.7

```text
Explore subagent
Reviewer subagent
Visible delegation
```

## Forge 0.8

```text
Tester subagent
Coder patch proposals
Improved orchestration
```

## Forge 0.9

```text
Textual interface
Autocomplete
Performance work
Security hardening
Benchmarks
```

## Forge 1.0

```text
Stable
Documented
Recoverable
Tested
Secure by default
Suitable for real daily coding tasks
```

---

# Definition of Done

A milestone is complete only when all applicable conditions are satisfied:

* Implementation matches the milestone scope.
* Public interfaces have type annotations.
* Unit tests cover normal and failure paths.
* Integration tests cover major workflows.
* Security-sensitive behavior has dedicated tests.
* Ruff passes.
* Pyright passes.
* Pytest passes.
* Documentation is updated.
* No secrets or credentials are present.
* No placeholder or fake implementation remains.
* Error messages are actionable.
* Existing functionality still works.
* The implementation agent reports exact commands and results.

---

# Priority Rule

When roadmap items conflict, use this priority:

```text
Safety
Correctness
Recoverability
Testability
Clarity
Compatibility
Performance
Convenience
Visual polish
Feature count
```

Forge should become trustworthy before it becomes large.

