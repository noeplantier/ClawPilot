# Plantiers OutreachOS UX corrective pass

## Files changed

- `frontend/src/index.css`
- `frontend/src/components/Layout.jsx`
- `frontend/src/components/layout.test.jsx`
- `frontend/src/pages/Agents.jsx`
- `frontend/src/pages/Analytics.jsx`
- `frontend/src/pages/Campaigns.jsx`
- `frontend/src/pages/Dashboard.jsx`
- `frontend/src/pages/Leads.jsx`
- `frontend/src/pages/MapSearch.jsx`
- `frontend/src/pages/Messages.jsx`
- `frontend/src/pages/ReviewQueue.jsx`
- `frontend/src/pages/SystemHealth.jsx`
- `frontend/src/pages/dashboard.test.jsx`
- `docs/product/PLANTIERS_UX_OVERHAUL_REPORT.md`

## Improvements

- Shared surfaces, buttons, inputs, chips, dashboard accents, and focus styles now use the existing Plantiers ink/violet/lilac and surface tokens. Removed cyan accents, broad glow, and hover movement from shared controls.
- CRM navigation has separate Contacts and Pipeline destinations. Pipeline links to the existing Kanban view via `?view=kanban`; the route receives its own active state. Folded and mobile navigation keep all destinations in their existing groups. Mobile Escape and focus handling from PR #58 remain in place.
- Dashboard exposes a direct Review Queue action when the server reports pending prospects. Existing real-data widgets, empty states, and refresh remain intact.
- Leads controls wrap on narrow screens, Kanban selection is URL-addressable, and list rows no longer animate in with staggered delays.
- Map results are deduplicated by source identifier before rendering; mobile map toolbar and search panel no longer occupy the same top position.
- Browser QA found and fixed a mobile map/footer overlap: the map now fits above the footer, the results panel clears its toggle, and the toggle clears map attribution.
- Removed one user-facing source comment containing the former product name; CI's branding test had caught it.
- Campaigns, messages, and agents expose explicit loading/error/retry states. Messages tables scroll horizontally on narrow screens. Agent refresh pauses in hidden tabs and runs every 30 seconds while visible. Delete actions use the shared destructive style and named accessible labels.
- System Health shows a derived overall status from existing checks; database or migration failure maps to failing, other core check failures to degraded, and absent optional integrations do not claim a system failure.
- Analytics labels the funnel as all recorded time and uses the existing violet/ink identity in its charts. Review and map selection filters share the violet selected state.

## Accessibility

- Added a distinct `aria-current="page"` state for the CRM Pipeline route.
- Pipeline, deletion, loading, and error actions have explicit labels or live/error semantics.
- Existing PR #58 keyboard navigation, folded sidebar access, mobile drawer focus trap, and Escape close behavior are preserved and covered by layout tests.

## Performance

- Removed staggered row animations in Leads and Messages and card entrance animations in Agents.
- Agent polling is visibility-aware and reduced from 8 seconds to 30 seconds.
- Map result deduplication happens in a memoized projection; no provider, dependency, or request was added.
- No performance benchmark was run; latency changes are not claimed.

## QA checklist

- [x] `git diff --check`
- [x] Frontend production build (local only; not deployed)
- [x] Targeted UI tests: layout/navigation, dashboard, messages, map search, and map clustering (31 tests)
- [x] Targeted branding regression test after CI found the stale product name
- [x] ESLint on changed UI and test files (no warnings or errors)
- [x] Browser at 1280×800: Dashboard, Leads table/Pipeline, Map Search, Prospects, Review Queue, Campaigns, Messages, Agents, Analytics, System Health, Settings
- [x] Folded desktop sidebar and mobile drawer open/close with Escape
- [x] Browser at 390×844: Dashboard, Leads, Map Search, Prospects, Review Queue, Campaigns, Messages, Agents, Analytics, System Health, Settings
- [x] No horizontal overflow at tested sizes; map toolbar/search and results toggle/attribution do not overlap
- [x] No JavaScript page errors in the browser walkthrough; API responses were local fixtures
- [x] Loading/error/empty routes rendered with fixture data or explicit error states; no destructive, send, or campaign action was invoked
- [x] Dark/light check: the app uses its existing light application surfaces; no separate dark theme applies to these routes
- [ ] Live OpenStreetMap delivery and external Google Fonts remain unverified: external requests were blocked; map tile nodes used local image stubs

## TODOs and non-blockers

- TODO: verify live OpenStreetMap tile delivery in an approved environment; this browser pass confirms Leaflet controls/layout with local tile stubs only.
- The browser fixture deliberately returned HTTP 503 for unneeded API data and blocked Google Fonts; corresponding resource log entries are test-fixture effects, not JavaScript page errors.
- Integrations, campaign dispatch, agent execution, and sending were not invoked; their service-side operation is outside this UI pass.

## Rollback

Revert the corrective-pass changes on this feature branch. No migration, backend/data change, deployment, or production action is part of this pass.
