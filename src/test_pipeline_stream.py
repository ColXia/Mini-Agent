"""
Pipelined Streaming Test
Tests data pipeline streaming operations
"""
import json
import time
from collections import deque

print("Pipeline Streaming Test")
print("=" * 60)

# Test 1: Pipeline stages
print("\n[Test 1] Multi-stage Pipeline...")
def stage_source(n):
    for i in range(n):
        yield i

def stage_filter_even(data):
    for item in data:
        if item % 2 == 0:
            yield item

def stage_transform(data):
    for item in data:
        yield {"original": item, "squared": item ** 2}

def stage_aggregate(data):
    results = []
    for item in data:
        results.append(item)
    return results

source = stage_source(20)
filtered = stage_filter_even(source)
transformed = stage_transform(filtered)
result = stage_aggregate(transformed)
print(f"✓ Pipeline: 20 items → {len(result)} results")

# Test 2: Buffer-based streaming
print("\n[Test 2] Buffered Streaming...")
buffer = deque(maxlen=3)
for i in range(10):
    buffer.append(i)
print(f"✓ Buffer: Final buffer {list(buffer)}")

# Test 3: Stream with backpressure
print("\n[Test 3] Backpressure Simulation...")
buffer_size = 5
produced = 0
consumed = 0
items = list(range(20))

# Simulate producer
production_buffer = []
for item in items:
    if len(production_buffer) < buffer_size:
        production_buffer.append(item)
        produced += 1

# Simulate consumer
consumed_items = []
while production_buffer:
    consumed_items.append(production_buffer.pop(0))
    consumed += 1

print(f"✓ Backpressure: Produced {produced}, Consumed {consumed}")

# Test 4: Stream merging
print("\n[Test 4] Stream Merging...")
def merge(*streams):
    for stream in streams:
        yield from stream

merged = list(merge([1, 2], [3, 4], [5, 6]))
print(f"✓ Merge: {[1, 2]} + {[3, 4]} + {[5, 6]} → {merged}")

# Test 5: Stream splitting
print("\n[Test 5] Stream Splitting...")
data = [1, 2, 3, 4, 5, 6]
even = []
odd = []
for item in data:
    if item % 2 == 0:
        even.append(item)
    else:
        odd.append(item)
print(f"✓ Split: {data} → Even: {even}, Odd: {odd}")

# Test 6: Stream with timeout simulation
print("\n[Test 6] Stream with Timing...")
timestamps = []
start = time.time()
for i in range(5):
    timestamps.append(time.time() - start)
    time.sleep(0.05)
intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
print(f"✓ Timed stream: {len(intervals)} intervals, avg: {sum(intervals)/len(intervals):.3f}s")

print("\nPipeline Streaming Complete ✓")
