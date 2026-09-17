from fastapi import APIRouter

from app.services.correction_service import CorrectionService

router = APIRouter(tags=["readings"])


@router.get("/readings")
def list_readings():
    with CorrectionService() as svc:
        return {"items": svc.list_readings()}
