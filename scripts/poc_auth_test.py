#!/usr/bin/env python
"""
POC: Validate that Agent SDK inherits Claude Code auth.
Run this from within a Claude Code session to test.
"""

import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage


async def test_auth_inheritance():
    """Simple test - if this works, auth was inherited."""

    print("Testing Agent SDK auth inheritance...")
    print("If you're using Bedrock/Vertex, this should use your configured auth.\n")

    try:
        async for message in query(
            prompt="What is 2 + 2? Reply with just the number.",
            options=ClaudeAgentOptions(
                max_turns=1,
                allowed_tools=[],  # No tools, just test API access
            ),
        ):
            if isinstance(message, ResultMessage):
                if message.subtype == "success":
                    print("SUCCESS: Auth inherited correctly")
                    print(f"   Result: {message.result}")
                    print(f"   Cost: ${message.total_cost_usd:.6f}")
                    return True
                else:
                    print(f"FAILED: {message.subtype}")
                    return False

    except Exception as e:
        print(f"ERROR: {e}")
        print("\nThis might mean:")
        print("  - Agent SDK couldn't find Claude Code CLI")
        print("  - Auth wasn't inherited correctly")
        print("  - Claude Code isn't authenticated")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_auth_inheritance())
    exit(0 if success else 1)
