from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urljoin

import httpx
import yaml
from bs4 import BeautifulSoup

from ..schemas import ParsedDeal, SearchProfile
from ..utils import clean_text, extract_nights, extract_price, first_non_empty


@dataclass(slots=True)
class SourceConfig:
    name: str
    enabled: bool
    use_playwright: bool
    search_url: str
    item_selector: str
    fields: dict[str, dict[str, Any]]
    timeout_seconds: int = 35
    currency: str = "RUB"
    allowed_destination_keywords: list[str] = field(default_factory=list)
    banned_hotel_keywords: list[str] = field(default_factory=list)
    min_price: int | None = None
    max_price: int | None = None


class GenericScraper:
    def __init__(self, cfg: SourceConfig, enable_playwright: bool = True):
        self.cfg = cfg
        self.enable_playwright = enable_playwright

    def build_search_url(self, profile: SearchProfile) -> str:
        mapping = {
            "departure_city": profile.departure_city,
            "destination": profile.destination,
            "adults": profile.adults,
            "children": profile.children,
            "budget": profile.budget,
            "nights_min": profile.nights_min,
            "nights_max": profile.nights_max,
            "date_from": profile.date_from.isoformat() if profile.date_from else "",
            "date_to": profile.date_to.isoformat() if profile.date_to else "",
            "departure_city_q": quote_plus(profile.departure_city),
            "destination_q": quote_plus(profile.destination),
        }
        return self.cfg.search_url.format(**mapping)

    async def fetch_html(self, profile: SearchProfile) -> str:
        url = self.build_search_url(profile)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        if self.cfg.use_playwright and self.enable_playwright:
            return await self._fetch_with_playwright(url)
        async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    async def _fetch_with_playwright(self, url: str) -> str:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(locale="ru-RU")
            await page.goto(url, wait_until="domcontentloaded", timeout=self.cfg.timeout_seconds * 1000)
            await page.wait_for_timeout(3500)
            content = await page.content()
            await browser.close()
            return content

    async def collect(self, profile: SearchProfile) -> list[ParsedDeal]:
        html = await self.fetch_html(profile)
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(self.cfg.item_selector)
        deals: list[ParsedDeal] = []
        seen: set[tuple[str, int, str | None, int | None]] = set()
        for item in items[: profile.max_results_per_source]:
            deal = self._parse_item(item, profile)
            if not deal:
                continue
            if deal.nights is not None and not (profile.nights_min <= deal.nights <= profile.nights_max):
                continue
            key = (deal.hotel_name, deal.price, deal.departure_date, deal.nights)
            if key in seen:
                continue
            seen.add(key)
            deals.append(deal)
        return deals

    def _parse_item(self, item, profile: SearchProfile) -> ParsedDeal | None:
        hotel_name = self._extract_field(item, "hotel_name")
        price_text = self._extract_field(item, "price_text")
        if not hotel_name or not price_text:
            return None

        hotel_name_l = hotel_name.lower()
        destination_l = profile.destination.lower()
        if destination_l and destination_l not in hotel_name_l:
            allowed = [x.lower() for x in self.cfg.allowed_destination_keywords]
            if allowed and not any(word in hotel_name_l for word in allowed):
                return None
        banned = [x.lower() for x in self.cfg.banned_hotel_keywords]
        if any(word in hotel_name_l for word in banned):
            return None

        price = extract_price(price_text)
        if not price:
            return None
        if self.cfg.min_price is not None and price < self.cfg.min_price:
            return None
        if self.cfg.max_price is not None and price > self.cfg.max_price:
            return None
        if price > int(profile.budget * 1.8):
            return None

        departure_text = self._extract_field(item, "departure_text")
        nights_text = self._extract_field(item, "nights_text")
        meal = self._extract_field(item, "meal")
        link = self._extract_field(item, "link")
        if link and link.startswith("/"):
            link = urljoin(self.build_search_url(profile), link)

        return ParsedDeal(
            source=self.cfg.name,
            hotel_name=hotel_name,
            price=price,
            currency=self.cfg.currency,
            link=link,
            departure_date=departure_text,
            nights=extract_nights(nights_text or "") if nights_text else None,
            meal=meal,
            raw_payload={
                "hotel_name": hotel_name,
                "price_text": price_text,
                "departure_text": departure_text,
                "nights_text": nights_text,
                "meal": meal,
                "link": link,
            },
        )

    def _extract_field(self, item, field_name: str) -> str | None:
        field_cfg = self.cfg.fields.get(field_name) or {}
        selectors = field_cfg.get("selectors", [])
        attr = field_cfg.get("attr")
        values: list[str | None] = []
        for selector in selectors:
            node = item.select_one(selector)
            if not node:
                continue
            if attr:
                values.append(node.get(attr))
            else:
                values.append(node.get_text(" ", strip=True))
        value = first_non_empty(values)
        return clean_text(value)


def load_sources(path: str) -> list[SourceConfig]:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    defaults = payload.get("global_defaults", {})
    result: list[SourceConfig] = []
    for item in payload.get("sources", []):
        result.append(
            SourceConfig(
                name=item["name"],
                enabled=item.get("enabled", defaults.get("enabled", True)),
                use_playwright=item.get("use_playwright", False),
                search_url=item["search_url"],
                item_selector=item["item_selector"],
                fields=item.get("fields", {}),
                timeout_seconds=item.get("timeout_seconds", defaults.get("timeout_seconds", 35)),
                currency=item.get("currency", defaults.get("currency", "RUB")),
                allowed_destination_keywords=item.get("allowed_destination_keywords", []),
                banned_hotel_keywords=item.get("banned_hotel_keywords", []),
                min_price=item.get("min_price"),
                max_price=item.get("max_price"),
            )
        )
    return result
