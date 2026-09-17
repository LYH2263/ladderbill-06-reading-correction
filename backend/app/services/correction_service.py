from fastapi import HTTPException

from app.db import connect
from app.engines.tier_progressive import calc_bill
from app.repositories import corrections as corr_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo

PENDING = corr_repo.STATUS_PENDING
CONFIRMED = corr_repo.STATUS_CONFIRMED


class CorrectionService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ----- readings -------------------------------------------------------
    def list_readings(self) -> list[dict]:
        rows = readings_repo.list_all(self._conn)
        return [self._enrich_reading(r) for r in rows]

    def readings_for_account(self, account_id: int) -> list[dict]:
        return [self._enrich_reading(r) for r in readings_repo.for_account(self._conn, account_id)]

    def get_reading(self, reading_id: int) -> dict | None:
        row = readings_repo.get(self._conn, reading_id)
        return self._enrich_reading(row) if row else None

    def _enrich_reading(self, row: dict) -> dict:
        pending = [
            c for c in corr_repo.list_for_reading(self._conn, row["id"])
            if c["status"] == PENDING
        ]
        latest_confirmed = corr_repo.latest_confirmed_for_reading(self._conn, row["id"])
        row["has_pending_correction"] = bool(pending)
        row["pending_correction_id"] = pending[0]["id"] if pending else None
        row["last_correction_id"] = latest_confirmed["id"] if latest_confirmed else None
        row["is_corrected"] = row["original_kwh"] is not None
        return row

    # ----- corrections ----------------------------------------------------
    def list_corrections(self, reading_id: int | None = None) -> list[dict]:
        if reading_id is not None:
            return corr_repo.list_for_reading(self._conn, reading_id)
        return corr_repo.list_all(self._conn)

    def get_correction(self, correction_id: int) -> dict:
        row = corr_repo.get(self._conn, correction_id)
        if not row:
            raise HTTPException(404, "correction not found")
        row["audit"] = corr_repo.audit_chain(self._conn, correction_id)
        return row

    def create_correction(
        self, reading_id: int, new_kwh: float, new_peak: bool, reason: str, note: str | None
    ) -> dict:
        reading = readings_repo.get(self._conn, reading_id)
        if not reading:
            raise HTTPException(404, "reading not found")
        if readings_repo.has_pending_correction(self._conn, reading_id):
            raise HTTPException(409, "该抄表已有待确认更正单，不能重复发起")
        if float(new_kwh) == float(reading["kwh"]) and bool(new_peak) == bool(reading["peak"]):
            raise HTTPException(422, "新电量与当前有效电量一致，无需更正")

        latest = corr_repo.latest_confirmed_for_reading(self._conn, reading_id)
        correction_id = corr_repo.create(
            self._conn,
            reading_id=reading_id,
            account_id=reading["account_id"],
            period=reading.get("period"),
            old_kwh=reading["kwh"],
            new_kwh=new_kwh,
            old_peak=int(reading["peak"] or 0),
            new_peak=int(bool(new_peak)),
            reason=reason,
            note=note,
            supersedes_correction_id=latest["id"] if latest else None,
        )
        corr_repo.add_audit(
            self._conn,
            correction_id,
            "created",
            {
                "reading_id": reading_id,
                "period": reading.get("period"),
                "current_kwh": reading["kwh"],
                "proposed_kwh": new_kwh,
                "reason": reason,
                "note": note,
                "supersedes_correction_id": latest["id"] if latest else None,
            },
        )
        # Pending stage: readings.kwh is intentionally left untouched.
        return self.get_correction(correction_id)

    def confirm_correction(self, correction_id: int) -> dict:
        corr = corr_repo.get(self._conn, correction_id)
        if not corr:
            raise HTTPException(404, "correction not found")
        if corr["status"] == CONFIRMED:
            raise HTTPException(409, "更正单已确认，不能重复确认")
        if corr["status"] != PENDING:
            raise HTTPException(409, f"更正单状态为 {corr['status']}，不可确认")

        reading = readings_repo.get(self._conn, corr["reading_id"])
        if not reading:
            raise HTTPException(404, "reading not found")

        # Switch current effective value and freeze the read-only snapshot atomically.
        readings_repo.apply_correction(
            self._conn, reading["id"], corr["new_kwh"], corr["new_peak"], correction_id
        )
        corr_repo.mark_confirmed(self._conn, correction_id)
        corr_repo.add_audit(
            self._conn,
            correction_id,
            "confirmed",
            {
                "reading_id": reading["id"],
                "period": corr["period"],
                "old_kwh": corr["old_kwh"],
                "new_kwh": corr["new_kwh"],
                "old_peak": corr["old_peak"],
                "new_peak": corr["new_peak"],
                "frozen_original_kwh": reading["original_kwh"]
                if reading["original_kwh"] is not None
                else corr["old_kwh"],
                "frozen_original_peak": reading["original_peak"]
                if reading["original_peak"] is not None
                else corr["old_peak"],
                "supersedes_correction_id": corr["supersedes_correction_id"],
            },
        )
        return self.get_correction(correction_id)

    # ----- chain & rerun --------------------------------------------------
    def reading_chain(self, reading_id: int) -> dict:
        reading = self.get_reading(reading_id)
        if not reading:
            raise HTTPException(404, "reading not found")
        corrections = corr_repo.list_for_reading(self._conn, reading_id)
        for c in corrections:
            c["audit"] = corr_repo.audit_chain(self._conn, c["id"])
        return {
            "reading": reading,
            "corrections": corrections,
            "runs": runs_repo.list_for_reading(self._conn, reading_id),
        }

    def rerun_reading(self, reading_id: int) -> dict:
        """Re-measure on the current effective kwh. Always inserts a NEW run."""
        reading = readings_repo.get(self._conn, reading_id)
        if not reading:
            raise HTTPException(404, "reading not found")
        pending = readings_repo.has_pending_correction(self._conn, reading_id)
        if pending:
            raise HTTPException(409, "存在待确认更正单，确认前不得基于新电量再测")

        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        peak = bool(reading["peak"])
        factor = pf if peak else 1.0
        result = calc_bill(reading["kwh"], tiers, factor)
        run_id = runs_repo.insert(
            self._conn,
            "bill",
            {
                "kwh": reading["kwh"],
                "peak": peak,
                "account_id": reading["account_id"],
                "reading_id": reading_id,
                "period": reading.get("period"),
                "source": "correction_rerun",
            },
            result,
            account_id=reading["account_id"],
            reading_id=reading_id,
        )
        return {
            "run_id": run_id,
            "reading_id": reading_id,
            "period": reading.get("period"),
            "kwh": reading["kwh"],
            "peak": int(peak),
            **result,
        }
