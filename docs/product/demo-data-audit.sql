-- Read-only audit. Run only with an explicitly approved, read-only database role.
-- No name match alone is treated as proof, and this file contains no UPDATE/DELETE.
WITH evidence AS (
    SELECT
        l.account_id,
        l.id AS lead_id,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM prospect_sources ps
                WHERE ps.account_id = l.account_id AND ps.lead_id = l.id
                  AND (ps.source_name IN ('fixture_directory', 'world_fixture')
                       OR ps.source_url LIKE 'fixture://%'
                       OR ps.license_note ILIKE '%fictional data%')
            ) THEN 'confirmed_fixture_provenance'
            WHEN EXISTS (
                SELECT 1
                FROM contacts c
                JOIN consent_records cr ON cr.contact_id = c.id
                WHERE c.account_id = l.account_id AND c.lead_id = l.id
                  AND cr.account_id = l.account_id AND cr.source = 'demo_seed'
            ) THEN 'confirmed_demo_seed_consent'
            WHEN lower(coalesce(l.email, '')) LIKE '%.example'
                 OR lower(coalesce(l.website, '')) LIKE '%.example%'
                 OR lower(coalesce(l.website, '')) LIKE '%latable-alice%'
                 OR lower(coalesce(l.website, '')) LIKE '%chez-marcel%'
                 OR lower(coalesce(l.website, '')) LIKE '%brasserie-rhone%'
              THEN 'suspect_only_manual_review'
            ELSE NULL
        END AS evidence_code
    FROM leads l
    WHERE l.deleted_at IS NULL
)
SELECT account_id, evidence_code, count(*) AS candidate_count, array_agg(lead_id ORDER BY lead_id) AS candidate_ids
FROM evidence
WHERE evidence_code IS NOT NULL
GROUP BY account_id, evidence_code
ORDER BY account_id, evidence_code;
