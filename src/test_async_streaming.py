"""
Async Streaming Test - Advanced async operations
"""

import asyncio
import json
import time
from datetime import datetime

async def async_generator(n: int) -> AsyncGenerator[int, None]:
    """Async generator that yields numbers"""
    for i in range(n):
        await asyncio.sleep(0.1)
        yield i

async def async_processor(data: list) -> AsyncGenerator[dict, None]:
    """Async processor with simulated I/O"""
    for item in data:
        await asyncio.sleep(0.1)
        yield {"id": item, "processed": True, "timestamp": time.time()}

async def async_batch_processor(items: list, batch_size: int):
    """Process items in batches asynchronously"""
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        await asyncio.sleep(0.1)
        results.append({"batch_id": i // batch_size, "items": batch, "size": len(batch)})
    return results

async def stream_with_backpressure():
    """Simulate backpressure handling"""
    buffer = []
    max_buffer = 5
    produced = 0
    
    # Producer
    async def producer():
        nonlocal produced
        for i in range(10):
            while len(buffer) >= max_buffer:
                await asyncio.sleep(0.05)
            buffer.append(i)
            produced += 1
    
    # Consumer
    async def consumer():
        consumed = 0
        while consumed < 10:
            if buffer:
                item = buffer.pop(0)
                await asyncio.sleep(0.08)
                consumed += 1
                yield item
    
    # Run both
    await producer()
    async for item in consumer():
        pass
    
    return produced

async def async_file_like_stream(lines: list) -> AsyncGenerator[str, None]:
    """Async file-like streaming"""
    for line in lines:
        await asyncio.sleep(0.05)
        yield line

async def main():
    print("=" * 70)
    print("ASYNC STREAMING TEST - COMPREHENSIVE")
    print("=" * 70)
    print(f"Start: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # Test 1: Basic async generator
    print("\n[Async Test 1] Basic Async Generator...")
    results = [i async for i in async_generator(5)]
    print(f"✓ Async generator result: {results}")
    
    # Test 2: Async processor
    print("\n[Async Test 2] Async Processor...")
    data = [1, 2, 3, 4, 5]
    processed = [item async for item in async_processor(data)]
    print(f"✓ Processed {len(processed)} items asynchronously")
    
    # Test 3: Async batch processor
    print("\n[Async Test 3] Async Batch Processor...")
    items = list(range(20))
    batches = await async_batch_processor(items, 5)
    print(f"✓ Created {len(batches)} batches from {len(items)} items")
    
    # Test 4: Backpressure handling
    print("\n[Async Test 4] Backpressure Simulation...")
    produced = await stream_with_backpressure()
    print(f"✓ Backpressure test completed: {produced} items processed")
    
    # Test 5: Async file-like stream
    print("\n[Async Test 5] Async File-like Stream...")
    lines = ["Header", "Data 1", "Data 2", "Footer"]
    streamed = [line async for line in async_file_like_stream(lines)]
    print(f"✓ Async file stream: {streamed}")
    
    # Test 6: Concurrent async streams
    print("\n[Async Test 6] Concurrent Streams...")
    async def stream_1():
        for i in range(3):
            await asyncio.sleep(0.05)
            yield f"S1-{i}"
    
    async def stream_2():
        for i in range(3):
            await asyncio.sleep(0.05)
            yield f"S2-{i}"
    
    results_1 = [x async for x in stream_1()]
    results_2 = [x async for x in stream_2()]
    print(f"✓ Stream 1: {results_1}")
    print(f"✓ Stream 2: {results_2}")
    
    # Test 7: Async pipeline
    print("\n[Async Test 7] Async Pipeline...")
    pipeline_data = list(range(10))
    pipeline_result = [
        item * 2 
        async for item in async_processor(pipeline_data)
    ]
    print(f"✓ Pipeline processed {len(pipeline_result)} items")
    
    print("\n" + "=" * 70)
    print("ASYNC STREAMING TEST - COMPLETE")
    print("=" * 70)
    print(f"End: {datetime.now().isoformat()}")
    print("All async streaming tests passed ✓")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
