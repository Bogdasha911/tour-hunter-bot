from __future__ import annotations

from .models import DealAggregateModel
from .schemas import DealScore, ParsedDeal, SearchProfile


_FLASH_WORDS = (
    "сегодня",
    "завтра",
    "горящий",
    "last minute",
    "вылет",
)


def score_deal(profile: SearchProfile, deal: ParsedDeal, aggregate: DealAggregateModel | None) -> DealScore:
    score = 0.0
    reasons: list[str] = []
    price_drop_percent = 0.0
    is_new_low = False
    is_flash = False

    if deal.price <= profile.budget:
        score += 45
        reasons.append(f"ниже бюджета ({deal.price} ≤ {profile.budget})")

    if deal.nights is not None and profile.nights_min <= deal.nights <= profile.nights_max:
        score += 8
    elif deal.nights is not None:
        score -= 12

    if deal.meal:
        meal_l = deal.meal.lower()
        if any(x in meal_l for x in ("all", "завтрак", "bb", "hb", "fb", "ultra")):
            score += 3

    if deal.departure_date:
        departure_l = deal.departure_date.lower()
        if any(word in departure_l for word in _FLASH_WORDS):
            score += 8
            reasons.append("близкий вылет")

    if aggregate is None:
        score += 18
        reasons.append("новый вариант")
        is_new_low = True
    else:
        if aggregate.last_price > 0 and deal.price < aggregate.last_price:
            price_drop_percent = round(((aggregate.last_price - deal.price) / aggregate.last_price) * 100, 2)
            score += min(price_drop_percent * 1.8, 30)
            reasons.append(f"падение цены {price_drop_percent}%")
        if deal.price <= aggregate.min_price:
            score += 18
            is_new_low = True
            reasons.append("новый минимум")
        if aggregate.observations <= 2:
            score += 4
        if aggregate.min_price > 0 and deal.price <= int(aggregate.min_price * 0.94):
            score += 10
            reasons.append("ниже прежнего минимума с запасом")

    if price_drop_percent >= max(5.0, profile.min_drop_percent):
        score += 20
        is_flash = True
        reasons.append("похоже на горящий/слив цены")

    if deal.price <= int(profile.budget * 0.88):
        score += 12
        reasons.append("аномально дёшево относительно бюджета")

    if deal.price <= int(profile.budget * 0.75):
        score += 12
        reasons.append("сильное отклонение вниз от бюджета")

    return DealScore(
        is_candidate=score >= 40,
        total_score=round(score, 2),
        reason=", ".join(reasons) if reasons else "под наблюдением",
        price_drop_percent=price_drop_percent,
        is_new_low=is_new_low,
        is_flash=is_flash,
    )


def build_alert_key(deal: ParsedDeal, score: DealScore) -> str:
    return "|".join(
        [
            deal.source,
            deal.hotel_name,
            str(deal.departure_date or ""),
            str(deal.nights or ""),
            str(deal.price),
            f"{score.price_drop_percent}",
        ]
    )
