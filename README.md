test deploy FINAL
# Tour Hunter Bot

Мощный Telegram-бот для поиска самых дешёвых и горящих туров с запуском на сервере.

Что умеет:
- мониторить несколько источников;
- хранить историю цен в SQLite;
- считать «аномально дешёвые» туры относительно предыдущих цен;
- отправлять только подходящие предложения в Telegram;
- управляться с телефона через Telegram-команды;
- подтягивать новый код из GitHub и перезапускаться через `/deploy`;
- работать как systemd-сервис на Ubuntu.

## Как менять код с телефона

Самая удобная схема:
1. Загружаешь этот проект в GitHub.
2. На телефоне открываешь GitHub и редактируешь файлы прямо там.
3. Коммитишь изменения.
4. В Telegram отправляешь боту `/deploy`.
5. Бот делает `git pull` и сам завершает процесс.
6. systemd автоматически поднимает его уже на новом коде.

## Что важно понимать

Этот проект уже готов под серверную архитектуру, но у тур-сайтов часто меняется вёрстка и часть сайтов рендерится JavaScript.
Поэтому в проекте сделан **адаптерный** подход:
- можно использовать обычный HTML-парсинг;
- можно включить Playwright для тяжёлых сайтов;
- селекторы и URL вынесены в `data/sources.yaml`, чтобы быстро править их даже с телефона.

## Быстрый старт на Ubuntu 22.04/24.04

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
cd /opt
sudo git clone YOUR_REPO_URL tour-hunter-bot
cd /opt/tour-hunter-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
nano .env
```

Заполни минимум:
- `BOT_TOKEN`
- `ADMIN_IDS`
- `REPO_DIR=/opt/tour-hunter-bot`

Запуск вручную:
```bash
source .venv/bin/activate
python -m app.main
```

## Установка как сервис

```bash
sudo cp deploy/tour-hunter-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tour-hunter-bot
sudo systemctl status tour-hunter-bot
```

## Команды бота

- `/start` — показать меню
- `/status` — состояние системы
- `/scan_now` — немедленный запуск проверки
- `/sources` — показать источники
- `/set_budget 60000`
- `/set_nights 3 10`
- `/set_dates 2026-04-01 2026-04-10`
- `/set_city Москва`
- `/set_destination Дубай`
- `/set_adults 1`
- `/set_children 0`
- `/toggle_source leveltravel on`
- `/deploy` — подтянуть новый код с GitHub и перезапустить процесс
- `/reload_sources` — перечитать `sources.yaml`
- `/top_deals` — лучшие предложения из базы
- `/history` — последние изменения цен

## Где настраивать источники

Файл: `data/sources.yaml`

Там можно:
- добавлять новые сайты;
- менять URL;
- менять CSS-селекторы;
- включать/выключать Playwright.

## Логика «горящих» туров

Тур считается сильным кандидатом, если выполнено хотя бы одно:
- цена ниже заданного бюджета;
- цена упала на заданный процент от последней известной;
- цена входит в нижний перцентиль по базе;
- до вылета мало времени;
- найден новый редкий дешёвый вариант.

## Автоперезапуск после `/deploy`

Команда `/deploy`:
- делает `git fetch`;
- `git reset --hard origin/main`;
- пишет сообщение в Telegram;
- завершает процесс с кодом 0.

Так как сервис настроен с `Restart=always`, systemd сразу поднимет обновлённую версию.

## Структура

- `app/main.py` — входная точка
- `app/config.py` — конфиг
- `app/db.py` — база
- `app/models.py` — модели
- `app/schemas.py` — dataclass-структуры
- `app/repositories.py` — работа с БД
- `app/deals.py` — логика оценки выгодности
- `app/deployer.py` — git deploy
- `app/scheduler.py` — APScheduler
- `app/bot_handlers.py` — команды Telegram
- `app/sources/` — адаптеры сайтов
- `data/sources.yaml` — список сайтов и селекторы
- `deploy/tour-hunter-bot.service` — systemd unit

