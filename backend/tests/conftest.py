"""Make the backend modules importable from the integration tests that call them in-process (backend/ is the root)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
