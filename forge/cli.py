import shutil
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

from .forge import ForgeRuntimeError, build_runtime
from .forge_core.agent import AgentMode
from .forge_core.config import (
    ConfigurationError,
    ConfigurationOverrides,
    ForgeConfig,
    get_api_key,
    load_configuration,
)
from .forge_core.credentials import (
    CredentialStoreError,
    CredentialStoreUnavailableError,
    resolve_credential,
    system_credential_store,
)
from .forge_core.discovery import discover_project
from .forge_core.instructions import load_project_instructions
from .forge_core.models import MODELS
from .forge_core.provider import ForgeProvider, ForgeProviderError
from .forge_core.providers import PROVIDERS, ProviderConfig, provider_by_id
from .ui.app import ForgeApp
from .version import __version__

FORGE_VERSION: Final = __version__

app = typer.Typer(
    name="forge",
    help="Forge is a workflow-first terminal coding agent.",
    add_completion=False,
    no_args_is_help=False,
    rich_markup_mode=None,
)
provider_app = typer.Typer(help="Test a configured model provider.", no_args_is_help=True)
app.add_typer(provider_app, name="provider")
auth_app = typer.Typer(
    help="Manage provider credentials in the operating-system keyring.",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")


def is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _load_configuration_or_exit(overrides: ConfigurationOverrides) -> ForgeConfig:
    try:
        return load_configuration(overrides)
    except ConfigurationError as error:
        typer.echo(f"Forge configuration error: {error}", err=True)
        raise typer.Exit(code=1) from None


@app.callback(invoke_without_command=True)
def forge(
    context: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", help="Show Forge's version and exit."),
    ] = False,
) -> None:
    if version:
        typer.echo(f"Forge {FORGE_VERSION}")
        raise typer.Exit()
    if context.invoked_subcommand is None:
        chat()


@app.command()
def doctor() -> None:
    """Show local Forge diagnostics without starting a model provider."""
    configuration = _load_configuration_or_exit(ConfigurationOverrides())
    project_directory = Path.cwd().resolve()
    discovery = discover_project(project_directory)
    project_instructions = load_project_instructions(
        project_directory,
        repository_root=discovery.root,
    )
    terminal = "interactive" if is_interactive_terminal() else "plain-text"
    git = "available" if shutil.which("git") else "unavailable"
    ripgrep = "available" if shutil.which("rg") else "unavailable"
    python = ".".join(map(str, sys.version_info[:3]))

    def display(values: tuple[str, ...]) -> str:
        return ", ".join(values) or "none"

    typer.echo(
        "\n".join(
            (
                "Forge Doctor",
                f"Version: {FORGE_VERSION}",
                f"Model: {configuration.model}",
                f"Python: {python}",
                f"Project directory: {project_directory}",
                f"Discovery root: {discovery.root}",
                f"Git repository: {'yes' if discovery.git_repository else 'no'}",
                f"Current branch: {discovery.current_branch or 'unavailable'}",
                f"Project types: {display(discovery.project_types)}",
                f"Test frameworks: {display(discovery.test_frameworks)}",
                f"Formatters: {display(discovery.formatters)}",
                f"Type checkers: {display(discovery.type_checkers)}",
                f"Project instructions: {display(project_instructions.paths)}",
                f"Git: {git}",
                f"Ripgrep: {ripgrep}",
                f"Terminal: {terminal}",
            )
        )
    )


@app.command()
def providers() -> None:
    """List configured provider profiles without rendering credentials."""
    configuration = _load_configuration_or_exit(ConfigurationOverrides())
    lines = ["Forge Providers", f"Active model: {configuration.model}"]
    if configuration.base_url is not None:
        lines.append(f"Endpoint: {configuration.base_url}")
        selected = MODELS.get(configuration.model)
        if (
            configuration.base_url.startswith("http://")
            and selected
            and not selected.capabilities.local
        ):
            lines.append("Warning: the custom cloud-provider endpoint does not use HTTPS.")
    for alias, model in MODELS.items():
        status = "local" if model.requires_key is None else "configured"
        if model.requires_key is not None and get_api_key(model.requires_key) is None:
            status = f"missing {model.requires_key}"
        lines.append(f"{alias}: {model.provider} ({status})")
    typer.echo("\n".join(lines))


@app.command()
def models() -> None:
    """List selectable model profiles and declared capabilities."""
    lines = ["Forge Models"]
    for alias, model in MODELS.items():
        capabilities = []
        if model.capabilities.streaming:
            capabilities.append("streaming")
        if model.capabilities.tool_calling:
            capabilities.append("tools")
        if model.capabilities.local:
            capabilities.append("local")
        lines.append(f"{alias}: {model.model_id} ({', '.join(capabilities)})")
    typer.echo("\n".join(lines))


def _resolve_provider(identifier: str) -> ProviderConfig:
    provider = provider_by_id(identifier)
    if provider is None:
        available = ", ".join(PROVIDERS)
        typer.echo(
            f"Unknown provider '{identifier}'. Available providers: {available}",
            err=True,
        )
        raise typer.Exit(code=1)
    return provider


def _prompt_for_provider() -> ProviderConfig:
    providers = list(PROVIDERS.values())
    for index, provider in enumerate(providers, start=1):
        typer.echo(f"{index:>2}. {provider.id:<14} {provider.label}")
    selection = typer.prompt("Provider").strip().lower()
    if selection.isdigit():
        position = int(selection)
        if 1 <= position <= len(providers):
            return providers[position - 1]
        typer.echo("Provider number is out of range.", err=True)
        raise typer.Exit(code=1)
    return _resolve_provider(selection)


@auth_app.command("login")
def auth_login(
    provider: Annotated[
        str | None,
        typer.Argument(help="Provider id to authenticate, for example 'openai'."),
    ] = None,
) -> None:
    """Store a provider API key in the operating-system keyring."""
    selected = _resolve_provider(provider) if provider is not None else _prompt_for_provider()
    if selected.env_var is None:
        typer.echo(f"{selected.label} runs locally and does not require an API key.")
        return
    secret = typer.prompt(f"{selected.label} API key", hide_input=True).strip()
    if not secret:
        typer.echo("Provider credential must not be blank.", err=True)
        raise typer.Exit(code=1)
    try:
        system_credential_store().set(selected.env_var, secret)
    except CredentialStoreUnavailableError:
        typer.echo(
            "Forge could not access a secure operating-system keyring. "
            f"Set {selected.env_var} in the environment instead.",
            err=True,
        )
        raise typer.Exit(code=1) from None
    except CredentialStoreError as error:
        typer.echo(f"Forge could not store the credential: {error}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Stored {selected.env_var} in the operating-system keyring.")


@auth_app.command("list")
def auth_list() -> None:
    """List provider credential status without revealing secret values."""
    lines = ["Forge Credentials"]
    store = system_credential_store()
    for provider in PROVIDERS.values():
        if provider.env_var is None:
            status = "local"
        elif resolve_credential(provider.env_var, store) is not None:
            status = "configured"
        else:
            status = f"missing {provider.env_var}"
        lines.append(f"{provider.id}: {provider.label} ({status})")
    typer.echo("\n".join(lines))


@auth_app.command("logout")
def auth_logout(
    provider: Annotated[str, typer.Argument(help="Provider id whose credential to remove.")],
) -> None:
    """Remove a provider API key from the operating-system keyring."""
    selected = _resolve_provider(provider)
    if selected.env_var is None:
        typer.echo(f"{selected.label} runs locally and does not require an API key.")
        return
    try:
        system_credential_store().delete(selected.env_var)
    except CredentialStoreUnavailableError:
        typer.echo("Forge could not access a secure operating-system keyring.", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Removed {selected.env_var} from the operating-system keyring.")


@provider_app.command("test")
def test_provider(provider: str) -> None:
    """Run an explicit minimal completion request against one provider profile."""
    configuration = _load_configuration_or_exit(ConfigurationOverrides(model=provider))
    try:
        health = ForgeProvider(configuration.model, configuration=configuration).test_connection()
    except (ForgeProviderError, ForgeRuntimeError) as error:
        typer.echo(f"Provider test failed: {error}", err=True)
        raise typer.Exit(code=1) from None
    status = "reachable" if health.reachable else "unreachable"
    typer.echo(
        "\n".join(
            (
                f"Provider test: {health.provider}",
                f"Model: {health.model_id}",
                f"Status: {status}",
                f"Detail: {health.detail or 'No detail.'}",
            )
        )
    )
    if not health.reachable:
        raise typer.Exit(code=1)


@app.command()
def chat(
    model: Annotated[
        str | None, typer.Option("--model", help="Override the configured model.")
    ] = None,
    mode: Annotated[
        AgentMode,
        typer.Option("--mode", help="Select read-only ask/architect or approval-gated build."),
    ] = AgentMode.ASK,
) -> None:
    """Launch Forge's interactive terminal interface."""
    if not is_interactive_terminal():
        typer.echo(
            "Forge chat requires an interactive terminal. Run 'forge doctor' for diagnostics."
        )
        raise typer.Exit(code=1)
    configuration = _load_configuration_or_exit(ConfigurationOverrides(model=model))
    try:
        runtime = build_runtime(configuration=configuration, mode=mode)
    except ForgeProviderError as error:
        typer.echo(f"Forge could not start: {error}", err=True)
        raise typer.Exit(code=1) from None
    try:
        ForgeApp(runtime).run()
    except KeyboardInterrupt:
        typer.echo("\nForge interrupted.")
        raise typer.Exit(code=130) from None


def main() -> None:
    app()
