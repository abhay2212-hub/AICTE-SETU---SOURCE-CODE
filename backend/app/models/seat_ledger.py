# Owner: Dev B
from __future__ import annotations

from pydantic import BaseModel

from app.models.common import SeatPool


class PoolLedger(BaseModel):
    pool: SeatPool
    approved_seats: int
    admitted: int
    available: int
    overrun: int
    rule_version: str


class ProgrammeLedger(BaseModel):
    programme_id: str
    programme_code: str
    programme_name: str
    approved_total: int
    admitted_total: int
    overrun: int
    pools: list[PoolLedger]


class SeatLedger(BaseModel):
    institution_id: str
    academic_year: str
    programmes: list[ProgrammeLedger]
