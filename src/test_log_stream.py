"""
Log Streaming Simulation
Simulates real-time log streaming
"""
import json
import time
from datetime import datetime

print("Log Streaming Simulation")
print("=" * 70)

log_levels = ["INFO", "WARN", "ERROR", "DEBUG"]
messages = [
    "Application started",
    "Loading configuration",
    "Database connection established",
    "Processing request",
    "Request completed successfully",
    "Cache hit",
    "Cache miss - fetching from database",
    "User authentication successful",
    "Session created",
    "Processing batch job"
]

print("\n[Log Stream Output]")
print("-" * 70)
start = time.time()
for i in range(15):
    timestamp = datetime.now().isoformat()
    level = log_levels[i % len(log_levels)]
    message = messages[i % len(messages)]
    log_entry = f"[{timestamp}] [{level}] {message}"
    print(log_entry)
    time.sleep(0.1)
    
print("-" * 70)
elapsed = time.time() - start
print(f"Log stream: {15} entries in {elapsed:.2f}s")
print("=" * 70)
