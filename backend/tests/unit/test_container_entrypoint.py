"""The container starts through start.sh: migrations first, then the port the platform provides (Render sets PORT)."""

import os
import stat
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_the_dockerfile_runs_the_start_script_not_a_hard_coded_port():
    dockerfile = (BACKEND / "Dockerfile").read_text()
    assert 'CMD ["sh", "/app/start.sh"]' in dockerfile
    assert "--port 8000" not in dockerfile


def test_the_start_script_migrates_then_binds_to_port_with_a_local_default():
    script = (BACKEND / "start.sh").read_text()
    assert script.index("alembic upgrade head") < script.index("exec uvicorn")
    assert '--port "${PORT:-8000}"' in script and "--host 0.0.0.0" in script
    assert "set -e" in script  # a failed migration must stop the start, never serve on a half-migrated schema
    assert os.stat(BACKEND / "start.sh").st_mode & stat.S_IXUSR
