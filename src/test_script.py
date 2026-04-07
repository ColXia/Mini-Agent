import json
import sys
from datetime import datetime

# Test data processing
test_data = [
    {"id": 1, "name": "Test Item 1", "value": 100},
    {"id": 2, "name": "Test Item 2", "value": 200},
    {"id": 3, "name": "Test Item 3", "value": 300}
]

# Perform calculations
total = sum(item["value"] for item in test_data)
avg = total / len(test_data)

# Create result
result = {
    "timestamp": datetime.now().isoformat(),
    "python_version": sys.version,
    "test_data": test_data,
    "calculations": {
        "total": total,
        "average": avg,
        "count": len(test_data)
    },
    "platform": sys.platform,
    "status": "success"
}

# Output as formatted JSON
print(json.dumps(result, indent=2))
