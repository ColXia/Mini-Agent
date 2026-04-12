"""Test bootstrap for src-layout imports."""

from __future__ import annotations

import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Keep gateway API tests isolated from any real locally running demo stack.
os.environ.setdefault("MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK", "0")
