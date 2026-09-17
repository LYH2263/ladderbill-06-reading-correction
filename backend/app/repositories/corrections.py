import json
import sqlite3
from datetime import datetime, timezone

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"

_COLS = (
    "id, reading_id, account_id, period, old_kwh, new_kwh, old_peak, new_peak, "
    "reason, note, status, supersedes_correction_id, created_at, confirmed_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(
    conn: sqlite3.Connection,
    reading_id: int,
    account_id: int | None,
    period: str | None,
    old_kwh: float,
    new_kwh: float,
    old_peak: int,
    new_peak: int,
    reason: str,
    note: str | None,
    supersedes_correction_id: int | None,
) -> int:
    cur = conn.execute(
        f"""
        INSERT INTO reading_corrections(
            reading_id, account_id, period, old_kwh, new_kwh, old_peak, new_peak,
            reason, note, status, supersedes_correction_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            reading_id,
            account_id,
            period,
            old_kwh,
            new_kwh,
            old_peak,
            new_peak,
            reason,
            note,
            STATUS_PENDING,
            supersedes_correction_id,
            _now(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, correction_id: int) -> dict | None:
    row = conn.execute(
        f"SELECT {_COLS} FROM reading_corrections WHERE id=?", (correction_id,)
    ).fetchone()
    return dict(row) if row else None


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        f"SELECT {_COLS} FROM reading_corrections ORDER BY id DESC"
    ).fetchall()]


def list_for_reading(conn: sqlite3.Connection, reading_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        f"SELECT {_COLS} FROM reading_corrections WHERE reading_id=? ORDER BY id",
        (reading_id,),
    ).fetchall()]


def latest_confirmed_for_reading(conn: sqlite3.Connection, reading_id: int) -> dict | None:
    row = conn.execute(
        f"""
        SELECT {_COLS} FROM reading_corrections
        WHERE reading_id=? AND status='{STATUS_CONFIRMED}'
        ORDER BY id DESC LIMIT 1
        """,
        (reading_id,),
    ).fetchone()
    return dict(row) if row else None


def mark_confirmed(conn: sqlite3.Connection, correction_id: int):
    conn.execute(
        "UPDATE reading_corrections SET status=?, confirmed_at=? WHERE id=?",
        (STATUS_CONFIRMED, _now(), correction_id),
    )
    conn.commit()


def add_audit(conn: sqlite3.Connection, correction_id: int, event: str, detail: dict):
    conn.execute(
        "INSERT INTO correction_audit(correction_id, event, detail, created_at) VALUES (?,?,?,?)",
        (correction_id, event, json.dumps(detail, ensure_ascii=False), _now()),
    )
    conn.commit()


def audit_chain(conn: sqlite3.Connection, correction_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, correction_id, event, detail, created_at FROM correction_audit "
        "WHERE correction_id=? ORDER BY id",
        (correction_id,),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        try:
            item["detail"] = json.loads(item["detail"]) if item.get("detail") else None
        except (TypeError, json.JSONDecodeError):
            pass
        out.append(item)
    return out
