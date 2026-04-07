import time
import sys

print("Starting streaming test...")
for i in range(1, 6):
    print(f"Processing item {i}/{5}")
    time.sleep(0.5)
print("Streaming test complete!")
