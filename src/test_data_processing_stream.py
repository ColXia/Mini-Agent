"""
Data Processing Stream
Tests data processing and transformation
"""
import json

print("Data Processing Stream Test")
print("=" * 70)

# Test 1: ETL Stream
print("\n[Test 1] ETL (Extract-Transform-Load) Stream...")
def extract(data_source):
    for record in data_source:
        yield record

def transform(record):
    return {
        "id": record["id"],
        "full_name": f"{record['first']} {record['last']}",
        "age": 2026 - record["birth_year"],
        "department": record["dept"].upper()
    }

def load(records):
    return list(records)

raw_data = [
    {"id": 1, "first": "John", "last": "Doe", "birth_year": 1990, "dept": "engineering"},
    {"id": 2, "first": "Jane", "last": "Smith", "birth_year": 1985, "dept": "marketing"},
    {"id": 3, "first": "Bob", "last": "Johnson", "birth_year": 1992, "dept": "sales"}
]

extracted = extract(raw_data)
transformed = (transform(r) for r in extracted)
loaded = load(transformed)
print(f"✓ ETL Stream: {len(loaded)} records processed")

# Test 2: Aggregation stream
print("\n[Test 2] Aggregation Stream...")
def aggregate_transactions(transactions):
    totals = {}
    for txn in transactions:
        category = txn["category"]
        if category not in totals:
            totals[category] = {"count": 0, "total": 0}
        totals[category]["count"] += 1
        totals[category]["total"] += txn["amount"]
    return totals

transactions = [
    {"category": "food", "amount": 50},
    {"category": "transport", "amount": 30},
    {"category": "food", "amount": 25},
    {"category": "entertainment", "amount": 100},
    {"category": "transport", "amount": 45},
    {"category": "food", "amount": 60}
]

aggregated = aggregate_transactions(transactions)
print(f"✓ Aggregation: {len(aggregated)} categories")
for cat, data in aggregated.items():
    print(f"  - {cat}: {data['count']} transactions, total=${data['total']}")

# Test 3: Join stream
print("\n[Test 3] Join Stream...")
users = [
    {"id": 1, "name": "User A"},
    {"id": 2, "name": "User B"},
    {"id": 3, "name": "User C"}
]

orders = [
    {"user_id": 1, "order": "Order 1"},
    {"user_id": 2, "order": "Order 2"},
    {"user_id": 1, "order": "Order 3"}
]

user_dict = {u["id"]: u for u in users}
joined = [
    {**order, "user": user_dict[order["user_id"]]["name"]}
    for order in orders
]
print(f"✓ Join: {len(joined)} joined records")

# Test 4: Window aggregation
print("\n[Test 4] Window Aggregation Stream...")
data_points = list(range(1, 21))
window_size = 5
windows = [
    data_points[i:i+window_size] 
    for i in range(0, len(data_points), window_size)
]
window_stats = [
    {"window": i+1, "min": min(w), "max": max(w), "avg": sum(w)/len(w)}
    for i, w in enumerate(windows)
]
print(f"✓ Windows: {len(window_stats)} windows created")
for ws in window_stats:
    print(f"  Window {ws['window']}: min={ws['min']}, max={ws['max']}, avg={ws['avg']:.1f}")

# Test 5: State machine stream
print("\n[Test 5] State Machine Stream...")
def state_machine(events):
    state = "IDLE"
    for event in events:
        if state == "IDLE" and event == "START":
            state = "RUNNING"
        elif state == "RUNNING" and event == "PAUSE":
            state = "PAUSED"
        elif state == "PAUSED" and event == "RESUME":
            state = "RUNNING"
        elif state == "RUNNING" and event == "STOP":
            state = "IDLE"
        yield {"event": event, "state": state}

events = ["START", "PAUSE", "RESUME", "STOP", "START", "STOP"]
states = list(state_machine(events))
print(f"✓ State machine: {len(states)} transitions")
for s in states:
    print(f"  Event: {s['event']:6s} → State: {s['state']}")

print("\nData Processing Stream Complete ✓")
