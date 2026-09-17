import sqlite3

_COLS = (
    "id, account_id, kwh, peak, period, original_kwh, original_peak, "
    "superseded_by_correction_id"
)


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(f"SELECT {_COLS} FROM readings ORDER BY id").fetchall()]


def for_account(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    q = f"SELECT {_COLS} FROM readings WHERE account_id=? ORDER BY id"
    return [dict(r) for r in conn.execute(q, (account_id,)).fetchall()]


def get(conn: sqlite3.Connection, reading_id: int) -> dict | None:
    row = conn.execute(f"SELECT {_COLS} FROM readings WHERE id=?", (reading_id,)).fetchone()
    return dict(row) if row else None


def has_pending_correction(conn: sqlite3.Connection, reading_id: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) c FROM reading_corrections WHERE reading_id=? AND status='pending'",
        (reading_id,),
    ).fetchone()
    return row["c"] > 0


def apply_correction(conn: sqlite3.Connection, reading_id: int, new_kwh: float, new_peak: int, correction_id: int):
    """Confirm-time switch.

    RHS in an UPDATE sees the old row, so COALESCE(original_kwh, kwh) freezes
    the first-ever value; later corrections only move the current kwh/peak.
    """
    conn.execute(
        """
        UPDATE readings
        SET kwh=?, peak=?,
            original_kwh=COALESCE(original_kwh, kwh),
            original_peak=COALESCE(original_peak, peak),
            superseded_by_correction_id=?
        WHERE id=?
        """,
        (new_kwh, new_peak, correction_id, reading_id),
    )
