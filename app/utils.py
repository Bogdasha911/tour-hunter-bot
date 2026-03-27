from __future__ import annotations

import re
from typing import Iterable


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def extract_price(text: str) -> int | None:
    digits = re.findall(r"\d+", text.replace(" ", ""))
    if not digits:
        return None
    joined = "".join(digits)
    try:
        return int(joined)
    except ValueError:
        return None


def extract_nights(text: str) -> int | None:
    match = re.search(r"(\d{1,2})", text)
    return int(match.group(1)) if match else None


def first_non_empty(values: Iterable[str | None]) -> str | None:
    for item in values:
        if item and item.strip():
            return item.strip()
    return None
