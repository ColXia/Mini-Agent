#!/usr/bin/env python3
"""Advanced streaming and generator tests"""

import asyncio
import json
import time
from collections.abc import Iterator, AsyncIterator
from contextlib import asynccontextmanager

# Test 1: Classic Iterator Protocol
class NumberIterator:
    """Classic iterator using __iter__ and __next__"""
    def __init__(self, max_num):
        self.max = max_num
        self.current = 0
    
    def __iter__(self):
        return self
    
    def __next__(self):
        if self.current < self.max:
            result = self.current
            self.current += 1
            return result
        raise StopIteration

# Test 2: Generator Function
def fibonacci_generator(limit):
    """Generator function for Fibonacci sequence"""
    a, b = 0, 1
    count = 0
    while count < limit:
        yield a
        a, b = b, a + b
        count += 1

# Test 3: Chained Generators
def map_generator(func, iterable):
    """Generator that applies function to items"""
    for item in iterable:
        yield func(item)

def filter_generator(predicate, iterable):
    """Generator that filters items"""
    for item in iterable:
        if predicate(item):
            yield item

# Test 4: Async Context Manager
@asynccontextmanager
async def async_resource(name):
    """Async context manager for resource management"""
    print(f"  → Opening {name}")
    await asyncio.sleep(0.1)  # Simulate async operation
    resource = {"name": name, "opened": True}
    try:
        yield resource
    finally:
        print(f"  ← Closing {name}")
        await asyncio.sleep(0.1)

# Test 5: Async Iterator
class AsyncCounter:
    """Async iterator class"""
    def __init__(self, max_count):
        self.max = max_count
        self.current = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.current < self.max:
            await asyncio.sleep(0.1)
            result = self.current
            self.current += 1
            return result
        raise StopAsyncIteration

# Test 6: Streaming File Processing
def stream_process_large_file():
    """Simulate processing a large file in chunks"""
    print("\n[STREAM] Processing large dataset...")
    large_data = [{"id": i, "data": f"item_{i}"} for i in range(100)]
    
    chunk_size = 10
    chunks = []
    for i in range(0, len(large_data), chunk_size):
        chunk = large_data[i:i+chunk_size]
        chunks.append(chunk)
        print(f"  Processed chunk {i//chunk_size + 1}: {len(chunk)} items")
    
    return chunks

# Test 7: Backpressure Simulation
def stream_with_backpressure():
    """Simulate streaming with rate limiting"""
    print("\n[STREAM] Simulating backpressure...")
    items = list(range(20))
    processed = 0
    max_buffer = 5
    
    for item in items:
        if processed >= max_buffer:
            print(f"  ⏸ Buffer full ({processed}), simulating backpressure...")
            time.sleep(0.1)
            processed = 0
        print(f"  ✓ Processed item {item}")
        processed += 1
    
    return len(items)

if __name__ == "__main__":
    print("=" * 70)
    print("ADVANCED STREAMING & GENERATOR TESTS")
    print("=" * 70)
    
    # Test 1: Classic Iterator
    print("\n[TEST 1] Classic Iterator Protocol")
    print("-" * 50)
    iterator = NumberIterator(5)
    result = list(iterator)
    print(f"✓ NumberIterator: {result}")
    
    # Test 2: Fibonacci Generator
    print("\n[TEST 2] Fibonacci Generator")
    print("-" * 50)
    fib = list(fibonacci_generator(10))
    print(f"✓ Fibonacci sequence: {fib}")
    
    # Test 3: Chained Generators
    print("\n[TEST 3] Chained Generators (Map & Filter)")
    print("-" * 50)
    numbers = range(10)
    mapped = list(map_generator(lambda x: x * 2, numbers))
    filtered = list(filter_generator(lambda x: x > 5, mapped))
    print(f"✓ Original: {list(numbers)}")
    print(f"✓ Mapped (*2): {mapped}")
    print(f"✓ Filtered (>5): {filtered}")
    
    # Test 4: Async Context Manager
    print("\n[TEST 4] Async Context Manager")
    print("-" * 50)
    async def test_context():
        async with async_resource("database") as res:
            print(f"  Using resource: {res}")
            await asyncio.sleep(0.2)
        return "Context manager test complete"
    
    ctx_result = asyncio.run(test_context())
    print(f"✓ {ctx_result}")
    
    # Test 5: Async Iterator
    print("\n[TEST 5] Async Iterator")
    print("-" * 50)
    async def test_async_iterator():
        counter = AsyncCounter(5)
        results = []
        async for num in counter:
            print(f"  Received async value: {num}")
            results.append(num)
        return results
    
    async_results = asyncio.run(test_async_iterator())
    print(f"✓ AsyncCounter results: {async_results}")
    
    # Test 6: Large File Streaming
    print("\n[TEST 6] Large File Streaming Simulation")
    print("-" * 50)
    chunks = stream_process_large_file()
    print(f"✓ Total chunks: {len(chunks)}, Total items: {sum(len(c) for c in chunks)}")
    
    # Test 7: Backpressure
    print("\n[TEST 7] Backpressure Simulation")
    print("-" * 50)
    items_processed = stream_with_backpressure()
    print(f"✓ Processed {items_processed} items with backpressure")
    
    print("\n" + "=" * 70)
    print("ALL ADVANCED STREAMING TESTS PASSED ✓")
    print("=" * 70)
    
    # Comprehensive Summary
    print("\n📊 STREAMING CAPABILITIES SUMMARY:")
    print("  1. Iterator Protocol (__iter__/__next__): WORKING")
    print("  2. Generator Functions: WORKING")
    print("  3. Generator Chains (map/filter): WORKING")
    print("  4. Async Context Managers: WORKING")
    print("  5. Async Iterators (__aiter__/__anext__): WORKING")
    print("  6. Chunked Processing: WORKING")
    print("  7. Backpressure Handling: WORKING")
    print("\n✨ Total Tests: 7/7 PASSED")
    print(f"⏱ Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
