# Parity proof (wave 1: crew)

This is the artifact that answers the brief:

> Characterization tests, replay diffs, DB snapshot comparisons —
> your choice, but "it looks right" doesn't count. Show us how you'd know
> if your wrapper drifted from Callboard.

"Looks right" is not the proof. The proof is: **same HTTP envelope + same
DB row** after the same request, plus mixed-routing cases that the gateway
will actually produce.

# Manual verification my machine
Run the stack and execute the following requests.
```bash
yifanguo@Yifans-MacBook-Pro-2 pressw-llc-be-engineering-assessment-58be5ec5a0a97628f932968bdcef83f2498105bb % curl -s -H "X-Org-Id: 7" -X POST "http://localhost:8080/callboard/crew/update" \
  -d "crew_id=10&notes=via gateway org7" | jq
{
  "result": "ok",
  "data": {
    "crew_id": 10,
    "crew_name": "priya.raman@harborlight.example",
    "display_name": "P. Raman",
    "is_lead": "N",
    "notes": "via gateway org7",
    "org": 7,
    "rate": "26.75"
  },
  "tg_flash": null
}
yifanguo@Yifans-MacBook-Pro-2 pressw-llc-be-engineering-assessment-58be5ec5a0a97628f932968bdcef83f2498105bb % curl -s -H "X-Org-Id: 3" -X POST "http://localhost:8080/callboard/crew/update" \
  -d "crew_id=9&notes=still callboard" | jq
{
  "data": {
    "crew_id": 9,
    "crew_name": "priya.raman@meridianstage.example",
    "display_name": "P. Raman",
    "is_lead": "N",
    "notes": "still callboard",
    "org": 3,
    "rate": "26.75"
  },
  "result": "ok",
  "tg_flash": null
}
yifanguo@Yifans-MacBook-Pro-2 pressw-llc-be-engineering-assessment-58be5ec5a0a97628f932968bdcef83f2498105bb % python3 traffic/replay.py --index 10 --base http://localhost:8092
[ 10] 200 via -: POST /callboard/crew/update
{"result":"ok","data":{"crew_id":9,"crew_name":"priya.raman@meridianstage.example","display_name":"P. Raman","is_lead":"N","notes":"cleared for fly rail as of this week","org":3,"rate":"26.75"},"tg_flash":null}
```

## How we would know the wrapper drifted

| Check | Passes if | Fails (drift) if |
| --- | --- | --- |
| Replay list/show against 8091 vs 8092 | JSON keys, types, and values match (rate string, Y/N, envelope) | Extra/missing field, `rate` as number, missing `tg_flash` |
| Replay update then `SELECT notes FROM tg_crew` | Only that row's `notes` changed; other columns untouched | Extra column mutated, wrong org row updated |
| Org isolation | Org 7 cannot read/write org 3's crew_id | Cross-org row returned or updated |
| Mixed routing (shared DB) | Write on one backend is visible on the other | Reader returns pre-write notes |

Captured Callboard fixtures (org 3, pre-update):

- list envelope: `{result, data:{crew, page, total}, tg_flash}`
- show adds `prefs` (stringified `prefs_blob`)
- update returns list-shaped crew (no `prefs`), writes only `notes`

## Commands (run against a live stack)

```bash
# A. Characterization: same request, two backends
python3 traffic/replay.py --index 0 --base http://localhost:8091 > /tmp/cb_list.json
python3 traffic/replay.py --index 0 --base http://localhost:8092 > /tmp/en_list.json
# Compare the JSON bodies (ignore request metadata the script prints).

python3 traffic/replay.py --index 3 --base http://localhost:8091
python3 traffic/replay.py --index 3 --base http://localhost:8092

# B. DB snapshot around a write
psql postgresql://showcall:showcall@localhost:5432/showcall \
  -c "SELECT id, org, notes FROM tg_crew WHERE id = 10;"
# then POST update, then the same SELECT again.
```

## Simulated mid-migration success paths

All four cases work **because there is one Postgres**. Routing decides
*which process handles the HTTP request*; it does not create a second
copy of `tg_crew`.

### 1. Full migration (org 7 crew → Encore)

`routes.yaml` points list/show/update at Encore for org 7.

- POST `/callboard/crew/update` (org 7) → Encore writes `tg_crew.notes`
- GET `/callboard/crew/show` (org 7) → Encore reads the same row
- Success: notes in the response equal notes in the DB

### 2. Mid-migration (write on Callboard, read on Encore)

This is the state *before* we flipped update, and the state any org still
on Callboard for writes would be in.

- POST update via **8091** (Callboard)
- GET show via **8092** (Encore)
- Success: Encore returns the notes Callboard just wrote

Nothing "syncs." Both processes `SELECT`/`UPDATE` the same table.

### 3. Rollback (Encore write → flip routes back → Callboard write)

- Update via Encore; notes = `"encore-1"`
- Flip org 7 update (or all crew paths) back to `callboard` in `routes.yaml`
- Update via Callboard; notes = `"callboard-2"`
- Read from either backend
- Success: last writer wins; row is `"callboard-2"`; no split-brain

### 4. Roll-forward (Callboard write → flip to Encore → Encore write)

- Update via Callboard; notes = `"callboard-1"`
- Flip org 7 crew paths to Encore
- Update via Encore; notes = `"encore-2"`
- Read from Encore (and Callboard if you leave a path there)
- Success: last writer wins; row is `"encore-2"`

### What would *not* be a success path

- Two writers of **derived** columns on different backends
  (`assignment/accept` vs `shift/cancel` on `open_slots`). That is not
  this wave. Documented in `SEAMS.md`.

## Tests that encode this

`encore/tests/test_crew_migration.py`

- Always-on: Encore wrapper shape + Encore write/read + org scoping
  (runs with `TestClient` against the FastAPI app; needs DB).
- Live-stack (skipped unless `LIVE_STACK=1`): the four mixed-routing
  cases above against 8091 / 8092.

```bash
# against the running compose stack
docker compose exec -e LIVE_STACK=1 \
  -e CALLBOARD_URL=http://callboard:8080 \
  -e ENCORE_URL=http://encore:8080 \
  encore pytest tests/test_crew_migration.py -v
```



========================================================== test session starts ===========================================================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0 -- /usr/local/bin/python3.12
cachedir: .pytest_cache
rootdir: /srv
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 9 items                                                                                                                        

tests/test_crew_migration.py::test_legacy_list_envelope_and_field_quirks PASSED                                                    [ 11%]
tests/test_crew_migration.py::test_legacy_show_includes_prefs_string PASSED                                                        [ 22%]
tests/test_crew_migration.py::test_missing_org_is_rejected PASSED                                                                  [ 33%]
tests/test_crew_migration.py::test_full_migration_update_then_show_on_encore PASSED                                                [ 44%]
tests/test_crew_migration.py::test_update_does_not_cross_org PASSED                                                                [ 55%]
tests/test_crew_migration.py::test_mid_migration_write_callboard_read_encore PASSED                                                [ 66%]
tests/test_crew_migration.py::test_rollback_encore_then_callboard_then_read PASSED                                                 [ 77%]
tests/test_crew_migration.py::test_rollforward_callboard_then_encore_then_read PASSED                                              [ 88%]
tests/test_crew_migration.py::test_full_migration_live_encore_only PASSED                                                          [100%]


===================================================== 9 passed, 2 warnings in 0.83s ======================================================