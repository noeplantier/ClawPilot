# Schéma de données

Généré par `backend/scripts/gen_schema_doc.py` depuis les modèles ORM — ne pas éditer à la main.

## `accounts`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `name` | VARCHAR | non |  |
| `plan` | VARCHAR | non | `pro` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |

**Contraintes CHECK**

- `ck_accounts_plan`: `plan IN ('free','pro','enterprise')`

## `agents`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `name` | VARCHAR | non |  |
| `role` | VARCHAR | non | `outreach` |
| `status` | VARCHAR | non | `idle` |
| `tasks_completed` | INTEGER | non | `0` |
| `tasks_in_queue` | INTEGER | non | `0` |
| `last_heartbeat` | DATETIME | non | `now()` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |
| `deleted_at` | DATETIME | oui |  |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_agents_role`: `role IN ('outreach','enrichment','scraper','responder')`
- `ck_agents_status`: `status IN ('idle','running','paused','error')`

## `audit_logs`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `actor_user_id` | UUID | oui |  |
| `actor_type` | VARCHAR | non | `user` |
| `action` | VARCHAR | non |  |
| `resource_type` | VARCHAR | non |  |
| `resource_id` | UUID | oui |  |
| `diff` | JSONB | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `actor_user_id` → `users.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_audit_logs_actor_type`: `actor_type IN ('user','system','celery_task')`

**Index**

- `ix_audit_logs_account_created` (audit_logs.account_id, created_at DESC)

## `campaign_leads`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `campaign_id` (PK) | UUID | non |  |
| `lead_id` (PK) | UUID | non |  |
| `assigned_at` | DATETIME | non | `now()` |

**Relations**

- `campaign_id` → `campaigns.id` (ON DELETE CASCADE)
- `lead_id` → `leads.id` (ON DELETE CASCADE)

**Index**

- `ix_campaign_leads_lead` (campaign_leads.lead_id)

## `campaign_steps`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `campaign_id` | UUID | non |  |
| `step_index` | INTEGER | non |  |
| `channel` | VARCHAR | non | `email` |
| `delay_hours` | INTEGER | non | `0` |
| `subject` | VARCHAR | oui |  |
| `body` | TEXT | non | `` |
| `language` | VARCHAR | non | `en` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |

**Relations**

- `campaign_id` → `campaigns.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_campaign_steps_channel`: `channel IN ('email','whatsapp')`

**Index**

- `uq_campaign_steps_campaign_index` (campaign_steps.campaign_id, campaign_steps.step_index)

## `campaigns`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `name` | VARCHAR | non |  |
| `goal` | TEXT | oui |  |
| `status` | VARCHAR | non | `draft` |
| `channels` | ARRAY | non | `'{email}'` |
| `agent_id` | UUID | oui |  |
| `sent` | INTEGER | non | `0` |
| `opened` | INTEGER | non | `0` |
| `replied` | INTEGER | non | `0` |
| `converted` | INTEGER | non | `0` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |
| `deleted_at` | DATETIME | oui |  |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `agent_id` → `agents.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_campaigns_status`: `status IN ('draft','running','paused','completed')`

**Index**

- `ix_campaigns_account_id` (campaigns.account_id)

## `consent_current`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `contact_id` (PK) | UUID | non |  |
| `channel` (PK) | VARCHAR | non |  |
| `status` | VARCHAR | non |  |
| `updated_at` | DATETIME | non | `now()` |

**Relations**

- `contact_id` → `contacts.id` (ON DELETE CASCADE)

## `consent_records`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `contact_id` | UUID | non |  |
| `channel` | VARCHAR | non |  |
| `status` | VARCHAR | non |  |
| `source` | VARCHAR | non |  |
| `evidence` | JSONB | non | `'{}'::jsonb` |
| `recorded_at` | DATETIME | non | `now()` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `contact_id` → `contacts.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_consent_records_channel`: `channel IN ('email','whatsapp')`
- `ck_consent_records_status`: `status IN ('opted_in','opted_out','unknown')`

**Index**

- `ix_consent_records_contact_channel` (consent_records.contact_id, consent_records.channel, recorded_at DESC)

## `contacts`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `lead_id` | UUID | non |  |
| `full_name` | VARCHAR | non |  |
| `email` | CITEXT | oui |  |
| `phone` | VARCHAR | oui |  |
| `role_title` | VARCHAR | oui |  |
| `is_primary` | BOOLEAN | non | `true` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |
| `deleted_at` | DATETIME | oui |  |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `lead_id` → `leads.id` (ON DELETE CASCADE)

**Index**

- `uq_contacts_lead_email` (contacts.lead_id, contacts.email)

## `email_sends`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `campaign_id` | UUID | oui |  |
| `campaign_step_id` | UUID | oui |  |
| `contact_id` | UUID | oui |  |
| `to_email` | CITEXT | non |  |
| `subject` | VARCHAR | oui |  |
| `body` | TEXT | non |  |
| `status` | VARCHAR | non | `queued` |
| `provider` | VARCHAR | non | `sendgrid` |
| `provider_message_id` | VARCHAR | oui |  |
| `provider_message_id_base` | VARCHAR | oui | `split_part(provider_message_id, '.', 1)` |
| `error` | TEXT | oui |  |
| `sent_at` | DATETIME | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `campaign_id` → `campaigns.id` (ON DELETE SET NULL)
- `campaign_step_id` → `campaign_steps.id` (ON DELETE SET NULL)
- `contact_id` → `contacts.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_email_sends_status`: `status IN ('queued','sent','delivered','opened','clicked','replied','bounced','failed','mock')`

**Index**

- `ix_email_sends_provider_id_base` (email_sends.provider_message_id_base)
- `ix_email_sends_provider_message_id` (email_sends.provider_message_id)

## `lead_scores`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `lead_id` | UUID | non |  |
| `account_id` | UUID | non |  |
| `score` | INTEGER | non |  |
| `reason` | VARCHAR | non |  |
| `delta` | INTEGER | non |  |
| `computed_by` | VARCHAR | non | `system` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `lead_id` → `leads.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_lead_scores_computed_by`: `computed_by IN ('system','celery_task','manual')`

**Index**

- `ix_lead_scores_lead_created` (lead_scores.lead_id, created_at DESC)

## `lead_sources`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `name` | VARCHAR | non |  |
| `kind` | VARCHAR | non | `manual` |
| `config` | JSONB | non | `'{}'::jsonb` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_lead_sources_kind`: `kind IN ('manual','csv_import','scraper','api','enrichment','referral')`

**Index**

- `uq_lead_sources_account_name` (lead_sources.account_id, lead_sources.name)

## `lead_tags`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `lead_id` (PK) | UUID | non |  |
| `tag_id` (PK) | UUID | non |  |

**Relations**

- `lead_id` → `leads.id` (ON DELETE CASCADE)
- `tag_id` → `tags.id` (ON DELETE CASCADE)

## `leads`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `full_name` | VARCHAR | non |  |
| `email` | CITEXT | oui |  |
| `phone` | VARCHAR | oui |  |
| `company` | VARCHAR | oui |  |
| `title` | VARCHAR | oui |  |
| `country` | VARCHAR | oui |  |
| `language` | VARCHAR | non | `en` |
| `stage` | VARCHAR | non | `new` |
| `tags` | ARRAY | non | `'{}'` |
| `source_id` | UUID | oui |  |
| `notes` | TEXT | oui |  |
| `score` | INTEGER | non | `0` |
| `vertical` | VARCHAR | oui |  |
| `city` | VARCHAR | oui |  |
| `website` | VARCHAR | oui |  |
| `match_keys` | ARRAY | non | `'{}'` |
| `review_status` | VARCHAR | oui |  |
| `reviewed_at` | DATETIME | oui |  |
| `reviewed_by_user_id` | UUID | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |
| `deleted_at` | DATETIME | oui |  |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `reviewed_by_user_id` → `users.id` (ON DELETE SET NULL)
- `source_id` → `lead_sources.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_leads_review_status`: `review_status IS NULL OR review_status IN ('pending','approved','rejected')`
- `ck_leads_stage`: `stage IN ('new','contacted','engaged','qualified','won','lost')`

**Index**

- `ix_leads_account_created` (leads.account_id, created_at DESC)
- `ix_leads_account_review` (leads.account_id, leads.review_status)
- `ix_leads_account_score` (leads.account_id, score DESC)
- `ix_leads_account_stage` (leads.account_id, leads.stage)
- `ix_leads_match_keys_gin` (leads.match_keys)
- `ix_leads_tags_gin` (leads.tags)
- `uq_leads_account_email` (leads.account_id, leads.email)

## `message_drafts`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `lead_id` | UUID | non |  |
| `campaign_step_id` | UUID | oui |  |
| `channel` | VARCHAR | non | `email` |
| `subject` | VARCHAR | non |  |
| `body` | TEXT | non |  |
| `facts` | JSONB | non | `'[]'::jsonb` |
| `template_version` | VARCHAR | non |  |
| `status` | VARCHAR | non | `draft` |
| `dry_run` | BOOLEAN | non | `true` |
| `idempotency_key` | VARCHAR | non |  |
| `created_by_user_id` | UUID | oui |  |
| `reviewed_by_user_id` | UUID | oui |  |
| `reviewed_at` | DATETIME | oui |  |
| `review_note` | TEXT | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `campaign_step_id` → `campaign_steps.id` (ON DELETE SET NULL)
- `created_by_user_id` → `users.id` (ON DELETE SET NULL)
- `lead_id` → `leads.id` (ON DELETE CASCADE)
- `reviewed_by_user_id` → `users.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_message_drafts_channel`: `channel IN ('email')`
- `ck_message_drafts_status`: `status IN ('draft','approved','rejected')`

**Index**

- `ix_message_drafts_lead_created` (message_drafts.lead_id, created_at DESC)
- `uq_message_drafts_account_idempotency` (message_drafts.account_id, message_drafts.idempotency_key)

## `notes`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `lead_id` | UUID | oui |  |
| `campaign_id` | UUID | oui |  |
| `author_user_id` | UUID | non |  |
| `body` | TEXT | non |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |
| `deleted_at` | DATETIME | oui |  |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `author_user_id` → `users.id` (ON DELETE CASCADE)
- `campaign_id` → `campaigns.id` (ON DELETE CASCADE)
- `lead_id` → `leads.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_notes_target`: `lead_id IS NOT NULL OR campaign_id IS NOT NULL`

## `outreach_events`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `campaign_id` | UUID | oui |  |
| `campaign_step_id` | UUID | oui |  |
| `lead_id` | UUID | oui |  |
| `contact_id` | UUID | oui |  |
| `channel` | VARCHAR | non |  |
| `event_type` | VARCHAR | non |  |
| `direction` | VARCHAR | non | `outbound` |
| `occurred_at` | DATETIME | non | `now()` |
| `meta` | JSONB | non | `'{}'::jsonb` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `campaign_id` → `campaigns.id` (ON DELETE SET NULL)
- `campaign_step_id` → `campaign_steps.id` (ON DELETE SET NULL)
- `contact_id` → `contacts.id` (ON DELETE SET NULL)
- `lead_id` → `leads.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_outreach_events_channel`: `channel IN ('email','whatsapp')`
- `ck_outreach_events_direction`: `direction IN ('outbound','inbound')`
- `ck_outreach_events_event_type`: `event_type IN ('queued','sent','delivered','opened','clicked','replied','bounced','failed','opted_out')`

**Index**

- `ix_outreach_events_account_time` (outreach_events.account_id, occurred_at DESC)
- `ix_outreach_events_campaign_type` (outreach_events.campaign_id, outreach_events.event_type)

## `prospect_scores`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `lead_id` | UUID | non |  |
| `score_version_id` | UUID | non |  |
| `score` | INTEGER | non |  |
| `coverage` | FLOAT | non |  |
| `breakdown` | JSONB | non |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `lead_id` → `leads.id` (ON DELETE CASCADE)
- `score_version_id` → `score_versions.id` (ON DELETE RESTRICT)

**Contraintes CHECK**

- `ck_prospect_scores_range`: `score BETWEEN 0 AND 100`

**Index**

- `ix_prospect_scores_lead_created` (prospect_scores.lead_id, created_at DESC)

## `prospect_signals`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `lead_id` | UUID | non |  |
| `source_id` | UUID | oui |  |
| `signal_key` | VARCHAR | non |  |
| `state` | VARCHAR | non |  |
| `evidence` | TEXT | non |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `lead_id` → `leads.id` (ON DELETE CASCADE)
- `source_id` → `prospect_sources.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_prospect_signals_state`: `state IN ('unknown','detected','not_detected')`

**Index**

- `ix_prospect_signals_lead_key` (prospect_signals.lead_id, prospect_signals.signal_key, created_at DESC)

## `prospect_sources`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `lead_id` | UUID | non |  |
| `source_name` | VARCHAR | non |  |
| `source_url` | VARCHAR | non |  |
| `external_id` | VARCHAR | non |  |
| `license_note` | TEXT | non |  |
| `fetched_at` | DATETIME | non | `now()` |
| `content_hash` | VARCHAR | non |  |
| `fields` | JSONB | non | `'{}'::jsonb` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `lead_id` → `leads.id` (ON DELETE CASCADE)

**Index**

- `ix_prospect_sources_lead` (prospect_sources.lead_id)
- `uq_prospect_sources_listing_version` (prospect_sources.account_id, prospect_sources.source_name, prospect_sources.external_id, prospect_sources.content_hash)

## `score_versions`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `version` | INTEGER | non |  |
| `label` | VARCHAR | non |  |
| `config` | JSONB | non |  |
| `config_hash` | VARCHAR | non |  |
| `created_by_user_id` | UUID | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `created_by_user_id` → `users.id` (ON DELETE SET NULL)

**Index**

- `ix_score_versions_account_hash` (score_versions.account_id, score_versions.config_hash)
- `uq_score_versions_account_version` (score_versions.account_id, score_versions.version)

## `segments`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `name` | VARCHAR | non |  |
| `definition` | JSONB | non | `'{}'::jsonb` |
| `is_dynamic` | BOOLEAN | non | `true` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |
| `deleted_at` | DATETIME | oui |  |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Index**

- `uq_segments_account_name` (segments.account_id, segments.name)

## `send_policies`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `channel` | VARCHAR | non |  |
| `max_per_hour` | INTEGER | non | `100` |
| `window_start_hour` | INTEGER | non | `8` |
| `window_end_hour` | INTEGER | non | `18` |
| `timezone_source` | VARCHAR | non | `lead_country` |
| `account_default_timezone` | VARCHAR | non | `UTC` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_send_policies_channel`: `channel IN ('email','whatsapp')`
- `ck_send_policies_tz_source`: `timezone_source IN ('lead_country','account_default')`

**Index**

- `uq_send_policies_account_channel` (send_policies.account_id, send_policies.channel)

## `suppression_entries`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `kind` | VARCHAR | non |  |
| `identity_hash` | VARCHAR | non |  |
| `reason` | VARCHAR | non |  |
| `account_id` | UUID | non |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_suppression_entries_kind`: `kind IN ('email','phone','domain')`
- `ck_suppression_entries_reason`: `reason IN ('opt_out','erasure','bounce','manual')`

**Index**

- `uq_suppression_entries_identity` (suppression_entries.account_id, suppression_entries.kind, suppression_entries.identity_hash)

## `tags`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `name` | VARCHAR | non |  |
| `color` | VARCHAR | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Index**

- `uq_tags_account_name` (tags.account_id, tags.name)

## `tasks`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `lead_id` | UUID | oui |  |
| `campaign_id` | UUID | oui |  |
| `assigned_to_user_id` | UUID | oui |  |
| `title` | VARCHAR | non |  |
| `status` | VARCHAR | non | `open` |
| `due_at` | DATETIME | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |
| `deleted_at` | DATETIME | oui |  |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)
- `assigned_to_user_id` → `users.id` (ON DELETE SET NULL)
- `campaign_id` → `campaigns.id` (ON DELETE CASCADE)
- `lead_id` → `leads.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_tasks_status`: `status IN ('open','in_progress','done','cancelled')`

**Index**

- `ix_tasks_account_status` (tasks.account_id, tasks.status)

## `usage_records`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `kind` | VARCHAR | non |  |
| `quantity` | INTEGER | non |  |
| `meta` | JSONB | non | `'{}'::jsonb` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_usage_records_kind`: `kind IN ('discovery_run','signals_analyzed','drafts_generated')`
- `ck_usage_records_quantity`: `quantity >= 0`

**Index**

- `ix_usage_records_account_created` (usage_records.account_id, created_at DESC)

## `users`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | non |  |
| `email` | CITEXT | non |  |
| `password_hash` | VARCHAR | non |  |
| `full_name` | VARCHAR | non |  |
| `role` | VARCHAR | non | `owner` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE CASCADE)

**Contraintes CHECK**

- `ck_users_role`: `role IN ('owner','admin','member')`

**Unicité**

- `uq_users_email` (email)

**Index**

- `ix_users_account_id` (users.account_id)

## `webhook_events`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `provider` | VARCHAR | non |  |
| `event_type` | VARCHAR | oui |  |
| `raw_payload` | JSONB | non |  |
| `processed` | BOOLEAN | non | `false` |
| `processed_at` | DATETIME | oui |  |
| `error` | TEXT | oui |  |
| `received_at` | DATETIME | non | `now()` |
| `id` (PK) | UUID | non | `gen_random_uuid()` |

**Contraintes CHECK**

- `ck_webhook_events_provider`: `provider IN ('sendgrid','twilio')`

**Index**

- `ix_webhook_events_unprocessed` (webhook_events.received_at)

## `whatsapp_sends`

| Colonne | Type | Null | Défaut |
|---|---|---|---|
| `account_id` | UUID | oui |  |
| `campaign_id` | UUID | oui |  |
| `contact_id` | UUID | oui |  |
| `direction` | VARCHAR | non |  |
| `from_number` | VARCHAR | non |  |
| `to_number` | VARCHAR | non |  |
| `body` | TEXT | non |  |
| `status` | VARCHAR | non | `queued` |
| `provider` | VARCHAR | non | `twilio` |
| `provider_message_sid` | VARCHAR | oui |  |
| `error` | TEXT | oui |  |
| `sent_at` | DATETIME | oui |  |
| `id` (PK) | UUID | non | `gen_random_uuid()` |
| `created_at` | DATETIME | non | `now()` |
| `updated_at` | DATETIME | non | `now()` |

**Relations**

- `account_id` → `accounts.id` (ON DELETE SET NULL)
- `campaign_id` → `campaigns.id` (ON DELETE SET NULL)
- `contact_id` → `contacts.id` (ON DELETE SET NULL)

**Contraintes CHECK**

- `ck_whatsapp_sends_direction`: `direction IN ('outbound','inbound')`
- `ck_whatsapp_sends_status`: `status IN ('queued','sent','delivered','opened','replied','failed','mock')`

**Index**

- `ix_whatsapp_sends_contact_id` (whatsapp_sends.contact_id)
- `ix_whatsapp_sends_from_number` (whatsapp_sends.from_number)
- `ix_whatsapp_sends_provider_message_sid` (whatsapp_sends.provider_message_sid)
