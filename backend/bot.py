import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8286352882:AAFuO-HqBFrnA4gui9EUXsq2GTq6uyAS14U")
API_URL = os.getenv("API_URL", "http://localhost:8000")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # Telegram ID админа для уведомлений
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://trf404.digital")  # URL сайта для Web App

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

# Авторизованные пользователи: telegram_id -> user_data
authorized_users = {}


class States(StatesGroup):
    waiting_key = State()
    entering_log_number = State()
    entering_balance = State()
    entering_profit = State()
    entering_owner = State()
    entering_install_date = State()
    entering_check_date = State()
    selecting_tag = State()
    entering_comment = State()
    selecting_worker = State()


TAG_LABELS = {
    "fat": "🔥 Жир",
    "poor": "💸 Нищий",
    "medium": "📊 Средний",
    "salary": "💰 Есть ЗП"
}


def main_kb(is_admin=False, user_token=None):
    """Клавиатура меню с Web App. Админ может добавлять логи, воркеры - нет"""
    # Web App кнопка с токеном для авторизации
    webapp_url = WEB_APP_URL
    if user_token:
        webapp_url = f"{WEB_APP_URL}?token={user_token}"
    
    webapp_btn = KeyboardButton(text="🌐 Открыть сайт", web_app=WebAppInfo(url=webapp_url))
    
    if is_admin:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="➕ Добавить лог"), KeyboardButton(text="📋 Все логи")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🏆 Топ недели")],
            [KeyboardButton(text="🔔 Проверки"), KeyboardButton(text="🔍 Поиск")],
            [KeyboardButton(text="🎯 Прогресс"), webapp_btn],
            [KeyboardButton(text="🚪 Выйти")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📋 Мои логи"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🏆 Топ недели"), KeyboardButton(text="🔔 Проверки")],
            [KeyboardButton(text="🎯 Мой прогресс"), webapp_btn],
            [KeyboardButton(text="🚪 Выйти")]
        ], resize_keyboard=True)


def tag_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Жир", callback_data="tag_fat")],
        [InlineKeyboardButton(text="💸 Нищий", callback_data="tag_poor")],
        [InlineKeyboardButton(text="📊 Средний", callback_data="tag_medium")],
        [InlineKeyboardButton(text="💰 Есть ЗП", callback_data="tag_salary")],
    ])


def skip_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip")]
    ])


def log_actions_kb(log_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Баланс", callback_data=f"eb_{log_id}"),
         InlineKeyboardButton(text="🏷 Тег", callback_data=f"et_{log_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{log_id}")]
    ])


def workers_kb(workers):
    """Клавиатура выбора воркера"""
    btns = [[InlineKeyboardButton(text=f"👤 {w['name']}", callback_data=f"sw_{w['id']}")] for w in workers]
    return InlineKeyboardMarkup(inline_keyboard=btns)


async def api_req(method, endpoint, data=None, user_data=None):
    """API запрос для бота"""
    async with aiohttp.ClientSession() as s:
        url = f"{API_URL}{endpoint}"
        
        try:
            if method == "GET":
                params = data or {}
                # Для воркера фильтруем по worker_id, для админа - все логи
                if user_data and user_data.get("worker_id") and user_data.get("role") != "admin":
                    params["worker_id"] = user_data["worker_id"]
                async with s.get(url, params=params) as r:
                    return await r.json() if r.status == 200 else None
            elif method == "POST":
                async with s.post(url, json=data) as r:
                    return await r.json() if r.status in [200, 201] else None
            elif method == "PUT":
                async with s.put(url, json=data) as r:
                    return await r.json() if r.status == 200 else None
            elif method == "DELETE":
                async with s.delete(url) as r:
                    return await r.json() if r.status == 200 else None
        except Exception as e:
            logging.error(f"API Error: {e}")
            return None


async def check_auth(message: types.Message) -> dict:
    """Проверить авторизацию пользователя"""
    user_id = message.from_user.id
    return authorized_users.get(user_id)


def get_user(message: types.Message) -> dict:
    return authorized_users.get(message.from_user.id)


# ========== START & AUTH ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if user_id in authorized_users:
        user = authorized_users[user_id]
        is_admin = user.get('role') == 'admin'
        user_token = user.get('token')
        await message.answer(
            f"👋 С возвращением, *{user.get('worker_name', user.get('username'))}*!",
            reply_markup=main_kb(is_admin, user_token),
            parse_mode="Markdown"
        )
        return
    
    await state.set_state(States.waiting_key)
    await message.answer(
        "🔐 *Авторизация*\n\n"
        "Введите ваш ключ доступа:",
        parse_mode="Markdown"
    )


@dp.message(States.waiting_key)
async def process_key(message: types.Message, state: FSMContext):
    key = message.text.strip()
    
    # Проверяем ключ через API
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(f"{API_URL}/api/bot/auth", json={"key": key}) as r:
                data = await r.json()
                
                if data.get("ok"):
                    user = data["user"]
                    authorized_users[message.from_user.id] = user
                    
                    await state.clear()
                    is_admin = user.get('role') == 'admin'
                    user_token = user.get('token')
                    await message.answer(
                        f"✅ *Авторизация успешна!*\n\n"
                        f"Добро пожаловать, *{user.get('worker_name', user.get('username'))}*!",
                        reply_markup=main_kb(is_admin, user_token),
                        parse_mode="Markdown"
                    )
                else:
                    await message.answer("❌ Неверный ключ. Попробуйте снова:")
        except Exception as e:
            logging.error(f"Auth error: {e}")
            await message.answer("❌ Ошибка сервера. Попробуйте позже.")


@dp.message(F.text == "🚪 Выйти")
async def logout(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in authorized_users:
        del authorized_users[user_id]
    await state.clear()
    await message.answer(
        "👋 Вы вышли из системы.\n\nДля входа отправьте /start",
        reply_markup=types.ReplyKeyboardRemove()
    )


# ========== ПРОВЕРКА АВТОРИЗАЦИИ ==========

async def require_auth(message: types.Message) -> dict:
    """Проверка авторизации, возвращает user или None"""
    user = get_user(message)
    if not user:
        await message.answer(
            "🔐 Вы не авторизованы.\n\nОтправьте /start для входа."
        )
        return None
    return user


# ========== ДОБАВЛЕНИЕ ЛОГА ==========

@dp.message(F.text == "➕ Добавить лог")
async def add_log_start(msg: types.Message, state: FSMContext):
    user = await require_auth(msg)
    if not user:
        return
    
    # Только админ может добавлять логи
    if user.get('role') != 'admin':
        await msg.answer("❌ Только администратор может добавлять логи.")
        return
    
    await state.set_state(States.entering_log_number)
    await msg.answer("🔢 *Введите номер лога:*", parse_mode="Markdown")


@dp.message(States.entering_log_number)
async def enter_log_number(msg: types.Message, state: FSMContext):
    await state.update_data(log_number=msg.text)
    await state.set_state(States.entering_balance)
    await msg.answer("💰 *Баланс* (400к, 1.5кк):", parse_mode="Markdown")


@dp.message(States.entering_balance)
async def enter_balance(msg: types.Message, state: FSMContext):
    await state.update_data(balance=msg.text)
    await state.set_state(States.entering_profit)
    await msg.answer("💵 *Профит* (50к, 100к):", reply_markup=skip_kb(), parse_mode="Markdown")


@dp.callback_query(F.data == "skip", States.entering_profit)
async def skip_profit(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(profit=None)
    await state.set_state(States.entering_owner)
    await cb.message.edit_text("👤 *Принадлежащий* (тег владельца):", reply_markup=skip_kb(), parse_mode="Markdown")


@dp.message(States.entering_profit)
async def enter_profit(msg: types.Message, state: FSMContext):
    await state.update_data(profit=msg.text)
    await state.set_state(States.entering_owner)
    await msg.answer("👤 *Принадлежащий* (тег владельца):", reply_markup=skip_kb(), parse_mode="Markdown")


@dp.callback_query(F.data == "skip", States.entering_owner)
async def skip_owner(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(owner=None)
    await state.set_state(States.entering_install_date)
    await cb.message.edit_text("📅 *Дата установки* (3-5-7-25):", parse_mode="Markdown")


@dp.message(States.entering_owner)
async def enter_owner(msg: types.Message, state: FSMContext):
    await state.update_data(owner=msg.text)
    await state.set_state(States.entering_install_date)
    await msg.answer("📅 *Дата установки* (3-5-7-25):", parse_mode="Markdown")


@dp.message(States.entering_install_date)
async def enter_install_date(msg: types.Message, state: FSMContext):
    await state.update_data(install_date=msg.text)
    await state.set_state(States.entering_check_date)
    await msg.answer("🔔 *Дата проверки* (10-5-7-25):", reply_markup=skip_kb(), parse_mode="Markdown")


@dp.callback_query(F.data == "skip", States.entering_check_date)
async def skip_check_date(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(check_date="")  # Пустая строка вместо None
    await state.set_state(States.selecting_tag)
    await cb.message.edit_text("🏷 *Выберите тег:*", reply_markup=tag_kb(), parse_mode="Markdown")


@dp.message(States.entering_check_date)
async def enter_check_date(msg: types.Message, state: FSMContext):
    await state.update_data(check_date=msg.text)
    await state.set_state(States.selecting_tag)
    await msg.answer("🏷 *Выберите тег:*", reply_markup=tag_kb(), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("tag_"), States.selecting_tag)
async def select_tag(cb: types.CallbackQuery, state: FSMContext):
    tag = cb.data.replace("tag_", "")
    await state.update_data(tag=tag)
    await state.set_state(States.entering_comment)
    await cb.message.edit_text("💬 *Комментарий:*", reply_markup=skip_kb(), parse_mode="Markdown")


@dp.callback_query(F.data == "skip", States.entering_comment)
async def skip_comment(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(comment=None)
    await show_worker_selection(cb.message, state, edit=True)


@dp.message(States.entering_comment)
async def enter_comment(msg: types.Message, state: FSMContext):
    await state.update_data(comment=msg.text)
    await show_worker_selection(msg, state, edit=False)


async def show_worker_selection(msg, state: FSMContext, edit: bool = False):
    """Показать выбор воркера"""
    # Получаем список воркеров
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API_URL}/api/bot/workers") as r:
            if r.status == 200:
                workers = await r.json()
            else:
                workers = []
    
    if not workers:
        txt = "❌ Нет доступных воркеров"
        if edit:
            await msg.edit_text(txt)
        else:
            await msg.answer(txt)
        await state.clear()
        return
    
    await state.set_state(States.selecting_worker)
    txt = "👤 *Выберите воркера:*"
    kb = workers_kb(workers)
    
    if edit:
        await msg.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
    else:
        await msg.answer(txt, reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("sw_"), States.selecting_worker)
async def worker_selected(cb: types.CallbackQuery, state: FSMContext):
    worker_id = int(cb.data.split("_")[1])
    await state.update_data(worker_id=worker_id)
    
    data = await state.get_data()
    await save_log_final(cb.message, state, data)


async def notify_admin_new_log(log_data, worker_name, creator_name):
    """Уведомление админа о новом логе"""
    if not ADMIN_CHAT_ID:
        return
    
    try:
        tag = TAG_LABELS.get(log_data.get("tag"), log_data.get("tag"))
        txt = (f"📥 *Новый лог!*\n\n"
               f"👤 Создал: {creator_name}\n"
               f"📌 Воркер: {worker_name}\n"
               f"🔢 №{log_data.get('log_number')}\n"
               f"💰 {log_data.get('balance')}\n"
               f"🏷 {tag}")
        await bot.send_message(int(ADMIN_CHAT_ID), txt, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка уведомления админа: {e}")


async def save_log_final(msg, state, data):
    """Финальное сохранение лога после выбора воркера"""
    
    # Убедимся что check_date не пустая строка
    if not data.get("check_date"):
        data["check_date"] = None
    
    logging.info(f"Creating log with data: {data}")
    
    r = await api_req("POST", "/api/bot/logs", data)
    
    if r:
        tag = TAG_LABELS.get(data.get("tag"), data.get("tag"))
        # Имя воркера из ответа API
        worker_name = r.get("worker", {}).get("name", "???") if isinstance(r, dict) else "???"
        owner_text = f"@{data.get('owner')}" if data.get('owner') else "—"
        profit_text = f"+{data.get('profit')}" if data.get('profit') else "—"
        txt = (f"✅ *Лог добавлен!*\n\n"
               f"👤 Воркер: {worker_name}\n"
               f"🔢 №{data.get('log_number')}\n"
               f"💰 {data.get('balance')}\n"
               f"💵 Профит: {profit_text}\n"
               f"🏠 Владелец: {owner_text}\n"
               f"📅 Уст: {data.get('install_date')}\n"
               f"🔔 Пров: {data.get('check_date') or '—'}\n"
               f"🏷 {tag}\n"
               f"💬 {data.get('comment') or '—'}")
        await msg.edit_text(txt, parse_mode="Markdown")
        
        # Уведомляем админа
        creator_name = msg.chat.first_name or msg.chat.username or "Unknown"
        await notify_admin_new_log(data, worker_name, creator_name)
    else:
        await msg.edit_text("❌ Ошибка при сохранении")
    
    await state.clear()


# ========== МОИ ЛОГИ ==========

@dp.message(F.text.in_(["📋 Мои логи", "📋 Все логи"]))
async def show_logs(msg: types.Message):
    user = await require_auth(msg)
    if not user:
        return
    
    logs = await api_req("GET", "/api/bot/logs", {"limit": 15}, user)
    
    if not logs:
        await msg.answer("📭 Логов нет")
        return
    
    await msg.answer(f"📋 *Мои логи ({len(logs)}):*", parse_mode="Markdown")
    
    for log in logs:
        tag = TAG_LABELS.get(log.get("tag"), log.get("tag"))
        owner = f" | @{log['owner']}" if log.get('owner') else ""
        txt = (f"🔢 №{log['log_number']}{owner}\n"
               f"├ 💰 {log['balance']}\n"
               f"├ 📅 {log['install_date']}\n"
               f"├ 🔔 {log.get('check_date') or '—'}\n"
               f"└ 🏷 {tag}")
        await msg.answer(txt, reply_markup=log_actions_kb(log['id']), parse_mode="Markdown")


# ========== СТАТИСТИКА ==========

@dp.message(F.text == "📊 Статистика")
async def show_stats(msg: types.Message):
    user = await require_auth(msg)
    if not user:
        return
    
    # Получаем логи пользователя для подсчета
    logs = await api_req("GET", "/api/bot/logs", {"limit": 1000}, user) or []
    
    by_tag = {"fat": 0, "poor": 0, "medium": 0, "salary": 0}
    for log in logs:
        tag = log.get("tag")
        if tag in by_tag:
            by_tag[tag] += 1
    
    # Считаем профит
    total_profit = 0
    for log in logs:
        if log.get('profit'):
            try:
                p = log['profit'].lower().replace(' ', '')
                if 'кк' in p:
                    total_profit += float(p.replace('кк', '')) * 1000
                elif 'к' in p:
                    total_profit += float(p.replace('к', ''))
            except:
                pass
    
    profit_str = f"{total_profit/1000:.1f}кк" if total_profit >= 1000 else f"{total_profit:.0f}к"
    
    txt = (f"📊 *Моя статистика*\n\n"
           f"📝 Всего логов: *{len(logs)}*\n"
           f"💰 Общий профит: *{profit_str}*\n\n"
           f"*По тегам:*\n"
           f"  🔥 Жир: {by_tag.get('fat', 0)}\n"
           f"  💸 Нищий: {by_tag.get('poor', 0)}\n"
           f"  📊 Средний: {by_tag.get('medium', 0)}\n"
           f"  💰 Есть ЗП: {by_tag.get('salary', 0)}")
    
    await msg.answer(txt, parse_mode="Markdown")


# ========== ТОП НЕДЕЛИ ==========

@dp.message(F.text == "🏆 Топ недели")
async def show_top(msg: types.Message):
    user = await require_auth(msg)
    if not user:
        return
    
    data = await api_req("GET", "/api/bot/workers")
    if not data:
        await msg.answer("❌ Не удалось загрузить данные")
        return
    
    txt = "🏆 *Топ воркеров за неделю*\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    
    # Сортируем по количеству логов (logs_count)
    sorted_workers = sorted(data, key=lambda x: x.get('logs_count', 0), reverse=True)
    
    for i, w in enumerate(sorted_workers[:8]):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        txt += f"{medal} *{w['name']}* — {w.get('logs_count', 0)} логов\n"
    
    await msg.answer(txt, parse_mode="Markdown")


# ========== МОЙ ПРОГРЕСС ==========

@dp.message(F.text == "🎯 Мой прогресс")
async def show_progress(msg: types.Message):
    user = await require_auth(msg)
    if not user:
        return
    
    logs = await api_req("GET", "/api/bot/logs", {"limit": 1000}, user) or []
    
    # Считаем за сегодня и неделю
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    
    today_logs = sum(1 for l in logs if l.get('created_at', '').startswith(str(today)))
    week_logs = sum(1 for l in logs if l.get('created_at', '')[:10] >= str(week_start))
    
    daily_goal = 3
    weekly_goal = 15
    
    # Прогресс-бары
    daily_progress = min(today_logs / daily_goal, 1)
    weekly_progress = min(week_logs / weekly_goal, 1)
    
    def progress_bar(progress):
        filled = int(progress * 10)
        return "█" * filled + "░" * (10 - filled)
    
    daily_emoji = "✅" if today_logs >= daily_goal else "⏳"
    weekly_emoji = "✅" if week_logs >= weekly_goal else "⏳"
    
    txt = (f"🎯 *Мой прогресс*\n\n"
           f"*Сегодня:* {daily_emoji}\n"
           f"`{progress_bar(daily_progress)}` {today_logs}/{daily_goal}\n\n"
           f"*За неделю:* {weekly_emoji}\n"
           f"`{progress_bar(weekly_progress)}` {week_logs}/{weekly_goal}\n\n"
           f"📈 Всего логов: *{len(logs)}*")
    
    await msg.answer(txt, parse_mode="Markdown")


# ========== ПРОВЕРКИ ==========

@dp.message(F.text.in_(["🔔 Проверки", "🔔 Проверки сегодня"]))
async def show_today(msg: types.Message):
    user = await require_auth(msg)
    if not user:
        return
    
    logs = await api_req("GET", "/api/bot/reminders/today", None, user)
    
    if not logs:
        await msg.answer("✨ На сегодня проверок нет!")
        return
    
    await msg.answer(f"🔔 *Проверки сегодня ({len(logs)}):*", parse_mode="Markdown")
    
    for log in logs:
        tag = TAG_LABELS.get(log.get("tag"), log.get("tag"))
        owner = f" | @{log['owner']}" if log.get('owner') else ""
        txt = (f"🔢 №{log['log_number']}{owner}\n"
               f"├ 💰 {log['balance']}\n"
               f"└ 🏷 {tag}")
        await msg.answer(txt, reply_markup=log_actions_kb(log['id']), parse_mode="Markdown")


# ========== ПОИСК ==========

@dp.message(F.text == "🔍 Поиск")
async def search_prompt(msg: types.Message):
    user = await require_auth(msg)
    if not user:
        return
    await msg.answer("🔍 Введите пин или номер лога:")


@dp.message(StateFilter(None))
async def search(msg: types.Message):
    if msg.text.startswith("/") or msg.text in ["➕ Добавить лог", "📋 Мои логи", "📊 Статистика", "🔔 Проверки сегодня", "🔍 Поиск", "🚪 Выйти"]:
        return
    
    user = get_user(msg)
    if not user:
        return
    
    logs = await api_req("GET", "/api/bot/logs", {"search": msg.text}, user)
    
    if not logs:
        await msg.answer("🔍 Не найдено")
        return
    
    await msg.answer(f"🔍 *Найдено: {len(logs)}*", parse_mode="Markdown")
    
    for log in logs[:10]:
        tag = TAG_LABELS.get(log.get("tag"), log.get("tag"))
        owner = f" | @{log['owner']}" if log.get('owner') else ""
        txt = f"🔢 №{log['log_number']}{owner} | 🏷 {tag}"
        await msg.answer(txt, reply_markup=log_actions_kb(log['id']), parse_mode="Markdown")


# ========== ДЕЙСТВИЯ С ЛОГАМИ ==========

@dp.callback_query(F.data.startswith("del_"))
async def delete_log_confirm(cb: types.CallbackQuery):
    lid = int(cb.data.split("_")[1])
    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Удалить", callback_data=f"delc_{lid}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")]
    ]))


@dp.callback_query(F.data == "cdel")
async def cancel_delete(cb: types.CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith("delc_"))
async def delete_log(cb: types.CallbackQuery):
    lid = int(cb.data.split("_")[1])
    if await api_req("DELETE", f"/api/bot/logs/{lid}"):
        await cb.message.edit_text("🗑 Удалено")
    else:
        await cb.answer("❌ Ошибка")


@dp.callback_query(F.data.startswith("et_"))
async def edit_tag(cb: types.CallbackQuery, state: FSMContext):
    lid = int(cb.data.split("_")[1])
    await state.update_data(edit_log_id=lid)
    await cb.message.edit_text("🏷 *Новый тег:*", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Жир", callback_data="st_fat")],
        [InlineKeyboardButton(text="💸 Нищий", callback_data="st_poor")],
        [InlineKeyboardButton(text="📊 Средний", callback_data="st_medium")],
        [InlineKeyboardButton(text="💰 Есть ЗП", callback_data="st_salary")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")]
    ]), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("st_"))
async def set_tag(cb: types.CallbackQuery, state: FSMContext):
    tag = cb.data.split("_")[1]
    data = await state.get_data()
    lid = data.get("edit_log_id")
    if lid and await api_req("PUT", f"/api/bot/logs/{lid}", {"tag": tag}):
        await cb.message.edit_text(f"✅ Тег: {TAG_LABELS.get(tag, tag)}")
    else:
        await cb.message.edit_text("❌ Ошибка")
    await state.clear()


from datetime import datetime, timedelta

# ========== УТРЕННИЕ УВЕДОМЛЕНИЯ ==========

async def send_morning_notifications():
    """Отправить утренние уведомления о проверках"""
    logging.info("📬 Отправка утренних уведомлений...")
    
    for telegram_id, user in authorized_users.items():
        try:
            # Получаем проверки на сегодня
            logs = await api_req("GET", "/api/bot/reminders/today", None, user)
            
            if logs and len(logs) > 0:
                txt = f"🌅 *Доброе утро!*\n\n🔔 Сегодня {len(logs)} проверок:\n\n"
                for log in logs[:5]:
                    txt += f"• №{log['log_number']} — {log.get('balance', '—')}\n"
                if len(logs) > 5:
                    txt += f"\n...и ещё {len(logs) - 5}"
                txt += "\n\nУдачного дня! 💪"
                
                await bot.send_message(telegram_id, txt, parse_mode="Markdown")
                logging.info(f"✅ Уведомление отправлено {telegram_id}")
        except Exception as e:
            logging.error(f"Ошибка уведомления {telegram_id}: {e}")


async def send_evening_report():
    """Отправить вечерний отчёт"""
    logging.info("📊 Отправка вечерних отчётов...")
    
    for telegram_id, user in authorized_users.items():
        try:
            logs = await api_req("GET", "/api/bot/logs", {"limit": 1000}, user) or []
            
            # Подсчитываем логи за сегодня
            today = datetime.now().date()
            today_logs = [l for l in logs if l.get('created_at', '').startswith(str(today))]
            
            if len(today_logs) > 0 or len(logs) > 0:
                txt = (f"🌙 *Итоги дня*\n\n"
                       f"📝 Добавлено сегодня: *{len(today_logs)}*\n"
                       f"📊 Всего логов: *{len(logs)}*\n\n"
                       f"Отличная работа! 🎉")
                
                await bot.send_message(telegram_id, txt, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка вечернего отчёта {telegram_id}: {e}")


async def send_check_reminders():
    """Напоминания о проверках в течение дня"""
    logging.info("🔔 Проверка напоминаний о проверках...")
    
    for telegram_id, user in authorized_users.items():
        try:
            logs = await api_req("GET", "/api/bot/reminders/today", None, user)
            
            if logs and len(logs) > 0:
                txt = f"⏰ *Напоминание!*\n\nУ вас {len(logs)} логов на проверку сегодня:\n\n"
                for log in logs[:3]:
                    txt += f"• №{log['log_number']} — {log.get('balance', '—')}\n"
                if len(logs) > 3:
                    txt += f"\n...и ещё {len(logs) - 3}"
                
                await bot.send_message(telegram_id, txt, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка напоминания {telegram_id}: {e}")


async def send_backup_to_admin():
    """Отправка бэкапа БД админу"""
    if not ADMIN_CHAT_ID:
        logging.warning("ADMIN_CHAT_ID не установлен, бэкап не отправлен")
        return
    
    db_path = "logs_leads.db"
    if not os.path.exists(db_path):
        logging.error(f"Файл БД не найден: {db_path}")
        return
    
    try:
        from aiogram.types import FSInputFile
        backup_file = FSInputFile(db_path, filename=f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db")
        await bot.send_document(
            int(ADMIN_CHAT_ID),
            backup_file,
            caption=f"🗄️ *Автобэкап БД*\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
        logging.info("✅ Бэкап отправлен админу")
    except Exception as e:
        logging.error(f"Ошибка отправки бэкапа: {e}")


async def sync_geelark():
    """Автосинхронизация с Geelark"""
    logging.info("📱 Запуск автосинхронизации Geelark...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Проверяем включена ли автосинхронизация
            async with session.get(f"{API_URL}/api/geelark/settings") as resp:
                if resp.status != 200:
                    return
                settings = await resp.json()
                
                if not settings.get('configured') or not settings.get('auto_sync_enabled'):
                    logging.info("📱 Автосинхронизация Geelark отключена")
                    return
            
            # Выполняем синхронизацию
            async with session.post(f"{API_URL}/api/geelark/sync") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get('ok'):
                        imported = result.get('imported', 0)
                        if imported > 0:
                            logging.info(f"✅ Geelark: импортировано {imported} новых логов")
                            
                            # Уведомляем админа если были импортированы логи
                            if ADMIN_CHAT_ID and imported > 0:
                                try:
                                    await bot.send_message(
                                        int(ADMIN_CHAT_ID),
                                        f"📱 *Geelark Sync*\n\n"
                                        f"✅ Импортировано: *{imported}* логов\n"
                                        f"⏭️ Пропущено: {result.get('skipped', 0)}\n"
                                        f"📊 Всего в Geelark: {result.get('total_phones', '—')}",
                                        parse_mode="Markdown"
                                    )
                                except:
                                    pass
                        else:
                            logging.info("📱 Geelark: новых телефонов нет")
                    else:
                        logging.warning(f"⚠️ Geelark sync error: {result}")
                else:
                    logging.error(f"❌ Geelark sync failed: {resp.status}")
    except Exception as e:
        logging.error(f"❌ Ошибка синхронизации Geelark: {e}")


@dp.message(F.text == "/backup")
async def manual_backup(msg: types.Message):
    """Ручной бэкап (только админ)"""
    user = get_user(msg)
    if not user or user.get('role') != 'admin':
        await msg.answer("❌ Только для администратора")
        return
    
    await msg.answer("📦 Создаю бэкап...")
    
    db_path = "logs_leads.db"
    if not os.path.exists(db_path):
        await msg.answer("❌ Файл БД не найден")
        return
    
    try:
        from aiogram.types import FSInputFile
        backup_file = FSInputFile(db_path, filename=f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db")
        await msg.answer_document(
            backup_file,
            caption=f"🗄️ *Бэкап БД*\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")


async def scheduler():
    """Планировщик уведомлений"""
    geelark_last_sync = 0  # Время последней синхронизации Geelark
    
    while True:
        now = datetime.now()
        
        # Утренние уведомления в 9:00
        if now.hour == 9 and now.minute == 0:
            await send_morning_notifications()
        
        # Напоминание в 13:00
        if now.hour == 13 and now.minute == 0:
            await send_check_reminders()
        
        # Напоминание в 17:00
        if now.hour == 17 and now.minute == 0:
            await send_check_reminders()
        
        # Вечерние отчёты в 21:00
        if now.hour == 21 and now.minute == 0:
            await send_evening_report()
        
        # Автобэкап каждый день в 3:00
        if now.hour == 3 and now.minute == 0:
            await send_backup_to_admin()
        
        # Geelark автосинхронизация каждые 30 минут
        import time
        current_time = time.time()
        if current_time - geelark_last_sync >= 30 * 60:  # 30 минут
            await sync_geelark()
            geelark_last_sync = current_time
        
        # Ждём 60 секунд
        await asyncio.sleep(60)


async def main():
    logging.info("🤖 Бот запущен!")
    
    # Запускаем планировщик в фоне
    asyncio.create_task(scheduler())
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
