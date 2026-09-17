import pytest

from app import db, seed
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.services.correction_service import CorrectionService
from fastapi import HTTPException


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    seed.init_db()
    with CorrectionService() as s:
        yield s


def _reading(svc, reading_id=1):
    return readings_repo.get(svc._conn, reading_id)


def test_pending_does_not_change_current_kwh(svc):
    before = _reading(svc)
    corr = svc.create_correction(1, new_kwh=200, new_peak=False, reason="估抄改实抄", note=None)
    assert corr["status"] == "pending"
    after = _reading(svc)
    assert after["kwh"] == before["kwh"] == 120
    assert after["original_kwh"] is None
    enriched = svc.get_reading(1)
    assert enriched["has_pending_correction"] is True
    assert enriched["pending_correction_id"] == corr["id"]


def test_duplicate_pending_rejected(svc):
    svc.create_correction(1, 200, False, "第一次", None)
    with pytest.raises(HTTPException) as ei:
        svc.create_correction(1, 210, False, "第二次", None)
    assert ei.value.status_code == 409


def test_rerun_blocked_while_pending(svc):
    svc.create_correction(1, 200, False, "估抄改实抄", None)
    with pytest.raises(HTTPException) as ei:
        svc.rerun_reading(1)
    assert ei.value.status_code == 409
    # old run count unchanged
    assert len(runs_repo.list_for_reading(svc._conn, 1)) == 1


def test_confirm_switches_value_and_freezes_snapshot(svc):
    corr = svc.create_correction(1, 200, True, "估抄改实抄", "用户复核")
    out = svc.confirm_correction(corr["id"])
    assert out["status"] == "confirmed"
    assert out["confirmed_at"]
    r = _reading(svc)
    assert r["kwh"] == 200
    assert r["peak"] == 1
    # read-only snapshot keeps the first-ever value
    assert r["original_kwh"] == 120
    assert r["original_peak"] == 0
    assert r["superseded_by_correction_id"] == corr["id"]
    assert svc.get_reading(1)["has_pending_correction"] is False


def test_double_confirm_rejected(svc):
    corr = svc.create_correction(1, 200, False, "x", None)
    svc.confirm_correction(corr["id"])
    with pytest.raises(HTTPException) as ei:
        svc.confirm_correction(corr["id"])
    assert ei.value.status_code == 409


def test_confirm_writes_audit_chain(svc):
    corr = svc.create_correction(1, 200, False, "估抄改实抄", "备注A")
    svc.confirm_correction(corr["id"])
    detail = svc.get_correction(corr["id"])
    events = [a["event"] for a in detail["audit"]]
    assert events == ["created", "confirmed"]
    assert detail["audit"][0]["detail"]["proposed_kwh"] == 200
    assert detail["audit"][1]["detail"]["old_kwh"] == 120
    assert detail["audit"][1]["detail"]["new_kwh"] == 200

    chain = svc.reading_chain(1)
    assert chain["reading"]["kwh"] == 200
    assert [c["id"] for c in chain["corrections"]] == [corr["id"]]


def test_rerun_after_confirm_creates_new_run_without_overwriting(svc):
    old_runs = runs_repo.list_for_reading(svc._conn, 1)
    assert len(old_runs) == 1
    old_id = old_runs[0]["id"]

    corr = svc.create_correction(1, 200, False, "估抄改实抄", None)
    svc.confirm_correction(corr["id"])
    out = svc.rerun_reading(1)

    all_runs = runs_repo.list_for_reading(svc._conn, 1)
    assert len(all_runs) == 2
    assert all_runs[0]["id"] == old_id  # old run preserved, not overwritten
    assert out["run_id"] != old_id
    assert out["run_id"] == all_runs[-1]["id"]
    # new run computed on the new effective kwh: 180*0.52 + 20*0.62
    assert out["total"] == round(180 * 0.52 + 20 * 0.62, 2)
    assert out["kwh"] == 200


def test_second_correction_chain_keeps_original_snapshot(svc):
    c1 = svc.create_correction(1, 200, False, "第一次更正", None)
    svc.confirm_correction(c1["id"])
    c2 = svc.create_correction(1, 260, True, "第二次更正", None)
    assert c2["supersedes_correction_id"] == c1["id"]
    svc.confirm_correction(c2["id"])

    r = _reading(svc)
    assert r["kwh"] == 260
    assert r["peak"] == 1
    # snapshot remains the very first meter value, never rewritten
    assert r["original_kwh"] == 120
    assert r["original_peak"] == 0
    assert r["superseded_by_correction_id"] == c2["id"]

    chain = svc.reading_chain(1)
    assert [c["id"] for c in chain["corrections"]] == [c1["id"], c2["id"]]
    assert chain["corrections"][1]["supersedes_correction_id"] == c1["id"]


def test_noop_correction_rejected(svc):
    with pytest.raises(HTTPException) as ei:
        svc.create_correction(1, 120, False, "无变化", None)
    assert ei.value.status_code == 422
