import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from forge.forge_core.tools import Tool, ToolError, ToolRegistry, create_tool_registry
from forge.forge_core.workspace import Workspace


class TestTool:
    def test_tool_creation(self):
        def handler(x: str) -> str:
            return x

        tool = Tool(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )
        assert tool.name == "test_tool"
        assert tool.requires_approval is False

    def test_tool_with_approval(self):
        def handler(x: str) -> str:
            return x

        tool = Tool(
            name="dangerous",
            description="Requires approval",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            requires_approval=True,
        )
        assert tool.requires_approval is True

    def test_tool_as_llm_tool(self):
        def handler(x: str) -> str:
            return x

        tool = Tool(
            name="my_tool",
            description="Does something",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
            handler=handler,
        )
        llm_def = tool.as_llm_tool()
        assert llm_def["type"] == "function"
        assert llm_def["function"]["name"] == "my_tool"
        assert llm_def["function"]["description"] == "Does something"

    def test_tool_is_frozen(self):
        def handler(x: str) -> str:
            return x

        tool = Tool(
            name="test",
            description="desc",
            parameters={},
            handler=handler,
        )
        with pytest.raises(FrozenInstanceError):
            tool.__setattr__("name", "changed")


class TestToolRegistry:
    def test_register_and_get(self):
        def handler() -> str:
            return "ok"

        registry = ToolRegistry()
        tool = Tool(name="test", description="desc", parameters={}, handler=handler)
        registry.register(tool)
        assert registry.get("test") == tool

    def test_duplicate_register_raises(self):
        registry = ToolRegistry()

        def h1() -> str:
            return "1"

        def h2() -> str:
            return "2"

        registry.register(Tool(name="dup", description="d", parameters={}, handler=h1))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(Tool(name="dup", description="d", parameters={}, handler=h2))

    def test_get_unknown_tool_raises(self):
        registry = ToolRegistry()
        with pytest.raises(ToolError, match="Unknown tool"):
            registry.get("nonexistent")

    def test_execute_unknown_tool_raises(self):
        registry = ToolRegistry()
        with pytest.raises(ToolError, match="Unknown tool"):
            registry.execute("nonexistent", {})

    def test_definitions(self):
        registry = ToolRegistry()

        def h1() -> str:
            return "a"

        def h2() -> str:
            return "b"

        registry.register(Tool(name="t1", description="d1", parameters={}, handler=h1))
        registry.register(Tool(name="t2", description="d2", parameters={}, handler=h2))

        defs = registry.definitions()
        assert len(defs) == 2
        names = [d["function"]["name"] for d in defs]
        assert "t1" in names
        assert "t2" in names


class TestCreateToolRegistry:
    def test_creates_expected_tools(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Workspace(Path(tmpdir))
            registry = create_tool_registry(workspace)

            tool_names = [d["function"]["name"] for d in registry.definitions()]
            assert "list_files" in tool_names
            assert "read_file" in tool_names
            assert "search_files" in tool_names
            assert "git_status" in tool_names
            assert "git_diff" in tool_names
            assert "write_file" in tool_names
            assert "run_command" in tool_names
            assert "delegate_task" not in tool_names

    def test_list_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "file1.txt").write_text("hello")
            (root / "subdir").mkdir()
            (root / "subdir" / "file2.py").write_text("print('hi')")

            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            result = registry.execute("list_files", {})
            assert "file1.txt" in result
            assert "subdir/" in result

    def test_list_files_recursive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.py").write_text("a")
            (root / "sub").mkdir()
            (root / "sub" / "b.py").write_text("b")

            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            result = registry.execute("list_files", {"recursive": True})
            assert "a.py" in result
            assert "sub/b.py" in result

    def test_read_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "test.txt").write_text("line1\nline2\nline3\n")

            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            result = registry.execute("read_file", {"path": "test.txt"})
            assert "line1" in result
            assert "line2" in result
            assert "line3" in result

    def test_read_file_with_line_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "test.txt").write_text("line1\nline2\nline3\nline4\n")

            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            result = registry.execute(
                "read_file", {"path": "test.txt", "start_line": 2, "end_line": 3}
            )
            assert "line2" in result
            assert "line3" in result
            # line1 should not be in the output (start_line=2)
            assert "   1 |" not in result or "line1" not in result.split("\n")[0]

    def test_read_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Workspace(Path(tmpdir))
            registry = create_tool_registry(workspace)

            with pytest.raises(ToolError, match="does not exist"):
                registry.execute("read_file", {"path": "nonexistent.txt"})

    def test_write_file_creates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            result = registry.execute("write_file", {"path": "new.txt", "content": "hello world"})
            assert "Created" in result
            assert (root / "new.txt").read_text() == "hello world"

    def test_write_file_updates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "existing.txt").write_text("old")

            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            result = registry.execute("write_file", {"path": "existing.txt", "content": "new"})
            assert "Updated" in result
            assert (root / "existing.txt").read_text() == "new"

    def test_write_file_creates_parents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            registry.execute(
                "write_file",
                {"path": "deep/nested/file.txt", "content": "hello"},
            )
            assert (root / "deep" / "nested" / "file.txt").read_text() == "hello"

    def test_write_file_workspace_enforcement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = Workspace(root)
            registry = create_tool_registry(workspace)

            with pytest.raises(ToolError):
                registry.execute("write_file", {"path": "../outside.txt", "content": "x"})

    def test_write_tool_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Workspace(Path(tmpdir))
            registry = create_tool_registry(workspace)
            tool = registry.get("write_file")
            assert tool.requires_approval is True

    def test_run_command_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Workspace(Path(tmpdir))
            registry = create_tool_registry(workspace)
            tool = registry.get("run_command")
            assert tool.requires_approval is True

    @pytest.mark.parametrize(
        "command",
        [
            "python -c 'print(1)'",
            "env pytest",
            "/bin/sh -c 'pytest'",
            "git -c alias.run='!sh' run",
        ],
    )
    def test_run_command_rejects_unrecognized_executables(self, command: str, tmp_path) -> None:
        # Given: an approved tool call that wraps execution in an unsafe executable
        registry = create_tool_registry(Workspace(tmp_path))

        # When / Then: policy rejects it before a process starts
        with patch("forge.forge_core.command_tools.subprocess.run") as run:
            with pytest.raises(ToolError, match="not permitted"):
                registry.execute("run_command", {"command": command})
            run.assert_not_called()

    def test_search_files_excludes_forge_state(self, tmp_path) -> None:
        # Given: the same marker in source and private Forge state
        (tmp_path / "visible.txt").write_text("unique-marker", encoding="utf-8")
        state = tmp_path / ".forge"
        state.mkdir()
        (state / "session.json").write_text("unique-marker", encoding="utf-8")
        registry = create_tool_registry(Workspace(tmp_path))

        # When: repository search runs from the workspace root
        result = registry.execute("search_files", {"query": "unique-marker"})

        # Then: only project content is exposed
        assert "visible.txt" in result
        assert ".forge" not in result
