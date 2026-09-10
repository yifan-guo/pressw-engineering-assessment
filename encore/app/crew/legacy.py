"""Legacy /callboard/crew/... wrappers.

These must produce the exact wire shape Callboard returns so the existing
frontend cannot tell the difference. Shape captured from live Callboard
responses (org 3/7/12, list + show + not-found).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Header, Query

from . import service

router = APIRouter(prefix="/callboard/crew", tags=["legacy-crew"])


def _rate_str(rate: Any) -> str:
    if isinstance(rate, Decimal):
        return f"{rate:.2f}"
    if rate is None:
        return "0.00"
    return f"{float(rate):.2f}"


def _list_item(row: dict[str, Any]) -> dict[str, Any]:
    """List item shape: Callboard uses crew_name = user_name (email).

    Observed fields on list (no org_name, created, or prefs):
      crew_id, crew_name, display_name, is_lead, notes, org, rate
    """
    return {
        "crew_id": row["id"],
        "crew_name": row.get("user_name") or "",
        "display_name": row.get("display_name") or "",
        "is_lead": (row.get("is_lead") or "N").upper()[:1],
        "notes": row.get("notes") or "",
        "org": row["org"],
        "rate": _rate_str(row.get("rate")),
    }


def _show_item(row: dict[str, Any]) -> dict[str, Any]:
    """Show item shape: same as list plus prefs (raw JSON string)."""
    item = _list_item(row)
    item["prefs"] = row.get("prefs_blob") or ""
    return item


@router.get("/list")
def crew_list(
    x_org_id: int = Header(..., alias="X-Org-Id"),
    page: int | None = Query(None),
    per_page: int | None = Query(None),
):
    """GET /callboard/crew/list

    Callboard response shape:
      {
        "result": "ok",
        "data": { "crew": [...], "page": N, "total": N },
        "tg_flash": null
      }
    per_page is accepted as a query param (and applied) but is not echoed
    back in the response body.
    """
    effective_page = page if page is not None else 1
    # Callboard treats missing / 0 / negative as "all"
    effective_per = per_page if (per_page is not None and per_page > 0) else None

    rows = service.get_crew_rows(
        x_org_id,
        page=effective_page if effective_per else None,
        per_page=effective_per,
    )
    total = service.count_crew(x_org_id)

    return {
        "result": "ok",
        "data": {
            "crew": [_list_item(r) for r in rows],
            "page": effective_page,
            "total": total,
        },
        "tg_flash": None,
    }


@router.get("/show")
def crew_show(
    x_org_id: int = Header(..., alias="X-Org-Id"),
    crew_id: int = Query(...),
):
    """GET /callboard/crew/show?crew_id=N

    Success:
      { "result": "ok", "data": { ...fields + prefs }, "tg_flash": null }
    Missing:
      { "result": "fail", "error": "not found" }
    """
    rows = service.get_crew_rows(x_org_id, crew_id=crew_id)
    if not rows:
        return {"result": "fail", "error": "not found"}
    return {
        "result": "ok",
        "data": _show_item(rows[0]),
        "tg_flash": None,
    }
