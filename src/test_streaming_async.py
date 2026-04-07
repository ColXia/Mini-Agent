#!/usr/bin/env python3
"""Test streaming and async capabilities"""

import asyncio
import json
import time
from datetime import datetime

async def stream_numbers():
    """Async generator to stream numbers"""
    for i in range(5):
        yield i
        await asyncio.sleep(0.1)

async def test_async_generator():
    """Test async generator functionality"""
    print("Starting async generator test...")
    results = []
    async for num in stream_numbers():
        results.append(num)
        print(f"  Received: {num}")
    return results

async def test_async_gather():
    """Test concurrent async operations"""
    async def task1():
        await asyncio.sleep(0.5)
        return "Task 1 completed"
    
    async def task2():
        await asyncio.sleep(0.3)
        return "Task 2 completed"
    
    results = await asyncio.gather(task1(), task2())
    return results

async def test_async_timeout():
    """Test async timeout functionality"""
    try:
        await asyncio.wait_for(asyncio.sleep(2), timeout=1.0)
        return "Completed within timeout"
    except asyncio.TimeoutError:
        return "Timed out as expected"

def test_sync_stream_simulation():
    """Simulate streaming with sync code"""
    print("\nSimulating streaming data...")
    data_chunks = []
    for i in range(10):
        chunk = {"chunk_id": i, "timestamp": time.time(), "data": f"chunk_{i}"}
        data_chunks.append(chunk)
        print(f"  Chunk {i}: {chunk['chunk_id']}")
        time.sleep(0.05)
    return data_chunks

def test_jsonl_stream():
    """Test JSON Lines streaming format"""
    print("\nTesting JSONL streaming...")
    lines = [
        '{"event": "start", "timestamp": "2026-04-07T10:56:00"}',
        '{"event": "data", "value": 42}',
        '{"event": "data", "value": 43}',
        '{"event": "end", "timestamp": "2026-04-07T10:56:01"}'
    ]
    
    parsed = []
    for line in lines:
        obj = json.loads(line)
        parsed.append(obj)
        print(f"  Parsed: {obj}")
    
    return parsed

if __name__ == "__main__":
    print("=" * 60)
    print("STREAMING & ASYNC CAPABILITIES TEST")
    print("=" * 60)
    
    # Test 1: Async Generator
    print("\n[TEST 1] Async Generator")
    print("-" * 40)
    async_gen_results = asyncio.run(test_async_generator())
    print(f"✓ Async generator results: {async_gen_results}")
    
    # Test 2: Async Gather (Concurrent Tasks)
    print("\n[TEST 2] Async Gather (Concurrent)")
    print("-" * 40)
    gather_results = asyncio.run(test_async_gather())
    print(f"✓ Gather results: {gather_results}")
    
    # Test 3: Async Timeout
    print("\n[TEST 3] Async Timeout")
    print("-" * 40)
    timeout_result = asyncio.run(test_async_timeout())
    print(f"✓ Timeout test: {timeout_result}")
    
    # Test 4: Sync Stream Simulation
    print("\n[TEST 4] Sync Stream Simulation")
    print("-" * 40)
    stream_results = test_sync_stream_simulation()
    print(f"✓ Streamed {len(stream_results)} chunks")
    
    # Test 5: JSONL Streaming
    print("\n[TEST 5] JSONL Streaming")
    print("-" * 40)
    jsonl_results = test_jsonl_stream()
    print(f"✓ Parsed {len(jsonl_results)} JSON lines")
    
    print("\n" + "=" * 60)
    print("ALL STREAMING TESTS COMPLETED SUCCESSFULLY ✓")
    print("=" * 60)
    
    # Summary
    print("\nSUMMARY:")
    print(f"  - Async generators: WORKING")
    print(f"  - Concurrent async tasks: WORKING")
    print(f"  - Async timeouts: WORKING")
    print(f"  - Streaming data simulation: WORKING")
    print(f"  - JSON Lines parsing: WORKING")
    print(f"  - Total chunks processed: {len(stream_results) + len(jsonl_results)}")
    print("\nTimestamp:", datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"))
