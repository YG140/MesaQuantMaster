from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class QuoteResponse(BaseModel):
    ticker: str

    price: Decimal

    previous_close: Decimal | None = None

    change: Decimal | None = None

    change_percent: Decimal | None = None

    high: Decimal | None = None

    low: Decimal | None = None

    open: Decimal | None = None

    volume: int | None = None

    currency: str = "BRL"

    market_time: datetime | None = None

    source: str
