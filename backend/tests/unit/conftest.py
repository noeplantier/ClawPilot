"""Unit tests: no server, no network, no database. Import app modules from backend/."""

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# Importing the app builds (but never opens) a DB engine and reads JWT_SECRET.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost/unused")
os.environ.setdefault("JWT_SECRET", secrets.token_hex(16))
