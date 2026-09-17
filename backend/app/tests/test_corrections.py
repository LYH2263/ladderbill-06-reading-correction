import json

import pytest

from app import seed
from app.db import connect
from app.services.correction_service import ConflictError, CorrectionService, NotFoundError


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.db.DB_PATH", db_file)
    seed.init_db()
    yield db_file


def _reading(reading_id):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM readings WHERE id=?", (reading_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def _runs():
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM calc_runs ORDER BY id").fetchall()]
    finally:
        conn.close()


def test_pending_does_not_change_effective_kwh(db):
    with CorrectionService() as svc:
        corr = svc.create_correction(1, 200.0, "抄表录入错误", "复核后调整")
    assert corr["status"] == "PENDING"
    assert corr["old_kwh"] == 120.0
    assert corr["new_kwh"] == 200.0
    reading = _reading(1)
    assert reading["kwh"] == 120.0
    assert reading["original_kwh"] is None


def test_duplicate_pending_rejected(db):
    with CorrectionService() as svc:
        svc.create_correction(1, 200.0, "原因", None)
        with pytest.raises(ConflictError):
            svc.create_correction(1, 210.0, "原因", None)


def test_confirm_snapshots_and_switches(db):
    with CorrectionService() as svc:
        corr = svc.create_correction(1, 200.0, "原因", None)
        out = svc.confirm(corr["id"])
    assert out["correction"]["status"] == "CONFIRMED"
    assert out["correction"]["confirmed_at"]
    reading = out["reading"]
    assert reading["kwh"] == 200.0
    assert reading["original_kwh"] == 120.0


def test_double_confirm_rejected(db):
    with CorrectionService() as svc:
        corr = svc.create_correction(1, 200.0, "原因", None)
        svc.confirm(corr["id"])
        with pytest.raises(ConflictError):
            svc.confirm(corr["id"])


def test_snapshot_keeps_first_value_across_corrections(db):
    with CorrectionService() as svc:
        c1 = svc.create_correction(1, 200.0, "第一次", None)
        svc.confirm(c1["id"])
        c2 = svc.create_correction(1, 250.0, "第二次", None)
        svc.confirm(c2["id"])
    reading = _reading(1)
    assert reading["kwh"] == 250.0
    assert reading["original_kwh"] == 120.0


def test_rerun_requires_confirmed(db):
    with CorrectionService() as svc:
        corr = svc.create_correction(1, 200.0, "原因", None)
        with pytest.raises(ConflictError):
            svc.rerun(corr["id"])


def test_rerun_creates_new_run_without_overwriting(db):
    before = _runs()
    with CorrectionService() as svc:
        corr = svc.create_correction(1, 200.0, "原因", None)
        svc.confirm(corr["id"])
        out = svc.rerun(corr["id"])
    after = _runs()
    assert len(after) == len(before) + 1
    # Old runs untouched: same ids, same payloads.
    assert [r["id"] for r in before] == [r["id"] for r in after[: len(before)]]
    for old, kept in zip(before, after):
        assert old["result_json"] == kept["result_json"]
    run = out["run"]
    assert run["kind"] == "rebill"
    payload = json.loads(run["input_json"])
    assert payload["kwh"] == 200.0
    assert payload["correction_id"] == corr["id"]
    # 200 kWh on seeded tiers: 180*0.52 + 20*0.62
    assert out["result"]["total"] == 106.0
    assert out["correction"]["rerun_id"] == run["id"]


def test_chain_is_ordered_old_to_new(db):
    with CorrectionService() as svc:
        c1 = svc.create_correction(1, 200.0, "第一次", None)
        svc.confirm(c1["id"])
        svc.create_correction(1, 250.0, "第二次", None)
        chain = svc.chain_for_reading(1)
    assert [c["id"] for c in chain["items"]] == sorted(c["id"] for c in chain["items"])
    assert chain["items"][0]["old_kwh"] == 120.0
    assert chain["items"][0]["new_kwh"] == 200.0
    assert chain["items"][1]["old_kwh"] == 200.0
    # Second correction is still pending: effective kwh stays at the first corrected value.
    assert chain["reading"]["kwh"] == 200.0
    assert chain["reading"]["original_kwh"] == 120.0


def test_missing_reading_raises(db):
    with CorrectionService() as svc:
        with pytest.raises(NotFoundError):
            svc.create_correction(999, 100.0, "原因", None)
        with pytest.raises(NotFoundError):
            svc.chain_for_reading(999)
