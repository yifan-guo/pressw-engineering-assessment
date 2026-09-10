"""Legacy-compatible /callboard/crew/* wrappers.

These must match Callboard's wire format exactly so the existing frontend
cannot tell which backend answered. Shared logic lives in service.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from .. import db
from . import service

router = APIRouter(tags=["crew-legacy"])


def _require_org(x_org_id: str | None) -> int:
    if not x_org_id:
        raise HTTPException(status_code=400, detail={"error": "missing org", "result": "fail"})
    try:
        return int(x_org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid org", "result": "fail"}) from exc


def _crew_list_item(row: dict) -> dict:
    """Shape used inside list responses (no prefs)."""
    return {
        "crew_id": row["id"],
        "crew_name": row["user_name"],
        "display_name": row["display_name"],
        "is_lead": row["is_lead"] or "N",
        "notes": row["notes"] or "",
        "org": row["org"],
        "rate": service.format_rate(row["rate"]),
    }


def _crew_show_item(row: dict) -> dict:
    """Shape used by show (includes prefs as string)."""
    item = _crew_list_item(row)
    item["prefs"] = row["prefs_blob"] if row["prefs_blob"] is not None else ""
    return item


def _crew_update_item(row: dict) -> dict:
    """Shape returned by update (matches list item — no prefs)."""
    return _crew_list_item(row)


def _ok(data: dict) -> dict:
    return {"result": "ok", "data": data, "tg_flash": None}


@router.get("/callboard/crew/list")
def crew_list(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    page: int = Query(default=1),
    per_page: int = Query(default=25),
):
    org = _require_org(x_org_id)
    with db.session() as session:
        rows, total = service.list_crew(session, org, page=page, per_page=per_page)
    return _ok(
        {
            "crew": [_crew_list_item(r) for r in rows],
            "page": page if per_page else 1,
            "total": total,
        }
    )


@router.get("/callboard/crew/show")
def crew_show(
    crew_id: int = Query(...),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
):
    org = _require_org(x_org_id)
    with db.session() as session:
        row = service.get_crew(session, org, crew_id)
    if row is None:
        # Callboard-style failure envelope rather than a bare 404 body.
        return JSONResponse(
            status_code=200,
            content={"result": "fail", "data": None, "tg_flash": "crew not found"},
        )
    return _ok(_crew_show_item(row))


@router.post("/callboard/crew/update")
def crew_update(
    crew_id: int = Form(...),
    notes: str = Form(default=""),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
):
    """POST form: crew_id + notes (observed traffic index 10).

    Only notes is written. Response shape matches list item (no prefs).
    """
    org = _require_org(x_org_id)
    with db.session() as session:
        row = service.update_crew_notes(session, org, crew_id, notes)
    if row is None:
        return JSONResponse(
            status_code=200,
            content={"result": "fail", "data": None, "tg_flash": "crew not found"},
        )
    return _ok(_crew_update_item(row))
