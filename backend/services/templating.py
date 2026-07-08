"""Lead/contact field token substitution shared by campaign step execution and the scheduler."""

from __future__ import annotations

TOKEN_FIELDS = ("full_name", "company", "title", "country")


def render(template: str, lead: dict) -> str:
    """Substitute {{first_name}}, {{full_name}}, {{company}}, {{title}}, {{country}} tokens."""
    if not template:
        return ""
    first = (lead.get("full_name") or "").split(" ")[0] or "there"
    mapping = {"{{first_name}}": first}
    mapping.update({f"{{{{{f}}}}}": lead.get(f) or "" for f in TOKEN_FIELDS})
    out = template
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out
