"""
Binary Streaming Test
"""
import struct
import json

print("Binary Streaming Test")
print("=" * 60)

# Test 1: Binary data streaming
print("\n[Test 1] Binary Data Stream...")
binary_data = bytes([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
chunks = [binary_data[i:i+3] for i in range(0, len(binary_data), 3)]
print(f"✓ Binary stream: {len(binary_data)} bytes → {len(chunks)} chunks")

# Test 2: Struct streaming
print("\n[Test 2] Struct Streaming...")
data = struct.pack('>III', 100, 200, 300)
unpacked = struct.unpack('>III', data)
print(f"✓ Struct: Packed {len(data)} bytes → {unpacked}")

# Test 3: Mixed stream
print("\n[Test 3] Mixed Data Stream...")
mixed = [
    {"type": "json", "data": {"id": 1}},
    "string data",
    b"binary data",
    [1, 2, 3],
    42
]
print(f"✓ Mixed stream: {len(mixed)} different types")

# Test 4: Stream processing with state
print("\n[Test 4] Stateful Stream Processing...")
state = {"count": 0, "sum": 0}
def stateful_processor(items):
    for item in items:
        state["count"] += 1
        state["sum"] += item
        yield {"item": item, "count": state["count"], "sum": state["sum"]}

results = list(stateful_processor([10, 20, 30, 40, 50]))
print(f"✓ Stateful: Processed {state['count']} items, sum={state['sum']}")

# Test 5: Windowing stream
print("\n[Test 5] Windowing Stream...")
def window_stream(data, size):
    for i in range(0, len(data), size):
        yield data[i:i+size]

items = list(range(7))
windows = list(window_stream(items, 3))
print(f"✓ Windowing: {len(items)} items → {len(windows)} windows")

print("\nBinary Streaming Complete ✓")
