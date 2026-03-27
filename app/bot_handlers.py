from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
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

    def main_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Статус", callback_data="menu_status"),
                    InlineKeyboardButton(text="🔍 Сканировать", callback_data="menu_scan"),
                ],
                [
                    InlineKeyboardButton(text="🏆 Лучшие туры", callback_data="menu_top"),
                    InlineKeyboardButton(text="🕘 История", callback_data="menu_history"),
                ],
                [
                    InlineKeyboardButton(text="⚙️ Фильтры", callback_data="menu_filters"),
                    InlineKeyboardButton(text="🧩 Источники", callback_data="menu_sources"),
                ],
                [
                    InlineKeyboardButton(text="🛠 Админ", callback_data="menu_admin"),
                ],
            ]
        )

    def filters_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="💰 50k", callback_data="set_budget_50000"),
                    InlineKeyboardButton(text="💰 60k", callback_data="set_budget_60000"),
                    InlineKeyboardButton(text="💰 80k", callback_data="set_budget_80000"),
                ],
                [
                    InlineKeyboardButton(text="🌙 3-5", callback_data="set_nights_3_5"),
                    InlineKeyboardButton(text="🌙 5-7", callback_data="set_nights_5_7"),
                    InlineKeyboardButton(text="🌙 7-10", callback_data="set_nights_7_10"),
                ],
                [
                    InlineKeyboardButton(text="👤 1 взрослый", callback_data="set_adults_1"),
                    InlineKeyboardButton(text="👥 2 взрослых", callback_data="set_adults_2"),
                ],
                [
                    InlineKeyboardButton(text="🌍 Дубай", callback_data="set_destination_dubai"),
                    InlineKeyboardButton(text="✈️ Москва", callback_data="set_city_moscow"),
                ],
                [
                    InlineKeyboardButton(text="📉 Порог 5%", callback_data="set_drop_5"),
                    InlineKeyboardButton(text="📉 Порог 7%", callback_data="set_drop_7"),
                    InlineKeyboardButton(text="📉 Порог 10%", callback_data="set_drop_10"),
                ],
                [
                    InlineKeyboardButton(text="📦 30", callback_data="set_results_30"),
                    InlineKeyboardButton(text="📦 60", callback_data="set_results_60"),
                    InlineKeyboardButton(text="📦 100", callback_data="set_results_100"),
                ],
                [
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main"),
                ],
            ]
        )

    def admin_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📡 Статус сервисов", callback_data="admin_status"),
                ],
                [
                    InlineKeyboardButton(text="🔄 Перезапуск tour", callback_data="restart_tour"),
                    InlineKeyboardButton(text="🔄 Перезапуск avito", callback_data="restart_avito"),
                ],
                [
                    InlineKeyboardButton(text="📜 Логи tour", callback_data="logs_tour"),
                    InlineKeyboardButton(text="📜 Логи avito", callback_data="logs_avito"),
                ],
                [
                    InlineKeyboardButton(text="🚀 Deploy", callback_data="deploy_tour"),
                ],
                [
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main"),
                ],
            ]
        )

    async def render_status_text() -> str:
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
            f"Мин. падение цены: {profile.min_drop_percent}%",
            f"Лимит карточек на источник: {profile.max_results_per_source}",
            f"Источников: {len(sources)}",
            f"Сделок в истории: {stats['deals_total']}",
            f"Уникальных агрегатов: {stats['aggregates_total']}",
            f"Отправленных алертов: {stats['alerts_total']}",
            "",
            "<b>Источники</b>",
        ]
        for src in sources:
            enabled = source_states.get(src.name, src.enabled)
            lines.append(f"• {src.name}: {'ON' if enabled else 'OFF'}")
        return "\n".join(lines)

    async def render_top_deals_text() -> str:
        async with sessionmaker() as session:
            repo = Repo(session)
            items = await repo.get_top_deals(limit=12)

        if not items:
            return "Пока пусто."

        lines = ["<b>Лучшие предложения в базе</b>"]
        for item in items:
            lines.append(
                f"\n• <b>{item.hotel_name}</b>\n"
                f"Источник: {item.source}\n"
                f"Мин: {item.min_price} ₽ | Сейчас: {item.last_price} ₽\n"
                f"Ночей: {item.nights or '-'} | Вылет: {item.departure_date or '-'}\n"
                f"Ссылка: {item.last_link or '-'}"
            )
        return "\n".join(lines)

    async def render_history_text() -> str:
        async with sessionmaker() as session:
            repo = Repo(session)
            items = await repo.get_recent_history(limit=15)

        if not items:
            return "История пока пустая."

        lines = ["<b>Последние изменения</b>"]
        for item in items:
            lines.append(
                f"• {item.created_at:%d.%m %H:%M} | {item.source} | {item.hotel_name} | {item.price} ₽"
            )
        return "\n".join(lines)

    async def render_sources_text() -> str:
        async with sessionmaker() as session:
            repo = Repo(session)
            states = await repo.get_source_states()

        items = load_sources(str(settings.sources_file))
        lines = ["<b>Источники</b>"]
        for item in items:
            enabled = states.get(item.name, item.enabled)
            lines.append(
                f"• {item.name} | {'ON' if enabled else 'OFF'} | playwright={'yes' if item.use_playwright else 'no'}"
            )
            lines.append(f"  {item.search_url}")
        return "\n".join(lines)

    async def update_profile_and_answer(
        callback: CallbackQuery,
        **kwargs,
    ) -> None:
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return

        async with sessionmaker() as session:
            repo = Repo(session)
            profile = await repo.update_profile(**kwargs)

        await callback.message.answer(
            "✅ Обновлено:\n"
            f"Маршрут: {profile.departure_city} → {profile.destination}\n"
            f"Бюджет: {profile.budget} ₽\n"
            f"Ночей: {profile.nights_min}-{profile.nights_max}\n"
            f"Взрослых: {profile.adults}, детей: {profile.children}\n"
            f"Мин. падение: {profile.min_drop_percent}%\n"
            f"Лимит: {profile.max_results_per_source}",
            reply_markup=filters_menu(),
        )
        await callback.answer()

    def get_service_status(service: str) -> str:
        try:
            return subprocess.check_output(
                ["systemctl", "is-active", service],
                stderr=subprocess.STDOUT,
            ).decode().strip()
        except Exception:
            return "unknown"

    def get_service_logs(service: str, lines: int = 20) -> str:
        try:
            logs = subprocess.check_output(
                ["journalctl", "-u", service, "-n", str(lines), "--no-pager"],
                stderr=subprocess.STDOUT,
            ).decode()
            return logs[-3500:]
        except Exception as e:
            return f"Ошибка чтения логов {service}: {e}"

    @router.message(Command("start"))
    @admin_only
    async def start_cmd(message: Message):
        await message.answer(
            "Готово. Теперь можно управлять ботом кнопками.",
            reply_markup=main_menu(),
        )

    @router.message(Command("menu"))
    @admin_only
    async def menu_cmd(message: Message):
        await message.answer("Главное меню:", reply_markup=main_menu())

    @router.message(Command("admin"))
    @admin_only
    async def admin_panel(message: Message):
        await message.answer("Админ панель:", reply_markup=admin_menu())

    @router.message(Command("status"))
    @admin_only
    async def status_cmd(message: Message):
        await message.answer(await render_status_text())

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
        await message.answer(await render_top_deals_text(), disable_web_page_preview=True)

    @router.message(Command("history"))
    @admin_only
    async def history_cmd(message: Message):
        await message.answer(await render_history_text())

    @router.message(Command("sources"))
    @admin_only
    async def sources_cmd(message: Message):
        await message.answer(await render_sources_text(), disable_web_page_preview=True)

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

    @router.callback_query(F.data == "back_main")
    async def cb_back_main(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer("Главное меню:", reply_markup=main_menu())
        await callback.answer()

    @router.callback_query(F.data == "menu_status")
    async def cb_menu_status(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer(await render_status_text())
        await callback.answer()

    @router.callback_query(F.data == "menu_scan")
    async def cb_menu_scan(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer("Запускаю проверку...")
        stats = await engine.run_once()
        await callback.message.answer(
            f"Готово. Источников ок: {stats.sources_ok}, ошибок: {stats.sources_failed}, "
            f"увидел туров: {stats.deals_seen}, сохранил: {stats.deals_saved}, алертов: {stats.alerts_sent}"
        )
        await callback.answer()

    @router.callback_query(F.data == "menu_top")
    async def cb_menu_top(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer(await render_top_deals_text(), disable_web_page_preview=True)
        await callback.answer()

    @router.callback_query(F.data == "menu_history")
    async def cb_menu_history(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer(await render_history_text())
        await callback.answer()

    @router.callback_query(F.data == "menu_sources")
    async def cb_menu_sources(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer(await render_sources_text(), disable_web_page_preview=True)
        await callback.answer()

    @router.callback_query(F.data == "menu_filters")
    async def cb_menu_filters(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer("Фильтры:", reply_markup=filters_menu())
        await callback.answer()

    @router.callback_query(F.data == "menu_admin")
    async def cb_menu_admin(callback: CallbackQuery):
        if not is_admin_callback(callback):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer("Админ панель:", reply_markup=admin_menu())
        await callback.answer()

    @router.callback_query(F.data.startswith("set_budget_"))
    async def cb_set_budget(callback: CallbackQuery):
        value = int(callback.data.split("_")[-1])
        await update_profile_and_answer(callback, budget=value)

    @router.callback_query(F.data.startswith("set_nights_"))
    async def cb_set_nights(callback: CallbackQuery):
        parts = callback.data.split("_")
        min_n = int(parts[-2])
        max_n = int(parts[-1])
        await update_profile_and_answer(callback, nights_min=min_n, nights_max=max_n)

    @router.callback_query(F.data.startswith("set_adults_"))
    async def cb_set_adults(callback: CallbackQuery):
        value = int(callback.data.split("_")[-1])
        await update_profile_and_answer(callback, adults=value)

    @router.callback_query(F.data == "set_destination_dubai")
    async def cb_set_destination_dubai(callback: CallbackQuery):
        await update_profile_and_answer(callback, destination="Дубай")

    @router.callback_query(F.data == "set_city_moscow")
    async def cb_set_city_moscow(callback: CallbackQuery):
        await update_profile_and_answer(callback, departure_city="Москва")

    @router.callback_query(F.data.startswith("set_drop_"))
    async def cb_set_drop(callback: CallbackQuery):
        value = float(callback.data.split("_")[-1])
        await update_profile_and_answer(callback, min_drop_percent=value)

    @router.callback_query(F.data.startswith("set_results_"))
    async def cb_set_results(callback: CallbackQuery):
        value = int(callback.data.split("_")[-1])
        await update_profile_and_answer(callback, max_results_per_source=value)

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

    return router
