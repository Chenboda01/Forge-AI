# Forge

Forge is a workflow-first terminal coding agent. Models can request actions, but deterministic runtime code controls tools, permissions, approvals, workspace access, patches, validation, persistence, and recovery.

Forge is a pre-release prototype. The root `MILESTONE_AUDIT.md` records which roadmap capabilities have executable evidence; documentation alone is not completion evidence.

## Install and Run

Forge requires Python 3.12 or newer and uses `uv` for development.

```bash
uv sync --extra dev
uv run forge --help
uv run forge doctor
uv run forge chat
```

`forge chat` requires an interactive terminal. `forge doctor`, `forge providers`, and `forge models` provide non-interactive diagnostics.

## Credentials

Provider credentials resolve from the live process environment first and then the operating-system keyring. Forge does not load project `.env` files and does not persist a plaintext fallback when secure storage is unavailable.

```bash
export OPENAI_API_KEY="your-key"
export DEEPSEEK_API_KEY="your-key"
```

Forge can also store a provider key in the operating-system keyring. The secret is read through a hidden prompt and is never written to the repository, configuration, session data, or command output.

```bash
uv run forge auth login openai
uv run forge auth login            # choose from the provider list
uv run forge auth list             # show configured, missing, and local providers
uv run forge auth logout openai
```

The catalog covers Anthropic, OpenAI, Google Gemini, xAI, DeepSeek, MiniMax, Moonshot, Qwen (DashScope), OpenRouter, Together AI, Groq, Anyscale, Fireworks AI, Amazon Bedrock, Azure OpenAI, Cloudflare Workers AI, GitHub Models, Cohere, Mistral AI, Ollama, LM Studio, vLLM, OpenCode Go, and custom OpenAI-compatible endpoints. Bedrock, Azure, Cloudflare, OpenCode Go, and custom endpoints also require their documented endpoint or account configuration.

Allowed credential names are fixed by the model registry and provider catalog. A credential store that is unavailable fails closed; Forge never falls back to plaintext persistence.

Do not place credentials in `.forge/config.toml`, `FORGE.md`, source files, test fixtures, command output, or session data. Configured credential values are registered with the central redactor before provider, tool, terminal, validation, or persistence boundaries render them.

## Configuration

Trusted command-line, user, and environment sources may select provider routing:

```toml
# ~/.config/forge/config.toml
model = "openai"
model_id = "openai/gpt-5"
base_url = "https://api.example.com/v1"
timeout_seconds = 30
retry_limit = 0
```

Equivalent environment variables are `FORGE_MODEL`, `FORGE_MODEL_ID`, `FORGE_BASE_URL`, `FORGE_TIMEOUT_SECONDS`, and `FORGE_RETRY_LIMIT`.

Repository `.forge/config.toml` is untrusted. It may set only bounded `timeout_seconds` and `retry_limit` values. Forge rejects repository attempts to set `model`, `model_id`, or `base_url`. Custom cloud endpoints require HTTPS; local-provider custom endpoints must use `localhost` or a loopback IP address.

Forge never silently falls back to another provider.

## Modes and Approval

`ASK` is the default. `ASK` and `ARCHITECT` expose only local read-only tools. Mutation-capable operation must be selected explicitly:

```bash
uv run forge chat --mode build
```

`BUILD` exposes registered patch and validation tools, but patch application and command execution still require approval through the trusted interface. Model text, repository content, tool output, and subagent reports cannot grant approval.

## Interface

`forge chat` opens a Textual interface: a status rail for the session, queue, agents, context, cost, and MCP state; a conversation stream; and a composer. The header shows the workspace, model, mode, and active theme.

Themes are selected with `/theme` and saved for the current operating-system user in `$XDG_CONFIG_HOME/forge/preferences.toml` (default `~/.config/forge/preferences.toml`), so the choice survives restarts and shared machines keep separate preferences. `/settings` reports the active theme and preference path. The preferences file accepts only the `ui` table; unknown sections or keys are rejected instead of being silently ignored.

`/agents` opens a browser for the read-only subagents. Each entry shows its description, allowed tools, step limit, and delegation command; selecting a role preloads the composer with `/agent NAME`. `/agents NAME` prints the same detail directly. Press `Ctrl+X` then `A` to open the same browser without typing a command; the leader window lasts two seconds. The status rail shows how many subagents are ready and which one is active while delegation runs.

## Workspace and Patches

Forge confines model-facing filesystem operations to the resolved workspace. It rejects traversal, external symlinks, restricted credential files, private `.forge` state, binary text reads, and oversized reads. `.gitignore`, `.forgeignore`, built-in exclusions, and secret-file rules constrain context selection.

Patch application requires an exact one-shot match to the latest preview. Forge revalidates current content, creates a checkpoint, serializes writers, stages changes, and rolls back failed transactions. CREATE operations atomically refuse existing destinations. Destructive deletion refuses paths with uncommitted Git state.

## Validation

Validation accepts only recognized argument arrays; shell wrappers are not allowed. Commands require approval and run with a synthetic secret-free environment, network namespace isolation, fixed executable locations, timeouts, process-group termination, and output limits. Validation output is redacted before records are returned or persisted.

Validation still executes untrusted project code. Forge is not an operating-system security boundary and does not currently provide a container, memory limit, CPU quota, or complete filesystem sandbox.

Development gates are documented in the root `TESTING.md`:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev pyright
uv run --extra dev pytest -W error
uv lock --check
```

## Updates

Updates require explicit approval and install an exact binary package version. Forge does not update from mutable Git sources or execute package source builds. Release signing and package provenance are future hardening work.

## Security and Architecture

The authoritative policies are:

* `../SECURITY.md`
* `../ARCHITECTURE.md`
* `../ROADMAP.md`
* `../MILESTONE_AUDIT.md`
* `../TESTING.md`

Report security issues privately and use synthetic credentials in reproductions.
