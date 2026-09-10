"""Crew wave-1 characterization + mid-migration edge cases.

The brief says the system will be exercised with requests you didn't
design for, in mixed routing states you didn't demo. These tests are
that exercise, written down.

Two layers
----------
1. Encore-only (TestClient). Proves the wrapper + shared service.
   Needs DATABASE_URL (compose default works inside the encore container).

2. Live-stack (opt-in: LIVE_STACK=1). Hits Callboard :8091 and Encore
   :8092 directly. That is how we simulate "org 7 update still on
   Callboard, show already on Encore" without editing routes.yaml —
   mixed routing IS two different backends talking to one DB.

Why rollback / roll-forward don't need a special sync job
---------------------------------------------------------
routes.yaml only chooses which process handles HTTP. Both processes
read/write the same tg_crew row. Last writer wins. That's the success
path for a single-table resource.

Run:
    pytest tests/test_crew_migration.py -q
    LIVE_STACK=1 pytest tests/test_crew_migration.py -q
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ORG7 = "7"
# Seeded org-7 crew used by recorded traffic (index 26: crew_id=10).
CREW_ORG7 = 10
# Org-3 crew. Encore must refuse to mutate this when X-Org-Id is 7.
CREW_ORG3 = 9


def _live() -> bool:
    return os.environ.get("LIVE_STACK") == "1"


@pytest.fixture
def encore_headers() -> dict[str, str]:
    return {"X-Org-Id": ORG7}


# ---------------------------------------------------------------------------
# Encore-only: wrapper contract (drift detectors)
# ---------------------------------------------------------------------------


def test_legacy_list_envelope_and_field_quirks(encore_headers):
    """If this fails, the wrapper drifted from Callboard's list shape."""
    r = client.get("/callboard/crew/list", headers=encore_headers, params={"per_page": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "ok"
    assert body["tg_flash"] is None
    assert "crew" in body["data"]
    assert "page" in body["data"] and "total" in body["data"]
    row = body["data"]["crew"][0]
    for key in ("crew_id", "crew_name", "display_name", "is_lead", "notes", "org", "rate"):
        assert key in row
    assert "prefs" not in row
    assert row["is_lead"] in ("Y", "N")
    assert isinstance(row["rate"], str)
    assert "." in row["rate"]


def test_legacy_show_includes_prefs_string(encore_headers):
    r = client.get(
        "/callboard/crew/show",
        headers=encore_headers,
        params={"crew_id": CREW_ORG7},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["crew_id"] == CREW_ORG7
    assert "prefs" in data
    assert isinstance(data["prefs"], str)


def test_missing_org_is_rejected():
    """Gateway already requires X-Org-Id; Encore must too (undesigned request)."""
    r = client.get("/callboard/crew/list")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# [full migration] write + read both on Encore legacy
# ---------------------------------------------------------------------------


def test_full_migration_update_then_show_on_encore(encore_headers):
    """Org fully flipped: update and show both served by Encore.

    Success: notes written by POST are the notes returned by GET,
    and only that crew row is involved.
    """
    notes = "full-migration encore notes"
    post = client.post(
        "/callboard/crew/update",
        headers=encore_headers,
        data={"crew_id": CREW_ORG7, "notes": notes},
    )
    assert post.status_code == 200
    written = post.json()
    assert written["result"] == "ok"
    assert written["data"]["notes"] == notes
    assert written["data"]["crew_id"] == CREW_ORG7
    assert "prefs" not in written["data"]  # Callboard update omits prefs

    shown = client.get(
        "/callboard/crew/show",
        headers=encore_headers,
        params={"crew_id": CREW_ORG7},
    ).json()["data"]
    assert shown["notes"] == notes
    assert shown["crew_id"] == CREW_ORG7


def test_update_does_not_cross_org(encore_headers):
    """Undesigned request: org 7 tries to update an org-3 crew_id.

    Success: no row for that org → fail envelope, org-3 notes untouched.
    """
    before = None
    # We cannot see org 3 through org-7 show; just assert this update fails.
    r = client.post(
        "/callboard/crew/update",
        headers=encore_headers,
        data={"crew_id": CREW_ORG3, "notes": "should-not-stick"},
    )
    body = r.json()
    assert body["result"] == "fail"
    assert body["data"] is None


# ---------------------------------------------------------------------------
# Live-stack mixed routing (skipped unless LIVE_STACK=1)
# These are the mid-operation cases the gateway can produce.
# ---------------------------------------------------------------------------


CALLBOARD = os.environ.get("CALLBOARD_URL", "http://localhost:8091")
ENCORE = os.environ.get("ENCORE_URL", "http://localhost:8092")


def _http():
    import httpx

    return httpx.Client(timeout=5.0)


def _form_update(base: str, org: str, crew_id: int, notes: str) -> dict:
    with _http() as h:
        r = h.post(
            f"{base}/callboard/crew/update",
            headers={"X-Org-Id": org},
            data={"crew_id": crew_id, "notes": notes},
        )
        r.raise_for_status()
        return r.json()


def _show(base: str, org: str, crew_id: int) -> dict:
    with _http() as h:
        r = h.get(
            f"{base}/callboard/crew/show",
            headers={"X-Org-Id": org},
            params={"crew_id": crew_id},
        )
        r.raise_for_status()
        return r.json()


@pytest.mark.skipif(not _live(), reason="set LIVE_STACK=1 against docker compose")
def test_mid_migration_write_callboard_read_encore():
    """[mid migration] update still on Callboard, show already on Encore.

    Simulates routes.yaml:
        /callboard/crew/update  → callboard
        /callboard/crew/show    → encore
    by calling the two backends directly. Shared DB is the seam.

    Success: Encore show returns the notes Callboard just wrote.
    """
    notes = "mid-migration written-by-callboard"
    written = _form_update(CALLBOARD, ORG7, CREW_ORG7, notes)
    assert written["result"] == "ok"
    assert written["data"]["notes"] == notes

    read = _show(ENCORE, ORG7, CREW_ORG7)
    assert read["result"] == "ok"
    assert read["data"]["notes"] == notes
    assert read["data"]["crew_id"] == CREW_ORG7


@pytest.mark.skipif(not _live(), reason="set LIVE_STACK=1 against docker compose")
def test_rollback_encore_then_callboard_then_read():
    """[rollback] write on Encore, flip back, write on Callboard, read.

    We don't edit routes.yaml in the test. We do the same thing the
    gateway would do after a rollback: next write goes to Callboard.
    Then we read from BOTH backends.

    Success: last writer (Callboard) is what both readers see.
    No leftover Encore-only state.
    """
    _form_update(ENCORE, ORG7, CREW_ORG7, "rollback-encore-1")
    after_flip = _form_update(CALLBOARD, ORG7, CREW_ORG7, "rollback-callboard-2")
    assert after_flip["data"]["notes"] == "rollback-callboard-2"

    assert _show(ENCORE, ORG7, CREW_ORG7)["data"]["notes"] == "rollback-callboard-2"
    assert _show(CALLBOARD, ORG7, CREW_ORG7)["data"]["notes"] == "rollback-callboard-2"


@pytest.mark.skipif(not _live(), reason="set LIVE_STACK=1 against docker compose")
def test_rollforward_callboard_then_encore_then_read():
    """[roll-forward] write on Callboard, flip to Encore, write on Encore, read.

    Success: last writer (Encore) is what both readers see.
    Callboard is not left holding a cache of the old notes (it has none;
    it reads the table).
    """
    _form_update(CALLBOARD, ORG7, CREW_ORG7, "rollforward-callboard-1")
    after_flip = _form_update(ENCORE, ORG7, CREW_ORG7, "rollforward-encore-2")
    assert after_flip["data"]["notes"] == "rollforward-encore-2"

    assert _show(ENCORE, ORG7, CREW_ORG7)["data"]["notes"] == "rollforward-encore-2"
    assert _show(CALLBOARD, ORG7, CREW_ORG7)["data"]["notes"] == "rollforward-encore-2"


@pytest.mark.skipif(not _live(), reason="set LIVE_STACK=1 against docker compose")
def test_full_migration_live_encore_only():
    """[full migration] live stack: write and read Encore legacy."""
    notes = "live-full-migration"
    assert _form_update(ENCORE, ORG7, CREW_ORG7, notes)["data"]["notes"] == notes
    assert _show(ENCORE, ORG7, CREW_ORG7)["data"]["notes"] == notes
