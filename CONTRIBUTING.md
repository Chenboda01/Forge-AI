# Contributing to Forge

Thank you for your interest in contributing to Forge.

Forge is a terminal-based AI coding agent designed around safe, visible, reversible, and evidence-based workflows.

Contributions are welcome in many forms, including:

* Bug reports
* Documentation improvements
* Test cases
* Provider integrations
* Terminal interface improvements
* Security reviews
* Performance improvements
* Architecture discussions
* Benchmark tasks
* Focused feature implementations

Forge is intentionally developed in small milestones. Contributions should strengthen the current architecture rather than rapidly expand the feature count.

---

## 1. Project Principles

All contributions should support Forge’s core principles.

### Workflow First

Forge follows a controlled workflow.

Models may propose actions, but the runtime controls:

* Permissions
* Approvals
* Workspace boundaries
* Tool execution
* Patch application
* Validation
* Recovery
* Completion

### Safety Before Convenience

Forge should prefer a visible, reversible, approved action over a faster but less controlled action.

### Evidence Over Confidence

Forge must not claim success based only on model output.

Important claims should be supported by runtime evidence such as:

* Tool results
* Applied diffs
* Exit codes
* Test output
* Checkpoint records
* Validation reports

### Least Privilege

Agents and tools should receive only the permissions they need.

### Small, Reviewable Changes

Focused changes are easier to test, review, understand, and revert.

Large unrelated rewrites are discouraged.

### Honest Limitations

Forge should clearly distinguish:

* Implemented behavior
* Experimental behavior
* Planned behavior
* Unsupported behavior
* Failed validation
* Validation that was not run

---

## 2. Before Contributing

Before starting significant work:

1. Read `README.md`.
2. Read `ARCHITECTURE.md`.
3. Read `ROADMAP.md`.
4. Read `SECURITY.md`.
5. Read `AGENTS.md`.
6. Search existing issues and pull requests.
7. Confirm that the work fits the current development phase.

For small fixes, opening an issue first may not be necessary.

For major features, architectural changes, new dependencies, provider integrations, security-sensitive behavior, or broad refactors, start with a discussion or design issue before implementation.

This helps avoid duplicated effort and incompatible designs.

---

## 3. Current Development Strategy

Forge is built milestone by milestone.

Contributors should work within the active milestone whenever possible.

Do not implement distant roadmap features merely because they seem useful.

For example, if Forge is currently stabilizing read-only tools, a contribution should not simultaneously introduce:

* Parallel subagents
* Plugin loading
* Autonomous shell access
* Language-server integration
* A full web interface

Future-facing prototypes may be discussed separately, but they should not destabilize the main branch.

---

## 4. Ways to Contribute

### 4.1 Bug Reports

A useful bug report should include:

* Forge version or commit
* Operating system
* Python version
* Installation method
* Provider and model, when relevant
* Exact command or user action
* Expected behavior
* Actual behavior
* Relevant error output
* Minimal reproduction steps
* Whether the problem is consistent or intermittent

Remove secrets before posting logs or configuration.

Do not include:

* API keys
* Access tokens
* Passwords
* Private repository content
* Personal information
* Private keys
* Unredacted authorization headers

### 4.2 Feature Requests

A good feature request should explain:

* The user problem
* The current limitation
* The proposed behavior
* Why existing features are insufficient
* Security implications
* Expected interaction with the architecture
* Whether the feature belongs in the core or an optional extension

Feature requests should focus on outcomes rather than only implementation preferences.

### 4.3 Documentation

Documentation contributions are especially valuable.

Useful documentation work includes:

* Correcting outdated instructions
* Adding examples
* Clarifying limitations
* Improving installation instructions
* Documenting provider setup
* Explaining security behavior
* Creating troubleshooting guides
* Adding architecture diagrams
* Improving contributor onboarding

Documentation must describe actual behavior rather than planned behavior unless clearly labeled as planned.

### 4.4 Tests

High-value test contributions include:

* Regression tests for reported bugs
* Security abuse cases
* Provider response edge cases
* Workspace containment cases
* Patch rollback cases
* Malformed tool-call cases
* Session recovery cases
* Cross-platform behavior
* Benchmark fixtures

A test should fail before the fix and pass afterward whenever practical.

### 4.5 Provider Support

New provider integrations should not bypass Forge’s provider abstraction.

A provider contribution should include:

* Configuration model
* Capability declaration
* Error normalization
* Authentication handling
* Timeout handling
* Streaming behavior
* Tool-calling behavior, when supported
* Mocked tests
* User documentation
* Privacy and endpoint notes

Provider-specific response objects should not leak into the workflow layer.

### 4.6 Security Contributions

Security reports should follow `SECURITY.md`.

Do not open public issues for vulnerabilities that could put users at immediate risk.

Security hardening pull requests should include:

* Threat description
* Affected boundary
* Failure mode
* Tests demonstrating the issue
* Explanation of the fix
* Remaining limitations

### 4.7 User Interface Contributions

Interface changes should preserve separation between presentation and core logic.

The UI should subscribe to structured events rather than directly controlling:

* Providers
* Tool execution
* Approvals
* Patch application
* Workflow stages

Forge should remain usable in:

* Narrow terminals
* Plain-text terminals
* Environments without Nerd Fonts
* Environments with animations disabled

Avoid decorative complexity that hides important activity.

---

## 5. Development Environment

Forge targets Python 3.12 or newer.

Clone the repository:

```bash
git clone https://github.com/OWNER/forge.git
cd forge
```

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the project with development dependencies:

```bash
pip install -e ".[dev]"
```

The project may later recommend `uv` as an alternative development workflow. The canonical commands documented in the repository should remain functional.

---

## 6. Development Commands

Run the test suite:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=forge --cov-report=term-missing
```

Run lint checks:

```bash
ruff check .
```

Check formatting:

```bash
ruff format --check .
```

Apply formatting:

```bash
ruff format .
```

Run type checking:

```bash
pyright
```

Run all standard checks:

```bash
ruff check .
ruff format --check .
pyright
pytest
```

If the repository provides a project command such as:

```bash
make check
```

or:

```bash
forge-dev check
```

contributors may use it, but the underlying checks should remain independently runnable.

---

## 7. Branches

Create a focused branch from the current development base.

Examples:

```text
fix/workspace-symlink-check
feature/provider-health-command
docs/provider-configuration
test/patch-rollback
security/tool-output-redaction
```

Avoid unclear names such as:

```text
changes
update
new-stuff
fixes
```

Keep unrelated work on separate branches.

---

## 8. Commit Guidelines

Commits should be focused and understandable.

Recommended commit style:

```text
type(scope): concise description
```

Examples:

```text
feat(providers): add normalized timeout errors
fix(workspace): reject external symlink targets
test(patches): cover multi-file rollback
docs(security): clarify command execution risks
refactor(tools): separate schema validation from execution
```

Common types:

```text
feat
fix
docs
test
refactor
perf
build
ci
chore
security
```

A commit should ideally represent one coherent change.

Avoid combining:

* Formatting of the entire repository
* Dependency upgrades
* New features
* Unrelated bug fixes
* Large renames

in one commit.

Do not commit:

* API keys
* `.env` files
* Local credentials
* Provider request dumps
* Private repository fixtures
* Generated caches
* Virtual environments
* Personal configuration

---

## 9. Pull Requests

A pull request should explain:

### Summary

What changed?

### Motivation

What problem does the change solve?

### Scope

What is intentionally included and excluded?

### Architecture

Which Forge subsystem or boundary is affected?

### Security

Does the change affect:

* Filesystem access
* Tool permissions
* Command execution
* Provider communication
* Secrets
* Patches
* Approvals
* Sessions
* Subagents
* Network access

### Validation

List the exact commands executed and their results.

Example:

```text
ruff check . — passed
ruff format --check . — passed
pyright — passed
pytest — 184 passed
```

Do not write only:

```text
Tests pass.
```

### Screenshots

Include screenshots or recordings for meaningful interface changes when useful.

### Limitations

Document anything intentionally deferred or not fully supported.

---

## 10. Pull Request Checklist

Before requesting review, confirm:

* [ ] The change follows the active roadmap milestone.
* [ ] The change respects `ARCHITECTURE.md`.
* [ ] Security-sensitive behavior follows `SECURITY.md`.
* [ ] The implementation is focused.
* [ ] Public interfaces are typed.
* [ ] Error paths are handled.
* [ ] Tests cover normal behavior.
* [ ] Tests cover important failure behavior.
* [ ] Documentation is updated.
* [ ] No secrets are present.
* [ ] No placeholder implementation remains.
* [ ] No unrelated code was reformatted.
* [ ] Ruff passes.
* [ ] Formatting checks pass.
* [ ] Pyright passes.
* [ ] Pytest passes.
* [ ] Exact validation results are included in the pull request.

Not every checkbox applies to documentation-only changes, but applicable checks should still be completed.

---

## 11. Coding Standards

### 11.1 Python

Use modern Python 3.12 syntax where it improves clarity.

Prefer:

* Type annotations
* Small functions
* Explicit data models
* Clear exception types
* Context managers
* `pathlib.Path`
* Immutable configuration where appropriate
* Dependency injection at system boundaries
* Structured results over ambiguous strings

Avoid:

* Broad global state
* Hidden mutable singletons
* Bare `except`
* Silent exception suppression
* Deep inheritance hierarchies
* Dynamic monkey-patching
* Unvalidated dictionaries across subsystem boundaries
* Shell execution through strings
* Provider-specific objects outside provider adapters

### 11.2 Type Annotations

Public functions, methods, and models should have type annotations.

Avoid unnecessary use of `Any`.

`Any` may be used at external boundaries, but values should be validated and normalized before entering core systems.

### 11.3 Data Models

Use explicit models for important objects such as:

* Tasks
* Tool requests
* Tool results
* Patch proposals
* Approval decisions
* Validation results
* Provider responses
* Subagent reports
* Events

Avoid passing loosely structured dictionaries across multiple layers.

### 11.4 Exceptions

Use specific exception classes.

Examples:

```text
WorkspaceError
ToolValidationError
ToolPermissionError
ApprovalRequiredError
PatchValidationError
PatchApplicationError
ProviderAuthenticationError
ProviderTimeoutError
SessionRecoveryError
```

Expected user errors should not produce raw stack traces in normal operation.

Unexpected errors should be logged safely and surfaced with actionable messages.

### 11.5 Logging

Use structured logging where practical.

Never log:

* API keys
* Authorization headers
* Private keys
* Passwords
* Unredacted environment variables
* Complete provider requests by default
* Unrestricted source-file contents

Apply redaction before data reaches the logging backend.

### 11.6 Comments

Comments should explain:

* Why a security check exists
* Why an unusual design decision was chosen
* What invariant must remain true
* What external behavior requires a workaround

Avoid comments that merely repeat the code.

### 11.7 Docstrings

Public modules, classes, and non-obvious functions should have useful docstrings.

Docstrings should describe behavior, important constraints, and failure conditions.

---

## 12. Architectural Boundaries

Contributions must preserve subsystem boundaries.

### Provider Layer

Responsible for:

* Provider communication
* Streaming normalization
* Tool-call normalization
* Capability declarations
* Provider error classification

Must not:

* Apply patches
* Approve actions
* Read arbitrary workspace files
* Render terminal widgets

### Workflow Layer

Responsible for:

* Task stages
* Coordination
* Runtime decisions
* Completion rules
* Retry and stop behavior

Must not:

* Contain provider-specific parsing
* Directly manipulate UI widgets
* Bypass approval or tool policies

### Tool Runtime

Responsible for:

* Tool registration
* Schema validation
* Permission checks
* Risk classification
* Execution limits
* Structured results

Must not trust model-provided arguments without validation.

### Workspace Layer

Responsible for:

* Root detection
* Path containment
* Ignore rules
* Restricted files
* Secret handling
* File limits

All filesystem tools must pass through the workspace layer.

### Patch Layer

Responsible for:

* Parsing
* Validation
* Preview
* Checkpoints
* Application
* Rollback

Models should propose changes but must not directly perform unrestricted writes.

### Approval Layer

Responsible for authorization decisions.

No model, tool output, repository file, or subagent may grant approval.

### UI Layer

Responsible for:

* Input
* Rendering
* Interaction
* Approval prompts
* Event presentation

Core behavior should remain testable without launching the full UI.

---

## 13. Security-Sensitive Changes

Changes in these areas require additional review:

```text
src/forge/workspace/
src/forge/tools/runtime.py
src/forge/approvals/
src/forge/patches/
src/forge/providers/
src/forge/sessions/
src/forge/config/
src/forge/agents/
```

Security-sensitive pull requests should include dedicated abuse-case tests.

At least one reviewer should inspect whether the change affects the security invariants listed in `SECURITY.md`.

A feature should not be merged merely because its happy path works.

---

## 14. Adding a Tool

A new tool must define:

* Name
* Description
* Strict input schema
* Permission
* Risk level
* Approval requirement
* Network behavior
* Workspace-modification behavior
* Output limits
* Handler
* Tests

Before adding a tool, answer:

1. Why does the model need this capability?
2. Can an existing tool support the same outcome?
3. What is the minimum required permission?
4. Can it access secrets?
5. Can it leave the workspace?
6. Can it modify state?
7. Does it execute project-controlled code?
8. Can the action be reversed?
9. What happens when it times out?
10. What output limits are required?

Read-only tools should remain read-only at the operating-system interaction level whenever practical.

---

## 15. Adding a Provider

A provider adapter should normalize its behavior into Forge’s internal models.

Required work includes:

* Provider configuration
* Model configuration
* Capability metadata
* Authentication handling
* Base URL handling
* Completion support
* Streaming support
* Tool-call conversion
* Error normalization
* Timeout behavior
* Retry behavior
* Connection diagnostics
* Mocked tests
* Documentation

Do not silently approximate unsupported features.

For example, if a model does not support native tool calling, Forge should not mark tool calling as supported merely because prompt-based JSON is possible.

Prompt-based compatibility should be a separate, explicit capability.

---

## 16. Adding a Subagent

A new subagent must have:

* One clear purpose
* A distinct system prompt
* Explicit allowed tools
* Explicit denied capabilities
* A maximum step count
* A maximum delegation depth
* A structured output contract
* Tests for permission boundaries
* Documentation explaining when it should be used

Do not add agents that substantially overlap.

Poor separation:

```text
researcher
explorer
investigator
code-finder
repository-reader
```

Better separation:

```text
explore
reviewer
tester
coder
```

Subagents must not communicate directly with the user unless the interface explicitly supports manual invocation.

Subagents should return concise reports to the parent workflow.

---

## 17. Adding a Dependency

New dependencies should be justified in the pull request.

Include:

* What functionality it provides
* Why the standard library is insufficient
* Why an existing dependency cannot provide it
* Maintenance status
* License
* Security considerations
* Impact on package size
* Whether it executes code during installation
* Whether it introduces large transitive dependencies

Avoid adding a dependency for trivial helpers.

Do not reimplement mature security-sensitive functionality without strong justification.

---

## 18. Testing Requirements

### 18.1 Unit Tests

Unit tests should be deterministic and fast.

Mock:

* Provider network requests
* Time
* Random IDs when needed
* External command execution
* File operations outside temporary test directories

### 18.2 Integration Tests

Integration tests should verify boundaries between systems.

Examples:

* Provider response to normalized tool call
* Tool request through permission checks
* Patch approval through application
* Checkpoint through rollback
* Agent loop through tool result
* Session write through recovery

### 18.3 Security Tests

Security tests should cover abuse cases rather than only normal behavior.

Examples:

* Workspace traversal
* Symlink escape
* Secret leakage
* Fake approval
* Recursive delegation
* Dangerous command encoding
* Malformed patches
* Stale file contents
* Tool-output injection
* Provider-response corruption

### 18.4 Provider Tests

Normal automated tests must not require paid API calls.

Use mocked provider responses.

Optional live-provider tests should:

* Be clearly marked
* Be disabled by default
* Require explicit environment variables
* Avoid logging prompts or keys
* Use minimal token consumption

### 18.5 Snapshot Tests

Use snapshots carefully.

Snapshots should not hide important semantic changes.

Never store secrets, private prompts, or real provider responses in snapshots.

### 18.6 Temporary Files

Filesystem tests must use temporary directories.

Tests must not modify:

* The contributor’s real repository
* Home-directory configuration
* SSH files
* Global Git configuration
* Real provider credentials

---

## 19. Benchmark Contributions

Benchmarks should measure whether Forge completes known tasks safely and correctly.

A benchmark fixture should contain:

* A small project
* A clear task
* Known expected behavior
* Validation commands
* Expected changed files
* Forbidden actions
* Scoring criteria

Example structure:

```text
tests/benchmarks/broken-import/
├── project/
├── task.md
├── expected.patch
├── validation.toml
└── metadata.toml
```

Benchmarks should avoid requiring access to private services.

When model output makes full determinism impossible, separate:

* Runtime correctness
* Policy compliance
* Model-dependent task success

---

## 20. Documentation Standards

Documentation should be:

* Accurate
* Specific
* Testable where practical
* Clear about planned versus implemented features
* Free of secret values
* Consistent with command names and configuration
* Updated in the same pull request as behavior changes

Use examples that users can safely copy.

Avoid documentation that encourages:

* Running Forge as root
* Disabling certificate validation
* Committing `.env`
* Granting unrestricted shell approval
* Silently sending source code to cloud providers
* Disabling workspace protections

---

## 21. User-Facing Messages

Error and approval messages are part of Forge’s safety design.

Messages should tell the user:

* What happened
* What action was attempted
* Why it was blocked or failed
* Whether any state changed
* What can be done next

Good:

```text
Patch rejected because src/config.py changed after the proposal was created.
No files were modified. Generate a new patch from the current workspace state.
```

Weak:

```text
Patch error.
```

Approval messages must show the exact action rather than a vague description.

---

## 22. Generated Code and AI Assistance

Contributors may use AI tools to help write code, tests, or documentation.

AI-assisted contributions are held to the same standards as manually written work.

The contributor remains responsible for:

* Understanding the change
* Verifying licenses and attribution
* Reviewing generated code
* Removing fabricated APIs
* Running tests
* Checking security implications
* Ensuring documentation is accurate
* Confirming that no secrets were included

Do not submit large generated changes that you cannot explain or maintain.

Do not claim that generated code was tested when it was not.

AI tools must not be given private repository content without authorization.

---

## 23. Code Review Guidance

Reviewers should evaluate more than whether the code works.

Check:

### Scope

* Is the change focused?
* Does it belong in the current milestone?
* Are unrelated changes included?

### Architecture

* Does it preserve subsystem boundaries?
* Does it introduce duplicate abstractions?
* Is the dependency direction correct?

### Correctness

* Are normal and failure paths handled?
* Are errors classified accurately?
* Are state transitions valid?

### Security

* Is input treated as untrusted?
* Are permissions enforced at runtime?
* Can it expose secrets?
* Can it escape the workspace?
* Can approval be bypassed?
* Can failure cause data loss?

### Tests

* Would the tests fail without the implementation?
* Are abuse cases covered?
* Are tests deterministic?
* Are external services mocked?

### User Experience

* Are errors actionable?
* Are important actions visible?
* Are limitations stated honestly?

### Maintenance

* Is the code understandable?
* Is the abstraction justified?
* Will this make future changes easier or harder?

---

## 24. Review Outcomes

A review may result in:

* Approval
* Approval with minor follow-up
* Requested changes
* Architectural discussion
* Deferral to a later milestone
* Rejection because the feature conflicts with project principles

Deferral does not necessarily mean the idea is bad. It may mean the core is not ready for the added complexity.

---

## 25. Architecture Decisions

Significant architectural decisions should be documented through Architecture Decision Records.

Recommended location:

```text
docs/adr/
```

Example:

```text
docs/adr/0001-use-src-layout.md
docs/adr/0002-provider-normalization.md
docs/adr/0003-no-shell-by-default.md
```

An ADR should include:

* Context
* Decision
* Alternatives considered
* Consequences
* Security implications
* Status

Changes that contradict an accepted ADR should update or supersede it explicitly.

---

## 26. Backward Compatibility

Before Forge 1.0, interfaces may change as architecture stabilizes.

Even before 1.0, contributors should avoid unnecessary breaking changes.

After 1.0:

* Public CLI changes should include migration guidance.
* Configuration changes should support deprecation periods where practical.
* Session-format changes should include migration or safe fallback.
* Provider changes should preserve clear error behavior.
* Security fixes may require immediate breaking changes when necessary.

Security takes priority over backward compatibility.

---

## 27. Performance Contributions

Performance work should be supported by measurements.

Useful areas include:

* Startup time
* File search
* Context construction
* Session loading
* Event rendering
* Provider streaming
* Patch parsing
* Benchmark execution

Do not trade away correctness or safety for minor performance gains.

Avoid premature optimization of code that is not on a measured critical path.

---

## 28. Accessibility and Terminal Compatibility

Terminal interface contributions should consider:

* Small terminal widths
* Screen readers
* High-contrast themes
* Color-blind users
* No-color environments
* ASCII-only mode
* Disabled animations
* Terminals without Nerd Fonts
* Keyboard-only operation

Important states must not be communicated through color alone.

Examples:

* Include text labels for success and failure.
* Include symbols plus text for active and completed states.
* Keep approval controls keyboard accessible.

---

## 29. Community Conduct

Contributors should communicate respectfully.

Healthy discussion includes:

* Asking questions
* Challenging technical choices
* Requesting evidence
* Explaining tradeoffs
* Admitting uncertainty
* Revising an earlier position
* Helping new contributors understand the architecture

Unacceptable behavior includes:

* Personal attacks
* Harassment
* Discrimination
* Threats
* Publishing private information
* Intentionally misleading maintainers
* Submitting secrets or malicious code
* Retaliation against good-faith security reporters

A formal `CODE_OF_CONDUCT.md` may be added before the project’s first public community release.

---

## 30. Maintainer Responsibilities

Maintainers should:

* Review contributions consistently
* Explain significant rejections
* Protect architectural boundaries
* Prioritize security reports
* Avoid merging untested generated code
* Keep documentation aligned with behavior
* Label experimental features clearly
* Avoid promising unsupported timelines
* Encourage focused contributions
* Credit contributors fairly

Maintainers may close or defer changes that:

* Duplicate existing work
* Conflict with the roadmap
* Add unsafe authority
* Lack tests
* Introduce unjustified dependencies
* Expand scope excessively
* Cannot be maintained
* Misrepresent functionality

---

## 31. First Contributions

Good first contributions may include:

* Documentation corrections
* Typo fixes
* Better error messages
* Additional unit tests
* Missing type annotations
* Small diagnostic checks
* Provider mock fixtures
* Terminal compatibility fixes
* Benchmark fixture improvements
* Security regression tests

Issues suitable for new contributors should be labeled clearly.

Security-sensitive implementation may require prior familiarity with the codebase.

---

## 32. Contributor Checklist

Before submitting work, ask:

1. Does this solve a real problem?
2. Does it fit the current roadmap phase?
3. Is the change smaller than it needs to be?
4. Does it preserve architectural boundaries?
5. What untrusted input does it process?
6. What permissions does it require?
7. Can it expose secrets?
8. Can it modify user state?
9. Can the user undo it?
10. Are failures handled safely?
11. Are the important paths tested?
12. Did I run the documented validation commands?
13. Does the documentation match the implementation?
14. Can I explain every important part of the change?

If several answers are unclear, the contribution likely needs more design work before implementation.

---

## 33. Final Contribution Principle

Forge should not grow through feature accumulation alone.

Every contribution should make Forge more:

* Trustworthy
* Correct
* Recoverable
* Understandable
* Testable
* Useful

When a contribution creates a conflict, use this priority order:

```text
Safety
Correctness
Recoverability
Clarity
Testability
Compatibility
Performance
Convenience
Visual polish
Feature count
```

The goal is not to make Forge large.

The goal is to make Forge dependable.

