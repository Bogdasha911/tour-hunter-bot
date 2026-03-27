from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from sqlalchemy.ext.asyncio import async_sessionmaker

from .config import Settings
from .deployer import run_deploy
from .engine import ScanEngine
from .repositories import Repo
from .sources.base import load_sources


def build_router(settings: Settings, sessionmaker: async_sessionmaker, engine: ScanEngine) -> Router:
    router = Router()

    def admin_only(func):
        async def wrapper(message: Message, *args, **kwargs):
            if message.from_user is None or message.from_user.id not in settings.admin_ids:
                await message.answer("Нет доступа.")
                return
            return await func(message, *args)
        return wrapper

    def is_admin_callback(callback: CallbackQuery) -> bool:
        return callback.from_user is not None and callback.from_user.id in settings.admin_ids

    def admin_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Статус", callback_data="admin_status")],
                [
                    InlineKeyboardButton(text="🔄 Tour", callback_data="restart_tour"),
                    InlineKeyboardButton(text="🔄 Avito", callback_data="restart_avito"),
                ],
                [
                    InlineKeyboardButton(text="📜 Логи Tour", callback_data="logs_tour"),
                    InlineKeyboardButton(text="📜 Логи Avito", callback_data="logs_avito"),
                ],
                [InlineKeyboardButton(text="🚀 Деплой", callback_data="deploy_tour")],
            ]
        )

    def get_service_status(service: str) -> str:
        try:
            return subprocess.check_output(
                ["systemctl", "is-active", service],
                stderr=subprocess.STDOUT
            ).decode().strip()
        except Exception:
            return "unknown"

    def get_service_logs(service: str, lines: int = 20) -> str:
        try:
            logs = subprocess.check_output(
                ["journalctl", "-u", service, "-n", str(lines), "--no-pager"],
                stderr=subprocess.STDOUT
            ).decode()
            return logs[-3500:]
        except Exception as e:
            return f"Ошибка чтения логов {service}: {e}"

    @router.message(Command("start"))
    @admin_only
    async def start_cmd(message: Message):
        await message.answer(
            "Готово. Я слежу за дешёвыми и горящими турами.\n\n"
            "/admin\n/status\n/scan_now\n/top_deals\n/history\n/sources\n/reload_sources\n"
            "/set_budget 60000\n/set_nights 5 10\n/set_dates 2026-04-01 2026-04-10\n"
            "/set_city Москва\n/set_destination Дубай\n/set_adults 1\n/set_children 0\n"
            "/set_drop 7\n/set_results 60\n"
            "/toggle_source travelata on\n/deploy\n"
            "/bot_status\n/bot_restart tour\n/bot_restart avito\n/bot_logs tour"
        )

    @router.message(Command("admin"))
    @admin_only
    async def admin_panel(message: Message):
        await message.answer("Админ панель:", reply_markup=admin_keyboard())

    @router.message(Command("status"))
    @admin_only
    async def status_cmd(message: Message):
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.get_or_create_profile()
            stats = await repo.count_stats()
            source_states = await repo.get_source_states()

        sources = load_sources(str(settings.sources_file))
        lines = [
            "<b>Статус бота</b>",
            f"Маршрут: {profile.departure_city} → {profile.destination}",
            f"Бюджет: {profile.budget} ₽",
            f"Ночей: {profile.nights_min}-{profile.nights_max}",
            f"Даты: {profile.date_from or '-'} → {profile.date_to or '-'}",
            f"Взрослых: {profile.adults}, детей: {profile.children}",
            f"Минимальное падение цены: {profile.min_drop_percent}%",
            f"Лимит карточек на источник: {profile.max_results_per_source}",
            f"Источников в конфиге: {len(sources)}",
            f"Сделок в истории: {stats['deals_total']}",
            f"Уникальных агрегатов: {stats['aggregates_total']}",
            f"Отправленных алертов: {stats['alerts_total']}",
            "",
            "<b>Источники</b>",
        ]
        for src in sources:
            enabled = source_states.get(src.name, src.enabled)
            lines.append(f"- {src.name}: {'ON' if enabled else 'OFF'}")
        await message.answer("\n".join(lines))

    @router.message(Command("scan_now"))
    @admin_only
    async def scan_now_cmd(message: Message):
        await message.answer("Запускаю проверку...")
        stats = await engine.run_once()
        await message.answer(
            f"Готово. Источников ок: {stats.sources_ok}, ошибок: {stats.sources_failed}, "
            f"увидел туров: {stats.deals_seen}, сохранил: {stats.deals_saved}, алертов: {stats.alerts_sent}"
        )

    @router.message(Command("top_deals"))
    @admin_only
    async def top_deals_cmd(message: Message):
        async with sessionmaker() as session:
            repo = Repo(session)
            items = await repo.get_top_deals(limit=12)
        if not items:
            await message.answer("Пока пусто.")
            return
        lines = ["<b>Лучшие предложения в базе</b>"]
        for item in items:
            lines.append(
                f"\n• <b>{item.hotel_name}</b>\n"
                f"Источник: {item.source}\n"
                f"Мин: {item.min_price} ₽ | Сейчас: {item.last_price} ₽\n"
                f"Ночей: {item.nights or '-'} | Вылет: {item.departure_date or '-'}\n"
                f"Ссылка: {item.last_link or '-'}"
            )
        await message.answer("\n".join(lines), disable_web_page_preview=True)

    @router.message(Command("history"))
    @admin_only
    async def history_cmd(message: Message):
        async with sessionmaker() as session:
            repo = Repo(session)
            items = await repo.get_recent_history(limit=15)
        if not items:
            await message.answer("История пока пустая.")
            return
        lines = ["<b>Последние изменения</b>"]
        for item in items:
            lines.append(f"• {item.created_at:%d.%m %H:%M} | {item.source} | {item.hotel_name} | {item.price} ₽")
        await message.answer("\n".join(lines))

    @router.message(Command("sources"))
    @admin_only
    async def sources_cmd(message: Message):
        async with sessionmaker() as session:
            repo = Repo(session)
            states = await repo.get_source_states()
        items = load_sources(str(settings.sources_file))
        lines = ["<b>Источники</b>"]
        for item in items:
            enabled = states.get(item.name, item.enabled)
            lines.append(f"• {item.name} | {'ON' if enabled else 'OFF'} | playwright={'yes' if item.use_playwright else 'no'}")
            lines.append(f"  {item.search_url}")
        await message.answer("\n".join(lines), disable_web_page_preview=True)

    @router.message(Command("reload_sources"))
    @admin_only
    async def reload_sources_cmd(message: Message):
        engine.sources = load_sources(str(settings.sources_file))
        await message.answer(f"Источники перечитаны. Теперь их: {len(engine.sources)}")

    @router.message(Command("set_budget"))
    @admin_only
    async def set_budget_cmd(message: Message, command: CommandObject):
        parts = (command.args or "").split()
        if len(parts) != 1 or not parts[0].isdigit():
            await message.answer("Пример: /set_budget 60000")
            return
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(budget=int(parts[0]))
        await message.answer(f"Бюджет обновлён: {profile.budget} ₽")

    @router.message(Command("set_nights"))
    @admin_only
    async def set_nights_cmd(message: Message, command: CommandObject):
        parts = (command.args or "").split()
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            await message.answer("Пример: /set_nights 5 10")
            return
        min_n, max_n = map(int, parts)
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(nights_min=min_n, nights_max=max_n)
        await message.answer(f"Ночи обновлены: {profile.nights_min}-{profile.nights_max}")

    @router.message(Command("set_dates"))
    @admin_only
    async def set_dates_cmd(message: Message, command: CommandObject):
        parts = (command.args or "").split()
        if len(parts) != 2:
            await message.answer("Пример: /set_dates 2026-04-01 2026-04-10")
            return
        try:
            d1 = date.fromisoformat(parts[0])
            d2 = date.fromisoformat(parts[1])
        except ValueError:
            await message.answer("Дата должна быть в формате YYYY-MM-DD")
            return
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(date_from=d1.isoformat(), date_to=d2.isoformat())
        await message.answer(f"Даты обновлены: {profile.date_from} → {profile.date_to}")

    @router.message(Command("set_city"))
    @admin_only
    async def set_city_cmd(message: Message, command: CommandObject):
        value = (command.args or "").strip()
        if not value:
            await message.answer("Пример: /set_city Москва")
            return
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(departure_city=value)
        await message.answer(f"Город вылета: {profile.departure_city}")

    @router.message(Command("set_destination"))
    @admin_only
    async def set_destination_cmd(message: Message, command: CommandObject):
        value = (command.args or "").strip()
        if not value:
            await message.answer("Пример: /set_destination Дубай")
            return
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(destination=value)
        await message.answer(f"Направление: {profile.destination}")

    @router.message(Command("set_adults"))
    @admin_only
    async def set_adults_cmd(message: Message, command: CommandObject):
        value = (command.args or "").strip()
        if not value.isdigit():
            await message.answer("Пример: /set_adults 1")
            return
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(adults=int(value))
        await message.answer(f"Взрослых: {profile.adults}")

    @router.message(Command("set_children"))
    @admin_only
    async def set_children_cmd(message: Message, command: CommandObject):
        value = (command.args or "").strip()
        if not value.isdigit():
            await message.answer("Пример: /set_children 0")
            return
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(children=int(value))
        await message.answer(f"Детей: {profile.children}")

    @router.message(Command("set_drop"))
    @admin_only
    async def set_drop_cmd(message: Message, command: CommandObject):
        value = (command.args or "").strip().replace(",", ".")
        try:
            drop = float(value)
        except ValueError:
            await message.answer("Пример: /set_drop 7")
            return
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(min_drop_percent=drop)
        await message.answer(f"Минимальное падение для алерта: {profile.min_drop_percent}%")

    @router.message(Command("set_results"))
    @admin_only
    async def set_results_cmd(message: Message, command: CommandObject):
        value = (command.args or "").strip()
        if not value.isdigit():
            await message.answer("Пример: /set_results 60")
            return
        limit = max(10, min(200, int(value)))
        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(max_results_per_source=limit)
        await message.answer(f"Лимит карточек на источник: {profile.max_results_per_source}")

    @router.message(Command("toggle_source"))
    @admin_only
    async def toggle_source_cmd(message: Message, command: CommandObject):
        parts = (command.args or "").split()
        if len(parts) != 2 or parts[1].lower() not in {"on", "off"}:
            await message.answer("Пример: /toggle_source travelata on")
            return
        name, state = parts[0], parts[1].lower() == "on"
        async with sessionmaker() as session:
            repo = Repo(session)
            await repo.set_source_state(name, state)
        await message.answer(f"Источник {name}: {'ON' if state else 'OFF'}")

    @router.message(Command("bot_status"))
    @admin_only
    async def bot_status_cmd(message: Message):
        await message.answer(
            f"Статус сервисов:\n"
            f"tour-hunter-bot: {get_service_status('tour-hunter-bot')}\n"
            f"avito-bot: {get_service_status('avito-bot')}"
        )

    @router.message(Command("bot_restart"))
    @admin_only
    async def bot_restart_cmd(message: Message, command: CommandObject):
        arg = (command.args or "").strip().lower()
        mapping = {
            "tour": "tour-hunter-bot",
            "avito": "avito-bot",
        }
        if arg not in mapping:
            await message.answer("Пример: /bot_restart tour")
            return
        service = mapping[arg]
        try:
            subprocess.run(["systemctl", "restart", service], check=True)
            await message.answer(f"Перезапущен: {service}")
        except Exception as e:
            await message.answer(f"Ошибка перезапуска {service}: {e}")

    @router.message(Command("bot_logs"))
    @admin_only
    async def bot_logs_cmd(message: Message, command: CommandObject):
        arg = (command.args or "").strip().lower()
        mapping = {
            "tour": "tour-hunter-bot",
            "avito": "avito-bot",
        }
        if arg not in mapping:
            await message.answer("Пример: /bot_logs tour")
            return
        service = mapping[arg]
        await message.answer(f"<pre>{get_service_logs(service)}</pre>")

    @router.callback_query(F.data == "admin_status")
    async def cb_admin_status(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        text = (
            f"Статус сервисов:\n"
            f"tour-hunter-bot: {get_service_status('tour-hunter-bot')}\n"
            f"avito-bot: {get_service_status('avito-bot')}"
        )
        await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data == "restart_tour")
    async def cb_restart_tour(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        try:
            subprocess.run(["systemctl", "restart", "tour-hunter-bot"], check=True)
            await callback.message.answer("Перезапущен: tour-hunter-bot")
        except Exception as e:
            await callback.message.answer(f"Ошибка перезапуска tour-hunter-bot: {e}")
        await callback.answer()

    @router.callback_query(F.data == "restart_avito")
    async def cb_restart_avito(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        try:
            subprocess.run(["systemctl", "restart", "avito-bot"], check=True)
            await callback.message.answer("Перезапущен: avito-bot")
        except Exception as e:
            await callback.message.answer(f"Ошибка перезапуска avito-bot: {e}")
        await callback.answer()

    @router.callback_query(F.data == "logs_tour")
    async def cb_logs_tour(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer(f"<pre>{get_service_logs('tour-hunter-bot')}</pre>")
        await callback.answer()

    @router.callback_query(F.data == "logs_avito")
    async def cb_logs_avito(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer(f"<pre>{get_service_logs('avito-bot')}</pre>")
        await callback.answer()

    @router.callback_query(F.data == "deploy_tour")
    async def cb_deploy_tour(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer("Тяну новый код из Git...")
        ok, output = await run_deploy(settings.repo_dir, settings.git_remote, settings.deploy_branch)
        if not ok:
            await callback.message.answer(f"Deploy упал:\n<pre>{output[-3500:]}</pre>")
            await callback.answer()
            return
        await callback.message.answer(f"Git обновлён:\n<pre>{output[-3500:]}</pre>\nПерезапускаюсь...")
        await callback.answer()
        await asyncio.sleep(1)
        os._exit(0)

    @router.message(Command("deploy"))
    @admin_only
    async def deploy_cmd(message: Message):
        await message.answer("Тяну новый код из Git...")
        ok, output = await run_deploy(settings.repo_dir, settings.git_remote, settings.deploy_branch)
        if not ok:
            await message.answer(f"Deploy упал:\n<pre>{output[-3500:]}</pre>")
            return
        await message.answer(f"Git обновлён:\n<pre>{output[-3500:]}</pre>\nПерезапускаюсь...")
        await asyncio.sleep(1)
        os._exit(0)

    return router
