import json

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill


def _columns(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn):
    """Idempotent schema migration for existing app.db files."""
    cols = _columns(conn, "readings")
    if "period" not in cols:
        conn.execute("ALTER TABLE readings ADD COLUMN period TEXT")
    if "original_kwh" not in cols:
        conn.execute("ALTER TABLE readings ADD COLUMN original_kwh REAL")
    if "original_peak" not in cols:
        conn.execute("ALTER TABLE readings ADD COLUMN original_peak INTEGER")
    if "superseded_by_correction_id" not in cols:
        conn.execute("ALTER TABLE readings ADD COLUMN superseded_by_correction_id INTEGER")

    run_cols = _columns(conn, "calc_runs")
    if "reading_id" not in run_cols:
        conn.execute("ALTER TABLE calc_runs ADD COLUMN reading_id INTEGER")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reading_corrections(
            id INTEGER PRIMARY KEY,
            reading_id INTEGER NOT NULL,
            account_id INTEGER,
            period TEXT,
            old_kwh REAL NOT NULL,
            new_kwh REAL NOT NULL,
            old_peak INTEGER NOT NULL DEFAULT 0,
            new_peak INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            supersedes_correction_id INTEGER,
            created_at TEXT NOT NULL,
            confirmed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS correction_audit(
            id INTEGER PRIMARY KEY,
            correction_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def init_db():
    conn = connect()
    conn.executescript(
        """
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS accounts(
        id INTEGER PRIMARY KEY, name TEXT, meter_no TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS readings(
        id INTEGER PRIMARY KEY,
        account_id INTEGER,
        kwh REAL,
        peak INTEGER,
        period TEXT,
        original_kwh REAL,
        original_peak INTEGER,
        superseded_by_correction_id INTEGER);
    CREATE TABLE IF NOT EXISTS tiers(id INTEGER PRIMARY KEY, up_to REAL, price REAL, sort_order INTEGER);
    CREATE TABLE IF NOT EXISTS calc_runs(
        id INTEGER PRIMARY KEY,
        kind TEXT,
        account_id INTEGER,
        reading_id INTEGER,
        input_json TEXT,
        result_json TEXT,
        created_at TEXT
    );
    """
    )
    _migrate(conn)
    if conn.execute("SELECT COUNT(*) c FROM accounts").fetchone()["c"] == 0:
        conn.execute(
            "INSERT INTO accounts(name, meter_no, note) VALUES ('张家', 'M-1001', '对照：正常用量')"
        )
        conn.execute(
            "INSERT INTO accounts(name, meter_no, note) VALUES ('李家(种子偏高)', 'M-1002', '对照：高用量+尖峰')"
        )
        conn.executemany(
            "INSERT INTO tiers(up_to, price, sort_order) VALUES (?,?,?)",
            [(180, 0.52, 1), (260, 0.62, 2), (None, 0.82, 3)],
        )
        conn.execute(
            "INSERT INTO readings(account_id, kwh, peak, period) VALUES (1, 120, 0, '2026-08')"
        )
        conn.execute(
            "INSERT INTO readings(account_id, kwh, peak, period) VALUES (2, 400, 1, '2026-08')"
        )
        conn.execute("INSERT INTO settings(key, value) VALUES ('peak_factor', '1.2')")
        conn.execute("INSERT INTO settings(key, value) VALUES ('currency', 'CNY')")
        tiers = [{"up_to": r[0], "price": r[1]} for r in [(180, 0.52), (260, 0.62), (None, 0.82)]]
        bill1 = calc_bill(120, tiers, 1.0)
        conn.execute(
            "INSERT INTO calc_runs(kind, account_id, reading_id, input_json, result_json, created_at) VALUES (?,?,?,?,?,datetime('now'))",
            ("bill", 1, 1, json.dumps({"kwh": 120, "peak": False}, ensure_ascii=False), json.dumps(bill1, ensure_ascii=False)),
        )
        cmp2 = compare_plain_vs_peak(400, tiers, 1.2)
        conn.execute(
            "INSERT INTO calc_runs(kind, account_id, reading_id, input_json, result_json, created_at) VALUES (?,?,?,?,?,datetime('now'))",
            ("compare", 2, 2, json.dumps({"kwh": 400}, ensure_ascii=False), json.dumps(cmp2, ensure_ascii=False)),
        )
        conn.commit()
    conn.close()
