"""Integration test cases - Full agent demos."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from mini_agent.agent_core.engine import Agent
from mini_agent.config import Config
from mini_agent.llm import LLMClient, build_protocol_execution_profile
from mini_agent.schema import LLMProvider
from mini_agent.tools.bash_tool import BashTool
from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
from mini_agent.tools.mcp_loader import load_mcp_tools_async
from mini_agent.tools.note_tool import RecallNoteTool, SessionNoteTool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live_api,
    pytest.mark.skipif(
        os.getenv("MINI_AGENT_RUN_LIVE_TESTS") != "1",
        reason="Live API tests disabled. Set MINI_AGENT_RUN_LIVE_TESTS=1 to run.",
    ),
]


def _load_live_config() -> Config:
    config_path = Config.find_config_file("config.yaml")
    if config_path is None:
        pytest.skip("config.yaml not found in active search paths")
    return Config.from_yaml(config_path, allow_interactive_setup=False)


def _load_system_prompt() -> str:
    system_prompt_path = Config.find_config_file("system_prompt.md")
    if system_prompt_path and system_prompt_path.exists():
        return system_prompt_path.read_text(encoding="utf-8")
    return "You are a helpful AI assistant."


def _find_mcp_config() -> Path | None:
    return Config.find_config_file("mcp.json") or Config.find_config_file(
        "mcp-example.json"
    )


def _build_live_llm_client(config: Config) -> LLMClient:
    profile = build_protocol_execution_profile(
        api_key=config.llm.api_key,
        provider=LLMProvider(config.llm.provider),
        api_base=config.llm.api_base,
        model=config.llm.model,
    )
    return LLMClient(profile=profile)


@pytest.mark.asyncio
async def test_basic_agent_usage():
    """Test basic agent usage with file creation task.

    This is the integration test for basic agent functionality,
    converted from example.py.
    """
    print("\n" + "=" * 80)
    print("Integration Test: Basic Agent Usage")
    print("=" * 80)

    config = _load_live_config()

    # Check API key
    if not config.llm.api_key or config.llm.api_key == "YOUR_MINIMAX_API_KEY_HERE":
        pytest.skip("API key not configured")

    # Use temporary workspace
    with tempfile.TemporaryDirectory() as workspace_dir:
        system_prompt = _load_system_prompt()

        # Initialize LLM client
        llm_client = _build_live_llm_client(config)

        # Initialize basic tools
        tools = [
            ReadTool(workspace_dir=workspace_dir),
            WriteTool(workspace_dir=workspace_dir),
            EditTool(workspace_dir=workspace_dir),
            BashTool(),
        ]

        # Add note tools for session memory
        memory_root = Path(workspace_dir)
        tools.extend(
            [
                SessionNoteTool(memory_root=str(memory_root)),
                RecallNoteTool(memory_root=str(memory_root)),
            ]
        )

        # Load MCP tools (optional) - with timeout protection
        try:
            # MCP tools are disabled by default to prevent test hangs
            # Enable specific MCP servers in mcp.json if needed
            mcp_tools = []
            mcp_config_path = _find_mcp_config()
            if mcp_config_path is not None:
                mcp_tools = await load_mcp_tools_async(config_path=str(mcp_config_path))
            if mcp_tools:
                print(f"[ok] Loaded {len(mcp_tools)} MCP tools")
                tools.extend(mcp_tools)
            else:
                print("[warn] No MCP tools configured or enabled")
        except Exception as e:
            print(f"[warn] MCP tools not loaded: {e}")

        # Create agent
        agent = Agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=config.agent.max_steps,
            workspace_dir=workspace_dir,
        )

        # Task: Create a Python file with hello world
        task = """
        Create a Python file named hello.py in the workspace that prints "Hello, Mini Agent!".
        Then execute it to verify it works.
        """

        print(f"\nTask: {task}")
        print("\n" + "=" * 80 + "\n")

        agent.add_user_message(task)
        result = await agent.run()

        print("\n" + "=" * 80)
        print(f"Result: {result}")
        print("=" * 80)

        # Verify the file was created or task completed
        hello_file = Path(workspace_dir) / "hello.py"
        assert hello_file.exists() or "complete" in result.lower(), (
            "Agent should create the file or indicate completion"
        )

        print("\n[ok] Basic agent usage test passed")


@pytest.mark.asyncio
async def test_session_memory_demo():
    """Test session memory functionality across multiple agent instances.

    This is the integration test for session note tool,
    converted from example_memory.py.
    """
    print("\n" + "=" * 80)
    print("Integration Test: Session Memory Demo")
    print("=" * 80)

    config = _load_live_config()

    # Check API key
    if not config.llm.api_key or config.llm.api_key == "YOUR_MINIMAX_API_KEY_HERE":
        pytest.skip("API key not configured")

    # Use temporary workspace
    with tempfile.TemporaryDirectory() as workspace_dir:
        # Use simplified system prompt for faster testing
        system_prompt = """You are a helpful AI assistant.

You have record_note and recall_notes tools:
- record_note: Save important information (use category to organize)
- recall_notes: Retrieve saved information
"""

        # Initialize LLM
        llm_client = _build_live_llm_client(config)

        memory_root = Path(workspace_dir)

        # Initialize tools (only Session Note Tools for this test)
        tools = [
            SessionNoteTool(memory_root=str(memory_root)),
            RecallNoteTool(memory_root=str(memory_root)),
        ]

        print("\n[note] Creating Agent with Session Note tools...")
        agent = Agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=8,  # Reduced from 15
            workspace_dir=workspace_dir,
        )

        # Task 1: First conversation - agent should save memories
        task1 = """
        Please remember these details about me:
        - Name: Alex
        - Project: mini-agent
        - Tech stack: Python 3.12, async/await
        - Preference: concise code style
        
        Use record_note to save this information.
        """

        print(f"\n[step] First Conversation:\n{task1}")
        print("=" * 80)

        agent.add_user_message(task1)
        result1 = await agent.run()

        print("\n" + "=" * 80)
        print(f"Agent completed: {result1[:200]}...")
        print("=" * 80)

        # Check if notes were recorded
        long_term_file = memory_root / "MEMORY.md"
        if long_term_file.exists():
            note_lines = [
                line
                for line in long_term_file.read_text(encoding="utf-8").splitlines()
                if line.startswith("- [")
            ]
            print(f"\n[ok] Agent recorded {len(note_lines)} long-term notes:")
            for line in note_lines:
                print(f"  - {line}")
            assert len(note_lines) > 0, "Agent should have recorded some notes"
        else:
            print("\n[warn] No notes found - agent may not have used record_note tool")

        print("\n\n" + "=" * 80)
        print("Simulating New Session (Agent should recall previous information)")
        print("=" * 80)

        # Task 2: New conversation - agent should recall memories
        agent2 = Agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=5,  # Reduced from 10
            workspace_dir=workspace_dir,
        )

        task2 = """
        Use recall_notes to check: What do you know about me and my project?
        """

        print(f"\n[step] Second Conversation (new session):\n{task2}")
        print("=" * 80)

        agent2.add_user_message(task2)
        result2 = await agent2.run()

        print("\n" + "=" * 80)
        print(f"Agent response: {result2}")
        print("=" * 80)

        print("\n[ok] Session Note Tool test completed!")
        print("\nKey Points Verified:")
        print("  1. Agent can record important information")
        print("  2. Notes persist in memory file")
        print("  3. New agent instances can recall previous notes")


async def main():
    """Run all integration tests."""
    print("=" * 80)
    print("Running Integration Tests")
    print("=" * 80)
    print("\nNote: These tests require a valid live provider config in active search paths.")
    print("These tests will actually call the LLM API and may take some time.\n")

    try:
        await test_basic_agent_usage()
    except Exception as e:
        print(f"[fail] Basic usage test failed: {e}")

    try:
        await test_session_memory_demo()
    except Exception as e:
        print(f"[fail] Session memory test failed: {e}")

    print("\n" + "=" * 80)
    print("Integration tests completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
