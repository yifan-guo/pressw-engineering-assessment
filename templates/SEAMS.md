# Seam Map

## Probe log

What you tried, what you observed, what you concluded. Keep it terse but real — this is the
record of your discovery process, and we'll talk through it together.

| Probe | Observation | Conclusion |
| --- | --- | --- |
| GET /callboard/crew/list (org 3, index 0) | 200. Envelope `{result, data:{crew:[...], page, total}, tg_flash}`. Fields: crew_id, crew_name (=DB user_name), display_name, is_lead (Y/N), notes, org, rate (string). Matches tg_crew for org=3. | Pure read of tg_crew. No other tables. Strong wave-1 candidate. |
| GET /callboard/crew/show?crew_id=1 (org 3, index 3) | 200. Same envelope. Fields match list plus `prefs` (stringified prefs_blob). Single row from tg_crew. | Pure read of tg_crew
| POST /callboard/crew/update (org 3, crew_id=9, index 10) | 200. Returned updated crew. Only notes column of that one row changed. | Single-table write on tg_crew. Low coupling. |
| POST /callboard/assignment/accept (assignment_id=23, index 13) | 200. Response includes status=A, pay_estimate, crew_name, shift_title. DB: assignments.status→A, pay_estimate+accepted_at set; shifts.open_slots→0, staffing_status→FULL, lead_assignment_id→23. No new message, queue empty. 


## Couplings found

For each: what's coupled to what, and the evidence.

POST /callboard/assignment/accept couples assignments to shifts. Cannot move accept without also owning shift derived columns.


## Wave plan

| Wave | What moves (endpoints, behaviors, tables) | Why this is safe to move as a unit |
| --- | --- | --- |
| 1 | GET /crew/list /crew/show, tg_crew | single-table read; fields match list except prefs (stringified prefs_blob) |
| 2 | POST /crew/update | single table write ; could have clubbed with wave 1 but did not have time to get to it in this assessment |
| 3 | | |

## Cut couplings & mitigations

For every coupling a wave boundary cuts through: what goes wrong mid-migration, for whom,
and what you'd do about it.

Migration of /assignment/accept updates assignment and shift tables, crossing the boundary on shift service group.
Organizations still on callboard will overwrite fields values populated by Encore.

While the legacy wrapper exists, the record of the write operations will be split between the systems, reducing visibility of the org activity.

A moment later someone loads the shift via Callboard. Callboard may recompute or overwrite those columns using its own logic. The two systems are fighting over the same rows.

Batch the changes for schedule and assignment together, then migrate it in a single wave.

## Open questions

What you'd need to answer before running this plan against real customers.

Probe the remaining service endpoints to see if other service groups overlap with the assignment+shift boundary.

Branch based on the outcome:
- if no further coupling, commit to doing assignments as a wave
- if further coupling is found, de-prioritize the wave and gather evidence on the new coupled resources.
