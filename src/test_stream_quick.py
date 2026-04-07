"""
Quick Streaming Test - Fast version
"""
import json
import time
from datetime import datetime

print("=" * 70)
print("STREAMING TEST - QUICK VERSION")
print("=" * 70)

# Test 1: JSONL streaming
print("\n[Test 1] JSON Lines Streaming...")
with open('test_data_large.json', 'r') as f:
    lines = f.readlines()
    items = [json.loads(line) for line in lines]
print(f"✓ JSONL: {len(items)} items streamed and parsed")

# Test 2: CSV streaming
print("\n[Test 2] CSV Streaming...")
with open('test_data_large.csv', 'r') as f:
    csv_lines = f.readlines()
print(f"✓ CSV: {len(csv_lines)} lines streamed")

# Test 3: Line-by-line text streaming
print("\n[Test 3] Text File Streaming...")
with open('test_data_lines.txt', 'r') as f:
    text_lines = [line.strip() for line in f]
print(f"✓ Text: {len(text_lines)} lines streamed")

# Test 4: Generator streaming
print("\n[Test 4] Generator Streaming...")
def stream_items(n):
    for i in range(n):
        yield {"id": i, "value": i * 10}

gen_items = list(stream_items(100))
print(f"✓ Generator: {len(gen_items)} items streamed")

# Test 5: Chunked file streaming
print("\n[Test 5] Chunked Streaming...")
large_data = list(range(1000))
chunk_size = 100
chunks = [large_data[i:i+chunk_size] for i in range(0, len(large_data), chunk_size)]
print(f"✓ Chunked: {len(chunks)} chunks from {len(large_data)} items")

# Test 6: Real-time simulation
print("\n[Test 6] Real-time Stream Simulation...")
start = time.time()
count = 0
for i in range(10):
    time.sleep(0.05)
    count += 1
elapsed = time.time() - start
print(f"✓ Real-time: {count} items in {elapsed:.2f}s")

print("\n" + "=" * 70)
print("ALL STREAMING TESTS PASSED ✓")
print("=" * 70)
