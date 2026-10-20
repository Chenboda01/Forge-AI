import json
from pathlib import Path

from typer.testing import CliRunner

import forge.cli as cli_module
from forge.forge_core.discovery import discover_project

runner = CliRunner()


def test_discovery_reports_project_metadata_in_deterministic_order(tmp_path: Path) -> None:
    # Given: one workspace containing every supported project marker
    _write_git_head(tmp_path, "ref: refs/heads/main\n")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'dependencies = ["pytest", "ruff", "pyright"]\n'
        "[tool.pytest.ini_options]\n"
        "[tool.ruff]\n"
        "[tool.pyright]\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "devDependencies": {
                    "vitest": "1",
                    "prettier": "1",
                    "typescript": "1",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "sample"\n', encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.test/sample\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text(
        "<dependency>junit</dependency>\n<plugin>google-java-format</plugin>\n",
        encoding="utf-8",
    )
    for name in ("Makefile", "Dockerfile", "FORGE.md"):
        (tmp_path / name).write_text("metadata\n", encoding="utf-8")

    # When: Forge discovers the workspace twice
    first = discover_project(tmp_path)
    second = discover_project(tmp_path)

    # Then: metadata is stable and contains no provider- or runtime-dependent values
    assert first == second
    assert first.root == tmp_path.resolve()
    assert first.git_repository is True
    assert first.current_branch == "main"
    assert first.project_types == ("python", "node", "rust", "go", "java")
    assert first.test_frameworks == ("pytest", "vitest", "cargo test", "go test", "junit")
    assert first.formatters == ("ruff", "prettier", "rustfmt", "gofmt", "google-java-format")
    assert first.type_checkers == ("pyright", "typescript", "rustc", "go vet", "javac")
    assert first.instruction_files == ("FORGE.md",)
    assert first.relevant_files == tuple(
        sorted(
            (
                "Cargo.toml",
                "Dockerfile",
                "FORGE.md",
                "Makefile",
                "go.mod",
                "package.json",
                "pom.xml",
                "pyproject.toml",
            )
        )
    )


def test_discovery_uses_nearest_git_root_for_nested_directory(tmp_path: Path) -> None:
    # Given: a nested working directory inside a Git workspace
    _write_git_head(tmp_path, "ref: refs/heads/feature/discovery\n")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    nested = tmp_path / "src" / "package"
    nested.mkdir(parents=True)

    # When: discovery starts below the repository root
    result = discover_project(nested)

    # Then: repository metadata and project markers come from the nearest root
    assert result.root == tmp_path.resolve()
    assert result.git_repository is True
    assert result.current_branch == "feature/discovery"
    assert result.project_types == ("python",)


def test_discovery_does_not_execute_project_files(tmp_path: Path) -> None:
    # Given: metadata files containing commands that would create a marker if run
    (tmp_path / "setup.py").write_text(
        "from pathlib import Path\nPath('executed').write_text('bad')\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text("all:\n\ttouch executed\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("RUN touch executed\n", encoding="utf-8")

    # When: Forge inspects the project metadata
    result = discover_project(tmp_path)

    # Then: only metadata is read and no project-controlled command runs
    assert result.project_types == ("python",)
    assert not (tmp_path / "executed").exists()


def test_discovery_tolerates_malformed_metadata(tmp_path: Path) -> None:
    # Given: malformed TOML and JSON project metadata
    (tmp_path / "pyproject.toml").write_text("[broken", encoding="utf-8")
    (tmp_path / "package.json").write_text("{broken", encoding="utf-8")

    # When: Forge performs project discovery
    result = discover_project(tmp_path)

    # Then: marker-based project types remain visible without guessed tool names
    assert result.project_types == ("python", "node")
    assert result.test_frameworks == ()
    assert result.formatters == ()
    assert result.type_checkers == ()


def test_discovery_ignores_external_metadata_symlink(tmp_path: Path) -> None:
    # Given: a project marker redirected to metadata outside the project root
    project = tmp_path / "project"
    outside = tmp_path / "outside.toml"
    project.mkdir()
    outside.write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (project / "pyproject.toml").symlink_to(outside)

    # When: Forge performs non-executing project discovery
    result = discover_project(project)

    # Then: external metadata is not treated as project content
    assert result.project_types == ()
    assert result.test_frameworks == ()
    assert "pyproject.toml" not in result.relevant_files


def test_doctor_renders_project_discovery(monkeypatch, tmp_path: Path) -> None:
    # Given: a local Python workspace with a branch and project instructions
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    _write_git_head(tmp_path, "ref: refs/heads/main\n")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n[tool.ruff]\n[tool.pyright]\n",
        encoding="utf-8",
    )
    (tmp_path / "FORGE.md").write_text("Use the project conventions.\n", encoding="utf-8")

    # When: a user runs diagnostics
    result = runner.invoke(cli_module.app, ["doctor"])

    # Then: discovery is visible without starting a model provider
    assert result.exit_code == 0
    assert "Git repository: yes" in result.output
    assert "Current branch: main" in result.output
    assert "Project types: python" in result.output
    assert "Test frameworks: pytest" in result.output
    assert "Formatters: ruff" in result.output
    assert "Type checkers: pyright" in result.output
    assert "Project instructions: FORGE.md" in result.output


def _write_git_head(root: Path, content: str) -> None:
    git = root / ".git"
    git.mkdir(exist_ok=True)
    (git / "HEAD").write_text(content, encoding="utf-8")
