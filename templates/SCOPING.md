# Scoping

- **Scope committed:** what you're actually building, as a tight list

Wave 1 for org 7:

- Legacy wrappers: `GET /callboard/crew/list`, `GET /callboard/crew/show`, `POST /callboard/crew/update`
- Modern API: `GET /v3/crew`, `GET /v3/crew/{id}`, `PATCH /v3/crew/{id}`
- Shared service over `tg_crew` (one implementation)
- `routes.yaml` flips those three `/callboard/crew/*` paths for org 7 to Encore
- Parity proof: `templates/PARITY.md` + `encore/tests/test_crew_migration.py`

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
| `email` (DB `user_name`) | Callboard overloads `crew_name` with the email address. `/v3` names it. |
| `rate` as number | Avoids parsing `"31.00"` everywhere. |
| `is_lead` as boolean | Eliminates `"Y"`/`"N"` string checks. |
| `prefs` as parsed object | Callboard returns a JSON *string*. `/v3` parses at the boundary. |
| Missing resource → HTTP 404 | Standard. Legacy returns a fail envelope. |
| Update via PATCH JSON `{notes}` | Form posts stay on the legacy path only. |

## Side-by-side field mapping (same underlying row)

| Concept | Legacy (`/callboard/crew/...`) | Modern (`/v3/crew`) |
| --- | --- | --- |
| Envelope | `{ result, data, tg_flash }` | none (body is the resource) |
| Collection | `data.crew` | `items` |
| Id | `crew_id` | `id` |
| Login / email | `crew_name` (the email) | `email` |
| Human name | `display_name` | `display_name` |
| Rate | string `"31.00"` | number `31.0` |
| Lead flag | string `"Y"` / `"N"` | boolean `true` / `false` |
| Notes | `notes` | `notes` |
| Org | `org` | `org` |
| Prefs | raw JSON string (show only) | parsed object (show/get) |
| Pagination body | `page`, `total` | `page`, `total` |
| Not found | `{ result: fail, data: null, tg_flash }` | HTTP 404 |

## What we deliberately did *not* change in the legacy wrappers

- Envelope (`result`, `data`, `tg_flash`)
- `crew_name` = email, `rate` as string, `is_lead` as `"Y"`/`"N"`
- Update accepts form fields, not JSON
- Update response omits `prefs` (matches captured Callboard traffic)

## Current status

- list + show + update implemented on Encore
- Org 7 routed to Encore for those three paths only
- Parity method documented in `templates/PARITY.md`
- Mixed-routing tests in `encore/tests/test_crew_migration.py`

## How a client chooses the shape

- Old frontend → keeps calling `/callboard/crew/...`. When `routes.yaml` points that path at Encore for an org, it still receives the legacy shape.
- New client → calls `/v3/crew` on Encore (8092).

- **Scope cut:** what you considered and decided not to do, with reasoning

Assignments, shifts, messages, `callboard_queue` / 5-minute job. Each has
multi-table side-effects (proven for accept → shift derived columns). Not
enough window to characterize every writer.

- **Assumptions made:** what you decided without asking

Callboard only writes `tg_crew` via `/crew/update` (no job mutation observed).
Update only mutates `notes` (only field in recorded traffic).

- **Risks accepted:** what could bite later and why you're accepting it

If a hidden Callboard job later mutates crew notes for org 7, Encore reads
will still see it (same table). The residual risk is a *second writer* we
haven't found, not stale cache. Accepted for this window; listed as an open
question in `SEAMS.md`.
