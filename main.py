import asyncio
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dotenv import load_dotenv

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import AuthKeyUnregistered, UserDeactivated, SessionPasswordNeeded

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8785831667:AAHuaDCl13BfdvzpijG21QEDuOjI9ruk2B0"
API_ID = int(os.getenv("API_ID", "31799721"))
API_HASH = os.getenv("API_HASH", "eb2181220b3b8a0b6a7f93cd8075a559")

if not TOKEN:
    raise RuntimeError("Telegram bot token was not provided")

ADMIN_ID = int(os.getenv("ADMIN_ID", "8872934046"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003922108499"))

DB_PATH = os.getenv("DB_PATH", "data/shop.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path("sessions").mkdir(parents=True, exist_ok=True)
Path("sessions/season").mkdir(parents=True, exist_ok=True)

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
MSK = ZoneInfo("Europe/Moscow")

def is_admin(uid: int) -> bool: return uid == ADMIN_ID
def now_msk() -> str: return datetime.now(MSK).isoformat()

PREFIX_TO_ISO = {
    "1": "US", "7": "RU", "77": "KZ", "76": "KZ", "20": "EG", "27": "ZA",
    "30": "GR", "31": "NL", "32": "BE", "33": "FR", "34": "ES", "36": "HU",
    "39": "IT", "40": "RO", "41": "CH", "43": "AT", "44": "GB", "45": "DK",
    "46": "SE", "47": "NO", "48": "PL", "49": "DE", "51": "PE", "52": "MX",
    "53": "CU", "54": "AR", "55": "BR", "56": "CL", "57": "CO", "58": "VE",
    "60": "MY", "61": "AU", "62": "ID", "63": "PH", "64": "NZ", "65": "SG",
    "66": "TH", "81": "JP", "82": "KR", "84": "VN", "86": "CN", "90": "TR",
    "91": "IN", "92": "PK", "93": "AF", "94": "LK", "95": "MM", "98": "IR",
    "212": "MA", "213": "DZ", "216": "TN", "218": "LY", "220": "GM", "221": "SN",
    "233": "GH", "234": "NG", "237": "CM", "254": "KE", "255": "TZ", "256": "UG", "260": "ZM", "263": "ZW",
    "351": "PT", "352": "LU", "353": "IE", "354": "IS", "355": "AL", "358": "FI",
    "370": "LT", "371": "LV", "372": "EE", "373": "MD", "374": "AM", "375": "BY",
    "380": "UA", "381": "RS", "382": "ME", "385": "HR", "386": "SI", "387": "BA", "389": "MK",
    "420": "CZ", "421": "SK", "502": "GT", "503": "SV", "504": "HN", "505": "NI",
    "506": "CR", "507": "PA", "509": "HT", "591": "BO", "593": "EC", "595": "PY", "598": "UY",
    "852": "HK", "853": "MO", "855": "KH", "856": "LA", "880": "BD", "886": "TW",
    "960": "MV", "961": "LB", "962": "JO", "963": "SY", "964": "IQ", "965": "KW",
    "966": "SA", "967": "YE", "968": "OM", "971": "AE", "972": "IL", "973": "BH",
    "974": "QA", "975": "BT", "976": "MN", "977": "NP", "992": "TJ", "993": "TM",
    "994": "AZ", "995": "GE", "996": "KG", "998": "UZ"
}

FLAG_REGEX = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")

def iso_to_flag(iso_code: str) -> str:
    if not iso_code or len(iso_code) != 2:
        return "🌐 "
    iso_code = iso_code.upper()
    return chr(0x1F1E6 + ord(iso_code[0]) - 65) + chr(0x1F1E6 + ord(iso_code[1]) - 65) + " "

def extract_code_prefix(phone_or_name: str) -> str:
    digits = re.sub(r"\D", "", phone_or_name or "")
    if not digits:
        return "+1"
    for length in (3, 2, 1):
        if len(digits) >= length:
            pref = digits[:length]
            if pref in PREFIX_TO_ISO:
                return f"+{pref}"
    return f"+{digits[0]}" if digits else "+1"

def get_flag(text: str) -> str:
    if not text:
        return "📱 "
    if FLAG_REGEX.search(text):
        return ""
    code_pref = extract_code_prefix(text)
    clean_code = code_pref.replace("+", "")
    if clean_code in PREFIX_TO_ISO:
        return iso_to_flag(PREFIX_TO_ISO[clean_code])
    return "🌐 "
async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ("creator", "administrator", "member")
    except Exception:
        return False

async def db():
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn

async def one(conn, sql, params=()):
    cur = await conn.execute(sql, params)
    try: return await cur.fetchone()
    finally: await cur.close()

async def all_rows(conn, sql, params=()):
    cur = await conn.execute(sql, params)
    try: return await cur.fetchall()
    finally: await cur.close()

async def init_db():
    conn = await db()
    await conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, 
        username TEXT, 
        first_name TEXT, 
        created_at TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'buyer',
        total_spent REAL NOT NULL DEFAULT 0,
        total_earned REAL NOT NULL DEFAULT 0,
        referrer_id INTEGER DEFAULT NULL,
        ref_count INTEGER NOT NULL DEFAULT 0,
        season_claimed INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        kind TEXT NOT NULL, 
        name TEXT NOT NULL, 
        price_rub REAL NOT NULL, 
        price_stars INTEGER NOT NULL, 
        price_kzt REAL NOT NULL DEFAULT 0, 
        stock INTEGER NOT NULL DEFAULT 0, 
        sales INTEGER NOT NULL DEFAULT 0, 
        created_at TEXT NOT NULL, 
        file_id TEXT, 
        phone TEXT, 
        session_path TEXT,
        seller_id INTEGER NOT NULL DEFAULT 0,
        description TEXT
    );
    CREATE TABLE IF NOT EXISTS purchases(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER NOT NULL, 
        product_id INTEGER NOT NULL, 
        product_name TEXT NOT NULL, 
        payment TEXT NOT NULL, 
        amount REAL NOT NULL, 
        screenshot_file_id TEXT, 
        status TEXT NOT NULL DEFAULT 'pending', 
        created_at TEXT NOT NULL, 
        session_path TEXT
    );
    CREATE TABLE IF NOT EXISTS seller_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS season_accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        session_path TEXT NOT NULL,
        file_id TEXT,
        is_given INTEGER NOT NULL DEFAULT 0,
        given_to INTEGER DEFAULT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS referral_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER NOT NULL,
        invited_id INTEGER NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    );
    """)
    for col, t in [
        ("role", "TEXT NOT NULL DEFAULT 'buyer'"),
        ("total_spent", "REAL NOT NULL DEFAULT 0"),
        ("total_earned", "REAL NOT NULL DEFAULT 0"),
        ("referrer_id", "INTEGER DEFAULT NULL"),
        ("ref_count", "INTEGER NOT NULL DEFAULT 0"),
        ("season_claimed", "INTEGER NOT NULL DEFAULT 0")
    ]:
        try: await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {t}")
        except Exception: pass

    try: await conn.execute("ALTER TABLE products ADD COLUMN seller_id INTEGER NOT NULL DEFAULT 0")
    except Exception: pass
    try: await conn.execute("ALTER TABLE products ADD COLUMN description TEXT")
    except Exception: pass
    try: await conn.execute("ALTER TABLE purchases ADD COLUMN session_path TEXT")
    except Exception: pass

    await conn.commit()
    await conn.close()

def home_kb(uid: int):
    kb = ReplyKeyboardBuilder()
    kb.button(text="Каталог")
    kb.button(text="Профиль")
    kb.button(text="Отзывы")
    kb.button(text="Поддержка")
    kb.button(text="🎁 Сезоны раздач")
    if is_admin(uid): 
        kb.button(text="Админ панель")
    kb.adjust(1, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def admin_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Статистика")
    kb.button(text="Склад")
    kb.button(text="🎁 Подарить аккаунт")
    kb.button(text="📥 Загрузить сезонные аккаунты")
    kb.button(text="Рассылка")
    kb.button(text="Назад")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup(resize_keyboard=True)

def catalog_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Аккаунты")
    kb.button(text="Звезды")
    kb.button(text="Назад")
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)

def cancel_pub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="seller_pub_cancel")]
    ])
class AddProduct(StatesGroup):
    kind = State()
    name = State()
    description = State()
    price_rub = State()
    price_stars = State()
    price_kzt = State()
    account_file = State()
    phone = State()

class BulkAddProduct(StatesGroup):
    uploading = State()
    pricing = State()

class BulkAddSeason(StatesGroup):
    uploading = State()

class SellerAddAccount(StatesGroup):
    session_file = State()
    description = State()
    price_rub = State()
    price_stars = State()
    confirm = State()

class SellerAddStars(StatesGroup):
    count = State()
    description = State()
    price_rub = State()
    confirm = State()

class GiftAccount(StatesGroup):
    user_id = State()
    session_file = State()
    phone = State()
    confirm = State()

class Broadcast(StatesGroup):
    text = State()

class PaymentState(StatesGroup):
    waiting_for_proof = State()

async def is_suspicious_user(user_id: int) -> bool:
    try:
        user_chat = await bot.get_chat(user_id)
        has_username = bool(user_chat.username)
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        has_avatar = photos.total_count > 0
        if not has_username and not has_avatar:
            return True
        return False
    except Exception:
        return False

async def handle_referral_reward(referrer_id: int):
    conn = await db()
    row = await one(conn, "SELECT ref_count, season_claimed FROM users WHERE id=?", (referrer_id,))
    if not row:
        await conn.close()
        return

    if row["ref_count"] >= 25 and row["season_claimed"] == 0:
        season_acc = await one(conn, "SELECT * FROM season_accounts WHERE is_given=0 ORDER BY id ASC LIMIT 1")
        if season_acc:
            await conn.execute("UPDATE season_accounts SET is_given=1, given_to=? WHERE id=?", (referrer_id, season_acc["id"]))
            await conn.execute("UPDATE users SET season_claimed=1 WHERE id=?", (referrer_id,))
            await conn.commit()
            await conn.close()

            claim_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎁 Забрать аккаунт", callback_data=f"claim_season_acc:{season_acc['id']}")]
            ])
            try:
                await bot.send_message(
                    referrer_id,
                    "🎉 <b>Поздравляем! Вы пригласили 25 пользователей!</b>\n\n"
                    "Цель Сезона 1 выполнена. Заберите свой аккаунт по кнопке ниже:",
                    reply_markup=claim_kb
                )
            except Exception:
                pass
        else:
            await conn.close()
            try:
                await bot.send_message(
                    referrer_id,
                    "🎉 <b>Поздравляем! Вы пригласили 25 пользователей!</b>\n\n"
                    "Все сезонные аккаунты из пула временно разобрали. Как только администратор добавит новые, аккаунт выдастся вам автоматически!"
                )
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ <b>Внимание!</b> Пользователь <code>{referrer_id}</code> набрал 25 рефералов, но склад сезонных аккаунтов пуст! Загрузите аккаунты через админку."
                )
            except Exception:
                pass
    else:
        await conn.close()

async def send_sub_request(message_or_call, referrer_param: str = None):
    chat_info = await bot.get_chat(CHANNEL_ID)
    invite_link = chat_info.invite_link or (f"https://t.me/{chat_info.username}" if chat_info.username else None)
    
    cb_data = f"check_sub_{referrer_param}" if referrer_param else "check_subscription"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=invite_link or "https://t.me/")],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data=cb_data)]
    ])
    
    text_msg = "⚠️ <b>Для использования бота необходимо быть подписанным на наш канал!</b>\n\nПодпишитесь и нажмите кнопку «Я подписался»."
    
    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.answer(text_msg, reply_markup=kb)
    else:
        await message_or_call.answer(text_msg, reply_markup=kb)

async def finalize_user_registration(user, referrer_id: int = None):
    conn = await db()
    existing = await one(conn, "SELECT id FROM users WHERE id=?", (user.id,))
    
    if not existing:
        ref_valid = None
        if referrer_id and referrer_id != user.id:
            parent = await one(conn, "SELECT id FROM users WHERE id=?", (referrer_id,))
            if parent:
                is_fraud = await is_suspicious_user(user.id)
                if not is_fraud:
                    ref_valid = referrer_id

        await conn.execute(
            "INSERT INTO users (id, username, first_name, created_at, referrer_id) VALUES(?,?,?,?,?)",
            (user.id, user.username, user.first_name, now_msk(), ref_valid)
        )
        
        if ref_valid:
            try:
                await conn.execute(
                    "INSERT INTO referral_logs (referrer_id, invited_id, created_at) VALUES(?,?,?)",
                    (ref_valid, user.id, now_msk())
                )
                await conn.execute("UPDATE users SET ref_count = ref_count + 1 WHERE id=?", (ref_valid,))
                await conn.commit()
                await handle_referral_reward(ref_valid)
            except Exception:
                pass
        else:
            await conn.commit()
    await conn.close()
@dp.callback_query(F.data.startswith("check_sub"))
async def recheck_sub(call: CallbackQuery, state: FSMContext):
    referrer_id = None
    if call.data.startswith("check_sub_"):
        raw_ref = call.data.replace("check_sub_", "")
        if raw_ref.isdigit():
            referrer_id = int(raw_ref)

    if await check_sub(call.from_user.id):
        await finalize_user_registration(call.from_user, referrer_id)
        await call.answer("Спасибо за подписку! 🎉", show_alert=True)
        try: await call.message.delete()
        except Exception: pass
        name = call.from_user.username or call.from_user.first_name or "пользователь"
        await call.message.answer(f"Привет, {name}!\nТут ты можешь приобрести все что душе угодно.", reply_markup=home_kb(call.from_user.id))
    else:
        await call.answer("Вы всё еще не подписаны на канал! ❌", show_alert=True)

@dp.message(CommandStart())
async def start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)

    conn = await db()
    user = await one(conn, "SELECT id FROM users WHERE id=?", (m.from_user.id,))
    await conn.close()

    if not await check_sub(m.from_user.id):
        ref_arg = str(referrer_id) if (not user and referrer_id) else None
        return await send_sub_request(m, ref_arg)

    if not user:
        await finalize_user_registration(m.from_user, referrer_id)

    name = m.from_user.username or m.from_user.first_name or "пользователь"
    await m.answer(f"Привет, {name}!\nТут ты можешь приобрести все что душе угодно.", reply_markup=home_kb(m.from_user.id))

@dp.message(F.text == "Назад")
async def back_home(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Главное меню", reply_markup=home_kb(m.from_user.id))

@dp.message(F.text == "🎁 Сезоны раздач")
async def open_seasons(m: Message):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    conn = await db()
    user = await one(conn, "SELECT ref_count, season_claimed FROM users WHERE id=?", (m.from_user.id,))
    season_pool = (await one(conn, "SELECT COUNT(*) as c FROM season_accounts WHERE is_given=0"))["c"]
    await conn.close()

    ref_count = user["ref_count"] if user else 0
    claimed = user["season_claimed"] if user else 0
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={m.from_user.id}"

    status_str = "✅ Аккаунт уже получен!" if claimed == 1 else f"{ref_count}/25"

    text = (
        "🏆 <b>СЕЗОНЫ РАЗДАЧ NOVERASHOP</b>\n\n"
        "🔥 <b>Сезон 1: Реферальная система</b>\n"
        "Приглашай друзей и получай аккаунты бесплатно!\n\n"
        "🎯 <b>Задание:</b> Пригласить 25 человек в бота.\n"
        "⚡️ <b>Условие:</b> Человек должен запустить бота и обязательно подписаться на канал.\n"
        f"📊 <b>Твой прогресс:</b> <code>{status_str}</code>\n"
        f"📦 <b>Осталось аккаунтов в пуле сезона:</b> {season_pool} шт.\n\n"
        f"🔗 <b>Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "<i>Накрутка и фейковые аккаунты строго отсеиваются системой безопасности!</i>"
    )

    kb = InlineKeyboardBuilder()
    if ref_count >= 25 and claimed == 0:
        kb.button(text="🎁 Забрать аккаунт", callback_data="claim_season_now")
    kb.button(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text={quote('Заходи в Noverashop!')}")
    kb.adjust(1)

    await m.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "claim_season_now")
async def claim_season_btn(call: CallbackQuery):
    await call.answer()
    conn = await db()
    user = await one(conn, "SELECT ref_count, season_claimed FROM users WHERE id=?", (call.from_user.id,))
    if not user or user["ref_count"] < 25 or user["season_claimed"] == 1:
        await conn.close()
        return await call.message.answer("❌ У вас недостаточно приглашений или награда уже получена.")

    season_acc = await one(conn, "SELECT * FROM season_accounts WHERE is_given=0 ORDER BY id ASC LIMIT 1")
    if not season_acc:
        await conn.close()
        return await call.message.answer("⚠️ Аккаунты в пуле временно закончились. Скоро добавим!")

    await conn.execute("UPDATE season_accounts SET is_given=1, given_to=? WHERE id=?", (call.from_user.id, season_acc["id"]))
    await conn.execute("UPDATE users SET season_claimed=1 WHERE id=?", (call.from_user.id,))
    await conn.commit()
    await conn.close()

    session_path = season_acc["session_path"]
    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"

    if session_path and os.path.exists(session_path):
        await call.message.answer("🎉 <b>Награда активирована!</b>\n⏳ <i>Подключаемся к аккаунту для выдачи кода...</i>")
        asyncio.create_task(safe_listen_for_login_code(session_path, call.from_user.id, user_mention))
    else:
        await call.message.answer("⚠️ Файл сессии не найден. Напишите в поддержку.")

@dp.callback_query(F.data.startswith("claim_season_acc:"))
async def claim_season_callback(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split(":")[1])
    conn = await db()
    season_acc = await one(conn, "SELECT * FROM season_accounts WHERE id=? AND given_to=?", (acc_id, call.from_user.id))
    await conn.close()

    if not season_acc:
        return await call.message.answer("Награда не найдена или уже получена.")

    session_path = season_acc["session_path"]
    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"

    if session_path and os.path.exists(session_path):
        await call.message.answer("⏳ <i>Подключаемся к вашему сезонному аккаунту...</i>")
        asyncio.create_task(safe_listen_for_login_code(session_path, call.from_user.id, user_mention))
    else:
        await call.message.answer("⚠️ Файл сессии поврежден или отсутствует на сервере.")
@dp.message(F.text == "Профиль")
async def show_profile(m: Message):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    conn = await db()
    user = await one(conn, "SELECT * FROM users WHERE id=?", (m.from_user.id,))
    
    if not user:
        await conn.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, created_at) VALUES(?,?,?,?)",
            (m.from_user.id, m.from_user.username, m.from_user.first_name, now_msk())
        )
        await conn.commit()
        user = await one(conn, "SELECT * FROM users WHERE id=?", (m.from_user.id,))
    
    await conn.close()

    status_text = "продавец" if user["role"] == "seller" else "покупатель"
    total_spent = user["total_spent"]
    role = user["role"]
    earned = user["total_earned"]

    text = f"<b>Профиль</b>\n\nайди: <code>{m.from_user.id}</code>\nсумма покупок: {total_spent:.0f}₽\nстатус: {status_text}"
    kb = InlineKeyboardBuilder()

    if role == "seller":
        text += f"\nзаработано: {earned:.0f}₽"
        kb.button(text="Выложить товар на продажу", callback_data="seller_add_choice")
        kb.button(text="📦 Мои товары", callback_data="seller_my_products")
    else:
        kb.button(text="Стать продавцом", callback_data="become_seller_start")

    kb.adjust(1)
    await m.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "seller_my_products")
async def seller_my_products_cmd(call: CallbackQuery):
    await call.answer()
    conn = await db()
    rows = await all_rows(conn, "SELECT * FROM products WHERE seller_id=? AND stock>0 ORDER BY id DESC", (call.from_user.id,))
    await conn.close()

    if not rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="seller_back_profile")]])
        return await call.message.edit_text("У вас нет товаров в наличии.", reply_markup=kb)

    kb = InlineKeyboardBuilder()
    for p in rows:
        if p["kind"] == "account":
            code = extract_code_prefix(p["phone"] or p["name"])
            flag = get_flag(code)
            label = f"🗑 {flag}{code} [{p['price_rub']:.0f}₽]"
        else:
            flag = get_flag(p["name"])
            label = f"🗑 {flag}{p['name']} [{p['price_rub']:.0f}₽]"
        
        kb.button(text=label, callback_data=f"seller_del_prod:{p['id']}")

    kb.button(text="🔙 Назад в профиль", callback_data="seller_back_profile")
    kb.adjust(1)

    await call.message.edit_text("📦 <b>Ваши товары в наличии:</b>\n<i>Нажмите 🗑 напротив товара, чтобы удалить его с продажи.</i>", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("seller_del_prod:"))
async def seller_delete_product(call: CallbackQuery):
    pid = int(call.data.split(":")[1])
    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=? AND seller_id=?", (pid, call.from_user.id))
    
    if prod:
        s_path = prod["session_path"]
        if s_path and os.path.exists(s_path):
            try: os.remove(s_path)
            except Exception: pass

        await conn.execute("DELETE FROM products WHERE id=?", (pid,))
        await conn.commit()
        await call.answer("Товар удален с продажи ✅", show_alert=True)
    else:
        await call.answer("Товар не найден или уже был продан/удален.", show_alert=True)

    await conn.close()
    await seller_my_products_cmd(call)

@dp.callback_query(F.data == "become_seller_start")
async def become_seller_start(call: CallbackQuery):
    await call.answer()
    text = "Вы хотите стать продавцом в Noverashop.\nПодтвердите создание заявки:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="подтвердить", callback_data="become_seller_confirm")],
        [InlineKeyboardButton(text="назад", callback_data="seller_back_profile")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "seller_back_profile")
async def seller_back_profile(call: CallbackQuery):
    await call.answer()
    await call.message.delete()
    await show_profile(call.message)

@dp.callback_query(F.data == "become_seller_confirm")
async def become_seller_confirm(call: CallbackQuery):
    await call.answer()
    username = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"
    
    conn = await db()
    await conn.execute(
        "INSERT OR IGNORE INTO users (id, username, first_name, created_at) VALUES(?,?,?,?)",
        (call.from_user.id, call.from_user.username, call.from_user.first_name, now_msk())
    )
    cur = await conn.execute(
        "INSERT INTO seller_requests(user_id, username, status, created_at) VALUES(?,?,'pending',?)",
        (call.from_user.id, username, now_msk())
    )
    req_id = cur.lastrowid
    await conn.commit(); await conn.close()

    await call.message.edit_text("Заявка успешно отправлена администратору! Ожидайте решения.")

    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Одобрить", callback_data=f"adm_seller_appr:{req_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"adm_seller_rej:{req_id}")
        ]
    ])
    await bot.send_message(ADMIN_ID, f"Заявка на статус продавца от {username}", reply_markup=adm_kb)

@dp.callback_query(F.data.startswith("adm_seller_appr:"))
async def adm_seller_approve(call: CallbackQuery):
    await call.answer()
    req_id = int(call.data.split(":")[1])
    conn = await db()
    req = await one(conn, "SELECT * FROM seller_requests WHERE id=?", (req_id,))
    if req and req["status"] == "pending":
        await conn.execute("UPDATE seller_requests SET status='approved' WHERE id=?", (req_id,))
        await conn.execute("UPDATE users SET role='seller' WHERE id=?", (req["user_id"],))
        await conn.commit()
        await call.message.edit_text(f"✅ Пользователю {req['username']} выдан статус продавца.")
        
        msg = "Ваш статус обновлен на «Продавец» 🎉\nТеперь вы можете выставлять товары на продажу через раздел «Профиль».\nСпасибо, что выбрали нас 🤍"
        try: await bot.send_message(req["user_id"], msg)
        except Exception: pass
    else:
        await call.message.edit_text("Заявка не найдена или уже обработана.")
    await conn.close()

@dp.callback_query(F.data.startswith("adm_seller_rej:"))
async def adm_seller_reject(call: CallbackQuery):
    await call.answer()
    req_id = int(call.data.split(":")[1])
    conn = await db()
    req = await one(conn, "SELECT * FROM seller_requests WHERE id=?", (req_id,))
    if req and req["status"] == "pending":
        await conn.execute("UPDATE seller_requests SET status='rejected' WHERE id=?", (req_id,))
        await conn.commit()
        await call.message.edit_text(f"❌ Заявка пользователя {req['username']} отклонена.")
        
        msg = "К сожалению, ваша заявка на получение статуса продавца была отклонена."
        try: await bot.send_message(req["user_id"], msg)
        except Exception: pass
    else:
        await call.message.edit_text("Заявка не найдена или уже обработана.")
    await conn.close()
@dp.callback_query(F.data == "seller_add_choice")
async def seller_add_choice(call: CallbackQuery):
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Аккаунты", callback_data="seller_add_type:account")],
        [InlineKeyboardButton(text="⭐ Звезды", callback_data="seller_add_type:stars")]
    ])
    await call.message.answer("<b>Здравствуйте!</b> Что именно вы желаете выставить на продажу?", reply_markup=kb)

@dp.callback_query(F.data == "seller_add_type:account")
async def seller_add_account_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(SellerAddAccount.session_file)
    text = (
        "⚙️ <b>Загрузка аккаунта (Шаг 1 из 4)</b>\n\n"
        "Пожалуйста, отправьте файл сессии формата <code>.session</code> (Pyrogram) документом."
    )
    await call.message.answer(text, reply_markup=cancel_pub_kb())

@dp.message(SellerAddAccount.session_file, F.document)
async def seller_add_acc_file(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"seller_{secrets.token_hex(4)}.session"
    save_path = Path("sessions") / file_name

    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, save_path)

    full_phone = ""
    detected_code = "+1"
    client = None
    try:
        session_name = save_path.stem
        client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(save_path.parent), in_memory=False)
        await asyncio.wait_for(client.connect(), timeout=10.0)
        me = await client.get_me()
        if me and me.phone_number:
            full_phone = f"+{me.phone_number}"
            detected_code = extract_code_prefix(full_phone)
    except Exception:
        full_phone = extract_code_prefix(file_name)
        detected_code = extract_code_prefix(file_name)
    finally:
        if client and client.is_connected:
            try: await client.disconnect()
            except Exception: pass

    await asyncio.sleep(0.5)
    await state.update_data(file_id=file_id, session_path=str(save_path), phone=full_phone or detected_code, code=detected_code)
    await state.set_state(SellerAddAccount.description)
    
    text = "📝 <b>Загрузка аккаунта (Шаг 2 из 4)</b>\n\nУкажите подробное описание товара (или отправьте <code>-</code>):"
    await m.answer(text, reply_markup=cancel_pub_kb())

@dp.message(SellerAddAccount.description)
async def seller_add_acc_desc(m: Message, state: FSMContext):
    if m.text and m.text.lower() in ["назад", "отмена", "/cancel"]:
        await state.clear()
        return await m.answer("Выкладка товара отменена.", reply_markup=home_kb(m.from_user.id))

    desc = "" if m.text.strip() == "-" else m.text.strip()
    await state.update_data(description=desc)
    await state.set_state(SellerAddAccount.price_rub)
    await m.answer("💰 <b>Загрузка аккаунта (Шаг 3 из 4)</b>\n\nУкажите стоимость товара в <b>рублях (₽)</b>:", reply_markup=cancel_pub_kb())

@dp.message(SellerAddAccount.price_rub)
async def seller_add_acc_rub(m: Message, state: FSMContext):
    if m.text and m.text.lower() in ["назад", "отмена", "/cancel"]:
        await state.clear()
        return await m.answer("Выкладка товара отменена.", reply_markup=home_kb(m.from_user.id))

    try: price = float(m.text.replace(",", "."))
    except ValueError: return await m.answer("Пожалуйста, введите корректное число для цены в ₽:", reply_markup=cancel_pub_kb())
    
    await state.update_data(price_rub=price)
    await state.set_state(SellerAddAccount.price_stars)
    await m.answer("⭐ <b>Загрузка аккаунта (Шаг 4 из 4)</b>\n\nУкажите стоимость товара в <b>звездах (⭐)</b>:", reply_markup=cancel_pub_kb())

@dp.message(SellerAddAccount.price_stars)
async def seller_add_acc_stars(m: Message, state: FSMContext):
    if m.text and m.text.lower() in ["назад", "отмена", "/cancel"]:
        await state.clear()
        return await m.answer("Выкладка товара отменена.", reply_markup=home_kb(m.from_user.id))

    try: price = int(m.text)
    except ValueError: return await m.answer("Пожалуйста, введите целое число для цены в звездах:", reply_markup=cancel_pub_kb())
    
    await state.update_data(price_stars=price)
    data = await state.get_data()
    code = data["code"]
    desc_str = f"<b>Описание:</b> {data['description']}\n" if data.get('description') else ""
    
    text = (
        f"📋 <b>Проверьте и подтвердите информацию о товаре:</b>\n\n"
        f"<b>Тип:</b> Аккаунт ({code})\n"
        f"{desc_str}"
        f"<b>Цена в ₽:</b> {data['price_rub']:.0f}₽\n"
        f"<b>Цена в ⭐:</b> {data['price_stars']}⭐\n\n"
        f"Все ли указано верно?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выложить товар", callback_data="seller_pub_acc_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="seller_pub_cancel")]
    ])
    await state.set_state(SellerAddAccount.confirm)
    await m.answer(text, reply_markup=kb)

@dp.callback_query(SellerAddAccount.confirm, F.data == "seller_pub_acc_confirm")
async def seller_pub_acc_confirm(call: CallbackQuery, state: FSMContext):
    await call.answer()
    d = await state.get_data()
    conn = await db()
    await conn.execute(
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone, seller_id, description) VALUES('account',?,?,?,0,1,0,?,?,?,?,?,?)",
        (d["phone"], d["price_rub"], d["price_stars"], now_msk(), d["file_id"], d["session_path"], d["phone"], call.from_user.id, d.get("description", ""))
    )
    await conn.commit(); await conn.close()
    await state.clear()
    await call.message.edit_text("✨ <b>Благодарим! Товар успешно выложен на продажу.</b>")

@dp.callback_query(F.data == "seller_add_type:stars")
async def seller_add_stars_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(SellerAddStars.count)
    await call.message.answer("⭐ <b>Загрузка товара «Звезды» (Шаг 1 из 3)</b>\n\nУкажите количество звезд для продажи:", reply_markup=cancel_pub_kb())

@dp.message(SellerAddStars.count)
async def seller_add_stars_cnt(m: Message, state: FSMContext):
    if m.text and m.text.lower() in ["назад", "отмена", "/cancel"]:
        await state.clear()
        return await m.answer("Выкладка товара отменена.", reply_markup=home_kb(m.from_user.id))

    try: cnt = int(m.text)
    except ValueError: return await m.answer("Введите целое число:", reply_markup=cancel_pub_kb())
    
    await state.update_data(count=cnt)
    await state.set_state(SellerAddStars.description)
    await m.answer("📝 <b>Загрузка товара «Звезды» (Шаг 2 из 3)</b>\n\nДобавьте описание товара (или введите <code>-</code>):", reply_markup=cancel_pub_kb())

@dp.message(SellerAddStars.description)
async def seller_add_stars_desc(m: Message, state: FSMContext):
    if m.text and m.text.lower() in ["назад", "отмена", "/cancel"]:
        await state.clear()
        return await m.answer("Выкладка товара отменена.", reply_markup=home_kb(m.from_user.id))

    desc = "" if m.text.strip() == "-" else m.text.strip()
    await state.update_data(description=desc)
    await state.set_state(SellerAddStars.price_rub)
    await m.answer("💰 <b>Загрузка товара «Звезды» (Шаг 3 из 3)</b>\n\nУкажите цену в рублях:", reply_markup=cancel_pub_kb())

@dp.message(SellerAddStars.price_rub)
async def seller_add_stars_rub(m: Message, state: FSMContext):
    if m.text and m.text.lower() in ["назад", "отмена", "/cancel"]:
        await state.clear()
        return await m.answer("Выкладка товара отменена.", reply_markup=home_kb(m.from_user.id))

    try: price = float(m.text.replace(",", "."))
    except ValueError: return await m.answer("Введите корректную цену в рублях:", reply_markup=cancel_pub_kb())
    
    await state.update_data(price_rub=price)
    d = await state.get_data()
    desc_str = f"<b>Описание:</b> {d['description']}\n" if d.get('description') else ""
    text = (
        f"📋 <b>Подтвердите публикацию:</b>\n\n"
        f"<b>Товар:</b> {d['count']}⭐ Stars\n"
        f"{desc_str}"
        f"<b>Цена в ₽:</b> {d['price_rub']:.0f}₽"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выложить", callback_data="seller_pub_stars_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="seller_pub_cancel")]
    ])
    await state.set_state(SellerAddStars.confirm)
    await m.answer(text, reply_markup=kb)

@dp.callback_query(SellerAddStars.confirm, F.data == "seller_pub_stars_confirm")
async def seller_pub_stars_confirm(call: CallbackQuery, state: FSMContext):
    await call.answer()
    d = await state.get_data()
    conn = await db()
    await conn.execute(
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, seller_id, description) VALUES('stars',?,?,0,0,1,0,?,?,?)",
        (f"{d['count']} ⭐ Stars", d["price_rub"], now_msk(), call.from_user.id, d.get("description", ""))
    )
    await conn.commit(); await conn.close()
    await state.clear()
    await call.message.edit_text("✨ <b>Благодарим! Товар успешно выложен на продажу.</b>")

@dp.callback_query(F.data == "seller_pub_cancel")
async def seller_pub_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Отменено.")
    try: await call.message.edit_text("❌ Выкладка товара была отменена.")
    except Exception: await call.message.answer("❌ Выкладка товара была отменена.", reply_markup=home_kb(call.from_user.id))
@dp.message(F.text == "Каталог")
async def open_catalog(m: Message):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    await m.answer("Выберите тип товара:", reply_markup=catalog_kb())

@dp.message(F.text == "Отзывы")
async def open_reviews(m: Message):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    await m.answer("Отзывы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть отзывы", url="https://t.me/repacrisov")]]))

@dp.message(F.text == "Поддержка")
async def open_support(m: Message):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    await m.answer("Поддержка:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Написать в поддержку", url="https://t.me/suppnovera")]]))

@dp.message(F.text == "Аккаунты")
async def show_accounts(m: Message):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    await products(m, "account")

@dp.message(F.text == "Звезды")
async def show_stars(m: Message):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    await products(m, "stars")

async def products(m: Message, kind: str):
    conn = await db()
    rows = await all_rows(conn, "SELECT * FROM products WHERE kind=? AND stock>0 ORDER BY id", (kind,))
    await conn.close()
    if not rows: 
        return await m.answer("Товаров в наличии нет.", reply_markup=catalog_kb())
    
    kb = InlineKeyboardBuilder()
    if kind == "account":
        grouped = {}
        for p in rows:
            code = extract_code_prefix(p["phone"] or p["name"])
            price = p["price_rub"]
            group_key = f"{code}_{price}"

            if group_key not in grouped:
                grouped[group_key] = {"code": code, "price": price, "prod_id": p["id"], "count": 1}
            else:
                grouped[group_key]["count"] += 1
        
        for item in grouped.values():
            flag = get_flag(item["code"])
            cnt_str = f" ({item['count']} шт)" if item["count"] > 1 else ""
            btn_text = f"{flag}{item['code']} [{item['price']:.0f}₽]{cnt_str}"
            kb.button(text=btn_text, callback_data=f"buy_prefix:{item['code']}:{item['prod_id']}")
    else:
        for p in rows:
            flag = get_flag(p["name"]) or get_flag(p["phone"] or "")
            btn_text = f"{flag}{p['name']} [{p['price_rub']:.0f}₽]"
            kb.button(text=btn_text, callback_data=f"product:{p['id']}")
        
    kb.adjust(1)
    await m.answer("Выберите товар для покупки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_prefix:"))
async def buy_prefix_select(call: CallbackQuery):
    if not await check_sub(call.from_user.id): return await send_sub_request(call)
    await call.answer()
    
    parts = call.data.split(":")
    prefix = parts[1]
    target_pid = int(parts[2]) if len(parts) > 2 else None

    conn = await db()
    prod = None
    if target_pid:
        prod = await one(conn, "SELECT * FROM products WHERE id=? AND stock>0", (target_pid,))
    
    if not prod:
        raw_digits = re.sub(r"\D", "", prefix)
        prod = await one(conn, "SELECT * FROM products WHERE kind='account' AND stock>0 AND (phone LIKE ? OR name LIKE ? OR phone LIKE ?) ORDER BY RANDOM() LIMIT 1", (f"{prefix}%", f"{prefix}%", f"{raw_digits}%"))
    await conn.close()

    if not prod:
        return await call.message.answer("К сожалению, аккаунты с этим кодом закончились.")

    display_name = prefix
    flag = get_flag(prefix)
    desc_val = prod["description"] if "description" in prod.keys() else None
    desc_str = f"\n📖 <b>Описание:</b> {desc_val}\n" if desc_val else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Купить за {prod['price_rub']:.0f}₽", callback_data=f"pay:{prod['id']}:rub")],
        [InlineKeyboardButton(text=f"Купить за {prod['price_stars']}⭐ Stars", callback_data=f"pay:{prod['id']}:stars")],
        [InlineKeyboardButton(text=f"Купить за {prod['price_kzt']:.0f}₸", callback_data=f"pay:{prod['id']}:kzt")]
    ])
    await call.message.answer(f"🛒 <b>Покупка аккаунта: {flag}{display_name}</b>\n{desc_str}\nВыберите способ оплаты:", reply_markup=kb)

@dp.callback_query(F.data.startswith("product:"))
async def select_product(call: CallbackQuery):
    if not await check_sub(call.from_user.id): return await send_sub_request(call)
    await call.answer()
    pid = int(call.data.split(":")[1])
    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=? AND stock>0", (pid,))
    await conn.close()

    if not prod:
        return await call.message.answer("К сожалению, этого товара уже нет в наличии.")

    flag = get_flag(prod["name"]) or get_flag(prod["phone"] or "")
    desc_val = prod["description"] if "description" in prod.keys() else None
    desc_str = f"\n📖 <b>Описание:</b> {desc_val}\n" if desc_val else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Купить за {prod['price_rub']:.0f}₽", callback_data=f"pay:{prod['id']}:rub")],
        [InlineKeyboardButton(text=f"Купить за {prod['price_stars']}⭐ Stars", callback_data=f"pay:{prod['id']}:stars")],
        [InlineKeyboardButton(text=f"Купить за {prod['price_kzt']:.0f}₸", callback_data=f"pay:{prod['id']}:kzt")]
    ])
    await call.message.answer(f"🛒 <b>Покупка: {flag}{prod['name']}</b>\n{desc_str}\nВыберите способ оплаты:", reply_markup=kb)

@dp.callback_query(F.data.startswith("pay:"))
async def process_payment_info(call: CallbackQuery, state: FSMContext):
    if not await check_sub(call.from_user.id): return await send_sub_request(call)
    await call.answer()
    _, pid_str, pay_type = call.data.split(":")
    pid = int(pid_str)
    
    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    await conn.close()

    if not prod or prod["stock"] <= 0:
        return await call.message.answer("Товар закончился.")

    await state.update_data(product_id=pid, pay_type=pay_type)
    await state.set_state(PaymentState.waiting_for_proof)

    if pay_type == "rub":
        text_msg = (
            f"Переведите <b>{prod['price_rub']:.0f} ₽</b> на реквизиты:\n"
            f"<code>+79313716777</code>\n"
            f"• Т-Банк\n"
            f"• Наталья/Тимур\n\n"
            f"После оплаты <b>отправьте скриншот или чек оплаты</b> ответным сообщением в этот чат."
        )
    elif pay_type == "kzt":
        text_msg = (
            f"Переведите <b>{prod['price_kzt']:.0f} ₸</b> на реквизиты:\n"
            f"<code>4400430050959862</code>\n"
            f"• Банк: Kaspi\n"
            f"• Получатель: Мейрамбек.Е\n\n"
            f"После оплаты <b>отправьте скриншот или чек оплаты</b> ответным сообщением в этот чат."
        )
    else:
        text_msg = (
            f"Отправьте <b>{prod['price_stars']} ⭐</b> на аккаунт @kocetu\n\n"
            f"После отправки <b>отправьте скриншот подтверждения</b> ответным сообщением в этот чат."
        )

    await call.message.answer(text_msg)

@dp.message(PaymentState.waiting_for_proof, F.photo | F.document)
async def process_payment_proof(m: Message, state: FSMContext):
    if not await check_sub(m.from_user.id): return await send_sub_request(m)
    data = await state.get_data()
    pid = data["product_id"]
    pay_type = data["pay_type"]
    
    conn = await db()
    selected_prod = await one(conn, "SELECT * FROM products WHERE id=? AND stock>0", (pid,))
    
    if not selected_prod and pid:
        selected_prod = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
        if selected_prod and selected_prod["kind"] == "account":
            prefix = extract_code_prefix(selected_prod["phone"] or selected_prod["name"])
            raw_digits = re.sub(r"\D", "", prefix)
            selected_prod = await one(conn, "SELECT * FROM products WHERE kind='account' AND stock>0 AND (phone LIKE ? OR name LIKE ? OR phone LIKE ?) ORDER BY RANDOM() LIMIT 1", (f"{prefix}%", f"{prefix}%", f"{raw_digits}%"))

    if not selected_prod or selected_prod["stock"] <= 0:
        await conn.close()
        await state.clear()
        return await m.answer("К сожалению, данный товар закончился.")

    acc_session_path = selected_prod["session_path"]
    if selected_prod["kind"] == "account":
        await conn.execute("UPDATE products SET stock = 0, sales = sales + 1 WHERE id=?", (selected_prod["id"],))

    photo_id = m.photo[-1].file_id if m.photo else m.document.file_id
    amount = selected_prod["price_rub"] if pay_type == "rub" else (selected_prod["price_kzt"] if pay_type == "kzt" else selected_prod["price_stars"])
    pay_symbol = "₽" if pay_type == "rub" else ("₸" if pay_type == "kzt" else "⭐")

    cur = await conn.execute(
        "INSERT INTO purchases(user_id, product_id, product_name, payment, amount, screenshot_file_id, status, created_at, session_path) VALUES(?,?,?,?,?,?,'pending',?,?)",
        (m.from_user.id, selected_prod["id"], selected_prod["name"], pay_type, amount, photo_id, now_msk(), acc_session_path)
    )
    purch_id = cur.lastrowid

    seller_info_str = ""
    if selected_prod["seller_id"] != 0 and selected_prod["seller_id"] != ADMIN_ID:
        seller_user = await one(conn, "SELECT username, id FROM users WHERE id=?", (selected_prod["seller_id"],))
        seller_uname = f"@{seller_user['username']}" if (seller_user and seller_user['username']) else f"ID {selected_prod['seller_id']}"
        seller_info_str = f"\n\nвыложено: {seller_uname}"

    await conn.commit(); await conn.close()
    await state.clear()

    await m.answer("⏳ <b>Заявка отправлена администратору на проверку.</b> Ожидайте подтверждения.")

    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"adm_approve:{purch_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_reject:{purch_id}")
        ]
    ])
    
    user_info = f"@{m.from_user.username}" if m.from_user.username else f"ID {m.from_user.id}"
    disp_name = extract_code_prefix(selected_prod["phone"] or selected_prod["name"]) if selected_prod["kind"] == "account" else selected_prod["name"]
    flag = get_flag(disp_name)
    caption = f"📦 <b>Новая заявка на покупку #{purch_id}</b>\n\nПокупатель: {user_info}\nТовар: {flag}{disp_name}\nСумма: {amount:.0f} {pay_symbol}{seller_info_str}"
    
    if m.photo:
        await bot.send_photo(ADMIN_ID, photo_id, caption=caption, reply_markup=adm_kb)
    else:
        await bot.send_document(ADMIN_ID, photo_id, caption=caption, reply_markup=adm_kb)

@dp.callback_query(F.data.startswith("adm_approve:"))
async def approve_purchase(call: CallbackQuery):
    await call.answer("Принято!")
    purch_id = int(call.data.split(":")[1])
    conn = await db()
    purch = await one(conn, "SELECT * FROM purchases WHERE id=?", (purch_id,))
    
    if not purch or purch["status"] != "pending":
        await conn.close()
        return await call.message.edit_caption(caption=call.message.caption + "\n\n⚠️ Заявка уже обработана.")

    prod = await one(conn, "SELECT * FROM products WHERE id=?", (purch["product_id"],))
    if prod and prod["kind"] != "account":
        if prod["stock"] <= 1:
            await conn.execute("DELETE FROM products WHERE id=?", (purch["product_id"],))
        else:
            await conn.execute("UPDATE products SET stock = stock - 1, sales = sales + 1 WHERE id=?", (purch["product_id"],))
        
    await conn.execute("UPDATE purchases SET status = 'approved' WHERE id=?", (purch_id,))
    await conn.execute("UPDATE users SET total_spent = total_spent + ? WHERE id=?", (purch["amount"], purch["user_id"]))

    if prod and prod["seller_id"] != 0 and prod["seller_id"] != ADMIN_ID:
        await conn.execute("UPDATE users SET total_earned = total_earned + ? WHERE id=?", (prod["price_rub"], prod["seller_id"]))
        pay_url = "https://t.me/fegote?text=" + quote("Привет, хочу получить выплату")
        seller_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Выплата", url=pay_url)]])
        seller_msg = f"Товар: {prod['name']} продан!\nцена: {prod['price_rub']:.0f} р : {prod['price_stars']} в звездах\nвы можете получить выплату по кнопке ниже ( отправьте это сообщение )"
        try: await bot.send_message(prod["seller_id"], seller_msg, reply_markup=seller_kb)
        except Exception: pass

    await conn.commit(); await conn.close()
    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ <b>ОДОБРЕНО</b>")

    claim_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Получить аккаунт / Код", callback_data=f"claim_acc:{purch_id}")]
    ])
    await bot.send_message(purch["user_id"], "✅ <b>Ваш платеж успешно подтвержден!</b> Нажмите кнопку ниже, чтобы забрать товар:", reply_markup=claim_kb)

@dp.callback_query(F.data.startswith("adm_reject:"))
async def reject_purchase(call: CallbackQuery):
    await call.answer("Отклонено.")
    purch_id = int(call.data.split(":")[1])
    
    conn = await db()
    purch = await one(conn, "SELECT * FROM purchases WHERE id=?", (purch_id,))
    if purch:
        await conn.execute("UPDATE purchases SET status = 'rejected' WHERE id=?", (purch_id,))
        if purch["session_path"]:
            await conn.execute("UPDATE products SET stock = 1 WHERE session_path=?", (purch["session_path"],))
        await conn.commit()
    await conn.close()

    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ <b>ОТКЛОНЕНО</b>")
    if purch:
        await bot.send_message(purch["user_id"], "❌ Ваша оплата была отклонена администратором.")

@dp.callback_query(F.data.startswith("claim_acc:"))
async def claim_account(call: CallbackQuery):
    await call.answer()
    purch_id = int(call.data.split(":")[1])
    conn = await db()
    purch = await one(conn, "SELECT * FROM purchases WHERE id=?", (purch_id,))
    await conn.close()
    
    if not purch: return await call.message.answer("Заявка на покупку не найдена.")
        
    session_file = purch["session_path"]
    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"

    if session_file and os.path.exists(session_file):
        await call.message.answer("⏳ <i>Подключаемся к аккаунту...</i>")
        asyncio.create_task(safe_listen_for_login_code(session_file, call.from_user.id, user_mention))
    else:
        await call.message.answer("⚠️ Файл `.session` для этого аккаунта не найден на сервере.")

@dp.callback_query(F.data.startswith("claim_gift:"))
async def claim_gift_account(call: CallbackQuery):
    await call.answer()
    prod_id = int(call.data.split(":")[1])
    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=?", (prod_id,))
    await conn.close()
    
    if not prod: return await call.message.answer("Подарок не найден или уже был удален.")

    session_file = prod["session_path"]
    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"

    if session_file and os.path.exists(session_file):
        await call.message.answer("⏳ <i>Подключаемся к аккаунту...</i>")
        asyncio.create_task(safe_listen_for_login_code(session_file, call.from_user.id, user_mention))
    else:
        await call.message.answer("⚠️ Файл `.session` не найден на сервере.")

@dp.callback_query(F.data.startswith("more_code:"))
async def req_more_code(call: CallbackQuery):
    await call.answer("Ожидаем ещё один код...")
    session_path = call.data.split(":", 1)[1]
    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"
    await call.message.answer("⏳ <i>Подключаемся для получения нового кода...</i>")
    asyncio.create_task(safe_listen_for_login_code(session_path, call.from_user.id, user_mention))

async def safe_listen_for_login_code(session_path: str, user_id: int, user_mention: str):
    session_name = Path(session_path).stem
    session_dir = str(Path(session_path).parent)
    
    for ext in ["-journal", "-wal", "-shm"]:
        lock_file = Path(f"{session_path}{ext}")
        if lock_file.exists():
            try: os.remove(lock_file)
            except Exception: pass

    client = Client(
        session_name,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=session_dir,
        in_memory=False,
        takeout=False,
        max_concurrent_transmissions=1
    )
    login_notified = False

    async def code_handler(cli, message):
        nonlocal login_notified
        try:
            msg_text = message.text or message.caption or ""
            if not login_notified and ("устройство" in msg_text.lower() or "вход" in msg_text.lower() or (message.from_user and message.from_user.is_self)):
                login_notified = True
                admin_text = f"🔔 <b>Вход в аккаунт произведен!</b>\n\n📱 Аккаунт: <code>{phone_number}</code>\n👤 Покупатель: {user_mention}"
                try: await bot.send_message(ADMIN_ID, admin_text)
                except Exception: pass

            if msg_text:
                codes = re.findall(r'\b\d{5,6}\b', msg_text)
                if codes:
                    found_code = codes[0]
                    try:
                        await bot.send_message(user_id, f"🔑 <b>Ваш код авторизации:</b> <code>{found_code}</code>")
                        await asyncio.sleep(7)

                        kb_more = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="еще один код", callback_data=f"more_code:{session_path}")]
                        ])
                        await bot.send_message(user_id, "Код не пришел?", reply_markup=kb_more)
                        
                        if not login_notified:
                            login_notified = True
                            admin_text = f"🔔 <b>Вход в аккаунт произведен!</b>\n\n📱 Аккаунт: <code>{phone_number}</code>\n👤 Покупатель: {user_mention}"
                            try: await bot.send_message(ADMIN_ID, admin_text)
                            except Exception: pass

                        asyncio.create_task(send_post_purchase_info(user_id))
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        client.add_handler(MessageHandler(code_handler, filters.me | filters.service | filters.private))
        await asyncio.wait_for(client.start(), timeout=20.0)
        
        me = await client.get_me()
        phone_number = f"+{me.phone_number}" if (me and me.phone_number) else "Номер не определен"

        await bot.send_message(
            user_id,
            f"📱 <b>Номер аккаунта:</b> <code>{phone_number}</code>\n\n"
            f"Отправьте запрос кода авторизации в Telegram. Как только код придет, бот перешлет его сюда."
        )
        await asyncio.sleep(600)

    except asyncio.TimeoutError:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Написать в поддержку", url="https://t.me/fegote")]])
        await bot.send_message(user_id, "❌ <b>Не удалось подключиться к аккаунту (Таймаут).</b>\nФайл сессии занят или поврежден. Напишите в поддержку.", reply_markup=kb)
    except (AuthKeyUnregistered, UserDeactivated):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Написать в поддержку", url="https://t.me/kocetu")]])
        await bot.send_message(user_id, "❌ <b>Аккаунт недействителен.</b>\n\nНапишите в поддержку для решения проблемы.", reply_markup=kb)
        await bot.send_message(ADMIN_ID, f"⚠️ <b>Внимание!</b> Слетел аккаунт у пользователя <code>{user_id}</code>.\nФайл: <code>{session_path}</code>")
    except SessionPasswordNeeded:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Написать в поддержку", url="https://t.me/kocetu")]])
        await bot.send_message(user_id, "❌ <b>Ошибка:</b> На аккаунте установлен облачный пароль (2FA).\nНапишите в поддержку.", reply_markup=kb)
    except Exception:
        pass
    finally:
        if client and client.is_connected:
            try: await client.stop()
            except Exception: pass

async def send_post_purchase_info(user_id: int):
    await asyncio.sleep(7)
    try: await bot.send_message(user_id, "Спасибо за покупку!\nне меняйте описание, юз, ник, аватарку в течении суток\nгарантия на аккаунт - 1 час")
    except Exception: pass
    await asyncio.sleep(2)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Оставить отзыв", url="https://t.me/kocetu")]])
    try: await bot.send_message(user_id, "Пожалуйста, оставьте отзыв с юзом @kocetu!", reply_markup=kb)
    except Exception: pass

@dp.message(F.text == "Админ панель")
async def admin_panel(m: Message):
    if not is_admin(m.from_user.id): return
    await m.answer("Админ панель", reply_markup=admin_kb())

@dp.message(F.text == "Статистика")
async def stats_cmd(m: Message):
    if not is_admin(m.from_user.id): return
    conn = await db()
    u_cnt = (await one(conn, "SELECT COUNT(*) as c FROM users"))["c"]
    p_cnt = (await one(conn, "SELECT COUNT(*) as c FROM purchases WHERE status='approved'"))["c"]
    s_cnt = (await one(conn, "SELECT COUNT(*) as c FROM users WHERE role='seller'"))["c"]
    season_cnt = (await one(conn, "SELECT COUNT(*) as c FROM season_accounts WHERE is_given=0"))["c"]
    season_given = (await one(conn, "SELECT COUNT(*) as c FROM season_accounts WHERE is_given=1"))["c"]
    await conn.close()
    await m.answer(
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 Пользователей: {u_cnt}\n"
        f"🏪 Продавцов: {s_cnt}\n"
        f"🛍 Покупок: {p_cnt}\n\n"
        f"🎁 <b>Сезон 1:</b>\n"
        f"• В наличии наград: {season_cnt} шт.\n"
        f"• Выдано за рефералов: {season_given} шт."
    )

@dp.message(F.text == "📥 Загрузить сезонные аккаунты")
async def start_season_bulk_add(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    await state.set_state(BulkAddSeason.uploading)
    await state.update_data(count=0)
    
    finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Закончить загрузку сезонных", callback_data="finish_bulk_season")]
    ])
    await m.answer(
        "📥 <b>Загрузка сезонных аккаунтов</b>\n\n"
        "Отправляйте файлы `.session` (можно сразу пачкой документов).\n"
        "Когда закончите, нажмите кнопку ниже:",
        reply_markup=finish_kb
    )

@dp.message(BulkAddSeason.uploading, F.document)
async def process_season_bulk_doc(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"season_{secrets.token_hex(4)}.session"
    save_path = Path("sessions/season") / file_name
    
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, save_path)
    
    full_phone = ""
    client = None
    try:
        session_name = save_path.stem
        client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(save_path.parent), in_memory=False)
        await asyncio.wait_for(client.connect(), timeout=10.0)
        me = await client.get_me()
        if me and me.phone_number:
            full_phone = f"+{me.phone_number}"
    except Exception:
        full_phone = extract_code_prefix(file_name)
    finally:
        if client and client.is_connected:
            try: await client.disconnect()
            except Exception: pass

    conn = await db()
    await conn.execute(
        "INSERT INTO season_accounts(phone, session_path, file_id, is_given, created_at) VALUES(?, ?, ?, 0, ?)",
        (full_phone or file_name, str(save_path), file_id, now_msk())
    )
    await conn.commit()
    await conn.close()

    data = await state.get_data()
    c = data.get("count", 0) + 1
    await state.update_data(count=c)

@dp.callback_query(BulkAddSeason.uploading, F.data == "finish_bulk_season")
async def finish_bulk_season_h(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cnt = data.get("count", 0)
    await state.clear()
    await call.message.edit_text(f"✅ Успешно загружено сезонных аккаунтов: <b>{cnt} шт.</b>")
    await call.message.answer("Админ панель", reply_markup=admin_kb())

@dp.message(F.text == "Склад")
async def stock_cmd(m: Message):
    if not is_admin(m.from_user.id): return
    await stock(m)

async def stock(m_or_call):
    conn = await db()
    rows = await all_rows(conn, "SELECT p.*, u.username as seller_username FROM products p LEFT JOIN users u ON p.seller_id = u.id WHERE p.stock > 0 ORDER BY p.id DESC")
    season_cnt = (await one(conn, "SELECT COUNT(*) as c FROM season_accounts WHERE is_given=0"))["c"]
    await conn.close()
    
    kb = InlineKeyboardBuilder()
    if rows:
        grouped = {}
        for p in rows:
            if p["kind"] == "account":
                code = extract_code_prefix(p["phone"] or p["name"])
                seller_id = p["seller_id"]
                price = p["price_rub"]
                try: seller_uname = p['seller_username']
                except Exception: seller_uname = None

                group_key = f"acc_{code}_{seller_id}_{price}"
                if group_key not in grouped:
                    grouped[group_key] = {"kind": "account", "code": code, "seller_id": seller_id, "seller_uname": seller_uname, "price": price, "count": 1, "ids": [p["id"]]}
                else:
                    grouped[group_key]["count"] += 1
                    grouped[group_key]["ids"].append(p["id"])
            else:
                seller_id = p["seller_id"]
                price = p["price_rub"]
                try: seller_uname = p['seller_username']
                except Exception: seller_uname = None

                group_key = f"other_{p['id']}"
                grouped[group_key] = {"kind": p["kind"], "name": p["name"], "seller_id": seller_id, "seller_uname": seller_uname, "price": price, "count": p["stock"], "ids": [p["id"]]}

        for item in grouped.values():
            if item["kind"] == "account":
                flag = get_flag(item["code"])
                cnt_str = f" ({item['count']} шт)" if item["count"] > 1 else ""
                seller_str = f" @{item['seller_uname']}" if item.get('seller_uname') else (f" ID {item['seller_id']}" if item['seller_id'] not in (0, ADMIN_ID) else "")
                btn_label = f"🗑 {flag}{item['code']} [{item['price']:.0f}₽]{cnt_str}{seller_str}"
            else:
                flag = get_flag(item["name"])
                cnt_str = f" ({item['count']} шт)" if item["count"] > 1 else ""
                seller_str = f" @{item['seller_uname']}" if item.get('seller_uname') else (f" ID {item['seller_id']}" if item['seller_id'] not in (0, ADMIN_ID) else "")
                btn_label = f"🗑 {flag}{item['name']} [{item['price']:.0f}₽]{cnt_str}{seller_str}"

            kb.button(text=btn_label, callback_data=f"del_prod_direct:{item['ids'][0]}")
            
    kb.button(text="➕ Добавить товар", callback_data="add_product")
    kb.button(text="📦 Загрузить пачку", callback_data="add_bulk_pack")
    kb.adjust(1)

    text = f"📦 <b>Управление складом:</b>\n🎁 В пуле сезонов: <b>{season_cnt} шт.</b>\n\n<i>Нажмите 🗑 напротив товара, чтобы списать единицу со склада.</i>"
    if isinstance(m_or_call, CallbackQuery):
        await m_or_call.message.edit_text(text, reply_markup=kb.as_markup())
    else:
        await m_or_call.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("del_prod_direct:"))
async def delete_single_product_direct(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split(":")[1])

    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    
    if prod:
        s_path = prod["session_path"]
        if s_path and os.path.exists(s_path):
            try: os.remove(s_path)
            except Exception: pass

        await conn.execute("DELETE FROM products WHERE id=?", (pid,))
        await conn.commit()
        await call.answer("Товар и его файл удалены со склада ✅", show_alert=True)
    else:
        await call.answer("Товар не найден", show_alert=True)
        
    await conn.close()
    await stock(call)

@dp.message(F.text == "🎁 Подарить аккаунт")
async def gift_acc_start(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    await state.set_state(GiftAccount.user_id)
    await m.answer("🎁 <b>1 этап</b> — Введите <b>Telegram ID</b> пользователя, которому хотите подарить аккаунт:")

@dp.message(GiftAccount.user_id)
async def gift_acc_user_id(m: Message, state: FSMContext):
    try: target_id = int(m.text.strip())
    except ValueError: return await m.answer("❌ Введите корректный числовой Telegram ID пользователя.")
    await state.update_data(target_user_id=target_id)
    await state.set_state(GiftAccount.session_file)
    await m.answer("🎁 <b>2 этап</b> — Отправьте <b>.session файл Pyrogram</b> документом:")

@dp.message(GiftAccount.session_file, F.document)
async def gift_acc_session(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"gift_{secrets.token_hex(4)}.session"
    save_path = Path("sessions") / file_name
    
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, save_path)
    
    await state.update_data(file_id=file_id, session_path=str(save_path))
    data = await state.get_data()
    
    text = (
        f"🎁 <b>Подтверждение подарка:</b>\n\n"
        f"👤 <b>Получатель (ID):</b> <code>{data['target_user_id']}</code>\n"
        f"📁 <b>Файл:</b> <code>{Path(save_path).name}</code>\n\n"
        f"Отправить подарок пользователю?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Отправить", callback_data="gift_confirm_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="gift_cancel")]
    ])
    await state.set_state(GiftAccount.confirm)
    await m.answer(text, reply_markup=kb)

@dp.callback_query(GiftAccount.confirm, F.data == "gift_confirm_send")
async def gift_confirm_send(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    
    target_id = data["target_user_id"]
    session_path = data["session_path"]
    file_id = data.get("file_id")
    
    conn = await db()
    cur = await conn.execute(
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone, seller_id) VALUES('account', 'Подарок', 0, 0, 0, 0, 1, ?, ?, ?, '', 0)",
        (now_msk(), file_id, session_path)
    )
    prod_id = cur.lastrowid
    await conn.commit(); await conn.close()
    
    await state.clear()
    await call.message.edit_text("✅ <b>Подарок успешно отправлен пользователю!</b>")
    
    gift_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Забрать подарок", callback_data=f"claim_gift:{prod_id}")]
    ])
    
    gift_text = "Вы получили аккаунт от Noverashop!\nЗабрать аккаунт вы можете по кнопке ниже:"
    try: await bot.send_message(target_id, gift_text, reply_markup=gift_kb)
    except Exception as e: await call.message.answer(f"⚠️ Ошибка доставки сообщения пользователю: {e}")

@dp.callback_query(GiftAccount.confirm, F.data == "gift_cancel")
async def gift_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Отменено.")
    await call.message.edit_text("❌ Отправка подарка отменена.", reply_markup=None)

@dp.callback_query(F.data == "add_bulk_pack")
async def start_bulk_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(BulkAddProduct.uploading)
    await state.update_data(files=[], prefixes=set())
    
    finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Завершить загрузку пачки", callback_data="finish_bulk_upload")]
    ])
    await call.message.answer("Скидывайте `.session` файлы пачкой. Бот сам считает номера и распределит по кодам. Нажмите кнопку ниже по окончании:", reply_markup=finish_kb)
    await call.answer()

@dp.message(BulkAddProduct.uploading, F.document)
async def process_bulk_file(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"session_{secrets.token_hex(4)}.session"
    save_path = Path("sessions") / file_name
    
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, save_path)
    
    full_phone = ""
    detected_code = "+1"
    client = None
    try:
        session_name = save_path.stem
        client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(save_path.parent), in_memory=False)
        await asyncio.wait_for(client.connect(), timeout=10.0)
        me = await client.get_me()
        if me and me.phone_number:
            full_phone = f"+{me.phone_number}"
            detected_code = extract_code_prefix(full_phone)
    except Exception:
        full_phone = extract_code_prefix(file_name)
        detected_code = extract_code_prefix(file_name)
    finally:
        if client and client.is_connected:
            try: await client.disconnect()
            except Exception: pass

    data = await state.get_data()
    files_list = data.get("files", [])
    prefixes_set = set(data.get("prefixes", []))
    
    files_list.append({"file_id": file_id, "path": str(save_path), "code": detected_code, "phone": full_phone, "name": file_name})
    prefixes_set.add(detected_code)
    await state.update_data(files=files_list, prefixes=list(prefixes_set))

@dp.callback_query(BulkAddProduct.uploading, F.data == "finish_bulk_upload")
async def finish_bulk_upload_h(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prefixes = data.get("prefixes", [])
    if not prefixes:
        return await call.answer("Вы не загрузили ни одного файла!", show_alert=True)
        
    await state.update_data(remaining_prefixes=list(prefixes), price_map={})
    await state.set_state(BulkAddProduct.pricing)
    
    next_pref = prefixes[0]
    await call.message.answer(f"Введите цену для {next_pref}\nФормат: <code>хх₽, хх звезд, хх тг</code>")
    await call.answer()

@dp.message(BulkAddProduct.pricing)
async def process_bulk_pricing(m: Message, state: FSMContext):
    text = m.text.lower()
    rub_match = re.search(r'(\d+[\.,]?\d*)\s*(?:₽|руб|rub)', text)
    stars_match = re.search(r'(\d+)\s*(?:⭐|звезд|stars)', text)
    kzt_match = re.search(r'(\d+[\.,]?\d*)\s*(?:₸|тг|kzt)', text)
    
    if not (rub_match or stars_match or kzt_match):
        nums = re.findall(r'\d+[\.,]?\d*', text)
        if len(nums) >= 3:
            p_rub = float(nums[0].replace(',', '.'))
            p_stars = int(float(nums[1]))
            p_kzt = float(nums[2].replace(',', '.'))
        else:
            return await m.answer("Не удалось определить цены. Введите в формате: <code>100₽, 50 звезд, 500 тг</code>")
    else:
        p_rub = float(rub_match.group(1).replace(',', '.')) if rub_match else 0.0
        p_stars = int(stars_match.group(1)) if stars_match else 0
        p_kzt = float(kzt_match.group(1).replace(',', '.')) if kzt_match else 0.0

    data = await state.get_data()
    remaining = data["remaining_prefixes"]
    price_map = data.get("price_map", {})
    
    curr_pref = remaining.pop(0)
    price_map[curr_pref] = {"rub": p_rub, "stars": p_stars, "kzt": p_kzt}
    
    if remaining:
        await state.update_data(remaining_prefixes=remaining, price_map=price_map)
        next_pref = remaining[0]
        await m.answer(f"Введите цену для {next_pref}\nФормат: <code>хх₽, хх звезд, хх тг</code>")
    else:
        files = data["files"]
        conn = await db()
        count_added = 0
        
        for f_item in files:
            code = f_item["code"]
            phone_num = f_item["phone"]
            prices = price_map.get(code, {"rub": 0, "stars": 0, "kzt": 0})
            
            await conn.execute(
                "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone, seller_id) VALUES('account', ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, 0)",
                (phone_num or code, prices["rub"], prices["stars"], prices["kzt"], now_msk(), f_item["file_id"], f_item["path"], phone_num or code)
            )
            count_added += 1
            
        await conn.commit(); await conn.close()
        await state.clear()
        await m.answer(f"✅ Успешно обработано и добавлено аккаунтов: <b>{count_added} шт.</b>", reply_markup=admin_kb())

@dp.callback_query(F.data == "add_product")
async def add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AddProduct.kind)
    await call.message.answer("Выберите тип товара:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аккаунт", callback_data="addkind:account")],
        [InlineKeyboardButton(text="Stars", callback_data="addkind:stars")]
    ]))
    await call.answer()

@dp.callback_query(AddProduct.kind, F.data.startswith("addkind:"))
async def add_kind(call: CallbackQuery, state: FSMContext):
    await state.update_data(kind=call.data.split(":")[1])
    await state.set_state(AddProduct.name)
    await call.message.answer("1 этап — Введите название товара (например, +1 555-1234):")
    await call.answer()

@dp.message(AddProduct.name)
async def add_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await state.set_state(AddProduct.description)
    await m.answer("2 этап — Введите описание товара (или отправьте `-` если не требуется):")

@dp.message(AddProduct.description)
async def add_description(m: Message, state: FSMContext):
    desc = "" if m.text.strip() == "-" else m.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AddProduct.price_rub)
    await m.answer("3 этап — Введите цену в ₽:")

@dp.message(AddProduct.price_rub)
async def add_rub(m: Message, state: FSMContext):
    try: price = float(m.text.replace(",", "."))
    except ValueError: return await m.answer("Введите число, например 50")
    await state.update_data(price_rub=price)
    await state.set_state(AddProduct.price_stars)
    await m.answer("4 этап — Введите цену в звездах ⭐:")

@dp.message(AddProduct.price_stars)
async def add_stars(m: Message, state: FSMContext):
    try: price = int(m.text)
    except ValueError: return await m.answer("Введите целое число, например 60")
    await state.update_data(price_stars=price)
    await state.set_state(AddProduct.price_kzt)
    await m.answer("5 этап — Введите цену в тенге ₸:")

@dp.message(AddProduct.price_kzt)
async def add_kzt(m: Message, state: FSMContext):
    try: price = float(m.text.replace(",", "."))
    except ValueError: return await m.answer("Введите число, например 3000")
    await state.update_data(price_kzt=price)
    
    d = await state.get_data()
    if d.get("kind") == "account":
        await state.set_state(AddProduct.account_file)
        await m.answer("6 этап — Отправьте `.session` файл аккаунта документом:")
    else:
        await state.set_state(AddProduct.phone)
        await m.answer("6 этап — Введите количество товара на складе:")

@dp.message(AddProduct.account_file, F.document)
async def add_account_file(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"session_{secrets.token_hex(4)}.session"
    save_path = Path("sessions") / file_name
    
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, save_path)
    
    d = await state.get_data()
    product_name = d["name"]
    kind = d["kind"]
    code_pref = extract_code_prefix(product_name)
    
    conn = await db()
    await conn.execute(
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone, seller_id, description) VALUES(?,?,?,?,?,1,0,?,?,?,?,0,?)",
        (kind, code_pref, d["price_rub"], d["price_stars"], d["price_kzt"], now_msk(), file_id, str(save_path), product_name, d.get("description", ""))
    )
    msg_text = f"✅ <b>Товар «{code_pref}» успешно создан!</b>\nКоличество: <b>1 шт.</b>"
    await conn.commit(); await conn.close()
    
    await state.clear()
    await m.answer(msg_text, reply_markup=admin_kb())

@dp.message(AddProduct.phone)
async def add_finish_stars(m: Message, state: FSMContext):
    d = await state.get_data()
    conn = await db()
    
    try: stock_cnt = int(m.text)
    except ValueError: return await m.answer("Введите целое число.")
    
    await conn.execute(
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, seller_id, description) VALUES(?,?,?,?,?,?,0,?,0,?)",
        (d["kind"], d["name"], d["price_rub"], d["price_stars"], d["price_kzt"], stock_cnt, now_msk(), d.get("description", ""))
    )
        
    await conn.commit(); await conn.close()
    await state.clear()
    await m.answer("Товар успешно добавлен на склад ✅", reply_markup=admin_kb())

@dp.message(F.text == "Рассылка")
async def broadcast_cmd(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    await state.set_state(Broadcast.text)
    await m.answer("📢 <b>Отправьте сообщение для рассылки:</b>")

@dp.message(Broadcast.text)
async def broadcast_finish(m: Message, state: FSMContext):
    await state.clear()
    conn = await db()
    users = await all_rows(conn, "SELECT id FROM users")
    await conn.close()
    
    count, blocked = 0, 0
    status_msg = await m.answer("⏳ Рассылка запущена...")
    for u in users:
        try:
            await bot.copy_message(chat_id=u["id"], from_chat_id=m.chat.id, message_id=m.message_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            blocked += 1
            
    await status_msg.edit_text(f"✅ <b>Рассылка завершена!</b>\n\n👤 Успешно: <b>{count}</b>\n🚫 Заблокировано: <b>{blocked}</b>")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
