from decimal import Decimal

from pydantic import BaseModel


class StrategyRequest(BaseModel):
    strategy: str
    indicators: dict[str, Decimal | int | float]


class StrategyResponse(BaseModel):
    strategy: str
    approved: bool


class StrategyScoreRequest(BaseModel):
    criteria: dict[str, bool]


class StrategyScoreResponse(BaseModel):
    score: int
