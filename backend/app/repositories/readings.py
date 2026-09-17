import sqlite3


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM readings ORDER BY id").fetchall()]


def for_account(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    q = "SELECT * FROM readings WHERE account_id=? ORDER BY id"
    return [dict(r) for r in conn.execute(q, (account_id,)).fetchall()]


def get(conn: sqlite3.Connection, reading_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM readings WHERE id=?", (reading_id,)).fetchone()
    return dict(row) if row else None


def apply_correction(conn: sqlite3.Connection, reading_id: int, new_kwh: float) -> None:
    """Switch the current effective kwh, keeping the pre-correction value in the
    read-only snapshot column (written once, never overwritten).
    Does not commit (service owns the transaction)."""
    conn.execute(
        "UPDATE readings SET original_kwh=COALESCE(original_kwh, kwh), kwh=? WHERE id=?",
        (new_kwh, reading_id),
    )
