# Live map and dashboard widgets

## Map of your prospects (`/app/map`)
- Data: `GET /api/map/prospects`, the organisation's own discovery prospects that carry a position, with `vertical`, `country`,
  `score` (`null` = not scored, never 0), `signals` (keys detected **now**; a signal a reviewer dismissed does not count) and `created_at`.
- **Clusters**: grid clustering in the browser (`lib/mapCluster.js`, pure and tested), cell of 64 px at the current zoom, centroid
  position. No extra dependency. Clicking a cluster zooms to its members and lists them in the drawer.
- **Filters**: vertical, review status, a detected signal, minimum score. Choices come from the data. A prospect without a score never
  passes a score threshold (`not scored` is not 0).
- **Near real time**: the page polls every 20 s while the tab is visible (`POLL_MS`). The free Render plan has no WebSocket worker, so this
  is polling, and the page says when it last updated; if a poll fails it keeps the last data and says so. New prospects pulse.
- **Start campaign**: creates a *draft* campaign and assigns the ticked prospects that are **approved**; the others are counted and left out.
  Nothing is sent: steps, consent and the send gate still apply when the campaign is launched. If the API refuses the assignment (for
  instance live sending is off), the message says why and the empty draft stays in Campaigns.
- Limits: the page is only reachable when `FEATURE_EXTERNAL_SOURCES` is on (the same screen hosts the OpenStreetMap search); at most 2000
  positioned prospects are returned.

## Dashboard (`GET /api/dashboard/overview`)
- **Live discoveries**: latest prospects and signals (already refreshed every 30 s).
- **Top signals**: prospects per detected signal (`top_signals`), dismissed or unknown signals excluded.
- **Geographic distribution**: prospects per stored country and city (`geography`); those without a country or city are counted apart
  (`unknown_country`, `unknown_city`), never guessed.

## Rollback
No migration and no new environment variable. Revert the PR.
