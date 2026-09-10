"""Modern /v3/crew endpoints.

Clean shapes for 2026 clients. Same service layer as the legacy wrappers;
no result/data/tg_flash envelope, proper types, no single-char flags.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db
from . import service

router = APIRouter(prefix="/v3/crew", tags=["crew-v3"])


class CrewOut(BaseModel):
    id: int
    org: int
    email: str = Field(description="DB user_name")
    display_name: str | None
    rate: float
    is_lead: bool
    notes: str
    prefs: dict | None = None


class CrewListOut(BaseModel):
    items: list[CrewOut]
    page: int
    total: int


class CrewUpdateIn(BaseModel):
    notes: str


def _require_org(x_org_id: str | None) -> int:
    if not x_org_id:
        raise HTTPException(status_code=400, detail="missing X-Org-Id")
    try:
        return int(x_org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid X-Org-Id") from exc


def _to_out(row: dict, *, include_prefs: bool = False) -> CrewOut:
    prefs = None
    if include_prefs and row.get("prefs_blob"):
        import json

        try:
            prefs = json.loads(row["prefs_blob"])
        except (TypeError, ValueError):
            prefs = None
    return CrewOut(
        id=row["id"],
        org=row["org"],
        email=row["user_name"],
        display_name=row["display_name"],
        rate=float(row["rate"] or 0),
        is_lead=(row["is_lead"] or "N") == "Y",
        notes=row["notes"] or "",
        prefs=prefs,
    )


@router.get("", response_model=CrewListOut)
def list_crew(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=0, le=200),
):
    org = _require_org(x_org_id)
    with db.session() as session:
        rows, total = service.list_crew(session, org, page=page, per_page=per_page or None)
    return CrewListOut(
        items=[_to_out(r) for r in rows],
        page=page,
        total=total,
    )


@router.get("/{crew_id}", response_model=CrewOut)
def get_crew(
    crew_id: int,
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
):
    org = _require_org(x_org_id)
    with db.session() as session:
        row = service.get_crew(session, org, crew_id)
    if row is None:
        raise HTTPException(status_code=404, detail="crew not found")
    return _to_out(row, include_prefs=True)


@router.patch("/{crew_id}", response_model=CrewOut)
def update_crew(
    crew_id: int,
    body: CrewUpdateIn,
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
):
    org = _require_org(x_org_id)
    with db.session() as session:
        row = service.update_crew_notes(session, org, crew_id, body.notes)
    if row is None:
        raise HTTPException(status_code=404, detail="crew not found")
    return _to_out(row, include_prefs=True)
