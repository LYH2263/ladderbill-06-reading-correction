from fastapi import APIRouter

from app.schemas.correction import CorrectionCreate
from app.services.correction_service import CorrectionService

router = APIRouter(tags=["corrections"])


@router.get("/corrections")
def list_corrections(reading_id: int | None = None):
    with CorrectionService() as svc:
        return {"items": svc.list_corrections(reading_id)}


@router.post("/corrections")
def create_correction(body: CorrectionCreate):
    with CorrectionService() as svc:
        return svc.create_correction(
            body.reading_id, body.new_kwh, body.new_peak, body.reason, body.note
        )


@router.get("/corrections/{correction_id}")
def get_correction(correction_id: int):
    with CorrectionService() as svc:
        return svc.get_correction(correction_id)


@router.post("/corrections/{correction_id}/confirm")
def confirm_correction(correction_id: int):
    with CorrectionService() as svc:
        return svc.confirm_correction(correction_id)


@router.get("/readings/{reading_id}/chain")
def reading_chain(reading_id: int):
    with CorrectionService() as svc:
        return svc.reading_chain(reading_id)


@router.post("/readings/{reading_id}/rerun")
def rerun_reading(reading_id: int):
    with CorrectionService() as svc:
        return svc.rerun_reading(reading_id)
