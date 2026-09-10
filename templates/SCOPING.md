# Scoping

- **Scope committed:** what you're actually building, as a tight list

Encore: crew list + crew show (legacy wrappers + /v3 equivalents). Parity proven by response + DB snapshot comparison. routes.yaml flipped for org 7

# Crew API: legacy vs /v3

## Why two shapes exist

The migration is a strangler fig: the existing frontend must keep working with
zero changes. That frontend speaks the Callboard wire format
(`/callboard/crew/...`). Encore therefore exposes **legacy wrappers** on those
exact paths that reproduce Callboard’s JSON, including its quirks.

A second, modern surface under `/v3/crew` is intentional. New clients (or a
future frontend) can adopt a clean contract without dragging 15-year-old
stringly-typed fields, dual name fields, and envelope noise forward. The
gateway keeps the two worlds separate: route `/callboard/crew/` per-org to
Encore when ready; leave `/v3/` as a new path that only modern clients call.

## Rationale for the `/v3` design

| Decision | Rationale |
| --- | --- |
| No `result` / `data` / `tg_flash` envelope | HTTP status already conveys success/failure. Extra envelope adds noise and forces every client to unwrap. |
| Collection key `items` | Standard, unambiguous. Avoids the legacy singular `"crew"` array name. |
| Resource id field `id` | Conventional REST. Legacy keeps `crew_id` for compatibility. |
| `user_name` + `display_name` (no email-as-`crew_name`) | Callboard overloads `crew_name` with the email address. That is surprising and forces clients to keep a second field for the human name. `/v3` uses clear names. |
| `rate` as number | Avoids parsing `"31.00"` everywhere. Money remains decimal-safe at the DB boundary. |
| `is_lead` as boolean | Eliminates `"Y"`/`"N"` string checks and case sensitivity. |
| `prefs` as parsed object | Callboard returns a JSON *string*. Clients already have to `JSON.parse`; `/v3` does it once at the boundary. |
| Pagination includes `per_page` | Clients need to know the page size they received. Legacy omits it from the body even when the query param is used. |
| Missing resource → HTTP 404 | Standard. Legacy returns `200` + `{ "result": "fail", "error": "not found" }`. |
| List does not silently drop fields | `/v3` returns a consistent resource shape; clients do not have to special-case “list vs show”. |

## Side-by-side field mapping (same underlying row)

| Concept | Legacy (`/callboard/crew/...`) | Modern (`/v3/crew`) |
| --- | --- | --- |
| Envelope | `{ result, data, tg_flash }` | none (body is the resource) |
| Collection | `data.crew` | `items` |
| Id | `crew_id` | `id` |
| Login / email | `crew_name` (the email) | `user_name` |
| Human name | `display_name` | `display_name` |
| Rate | string `"31.00"` | number `31.0` |
| Lead flag | string `"Y"` / `"N"` | boolean `true` / `false` |
| Notes | `notes` | `notes` |
| Org | `org` | `org` |
| Prefs | raw JSON string (show only) | parsed object |
| Created | not present on list/show | `created` (unix epoch) |
| Org name | not present | `org_name` |
| Pagination body | `page`, `total` only | `page`, `per_page`, `total` |
| Not found | `{ "result": "fail", "error": "not found" }` | HTTP 404 |

## What we deliberately did *not* change in the legacy wrappers


## Current status

- Read parity (list + show + not-found) is established against live Callboard for the traffic indices that exercise those endpoints.
- Writes (`POST /callboard/crew/update`) are **not** implemented on Encore → 404. Deliberate scope cut for this wave.
- `/v3` is available for new clients and for characterization tests that want the clean shape.

## How a client chooses the shape

- Old frontend → keeps calling `/callboard/crew/...`. When `routes.yaml` points that prefix at Encore for an org, it still receives the legacy shape.
- New client → calls `/v3/crew`. Add a `/v3/` rule in `routes.yaml` (default `encore`) if you want those requests to go through the gateway; otherwise hit Encore directly on 8092 during development.



- **Scope cut:** what you considered and decided not to do, with reasoning
All writes, All writes, messaging, background job, assignment flow. Each has multi-table side-effects that need more probe time than remaining window
- **Assumptions made:** what you decided without asking
Callboard only writes to tg_crew via the explicit /crew/update endpoint. 
Writes are atomic.

- **Risks accepted:** what could bite later and why you're accepting it
If a callboard job mutates crew table, org 7 will see stale data (check the other systems logs) until the /crew/update service is also migrated and or dual-written.