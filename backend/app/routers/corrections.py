from fastapi import APIRouter, HTTPException

from app.schemas.corrections import CorrectionCreate
from app.services.correction_service import ConflictError, CorrectionService, NotFoundError

router = APIRouter(tags=["corrections"])


def _not_found(exc: NotFoundError):
    return HTTPException(404, str(exc))


@router.get("/corrections")
def list_corrections(account_id: int | None = None, status: str | None = None):
    with CorrectionService() as svc:
        return {"items": svc.list_corrections(account_id, status)}


@router.get("/readings/{reading_id}/corrections")
def reading_chain(reading_id: int):
    with CorrectionService() as svc:
        try:
            return svc.chain_for_reading(reading_id)
        except NotFoundError as exc:
            raise _not_found(exc)


@router.post("/readings/{reading_id}/corrections", status_code=201)
def create_correction(reading_id: int, body: CorrectionCreate):
    with CorrectionService() as svc:
        try:
            return svc.create_correction(reading_id, body.new_kwh, body.reason, body.remark)
        except NotFoundError as exc:
            raise _not_found(exc)
        except ConflictError as exc:
            raise HTTPException(409, str(exc))


@router.post("/corrections/{correction_id}/confirm")
def confirm_correction(correction_id: int):
    with CorrectionService() as svc:
        try:
            return svc.confirm(correction_id)
        except NotFoundError as exc:
            raise _not_found(exc)
        except ConflictError as exc:
            raise HTTPException(409, str(exc))


@router.post("/corrections/{correction_id}/rerun")
def rerun_correction(correction_id: int):
    with CorrectionService() as svc:
        try:
            return svc.rerun(correction_id)
        except NotFoundError as exc:
            raise _not_found(exc)
        except ConflictError as exc:
            raise HTTPException(409, str(exc))
