from __future__ import annotations

from pydantic import BaseModel


class HealthDto(BaseModel):
    ok: bool
    version: str
