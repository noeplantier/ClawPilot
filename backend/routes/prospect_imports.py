"""Import a prospect list (CSV/JSON) that a human supplies, with its origin and legal basis.

Off unless `FEATURE_PROSPECT_IMPORT=true`. Two steps: a preview (default, writes nothing) and the import, which needs
`attestation: true`. Imported prospects enter the same pipeline as discovered ones: deduplicated, checked against the
suppression list, scored from what is actually known (absence in a supplied list is UNKNOWN, never a finding), and
`pending` human review. Nothing is fetched from the network and nothing is sent. The list content is never logged or
audited: only its SHA-256 and counts.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from models import ImportBatchOut, ImportIn, ImportOut, ImportRowError
from repositories import audit_repo, import_repo
from services import feature_flags
from services.outreach_os import importer, pipeline
from services.site_fetcher_svc import HttpSiteFetcher

router = APIRouter(prefix="/prospect-imports", tags=["prospect-imports"])
decider = require_roles("owner", "admin")
MAX_ERRORS_SHOWN = 50


def _account(user: dict) -> uuid.UUID:
    return uuid.UUID(user["org_id"])


def _refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "retry_at": None})


def _batch_out(b) -> ImportBatchOut:
    return ImportBatchOut(
        id=str(b.id),
        created_at=b.created_at,
        filename=b.filename,
        format=b.format,
        origin=b.origin,
        legal_basis=b.legal_basis,
        legal_basis_note=b.legal_basis_note,
        rows_total=b.rows_total,
        source_name=b.source_name,
        summary=b.summary,
    )


@router.get("", response_model=list[ImportBatchOut])
async def list_imports(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return [_batch_out(b) for b in await import_repo.list_batches(session, _account(user))]


@router.post("", response_model=ImportOut)
async def import_prospects(
    payload: ImportIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    if not feature_flags.is_enabled("prospect_import"):
        raise _refuse(403, "feature_disabled", "Prospect import is off (FEATURE_PROSPECT_IMPORT)")
    if payload.check_websites and not feature_flags.is_enabled("external_sources"):
        raise _refuse(
            409, "external_sources_disabled", "Checking websites needs FEATURE_EXTERNAL_SOURCES (off by default)"
        )
    account_id = _account(user)
    batch_id = uuid.uuid4()
    source_name = f"import:{batch_id.hex[:8]}"
    try:
        parsed = importer.parse_import(
            payload.content, payload.format, source_name=source_name, default_source_url=f"import://{source_name}"
        )
    except importer.ImportRejected as exc:
        raise _refuse(422, "import_rejected", str(exc))

    already = await import_repo.get_by_hash(session, account_id, parsed.content_sha256) is not None
    shown_errors = [ImportRowError(row=e.row, message=e.message) for e in parsed.errors[:MAX_ERRORS_SHOWN]]

    def result(
        *,
        preview: bool,
        batch_id: str | None,
        entities: int,
        merged: int,
        suppressed: int,
        created: int,
        updated: int,
        sites_checked: int = 0,
    ) -> ImportOut:
        return ImportOut(
            preview=preview,
            batch_id=batch_id,
            rows_total=parsed.rows_total,
            rows_valid=len(parsed.listings),
            errors_count=len(parsed.errors),
            errors=shown_errors,
            ignored_columns=parsed.ignored_columns,
            entities=entities,
            duplicates_merged=merged,
            suppressed=suppressed,
            created=created,
            updated=updated,
            sites_checked=sites_checked,
            already_imported=already,
        )

    if payload.preview:
        pv = await pipeline.preview_listings(session, account_id, parsed.listings)
        return result(
            preview=True,
            batch_id=None,
            entities=pv.entities,
            merged=pv.duplicates_merged,
            suppressed=pv.suppressed,
            created=pv.would_create,
            updated=pv.would_update,
        )

    if not payload.attestation:
        raise _refuse(
            422, "attestation_required", "Confirm that you have the right to use this list on the stated legal basis"
        )
    if not parsed.listings:
        raise _refuse(422, "nothing_to_import", "No valid row to import")

    license_note = f"Supplied list: {payload.origin} — legal basis: {payload.legal_basis}"[:1000]
    summary = await pipeline.run_discovery(
        session,
        account_id,
        adapter=importer.ListAdapter(source_name, license_note, parsed.listings),
        fetcher=HttpSiteFetcher() if payload.check_websites else importer.NoNetworkFetcher(),
        now=date.today(),
        user_id=uuid.UUID(user["id"]),
        vertical=payload.vertical,
        country=payload.country,
        language=payload.language,
        trust_absence=False,
    )
    batch = await import_repo.create(
        session,
        account_id,
        id=batch_id,
        created_by_user_id=uuid.UUID(user["id"]),
        source_name=source_name,
        filename=payload.filename,
        format=payload.format,
        content_sha256=parsed.content_sha256,
        origin=payload.origin,
        legal_basis=payload.legal_basis,
        legal_basis_note=payload.legal_basis_note,
        country=payload.country,
        language=payload.language,
        rows_total=parsed.rows_total,
        summary={**summary.__dict__, "rows_valid": len(parsed.listings), "errors_count": len(parsed.errors)},
    )
    await audit_repo.log(
        session,
        account_id,
        action="prospect_import.committed",
        resource_type="prospect_import",
        resource_id=batch.id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={  # never the rows themselves
            "sha256": parsed.content_sha256,
            "legal_basis": payload.legal_basis,
            "rows_total": parsed.rows_total,
            "created": summary.prospects_created,
            "suppressed": summary.suppressed,
            "check_websites": payload.check_websites,
            "sites_checked": summary.sites_checked,
        },
    )
    return result(
        preview=False,
        batch_id=str(batch.id),
        entities=summary.entities,
        merged=summary.duplicates_merged,
        suppressed=summary.suppressed,
        created=summary.prospects_created,
        updated=summary.prospects_updated,
        sites_checked=summary.sites_checked,
    )
