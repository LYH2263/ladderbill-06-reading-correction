from app.db import connect
from app.engines.tier_progressive import calc_bill
from app.repositories import corrections as corrections_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo
from app.schemas.corrections import CorrectionStatus


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class CorrectionService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def list_corrections(self, account_id: int | None = None, status: str | None = None):
        return corrections_repo.list_all(self._conn, account_id, status)

    def chain_for_reading(self, reading_id: int):
        reading = readings_repo.get(self._conn, reading_id)
        if not reading:
            raise NotFoundError("reading not found")
        return {
            "reading": reading,
            "items": corrections_repo.for_reading(self._conn, reading_id),
        }

    def create_correction(self, reading_id: int, new_kwh: float, reason: str, remark: str | None):
        reading = readings_repo.get(self._conn, reading_id)
        if not reading:
            raise NotFoundError("reading not found")
        if corrections_repo.pending_for_reading(self._conn, reading_id):
            raise ConflictError("reading already has a pending correction")
        # PENDING only records intent: the reading's effective kwh stays untouched.
        cid = corrections_repo.insert(
            self._conn,
            reading_id=reading_id,
            account_id=reading["account_id"],
            old_kwh=reading["kwh"],
            new_kwh=new_kwh,
            reason=reason,
            remark=remark,
        )
        self._conn.commit()
        return corrections_repo.get(self._conn, cid)

    def confirm(self, correction_id: int):
        corr = corrections_repo.get(self._conn, correction_id)
        if not corr:
            raise NotFoundError("correction not found")
        if corr["status"] != CorrectionStatus.PENDING:
            raise ConflictError("correction is not pending")
        reading = readings_repo.get(self._conn, corr["reading_id"])
        if not reading:
            raise NotFoundError("reading not found")
        # Atomic: snapshot the old value (first time only), switch effective kwh,
        # and close the audit-chain entry.
        readings_repo.apply_correction(self._conn, reading["id"], corr["new_kwh"])
        corrections_repo.mark_confirmed(self._conn, correction_id)
        self._conn.commit()
        return {
            "correction": corrections_repo.get(self._conn, correction_id),
            "reading": readings_repo.get(self._conn, reading["id"]),
        }

    def rerun(self, correction_id: int):
        corr = corrections_repo.get(self._conn, correction_id)
        if not corr:
            raise NotFoundError("correction not found")
        if corr["status"] != CorrectionStatus.CONFIRMED:
            raise ConflictError("only a confirmed correction can be re-calculated")
        reading = readings_repo.get(self._conn, corr["reading_id"])
        if not reading:
            raise NotFoundError("reading not found")
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        peak = bool(reading["peak"])
        result = calc_bill(reading["kwh"], tiers, pf if peak else 1.0)
        # Always a brand-new run; historical runs are never overwritten.
        run_id = runs_repo.insert(
            self._conn,
            "rebill",
            {
                "account_id": reading["account_id"],
                "reading_id": reading["id"],
                "correction_id": correction_id,
                "kwh": reading["kwh"],
                "peak": peak,
            },
            result,
            reading["account_id"],
        )
        corrections_repo.set_rerun(self._conn, correction_id, run_id)
        self._conn.commit()
        return {
            "correction": corrections_repo.get(self._conn, correction_id),
            "run": runs_repo.get(self._conn, run_id),
            "result": result,
        }
