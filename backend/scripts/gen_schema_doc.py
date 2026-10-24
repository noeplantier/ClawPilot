"""Regenerate docs/schema.md from the ORM models (source of truth: backend/db/models).

cd backend && python -m scripts.gen_schema_doc          # write docs/schema.md
cd backend && python -m scripts.gen_schema_doc --check  # exit 1 if the file is stale
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost/unused")  # never connected

from sqlalchemy import CheckConstraint, ForeignKeyConstraint  # noqa: E402

import db.models  # noqa: E402,F401  (registers every table on Base.metadata)
from db.base import Base  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "schema.md"


def render() -> str:
    lines = [
        "# Schéma de données",
        "",
        "Généré par `backend/scripts/gen_schema_doc.py` depuis les modèles ORM — ne pas éditer à la main.",
        "",
    ]
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        lines += [f"## `{table.name}`", "", "| Colonne | Type | Null | Défaut |", "|---|---|---|---|"]
        for col in table.columns:
            default = ""
            sd = col.server_default
            if sd is not None:
                arg = sd.arg if hasattr(sd, "arg") else sd.sqltext
                default = f"`{arg.text if hasattr(arg, 'text') else arg}`"
            pk = " (PK)" if col.primary_key else ""
            lines.append(f"| `{col.name}`{pk} | {col.type} | {'oui' if col.nullable else 'non'} | {default} |")
        fks = sorted(
            f"`{', '.join(c.name for c in fk.columns)}` → `{fk.elements[0].target_fullname}` "
            f"(ON DELETE {fk.ondelete or 'NO ACTION'})"
            for fk in table.constraints
            if isinstance(fk, ForeignKeyConstraint)
        )
        checks = sorted(f"`{c.name}`: `{c.sqltext}`" for c in table.constraints if isinstance(c, CheckConstraint))
        uniques = sorted(
            f"`{c.name}` ({', '.join(col.name for col in c.columns)})"
            for c in table.constraints
            if c.__class__.__name__ == "UniqueConstraint"
        )
        indexes = sorted(f"`{i.name}` ({', '.join(str(c) for c in i.expressions)})" for i in table.indexes)
        for title, items in (
            ("Relations", fks),
            ("Contraintes CHECK", checks),
            ("Unicité", uniques),
            ("Index", indexes),
        ):
            if items:
                lines += ["", f"**{title}**", ""] + [f"- {x}" for x in items]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    content = render()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text() == content else 1)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(content)
    print(f"wrote {OUT}")
