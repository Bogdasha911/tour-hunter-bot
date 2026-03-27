from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Set

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _split_ints(value: str | None) -> Set[int]:
    if not value:
        return set()
    result = set()
    for part in value.split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_ids: Set[int]
    check_interval_minutes: int
    database_url: str
    tz: str
    repo_dir: Path
    enable_playwright: bool
    deploy_branch: str
    git_remote: str
    max_deals_per_alert: int
    default_currency: str
    sources_file: Path

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            bot_token=os.getenv("BOT_TOKEN", ""),
            admin_ids=_split_ints(os.getenv("ADMIN_IDS")),
            check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "20")),
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/tours.db"),
            tz=os.getenv("TZ", "Europe/Moscow"),
            repo_dir=Path(os.getenv("REPO_DIR", str(BASE_DIR))).resolve(),
            enable_playwright=os.getenv("ENABLE_PLAYWRIGHT", "1") == "1",
            deploy_branch=os.getenv("DEPLOY_BRANCH", "main"),
            git_remote=os.getenv("GIT_REMOTE", "origin"),
            max_deals_per_alert=int(os.getenv("MAX_DEALS_PER_ALERT", "10")),
            default_currency=os.getenv("DEFAULT_CURRENCY", "RUB"),
            sources_file=BASE_DIR / "data" / "sources.yaml",
        )
