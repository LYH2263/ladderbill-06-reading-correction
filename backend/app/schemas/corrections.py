from enum import StrEnum

from pydantic import BaseModel, Field


class CorrectionStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"


class CorrectionCreate(BaseModel):
    new_kwh: float = Field(ge=0)
    reason: str = Field(min_length=1, max_length=200)
    remark: str | None = Field(default=None, max_length=500)


class CorrectionOut(BaseModel):
    id: int
    reading_id: int
    account_id: int
    old_kwh: float
    new_kwh: float
    reason: str
    remark: str | None
    status: str
    created_at: str
    confirmed_at: str | None
    rerun_id: int | None
