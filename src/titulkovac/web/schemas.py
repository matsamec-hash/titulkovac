from __future__ import annotations

from pydantic import BaseModel


class JobOut(BaseModel):
    id: str
    filename: str
    languages: list[str]
    status: str
    step: str
    progress: float
    error: str | None = None


class CueOut(BaseModel):
    index: int
    start: float
    end: float
    text: str
    translations: dict[str, str] = {}
    edited: bool = False


class CuePatch(BaseModel):
    text: str | None = None
    start: float | None = None
    end: float | None = None
    translations: dict[str, str] | None = None
