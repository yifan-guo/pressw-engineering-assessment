"""Shared crew business logic.

One place that talks to tg_crew. Both the legacy wrappers and the /v3 endpoints
call into this module so the migration doesn't duplicate query/update rules.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Map a tg_crew row to a plain dict (DB column names)."""
    return {
        "id": row.id,
        "org": row.org,
        "user_name": row.user_name,
        "display_name": row.display_name,
        "rate": row.rate,
        "is_lead": row.is_lead,
        "notes": row.notes or "",
        "prefs_blob": row.prefs_blob,
    }


def list_crew(
    session: Session,
    org: int,
    *,
    page: int = 1,
    per_page: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return (rows, total) for an org, optionally paginated.

    per_page=0 or None means return all rows (matches Callboard quirk).
    """
    total = session.execute(
        text("SELECT COUNT(*) FROM tg_crew WHERE org = :org"),
        {"org": org},
    ).scalar_one()

    if per_page is None or per_page == 0:
        rows = session.execute(
            text(
                """
                SELECT id, org, user_name, display_name, rate, is_lead, notes, prefs_blob
                FROM tg_crew
                WHERE org = :org
                ORDER BY id
                """
            ),
            {"org": org},
        ).fetchall()
    else:
        offset = max(page - 1, 0) * per_page
        rows = session.execute(
            text(
                """
                SELECT id, org, user_name, display_name, rate, is_lead, notes, prefs_blob
                FROM tg_crew
                WHERE org = :org
                ORDER BY id
                LIMIT :limit OFFSET :offset
                """
            ),
            {"org": org, "limit": per_page, "offset": offset},
        ).fetchall()

    return [_row_to_dict(r) for r in rows], int(total)


def get_crew(session: Session, org: int, crew_id: int) -> dict[str, Any] | None:
    """Return one crew row scoped to org, or None if missing / wrong org."""
    row = session.execute(
        text(
            """
            SELECT id, org, user_name, display_name, rate, is_lead, notes, prefs_blob
            FROM tg_crew
            WHERE id = :id AND org = :org
            """
        ),
        {"id": crew_id, "org": org},
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def update_crew_notes(
    session: Session,
    org: int,
    crew_id: int,
    notes: str,
) -> dict[str, Any] | None:
    """Update notes for a crew member in this org. Returns the updated row or None.

    Observed Callboard behavior (traffic index 10): only the notes column changes.
    Org scoping is enforced so one org cannot mutate another's crew.
    """
    result = session.execute(
        text(
            """
            UPDATE tg_crew
            SET notes = :notes
            WHERE id = :id AND org = :org
            RETURNING id, org, user_name, display_name, rate, is_lead, notes, prefs_blob
            """
        ),
        {"id": crew_id, "org": org, "notes": notes},
    )
    row = result.fetchone()
    if row is None:
        return None
    session.commit()
    return _row_to_dict(row)


def format_rate(rate: Any) -> str:
    """Callboard returns rate as a string with two decimal places."""
    if rate is None:
        return "0.00"
    return f"{float(rate):.2f}"
