from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(slots=True)
class SearchProfile:
    departure_city: str = "Москва"
    destination: str = "Дубай"
    adults: int = 1
    children: int = 0
    budget: int = 60000
    nights_min: int = 3
    nights_max: int = 10
    date_from: date | None = None
    date_to: date | None = None
    min_drop_percent: float = 7.0
    max_results_per_source: int = 80


@dataclass(slots=True)
class ParsedDeal:
    source: str
    hotel_name: str
    price: int
    currency: str
    link: str | None = None
    departure_date: str | None = None
    nights: int | None = None
    meal: str | None = None
    room_type: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DealScore:
    is_candidate: bool
    total_score: float
    reason: str
    price_drop_percent: float = 0.0
    is_new_low: bool = False
    is_flash: bool = False


@dataclass(slots=True)
class ScanStats:
    started_at: datetime
    finished_at: datetime | None = None
    sources_total: int = 0
    sources_ok: int = 0
    sources_failed: int = 0
    deals_seen: int = 0
    deals_saved: int = 0
    alerts_sent: int = 0
