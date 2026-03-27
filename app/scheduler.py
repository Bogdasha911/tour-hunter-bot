from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


class BotScheduler:
    def __init__(self, minutes: int, callback):
        self.scheduler = AsyncIOScheduler()
        self.minutes = minutes
        self.callback = callback

    def start(self) -> None:
        self.scheduler.add_job(self.callback, IntervalTrigger(minutes=self.minutes), id="scan_job", replace_existing=True)
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
