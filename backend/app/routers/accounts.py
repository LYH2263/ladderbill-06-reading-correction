from fastapi import APIRouter, HTTPException

from app.services.billing_service import BillingService
from app.services.correction_service import CorrectionService

router = APIRouter(tags=["accounts"])


@router.get("/accounts")
def list_accounts():
    with BillingService() as svc:
        return {"items": svc.list_accounts()}


@router.get("/accounts/{account_id}")
def get_account(account_id: int):
    with BillingService() as svc:
        row = svc.get_account(account_id)
        if not row:
            raise HTTPException(404, "account not found")
    with CorrectionService() as corr_svc:
        readings = corr_svc.readings_for_account(account_id)
    return {"account": row, "readings": readings}
