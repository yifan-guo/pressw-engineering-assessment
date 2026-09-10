# Trade-offs

- **Built vs. scoped:** what got cut under time pressure

Built: crew list, show, update (legacy + /v3) and org-7 route flip.
Cut: assignments, shifts, messages, background job.

- **Specific trade-offs and why**

Fidelity of three crew endpoints over breadth. Crew is one table with one
observed writer, so a half-migrated org is safe. Assignment/accept is not
(writes shift derived columns).

Narrow path rules in `routes.yaml` instead of `/callboard/crew/`. That way
an unimplemented crew path cannot 404 for org 7.

- **What you'd do next with more time**

Characterize `shift/cancel` and the 5-minute job as writers of
`open_slots` / `staffing_status` / `lead_assignment_id`. Design wave 2 as
"every writer of those columns" for one org.

Capture Callboard's exact not-found body for show/update and lock it in a
fixture test.

- **Known issues or unhandled cases**

Not-found envelope on Encore is inferred, not captured from live Callboard.
`crew/update` only accepts `notes` (what traffic showed). Pagination
`per_page` default on Encore list is 25; confirm Callboard's default if a
client omits it.

- **Post-window commits, if any**

None yet.
