import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert(
    conn: sqlite3.Connection,
    reading_id: int,
    account_id: int,
    old_kwh: float,
    new_kwh: float,
    reason: str,
    remark: str | None,
) -> int:
    """Insert a PENDING correction. Does not commit (service owns the transaction)."""
    cur = conn.execute(
        """
        INSERT INTO reading_corrections(
            reading_id, account_id, old_kwh, new_kwh, reason, remark,
            status, created_at
        ) VALUES (?,?,?,?,?,?, 'PENDING', ?)
        """,
        (reading_id, account_id, old_kwh, new_kwh, reason, remark, _now()),
    )
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, correction_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM reading_corrections WHERE id=?", (correction_id,)).fetchone()
    return dict(row) if row else None


def pending_for_reading(conn: sqlite3.Connection, reading_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM reading_corrections WHERE reading_id=? AND status='PENDING' ORDER BY id DESC LIMIT 1",
        (reading_id,),
    ).fetchone()
    return dict(row) if row else None


def for_reading(conn: sqlite3.Connection, reading_id: int) -> list[dict]:
    """Audit chain for one reading, oldest first."""
    q = "SELECT * FROM reading_corrections WHERE reading_id=? ORDER BY id"
    return [dict(r) for r in conn.execute(q, (reading_id,)).fetchall()]


def list_all(
    conn: sqlite3.Connection,
    account_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    q = "SELECT * FROM reading_corrections"
    cond, args = [], []
    if account_id is not None:
        cond.append("account_id=?")
        args.append(account_id)
    if status is not None:
        cond.append("status=?")
        args.append(status)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY id DESC"
    return [dict(r) for r in conn.execute(q, args).fetchall()]


def mark_confirmed(conn: sqlite3.Connection, correction_id: int) -> None:
    """Does not commit (service owns the transaction)."""
    conn.execute(
        "UPDATE reading_corrections SET status='CONFIRMED', confirmed_at=? WHERE id=?",
        (_now(), correction_id),
    )


def set_rerun(conn: sqlite3.Connection, correction_id: int, run_id: int) -> None:
    """Does not commit (service owns the transaction)."""
    conn.execute(
        "UPDATE reading_corrections SET rerun_id=? WHERE id=?",
        (run_id, correction_id),
    )
