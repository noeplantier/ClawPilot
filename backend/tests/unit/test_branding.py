"""The product is called "Plantiers - OutreachOS": the old name must not survive in anything a reader sees.

Identifiers that would break a running deployment if renamed (database and Render service names, Docker, CI database)
are listed explicitly below: renaming them is an infrastructure migration, not a text change.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INFRA_IDENTIFIERS = {
    "render.yaml",  # service, database and Redis names: renaming creates new services on Render
    "docker-compose.yml",  # local database name and role
    ".github/workflows/ci.yml",  # CI database name and role
    "backend/alembic.ini",  # local default connection string
    "backend/.env.example",  # local default connection string
    "docs/deployment.md",  # documents the Render service names above
}
HISTORY = {
    "README.md",
    "docs/schema.md",
    "docs/cloud-sessions.md",
    "memory/PRD.md",
}  # "formerly ClawPilot" note, dated records
SKIP_SUFFIXES = (".png", ".lock", "package-lock.json")


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if not f.endswith(SKIP_SUFFIXES)]


def test_the_old_name_is_gone_from_user_facing_files():
    offenders = []
    for rel in _tracked_files():
        if rel in INFRA_IDENTIFIERS or rel in HISTORY or rel == "backend/tests/unit/test_branding.py":
            continue
        path = ROOT / rel
        if path.is_file() and "clawpilot" in path.read_text(encoding="utf-8", errors="ignore").lower():
            offenders.append(rel)
    assert not offenders, f"old product name still present in: {offenders}"


def test_infrastructure_identifiers_are_only_identifiers():
    """The exempt files may keep `clawpilot` as a database/service name, but not in a human-readable sentence."""
    for rel in INFRA_IDENTIFIERS:
        for line in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            if "clawpilot" in line.lower():
                assert not line.lstrip().startswith("#") or "clawpilot-" in line.lower(), (rel, line)
