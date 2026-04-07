import asyncio
import sys

async def test_async():
    """Test async operations"""
    print("✓ Async function defined")
    await asyncio.sleep(0.1)
    print("✓ Async sleep works")
    return "async operations working"

if __name__ == "__main__":
    print("Testing async capabilities...")
    result = asyncio.run(test_async())
    print(f"✓ Async result: {result}")
    print("✓ All async tests passed!")
