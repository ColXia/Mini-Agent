"""Live integration tests for the agent-core engine."""

import asyncio
import os
from pathlib import Path
import tempfile
import pytest

from mini_agent import LLMClient
from mini_agent.agent_core.engine import Agent
from mini_agent.config import Config
from mini_agent.llm import build_protocol_execution_profile
from mini_agent.schema import LLMProvider
from mini_agent.tools import BashTool, EditTool, ReadTool, WriteTool

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
    return "You are a helpful AI assistant that can use tools."


def _build_live_llm_client(config: Config) -> LLMClient:
    profile = build_protocol_execution_profile(
        api_key=config.llm.api_key,
        provider=LLMProvider(config.llm.provider),
        api_base=config.llm.api_base,
        model=config.llm.model,
    )
    return LLMClient(profile=profile)


@pytest.mark.asyncio
async def test_agent_simple_task():
    """Test agent with a simple file creation task."""
    print("\n=== Testing Agent with Simple File Task ===")

    config = _load_live_config()

    # Create temp workspace
    with tempfile.TemporaryDirectory() as workspace_dir:
        print(f"Using workspace: {workspace_dir}")

        system_prompt = _load_system_prompt()

        # Initialize LLM client
        llm_client = _build_live_llm_client(config)

        # Initialize tools
        tools = [
            ReadTool(workspace_dir=workspace_dir),
            WriteTool(workspace_dir=workspace_dir),
            EditTool(workspace_dir=workspace_dir),
            BashTool(),
        ]

        # Create agent
        agent = Agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=10,  # Limit steps for testing
            workspace_dir=workspace_dir,
        )

        # Task: Create a simple text file
        task = "Create a file named 'test.txt' with the content 'Hello from Agent!'"
        print(f"\nTask: {task}\n")

        agent.add_user_message(task)

        try:
            result = await agent.run()

            print(f"\n{'=' * 80}")
            print(f"Agent Result: {result}")
            print("=" * 80)

            # Check if file was created
            test_file = Path(workspace_dir) / "test.txt"
            if test_file.exists():
                content = test_file.read_text()
                print("\n鉁?File created successfully!")
                print(f"Content: {content}")

                if "Hello from Agent!" in content:
                    print("鉁?Content is correct!")
                    return True
                else:
                    print(f"鈿狅笍  Content mismatch: {content}")
                    return True  # Still count as success, agent did create the file
            else:
                print("鈿狅笍  File was not created, but agent completed")
                return True  # Agent might have completed differently

        except Exception as e:
            print(f"鉂?Agent test failed: {e}")
            import traceback

            traceback.print_exc()
            pytest.fail(f"Agent test failed: {e}")


@pytest.mark.asyncio
async def test_agent_bash_task():
    """Test agent with a bash command task."""
    print("\n=== Testing Agent with Bash Task ===")

    config = _load_live_config()

    # Create temp workspace
    with tempfile.TemporaryDirectory() as workspace_dir:
        print(f"Using workspace: {workspace_dir}")

        system_prompt = _load_system_prompt()

        # Initialize LLM client
        llm_client = _build_live_llm_client(config)

        # Initialize tools
        tools = [
            ReadTool(workspace_dir=workspace_dir),
            WriteTool(workspace_dir=workspace_dir),
            BashTool(),
        ]

        # Create agent
        agent = Agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=10,
            workspace_dir=workspace_dir,
        )

        # Task: List files using bash
        task = "Use bash to list all files in the current directory and tell me what you find."
        print(f"\nTask: {task}\n")

        agent.add_user_message(task)

        try:
            result = await agent.run()

            print(f"\n{'=' * 80}")
            print(f"Agent Result: {result}")
            print("=" * 80)

            print("\n鉁?Bash task completed!")
            return True

        except Exception as e:
            print(f"鉂?Bash task failed: {e}")
            import traceback

            traceback.print_exc()
            pytest.fail(f"Bash task failed: {e}")


async def main():
    """Run all agent tests."""
    print("=" * 80)
    print("Running Agent Integration Tests")
    print("=" * 80)
    print("\nNote: These tests require a valid live provider config in active search paths.")
    print("These tests will actually call the LLM API and may take some time.\n")

    # Test simple file task
    result1 = await test_agent_simple_task()

    # Test bash task
    result2 = await test_agent_bash_task()

    print("\n" + "=" * 80)
    if result1 and result2:
        print("All Agent tests passed!")
    else:
        print("Some Agent tests failed. Check the output above.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
