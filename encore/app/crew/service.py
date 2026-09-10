"""Shared business logic for crew reads against tg_crew.

One place that talks to the DB. Both legacy wrappers and /v3 endpoints call this.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .. import db


def get_crew_rows(
    org: int,
    *,
    crew_id: int | None = None,
    page: int | None = None,
    per_page: int | None = None,
) -> list[dict[str, Any]]:
    """Return raw crew rows for an org, optionally filtered and paginated.

    Returns list of dicts with keys matching tg_crew columns (plus any
    computed fields we need). Pagination is 1-based; per_page=0 means "all".
    """
    clauses = ["org = :org"]
    params: dict[str, Any] = {"org": org}

    if crew_id is not None:
        clauses.append("id = :crew_id")
        params["crew_id"] = crew_id

    where = " AND ".join(clauses)
    # Stable order so pagination and list responses are deterministic.
    sql = f"""
        SELECT id, org, org_name, user_name, display_name, password, rate,
               is_lead, notes, prefs_blob, created
        FROM tg_crew
        WHERE {where}
        ORDER BY id
    """

    # Apply pagination only when both page and a positive per_page are given.
    # Legacy quirk: per_page=0 (or missing) often means "return everything".
    if page is not None and per_page is not None and per_page > 0:
        offset = max(page - 1, 0) * per_page
        sql += " LIMIT :limit OFFSET :offset"
        params["limit"] = per_page
        params["offset"] = offset

    with db.session() as s:
        rows = s.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]


def count_crew(org: int) -> int:
    """Total crew members for an org (for pagination metadata)."""
    with db.session() as s:
        return s.execute(
            text("SELECT COUNT(*) FROM tg_crew WHERE org = :org"),
            {"org": org},
        ).scalar_one()
