from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from .deals import build_alert_key, score_deal
from .repositories import Repo
from .schemas import ScanStats
from .sources.base import GenericScraper, SourceConfig


class ScanEngine:
    def __init__(
        self,
        bot: Bot,
        sessionmaker: async_sessionmaker,
        sources: list[SourceConfig],
        admin_ids: set[int],
        enable_playwright: bool,
        max_alerts: int,
    ):
        self.bot = bot
        self.sessionmaker = sessionmaker
        self.sources = sources
        self.admin_ids = admin_ids
        self.enable_playwright = enable_playwright
        self.max_alerts = max_alerts

    async def run_once(self) -> ScanStats:
        stats = ScanStats(started_at=datetime.utcnow(), sources_total=len(self.sources))
        alerts: list[str] = []
        async with self.sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.get_or_create_profile()
            source_states = await repo.get_source_states()

            for source in self.sources:
                if source_states.get(source.name, source.enabled) is False:
                    continue
                scraper = GenericScraper(source, enable_playwright=self.enable_playwright)
                try:
                    deals = await scraper.collect(profile)
                    stats.sources_ok += 1
                    stats.deals_seen += len(deals)
                    for deal in deals:
                        aggregate = await repo.upsert_aggregate(deal)
                        score = score_deal(profile, deal, aggregate)
                        saved = await repo.save_deal(deal)
                        if saved:
                            stats.deals_saved += 1
                        if not score.is_candidate:
                            continue
                        dedupe_key = build_alert_key(deal, score)
                        if await repo.was_alert_sent(dedupe_key):
                            continue
                        await repo.mark_alert_sent(dedupe_key)
                        alerts.append(self._format_alert(deal, score))
                        if len(alerts) >= self.max_alerts:
                            break
                    await session.commit()
                except Exception as e:
                    stats.sources_failed += 1
                    alerts.append(f"⚠️ Источник {source.name} дал ошибку: {e}")
                    await session.rollback()
                if len(alerts) >= self.max_alerts:
                    break

        if alerts:
            text = "\n\n".join(alerts[: self.max_alerts])
            for admin_id in self.admin_ids:
                await self.bot.send_message(admin_id, text, disable_web_page_preview=True)
            stats.alerts_sent = len(alerts[: self.max_alerts])
        stats.finished_at = datetime.utcnow()
        return stats

    def _format_alert(self, deal, score) -> str:
        parts = [
            f"🔥 <b>{deal.hotel_name}</b>",
            f"Источник: {deal.source}",
            f"Цена: <b>{deal.price} {deal.currency}</b>",
        ]
        if deal.departure_date:
            parts.append(f"Вылет: {deal.departure_date}")
        if deal.nights:
            parts.append(f"Ночей: {deal.nights}")
        if deal.meal:
            parts.append(f"Питание: {deal.meal}")
        parts.append(f"Причина: {score.reason}")
        parts.append(f"Скор: {score.total_score}")
        if deal.link:
            parts.append(f"Ссылка: {deal.link}")
        return "\n".join(parts)
