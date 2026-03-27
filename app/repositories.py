from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import orjson
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AlertLogModel, DealAggregateModel, DealModel, SearchProfileModel, SourceStateModel
from .schemas import ParsedDeal, SearchProfile


class Repo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_profile(self) -> SearchProfile:
        model = await self.session.get(SearchProfileModel, 1)
        if not model:
            model = SearchProfileModel(id=1)
            self.session.add(model)
            await self.session.commit()
            await self.session.refresh(model)
        return SearchProfile(
            departure_city=model.departure_city,
            destination=model.destination,
            adults=model.adults,
            children=model.children,
            budget=model.budget,
            nights_min=model.nights_min,
            nights_max=model.nights_max,
            date_from=_parse_date(model.date_from),
            date_to=_parse_date(model.date_to),
            min_drop_percent=model.min_drop_percent,
            max_results_per_source=model.max_results_per_source,
        )

    async def update_profile(self, **kwargs) -> SearchProfile:
        model = await self.session.get(SearchProfileModel, 1)
        if not model:
            model = SearchProfileModel(id=1)
            self.session.add(model)
        for k, v in kwargs.items():
            setattr(model, k, v)
        await self.session.commit()
        return await self.get_or_create_profile()

    async def save_deal(self, deal: ParsedDeal) -> DealModel | None:
        model = DealModel(
            source=deal.source,
            hotel_name=deal.hotel_name[:300],
            price=deal.price,
            currency=deal.currency,
            link=deal.link,
            departure_date=deal.departure_date,
            nights=deal.nights,
            meal=deal.meal,
            room_type=deal.room_type,
            raw_json=orjson.dumps(deal.raw_payload).decode("utf-8"),
        )
        self.session.add(model)
        try:
            await self.session.flush()
        except Exception:
            await self.session.rollback()
            return None
        return model

    async def upsert_aggregate(self, deal: ParsedDeal) -> DealAggregateModel:
        stmt = select(DealAggregateModel).where(
            DealAggregateModel.source == deal.source,
            DealAggregateModel.hotel_name == deal.hotel_name,
            DealAggregateModel.departure_date == deal.departure_date,
            DealAggregateModel.nights == deal.nights,
            DealAggregateModel.meal == deal.meal,
            DealAggregateModel.room_type == deal.room_type,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.last_price = deal.price
            existing.min_price = min(existing.min_price, deal.price)
            existing.max_price = max(existing.max_price, deal.price)
            existing.observations += 1
            existing.last_link = deal.link
            existing.updated_at = datetime.utcnow()
            await self.session.flush()
            return existing

        created = DealAggregateModel(
            source=deal.source,
            hotel_name=deal.hotel_name,
            departure_date=deal.departure_date,
            nights=deal.nights,
            meal=deal.meal,
            room_type=deal.room_type,
            min_price=deal.price,
            last_price=deal.price,
            max_price=deal.price,
            observations=1,
            last_link=deal.link,
        )
        self.session.add(created)
        await self.session.flush()
        return created

    async def was_alert_sent(self, dedupe_key: str, ttl_hours: int = 24) -> bool:
        border = datetime.utcnow() - timedelta(hours=ttl_hours)
        stmt = select(AlertLogModel).where(AlertLogModel.dedupe_key == dedupe_key, AlertLogModel.sent_at >= border)
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def mark_alert_sent(self, dedupe_key: str) -> None:
        self.session.add(AlertLogModel(dedupe_key=dedupe_key))
        await self.session.flush()

    async def get_top_deals(self, limit: int = 15) -> list[DealAggregateModel]:
        stmt = select(DealAggregateModel).order_by(DealAggregateModel.min_price.asc(), DealAggregateModel.updated_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_recent_history(self, limit: int = 20) -> list[DealModel]:
        stmt = select(DealModel).order_by(DealModel.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_source_states(self) -> dict[str, bool]:
        stmt = select(SourceStateModel)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return {row.name: row.enabled for row in rows}

    async def set_source_state(self, name: str, enabled: bool) -> None:
        existing = await self.session.get(SourceStateModel, name)
        if existing:
            existing.enabled = enabled
            existing.updated_at = datetime.utcnow()
        else:
            self.session.add(SourceStateModel(name=name, enabled=enabled))
        await self.session.commit()

    async def prune_alert_logs(self, keep_days: int = 7) -> int:
        border = datetime.utcnow() - timedelta(days=keep_days)
        result = await self.session.execute(delete(AlertLogModel).where(AlertLogModel.sent_at < border))
        await self.session.commit()
        return result.rowcount or 0

    async def count_stats(self) -> dict[str, int]:
        deals_total = (await self.session.execute(select(func.count()).select_from(DealModel))).scalar_one()
        aggregates_total = (await self.session.execute(select(func.count()).select_from(DealAggregateModel))).scalar_one()
        alerts_total = (await self.session.execute(select(func.count()).select_from(AlertLogModel))).scalar_one()
        return {
            "deals_total": int(deals_total),
            "aggregates_total": int(aggregates_total),
            "alerts_total": int(alerts_total),
        }


def _parse_date(value: str | None):
    if not value:
        return None
    from datetime import date

    return date.fromisoformat(value)
