# Seam Map

## Probe log

What you tried, what you observed, what you concluded. Keep it terse but real — this is the
record of your discovery process, and we'll talk through it together.

| Probe | Observation | Conclusion |
| --- | --- | --- |
| GET /callboard/crew/list (org 3, index 0) | 200. Envelope `{result, data:{crew:[...], page, total}, tg_flash}`. Fields: crew_id, crew_name (=DB user_name), display_name, is_lead (Y/N), notes, org, rate (string). Matches tg_crew for org=3. | Pure read of tg_crew. No other tables. Strong wave-1 candidate. |
| GET /callboard/crew/show?crew_id=1 (org 3, index 3) | 200. Same envelope. Fields match list plus `prefs` (stringified prefs_blob). Single row from tg_crew. | Pure read of tg_crew. |
| POST /callboard/crew/update (org 3, crew_id=9, index 10) | 200. Returned updated crew (list shape, no prefs). Only notes column of that one row changed. | Single-table write on tg_crew. Low coupling; safe to include with reads. |
| POST /callboard/assignment/accept (assignment_id=23, index 13) | 200. Response includes status=A, pay_estimate, crew_name, shift_title. DB: assignments.status→A, pay_estimate+accepted_at set; shifts.open_slots→0, staffing_status→FULL, lead_assignment_id→23. No new message, queue empty. | Couples assignments ↔ shifts (derived columns). Later wave. |
| shift/show read-after-tamper (shift 8) | Manually set open_slots=99, staffing_status=OPEN, lead=NULL; Callboard show returned those values unchanged and did not rewrite DB. | Callboard does **not** recompute derived columns on read. Dual-writer risk only, not reader conflict. |

## Couplings found

- **assignment/accept → shifts.open_slots, staffing_status, lead_assignment_id**  
  Evidence: accept of assignment 23 wrote all three on shift 8.  
  Read test: wrong values survive shift/show (no recompute on read).  
  Migration implication: every *writer* of those columns for an org must land on the same backend (or dual-write). Pure shift readers can stay split.

- **crew/update → tg_crew.notes only**  
  Evidence: index 10 changed only notes on one row. Same table as the reads; single writer per org when routed together.

## Wave plan

| Wave | What moves (endpoints, behaviors, tables) | Why this is safe to move as a unit |
| --- | --- | --- |
| 1 | `/callboard/crew/list`, `/callboard/crew/show`, `/callboard/crew/update` (+ tg_crew) | Single table. Reads + the only observed writer for notes. Shared DB → half-migrated org is safe: one writer (Encore for org 7), same rows for everyone else still on Callboard. |
| 2 | (later) assignment/* + every writer of shift derived columns (accept, cancel, …) | Accept already mutates shift state. Move all writers of those columns together to avoid dual-writer window. |
| 3 | (later) messaging, background job / callboard_queue | Still uncharacterized. |

## Cut couplings & mitigations

- **Wave 1 boundary (crew):** No cut. All observed tg_crew traffic for org 7 goes to Encore. Residual risk: any hidden Callboard job that mutates crew notes for org 7 — not observed; accepted for this window.
- **assignment/accept boundary:**  
  - Encore accept + Callboard shift/show → safe (reader only; no recompute).  
  - Encore accept + Callboard shift/cancel (or any other writer of open_slots / staffing_status / lead) → dual writers, last write wins.  
  Mitigation: move all writers of those columns in the same wave, or dual-write until the last writer is migrated.

## Open questions

- Does shift/cancel (or the 5-min job) write the same derived columns? (Needed before an assignment wave.)
- Exact fail shapes for missing crew_id on show/update (guessed for now).
- Whether crew/update ever accepts fields beyond notes (traffic only shows notes).
