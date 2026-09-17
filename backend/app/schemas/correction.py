from pydantic import BaseModel, Field


class CorrectionCreate(BaseModel):
    reading_id: int
    new_kwh: float = Field(ge=0)
    new_peak: bool = False
    reason: str = Field(min_length=1)
    note: str | None = None


class CorrectionOut(BaseModel):
    id: int
    reading_id: int
    account_id: int | None = None
    period: str | None = None
    old_kwh: float
    new_kwh: float
    old_peak: int
    new_peak: int
    reason: str
    note: str | None = None
    status: str
    supersedes_correction_id: int | None = None
    created_at: str
    confirmed_at: str | None = None
