"""Modern /v3/crew/... endpoints.

Clean shape: proper types (bool, number), no legacy envelope, predictable
pagination. These deliberately do *not* reproduce Callboard quirks.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/v3/crew", tags=["v3-crew"])


class CrewOut(BaseModel):
    id: int
    org: int
    org_name: str | None = None
    user_name: str
    display_name: str | None = None
    rate: float
    is_lead: bool
    notes: str = ""
    prefs: dict[str, Any] | None = None
    created: int | None = None


class CrewListOut(BaseModel):
    items: list[CrewOut]
    total: int
    page: int
    per_page: int


def _to_crew_out(row: dict[str, Any]) -> CrewOut:
    rate = row.get("rate")
    if isinstance(rate, Decimal):
        rate_f = float(rate)
    else:
        rate_f = float(rate or 0)

    prefs = None
    raw = row.get("prefs_blob")
    if raw:
        try:
            import json
            prefs = json.loads(raw)
        except Exception:
            prefs = {"raw": raw}

    return CrewOut(
        id=row["id"],
        org=row["org"],
        org_name=row.get("org_name"),
        user_name=row.get("user_name") or "",
        display_name=row.get("display_name"),
        rate=rate_f,
        is_lead=(row.get("is_lead") or "N").upper()[:1] == "Y",
        notes=row.get("notes") or "",
        prefs=prefs,
        created=row.get("created"),
    )


@router.get("", response_model=CrewListOut)
def list_crew(
    x_org_id: int = Header(..., alias="X-Org-Id"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """GET /v3/crew — modern paginated list."""
    rows = service.get_crew_rows(x_org_id, page=page, per_page=per_page)
    total = service.count_crew(x_org_id)
    return CrewListOut(
        items=[_to_crew_out(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{crew_id}", response_model=CrewOut)
def get_crew(
    crew_id: int,
    x_org_id: int = Header(..., alias="X-Org-Id"),
):
    """GET /v3/crew/{id} — single crew member (404 if missing)."""
    rows = service.get_crew_rows(x_org_id, crew_id=crew_id)
    if not rows:
        raise HTTPException(status_code=404, detail="crew not found")
    return _to_crew_out(rows[0])
