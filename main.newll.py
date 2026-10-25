import asyncio
import html
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta
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
from pyrogram.raw import functions

logging.basicConfig(level=logging.INFO)
load_dotenv()

TOKEN = "8785831667:AAEB4PMpcUTrD_jbi7_bvaw4flnyu6g-57k"
API_ID = "31799721"
API_HASH = "eb2181220b3b8a0b6a7f93cd8075a559"

if not TOKEN:
    raise RuntimeError("Telegram bot token was not provided")

ADMIN_ID = 8872934046
CHANNEL_ID = "-1003922108499"

DB_PATH = os.getenv("DB_PATH", "data/shop.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path("sessions").mkdir(parents=True, exist_ok=True)
Path("sessions/season").mkdir(parents=True, exist_ok=True)

ACTIVE_CLIENTS: dict[str, Client] = {}

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
MSK = ZoneInfo("Europe/Moscow")

def is_admin(uid: int) -> bool:
    return int(uid) == ADMIN_ID

def now_msk() -> str:
    return datetime.now(MSK).isoformat()

def now_dt() -> datetime:
    return datetime.now(MSK)

def today_msk_prefix() -> str:
    return datetime.now(MSK).strftime("%Y-%m-%d")

CANADA_AREA_CODES = {
    "204", "226", "236", "249", "250", "289", "306", "343", "365", "367",
    "403", "416", "418", "431", "437", "438", "450", "506", "514", "519",
    "548", "579", "581", "587", "604", "613", "639", "647", "672", "705",
    "709", "778", "780", "782", "807", "819", "825", "867", "873", "902", "905"
}

PREFIX_TO_ISO = {
    "77": "KZ", "76": "KZ", "355": "AL", "213": "DZ", "376": "AD", "244": "AO",
    "54": "AR", "374": "AM", "61": "AU", "43": "AT", "994": "AZ", "973": "BH",
    "880": "BD", "375": "BY", "32": "BE", "501": "BZ", "229": "BJ", "975": "BT",
    "591": "BO", "387": "BA", "267": "BW", "55": "BR", "359": "BG", "226": "BF",
    "257": "BI", "855": "KH", "237": "CM", "238": "CV", "236": "CF", "235": "TD",
    "56": "CL", "86": "CN", "57": "CO", "269": "KM", "242": "CG", "243": "CD",
    "506": "CR", "385": "HR", "53": "CU", "357": "CY", "420": "CZ", "45": "DK",
    "253": "DJ", "593": "EC", "20": "EG", "503": "SV", "240": "GQ", "291": "ER",
    "372": "EE", "251": "ET", "679": "FJ", "358": "FI", "33": "FR", "241": "GA",
    "220": "GM", "995": "GE", "49": "DE", "233": "GH", "30": "GR", "502": "GT",
    "224": "GN", "245": "GW", "592": "GY", "509": "HT", "504": "HN", "852": "HK",
    "36": "HU", "354": "IS", "91": "IN", "62": "ID", "98": "IR", "964": "IQ",
    "353": "IE", "972": "IL", "39": "IT", "225": "CI", "81": "JP", "962": "JO",
    "254": "KE", "965": "KW", "996": "KG", "856": "LA", "371": "LV", "961": "LB",
    "266": "LS", "231": "LR", "218": "LY", "423": "LI", "370": "LT", "352": "LU",
    "853": "MO", "389": "MK", "261": "MG", "265": "MW", "60": "MY", "960": "MV",
    "223": "ML", "356": "MT", "222": "MR", "230": "MU", "52": "MX", "373": "MD",
    "377": "MC", "976": "MN", "382": "ME", "212": "MA", "258": "MZ", "95": "MM",
    "264": "NA", "977": "NP", "31": "NL", "64": "NZ", "505": "NI", "227": "NE",
    "234": "NG", "47": "NO", "968": "OM", "92": "PK", "507": "PA", "675": "PG",
    "595": "PY", "51": "PE", "63": "PH", "48": "PL", "351": "PT", "974": "QA",
    "40": "RO", "7": "RU", "250": "RW", "966": "SA", "221": "SN", "381": "RS",
    "248": "SC", "232": "SL", "65": "SG", "421": "SK", "386": "SI", "252": "SO",
    "27": "ZA", "82": "KR", "34": "ES", "94": "LK", "249": "SD", "597": "SR",
    "268": "SZ", "46": "SE", "41": "CH", "963": "SY", "886": "TW", "992": "TJ",
    "255": "TZ", "66": "TH", "228": "TG", "216": "TN", "90": "TR", "993": "TM",
    "256": "UG", "380": "UA", "971": "AE", "44": "GB", "1": "US", "598": "UY",
    "998": "UZ", "58": "VE", "84": "VN", "967": "YE", "260": "ZM", "263": "ZW"
}

ISO_TO_RU = {
    "US": "США", "CA": "Канада", "RU": "Россия", "KZ": "Казахстан", "UA": "Украина",
    "BY": "Беларусь", "UZ": "Узбекистан", "IN": "Индия", "GB": "Великобритания",
    "FR": "Франция", "DE": "Германия", "NL": "Нидерланды", "EC": "Эквадор",
    "BD": "Бангладеш", "MX": "Мексика", "IR": "Иран", "EE": "Эстония", "PL": "Польша",
    "TR": "Турция", "ID": "Индонезия", "BR": "Бразилия", "VN": "Вьетнам",
    "TH": "Таиланд", "ES": "Испания", "IT": "Италия", "EG": "Египет", "PH": "Филиппины",
    "MM": "Мьянма", "PK": "Пакистан", "NG": "Нигерия", "KE": "Кения", "ZA": "ЮАР",
    "CO": "Колумбия", "AR": "Аргентина", "PE": "Перу", "CL": "Чили", "MA": "Марокко",
    "DZ": "Алжир", "IQ": "Ирак", "SA": "Саудовская Аравия", "AE": "ОАЭ", "IL": "Израиль",
    "AZ": "Азербайджан", "AM": "Армения", "GE": "Грузия", "KG": "Кыргызстан",
    "TJ": "Таджикистан", "TM": "Туркменистан", "MD": "Молдова", "RO": "Румыния",
    "BG": "Болгария", "RS": "Сербия", "GR": "Греция", "PT": "Португалия", "CZ": "Чехия",
    "HU": "Венгрия", "AT": "Австрия", "CH": "Швейцария", "SE": "Швеция", "NO": "Норвегия",
    "FI": "Финляндия", "DK": "Дания", "SG": "Сингапур", "MY": "Малайзия", "HK": "Гонконг",
    "TW": "Тайвань", "KR": "Южная Корея", "JP": "Япония", "AU": "Австралия", "NZ": "Новая Зеландия"
}

RU_COUNTRY_TO_ISO = {v.lower(): k for k, v in ISO_TO_RU.items()}
RU_COUNTRY_TO_ISO["мм"] = "MM"
FLAG_REGEX = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
RANKS = [
    (0, 500, "new"),
    (500, 1500, "medium"),
    (1500, 5000, "hard"),
    (5000, 10000, "legend"),
    (10000, 999999999, "legend of novera")
]

def get_rank_info(total_spent: float):
    for low, high, title in RANKS:
        if low <= total_spent < high:
            diff = high - low
            current = total_spent - low
            pct = min(1.0, max(0.0, current / diff)) if diff > 0 else 1.0
            filled = int(pct * 10)
            bar = "▰" * filled + "▱" * (10 - filled)
            need_more = high - total_spent
            return title, bar, int(pct * 100), need_more, high
    title = RANKS[-1][2]
    return title, "▰" * 10, 100, 0, total_spent

def iso_to_flag(iso_code: str) -> str:
    if not iso_code or len(iso_code) != 2:
        return ""
    iso_code = iso_code.upper()
    return chr(0x1F1E6 + ord(iso_code[0]) - 65) + chr(0x1F1E6 + ord(iso_code[1]) - 65)

def extract_only_prefix(raw_text: str) -> str:
    digits = re.sub(r"\D", "", raw_text or "")
    if not digits:
        return "+1"
    sorted_prefixes = sorted(PREFIX_TO_ISO.keys(), key=lambda x: len(x), reverse=True)
    for pref in sorted_prefixes:
        if digits.startswith(pref):
            return f"+{pref}"
    return f"+{digits[0]}"

def extract_phone_and_country(raw_text: str) -> tuple[str, str, str]:
    text_clean = (raw_text or "").strip()
    text_lower = text_clean.lower()

    if "канад" in text_lower or re.search(r'\bca\b', text_lower):
        return "+1", "CA", "Канада"

    for iso_code, ru_name in ISO_TO_RU.items():
        if iso_code != "CA" and re.search(rf"\b{re.escape(iso_code.lower())}\b", text_lower):
            for p_code, iso_match in PREFIX_TO_ISO.items():
                if iso_match == iso_code:
                    return f"+{p_code}", iso_code, ru_name

    for cname_ru, iso_val in RU_COUNTRY_TO_ISO.items():
        if iso_val != "CA" and re.search(rf"\b{re.escape(cname_ru)}\b", text_lower):
            for p_code, iso_match in PREFIX_TO_ISO.items():
                if iso_match == iso_val:
                    return f"+{p_code}", iso_val, ISO_TO_RU.get(iso_val, cname_ru.capitalize())

    digits = re.sub(r"\D", "", raw_text or "")
    if not digits:
        return "+1", "US", "США"
    
    if digits.startswith("1"):
        if len(digits) >= 4 and digits[1:4] in CANADA_AREA_CODES:
            return "+1", "CA", "Канада"
        return "+1", "US", "США"

    sorted_prefixes = sorted(PREFIX_TO_ISO.keys(), key=lambda x: len(x), reverse=True)
    for pref in sorted_prefixes:
        if digits.startswith(pref):
            iso = PREFIX_TO_ISO[pref]
            cname = ISO_TO_RU.get(iso, "Аккаунт")
            return f"+{pref}", iso, cname

    return f"+{digits[0]}", "US", "США"

def get_flag_by_country_or_phone(name_or_phone: str) -> str:
    if not name_or_phone:
        return ""
    if FLAG_REGEX.search(name_or_phone):
        return ""
    _, iso, _ = extract_phone_and_country(name_or_phone)
    f = iso_to_flag(iso)
    return f + " " if f else ""

def strike_through(text: str) -> str:
    return "".join(c + "\u0336" for c in text)

def format_product_button_title(raw_name: str, price_rub: float, discount_percent: int = 0) -> str:
    clean = raw_name.strip()
    is_sb = bool(re.search(r'(со спамблоком|спамблок|\bсб\b)', clean, re.IGNORECASE) and not re.search(r'без', clean, re.IGNORECASE))
    
    prefix, iso, cname = extract_phone_and_country(clean)
    flag = iso_to_flag(iso)
    flag_str = f"{flag} " if flag else ""
    sb_suffix = " [СБ]" if is_sb else ""
    
    if discount_percent > 0:
        disc_price = max(1.0, price_rub * ((100 - discount_percent) / 100.0))
        striked = strike_through(f"{price_rub:.0f}₽")
        return f"{flag_str}{cname} ({prefix}){sb_suffix} [{striked} {disc_price:.0f}₽]"
    
    return f"{flag_str}{cname} ({prefix}){sb_suffix} [{price_rub:.0f}₽]"

def find_session_path(s_name: str) -> Path | None:
    for folder in [Path("sessions"), Path("sessions/season")]:
        candidate = folder / s_name
        if candidate.exists():
            return candidate
    return None

def clear_session_locks(session_path: Path):
    for ext in ["-journal", "-wal", "-shm"]:
        lock_file = Path(f"{session_path}{ext}")
        if lock_file.exists():
            try: os.remove(lock_file)
            except Exception: pass

async def stop_existing_client(session_path: str):
    s_key = str(Path(session_path).resolve())
    if s_key in ACTIVE_CLIENTS:
        old_cli = ACTIVE_CLIENTS.pop(s_key)
        try:
            if old_cli.is_connected:
                await old_cli.stop()
        except Exception:
            pass
    clear_session_locks(Path(session_path))

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
        total_spent REAL NOT NULL DEFAULT 0,
        referrer_id INTEGER DEFAULT NULL,
        ref_count INTEGER NOT NULL DEFAULT 0,
        season_claimed INTEGER NOT NULL DEFAULT 0,
        agreed_terms INTEGER NOT NULL DEFAULT 0,
        active_discount_percent INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        kind TEXT NOT NULL, 
        name TEXT NOT NULL, 
        price_rub REAL NOT NULL, 
        price_stars INTEGER NOT NULL DEFAULT 0, 
        price_kzt REAL NOT NULL DEFAULT 0, 
        stock INTEGER NOT NULL DEFAULT 0, 
        sales INTEGER NOT NULL DEFAULT 0, 
        created_at TEXT NOT NULL, 
        file_id TEXT, 
        phone TEXT, 
        session_path TEXT,
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
        session_path TEXT,
        qty INTEGER NOT NULL DEFAULT 1,
        session_paths_json TEXT,
        applied_disc INTEGER NOT NULL DEFAULT 0,
        applied_promo INTEGER NOT NULL DEFAULT 0
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
    CREATE TABLE IF NOT EXISTS required_channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        invite_link TEXT,
        until_ts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS promo_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        discount_percent INTEGER NOT NULL,
        max_uses INTEGER NOT NULL,
        current_uses INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_promo_uses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        used_at TEXT NOT NULL,
        UNIQUE(user_id, code)
    );
    CREATE TABLE IF NOT EXISTS global_discounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type TEXT NOT NULL,
        target_name TEXT,
        discount_percent INTEGER NOT NULL,
        until_ts INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS bot_settings(
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    cur = await conn.execute("PRAGMA table_info(purchases)")
    cols_purchases = [r[1] for r in await cur.fetchall()]
    await cur.close()

    if "applied_disc" not in cols_purchases:
        try: await conn.execute("ALTER TABLE purchases ADD COLUMN applied_disc INTEGER NOT NULL DEFAULT 0")
        except Exception: pass
    if "applied_promo" not in cols_purchases:
        try: await conn.execute("ALTER TABLE purchases ADD COLUMN applied_promo INTEGER NOT NULL DEFAULT 0")
        except Exception: pass

    cur = await conn.execute("PRAGMA table_info(users)")
    cols_users = [r[1] for r in await cur.fetchall()]
    await cur.close()

    if "agreed_terms" not in cols_users:
        try: await conn.execute("ALTER TABLE users ADD COLUMN agreed_terms INTEGER NOT NULL DEFAULT 0")
        except Exception: pass
    if "active_discount_percent" not in cols_users:
        try: await conn.execute("ALTER TABLE users ADD COLUMN active_discount_percent INTEGER NOT NULL DEFAULT 0")
        except Exception: pass

    cur = await conn.execute("PRAGMA table_info(products)")
    cols_products = [r[1] for r in await cur.fetchall()]
    await cur.close()

    if "price_stars" not in cols_products:
        try: await conn.execute("ALTER TABLE products ADD COLUMN price_stars INTEGER NOT NULL DEFAULT 0")
        except Exception: pass

    await conn.execute("DELETE FROM products WHERE kind='stars'")
    await conn.commit()

    if CHANNEL_ID:
        try:
            await conn.execute(
                "INSERT OR IGNORE INTO required_channels(channel_id, title, invite_link, until_ts, created_at) VALUES(?, 'Основной канал', '', 0, ?)",
                (str(CHANNEL_ID), now_msk())
            )
        except Exception: pass

    await conn.commit()
    await conn.close()

async def get_tech_works_config() -> tuple[bool, str]:
    conn = await db()
    status_row = await one(conn, "SELECT value FROM bot_settings WHERE key='tech_works_enabled'")
    text_row = await one(conn, "SELECT value FROM bot_settings WHERE key='tech_works_text'")
    await conn.close()
    enabled = bool(status_row and status_row["value"] == "1")
    text = text_row["value"] if text_row and text_row["value"] else "🔧 <b>Ведутся технические работы. Пожалуйста, подождите.</b>"
    return enabled, text

async def set_tech_works_config(enabled: bool, text: str = None):
    conn = await db()
    await conn.execute("INSERT OR REPLACE INTO bot_settings(key, value) VALUES('tech_works_enabled', ?)", ("1" if enabled else "0",))
    if text is not None:
        await conn.execute("INSERT OR REPLACE INTO bot_settings(key, value) VALUES('tech_works_text', ?)", (text,))
    await conn.commit()
    await conn.close()

async def get_active_channels():
    conn = await db()
    rows = await all_rows(conn, "SELECT * FROM required_channels")
    await conn.close()
    
    current_ts = int(time.time())
    active = []
    for r in rows:
        if r["until_ts"] == 0 or r["until_ts"] > current_ts:
            active.append(r)
    return active

async def check_user_subscriptions(user_id: int) -> tuple[bool, list[dict]]:
    channels = await get_active_channels()
    if not channels:
        return True, []

    missing = []
    for ch in channels:
        ch_id_val = ch["channel_id"]
        chat_identifier = int(ch_id_val) if (ch_id_val.startswith("-") or ch_id_val.isdigit()) else ch_id_val
        try:
            member = await bot.get_chat_member(chat_id=chat_identifier, user_id=user_id)
            if member.status not in ("creator", "administrator", "member"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
            
    return len(missing) == 0, missing

async def get_store_discount_for_product(product_name: str) -> int:
    conn = await db()
    current_ts = int(time.time())
    await conn.execute("DELETE FROM global_discounts WHERE until_ts <= ?", (current_ts,))
    await conn.commit()

    all_disc = await one(conn, "SELECT MAX(discount_percent) as m FROM global_discounts WHERE target_type='all'")
    max_all = all_disc["m"] if (all_disc and all_disc["m"] is not None) else 0

    item_disc = await one(conn, "SELECT MAX(discount_percent) as m FROM global_discounts WHERE target_type='item' AND target_name=?", (product_name,))
    max_item = item_disc["m"] if (item_disc and item_disc["m"] is not None) else 0
    await conn.close()

    return max(max_all, max_item)

async def get_user_promo_discount(user_id: int) -> int:
    conn = await db()
    u_row = await one(conn, "SELECT active_discount_percent FROM users WHERE id=?", (user_id,))
    await conn.close()
    return u_row["active_discount_percent"] if (u_row and u_row["active_discount_percent"]) else 0
def home_kb(uid: int):
    kb = ReplyKeyboardBuilder()
    kb.button(text="Каталог")
    kb.button(text="Профиль")
    kb.button(text="Отзывы")
    kb.button(text="Поддержка")
    kb.button(text="Сезоны раздач")
    if is_admin(uid): 
        kb.button(text="Панель управления")
    kb.adjust(1, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def admin_inline_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="adm_nav:stats")
    kb.button(text="🏆 Топ рефералов", callback_data="adm_nav:top_ref")
    kb.button(text="📦 Склад", callback_data="adm_nav:stock")
    kb.button(text="📢 Каналы подписки", callback_data="adm_nav:channels")
    kb.button(text="🎁 Подарить аккаунт", callback_data="adm_nav:gift")
    kb.button(text="📥 Загрузить сезонные", callback_data="adm_nav:season")
    kb.button(text="🏷 Скидки", callback_data="adm_nav:discounts")
    kb.button(text="✉️ Рассылка", callback_data="adm_nav:broadcast")
    kb.button(text="🛠 ТЕХ РАБОТЫ", callback_data="adm_nav:tech_works")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()

def terms_kb(referrer_param: str = None):
    kb = InlineKeyboardBuilder()
    cb_data = f"accept_terms_{referrer_param}" if referrer_param else "accept_terms"
    kb.button(text="Подтвердить", callback_data=cb_data)
    kb.adjust(1)
    return kb.as_markup()

async def send_terms_agreement(target, referrer_param: str = None):
    text = (
        "<b>Ознакомление с правилами:</b>\n\n"
        "Для продолжения работы подтвердите согласие со следующими документами:\n"
        "• <a href='https://telegra.ph/POLITIKA-KONFEDECIALNOSTI-10-19'>Политика конфиденциальности</a>\n"
        "• <a href='https://telegra.ph/POLZOVATELSKOE-SOGLASHENIE-10-19-42'>Пользовательское соглашение</a>\n\n"
        "Нажмите кнопку <b>«Подтвердить»</b> ниже для входа в сервис."
    )
    kb = terms_kb(referrer_param)
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await target.answer(text, reply_markup=kb, disable_web_page_preview=True)

class AddProduct(StatesGroup):
    kind = State()
    name = State()
    description = State()
    price_rub = State()
    price_stars = State()
    price_kzt = State()
    account_file = State()

class BulkAddProduct(StatesGroup):
    uploading = State()
    pricing = State()

class RestockProduct(StatesGroup):
    uploading = State()

class EditPriceGroup(StatesGroup):
    target_name = State()
    pricing = State()

class BulkAddSeason(StatesGroup):
    uploading = State()

class AddSubChannel(StatesGroup):
    channel = State()
    hours = State()

class GiftAccount(StatesGroup):
    user_id = State()
    session_file = State()
    confirm = State()

class Broadcast(StatesGroup):
    text = State()

class PaymentState(StatesGroup):
    waiting_for_proof = State()

class EnterPromoState(StatesGroup):
    code = State()

class CreatePromoState(StatesGroup):
    code = State()
    percent = State()
    max_uses = State()
    confirm = State()

class CreateDiscountState(StatesGroup):
    target_type = State()
    target_name = State()
    percent = State()
    hours = State()
    confirm = State()

class TechWorksState(StatesGroup):
    text = State()
    confirm = State()

@dp.message.outer_middleware()
async def tech_works_message_middleware(handler, event: Message, data: dict):
    if event.from_user and is_admin(event.from_user.id):
        return await handler(event, data)
    
    enabled, tech_text = await get_tech_works_config()
    if enabled:
        try:
            await event.answer(tech_text)
        except Exception:
            pass
        return
    return await handler(event, data)

@dp.callback_query.outer_middleware()
async def tech_works_callback_middleware(handler, event: CallbackQuery, data: dict):
    if event.from_user and is_admin(event.from_user.id):
        return await handler(event, data)
    
    enabled, tech_text = await get_tech_works_config()
    if enabled:
        try:
            await event.answer("Технические работы", show_alert=True)
            await event.message.answer(tech_text)
        except Exception:
            pass
        return
    return await handler(event, data)

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

    ref_count = row["ref_count"]
    claimed_count = row["season_claimed"]
    available_rewards = (ref_count // 15) - claimed_count

    if available_rewards > 0:
        season_acc = await one(conn, "SELECT * FROM season_accounts WHERE is_given=0 ORDER BY id ASC LIMIT 1")
        if season_acc:
            await conn.execute("UPDATE season_accounts SET is_given=1, given_to=? WHERE id=?", (referrer_id, season_acc["id"]))
            await conn.execute("UPDATE users SET season_claimed = season_claimed + 1 WHERE id=?", (referrer_id,))
            await conn.commit()
            await conn.close()

            claim_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Забрать аккаунт", callback_data=f"claim_season_acc:{season_acc['id']}")]
            ])
            try:
                await bot.send_message(
                    referrer_id,
                    "<b>Условия первого сезона выполнены!</b>\n"
                    f"Вы набрали очередные <b>15 пользователей</b> (всего: <b>{ref_count}</b>).\n"
                    "Счетчик текущего круга обновлен.\n\n"
                    "Заберите ваш бесплатный аккаунт по кнопке ниже:",
                    reply_markup=claim_kb
                )
            except Exception:
                pass
        else:
            await conn.close()
            try:
                await bot.send_message(
                    referrer_id,
                    "<b>Условия первого сезона выполнены!</b>\n"
                    f"Вы набрали необходимое число рефералов (всего: <b>{ref_count}</b>).\n\n"
                    "Пул аккаунтов временно пуст. Аккаунт будет выдан сразу после пополнения."
                )
            except Exception:
                pass
    else:
        await conn.close()

async def send_sub_request(message_or_call, missing_channels: list, referrer_param: str = None):
    kb = InlineKeyboardBuilder()
    for ch in missing_channels:
        link = ch["invite_link"]
        if not link:
            ch_val = ch["channel_id"]
            chat_id = int(ch_val) if (ch_val.startswith("-") or ch_val.isdigit()) else ch_val
            try:
                c_info = await bot.get_chat(chat_id)
                link = c_info.invite_link or (f"https://t.me/{c_info.username}" if c_info.username else None)
            except Exception:
                pass
        kb.button(text=f"Подписаться: {ch['title']}", url=link or "https://t.me/")

    cb_data = f"check_sub_{referrer_param}" if referrer_param else "check_subscription"
    kb.button(text="Проверить подписку", callback_data=cb_data)
    kb.adjust(1)
    
    text_msg = (
        "<b>Доступ ограничен.</b>\n\n"
        "Для продолжения работы с сервисом необходимо подписаться на каналы спонсоров.\n"
        "После вступления нажмите кнопку «Проверить подписку»."
    )
    
    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.answer(text_msg, reply_markup=kb.as_markup())
    else:
        await message_or_call.answer(text_msg, reply_markup=kb.as_markup())
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
            "INSERT INTO users (id, username, first_name, created_at, referrer_id, agreed_terms) VALUES(?,?,?,?,?,1)",
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
    else:
        await conn.execute("UPDATE users SET agreed_terms=1 WHERE id=?", (user.id,))
        await conn.commit()
    await conn.close()

def parse_pricing_line(raw_text: str) -> tuple[float, int, float, bool]:
    text = raw_text.lower().strip()
    is_sb = bool(re.search(r'(со спамблоком|спамблок|\bсб\b)', text) and not re.search(r'без', text))
    
    rub_match = re.search(r'(\d+[\.,]?\d*)\s*(?:₽|руб|rub)', text)
    stars_match = re.search(r'(\d+)\s*(?:⭐|звезд|stars)', text)
    kzt_match = re.search(r'(\d+[\.,]?\d*)\s*(?:₸|тг|kzt)', text)
    
    p_rub = float(rub_match.group(1).replace(',', '.')) if rub_match else None
    p_stars = int(stars_match.group(1)) if stars_match else None
    p_kzt = float(kzt_match.group(1).replace(',', '.')) if kzt_match else None

    if p_rub is None or p_stars is None or p_kzt is None:
        clean_text = re.sub(r'(без сб|со спамблоком|спамблок|\bсб\b|без спамблока)', '', text)
        nums = re.findall(r'\d+[\.,]?\d*', clean_text)
        if len(nums) >= 3:
            p_rub = float(nums[0].replace(',', '.')) if p_rub is None else p_rub
            p_stars = int(float(nums[1].replace(',', '.'))) if p_stars is None else p_stars
            p_kzt = float(nums[2].replace(',', '.')) if p_kzt is None else p_kzt
        elif len(nums) == 2:
            p_rub = float(nums[0].replace(',', '.')) if p_rub is None else p_rub
            p_stars = int(p_rub) if p_stars is None else p_stars
            p_kzt = float(nums[1].replace(',', '.')) if p_kzt is None else p_kzt
        elif len(nums) == 1:
            p_rub = float(nums[0].replace(',', '.')) if p_rub is None else p_rub
            p_stars = int(p_rub) if p_stars is None else p_stars
            p_kzt = float(p_rub * 6.0) if p_kzt is None else p_kzt

    p_rub = float(p_rub if p_rub is not None else 0.0)
    p_stars = int(p_stars if p_stars is not None else int(p_rub))
    p_kzt = float(p_kzt if p_kzt is not None else float(p_rub * 6.0))

    return p_rub, p_stars, p_kzt, is_sb

@dp.callback_query(F.data.startswith("accept_terms"))
async def accept_terms_callback(call: CallbackQuery):
    await call.answer("Согласие принято")
    referrer_id = None
    if call.data.startswith("accept_terms_"):
        raw_ref = call.data.replace("accept_terms_", "")
        if raw_ref.isdigit():
            referrer_id = int(raw_ref)

    conn = await db()
    user = await one(conn, "SELECT id FROM users WHERE id=?", (call.from_user.id,))
    if user:
        await conn.execute("UPDATE users SET agreed_terms=1 WHERE id=?", (call.from_user.id,))
        await conn.commit()
    else:
        await finalize_user_registration(call.from_user, referrer_id)
    await conn.close()

    try: await call.message.delete()
    except Exception: pass

    is_ok, missing = await check_user_subscriptions(call.from_user.id)
    if not is_ok:
        ref_arg = str(referrer_id) if referrer_id else None
        return await send_sub_request(call, missing, ref_arg)

    name = call.from_user.first_name or call.from_user.username or "пользователь"
    await call.message.answer(
        f"<b>Добро пожаловать, {name}.</b>\n"
        "Главное меню сервиса доступно ниже:",
        reply_markup=home_kb(call.from_user.id)
    )

@dp.callback_query(F.data.startswith("check_sub"))
async def recheck_sub(call: CallbackQuery, state: FSMContext):
    referrer_id = None
    if call.data.startswith("check_sub_"):
        raw_ref = call.data.replace("check_sub_", "")
        if raw_ref.isdigit():
            referrer_id = int(raw_ref)

    is_ok, missing = await check_user_subscriptions(call.from_user.id)
    if is_ok:
        conn = await db()
        user = await one(conn, "SELECT agreed_terms FROM users WHERE id=?", (call.from_user.id,))
        await conn.close()
        
        if not user or not user["agreed_terms"]:
            return await send_terms_agreement(call, str(referrer_id) if referrer_id else None)

        await finalize_user_registration(call.from_user, referrer_id)
        await call.answer("Подписка подтверждена.", show_alert=True)
        try: await call.message.delete()
        except Exception: pass
        name = call.from_user.first_name or call.from_user.username or "пользователь"
        await call.message.answer(
            f"<b>Добро пожаловать, {name}.</b>\n"
            "Главное меню сервиса доступно ниже:",
            reply_markup=home_kb(call.from_user.id)
        )
    else:
        await call.answer("Вы подписались не на все обязательные каналы.", show_alert=True)

@dp.message(CommandStart())
async def start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)

    conn = await db()
    user = await one(conn, "SELECT id, agreed_terms FROM users WHERE id=?", (m.from_user.id,))
    await conn.close()

    if not user or not user["agreed_terms"]:
        ref_arg = str(referrer_id) if referrer_id else None
        return await send_terms_agreement(m, ref_arg)

    is_ok, missing = await check_user_subscriptions(m.from_user.id)
    if not is_ok:
        ref_arg = str(referrer_id) if referrer_id else None
        return await send_sub_request(m, missing, ref_arg)

    name = m.from_user.first_name or m.from_user.username or "пользователь"
    await m.answer(
        f"<b>Добро пожаловать, {name}.</b>\n"
        "Главное меню сервиса доступно ниже:",
        reply_markup=home_kb(m.from_user.id)
    )

@dp.message(F.text == "Назад")
async def back_home(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("<b>Главное меню</b>", reply_markup=home_kb(m.from_user.id))
@dp.message(F.text == "Каталог")
async def open_catalog(m: Message):
    is_ok, missing = await check_user_subscriptions(m.from_user.id)
    if not is_ok: return await send_sub_request(m, missing)

    conn = await db()
    rows = await all_rows(conn, "SELECT * FROM products WHERE kind='account' AND stock>0 ORDER BY id DESC")
    await conn.close()

    if not rows:
        return await m.answer("<b>Аккаунты в наличии:</b>\n\n<i>Товары временно отсутствуют на складе.</i>", reply_markup=home_kb(m.from_user.id))

    grouped = {}
    for p in rows:
        name_display = p["name"]
        price = float(p["price_rub"])
        group_key = f"{name_display}_{price:.0f}"

        if group_key not in grouped:
            grouped[group_key] = {"name": name_display, "price": price, "prod_id": p["id"], "count": 1}
        else:
            grouped[group_key]["count"] += 1

    kb = InlineKeyboardBuilder()
    for item in grouped.values():
        store_disc = await get_store_discount_for_product(item["name"])
        btn_text = format_product_button_title(item["name"], item["price"], store_disc)
        kb.button(text=btn_text, callback_data=f"select_acc_qty:{item['prod_id']}")

    kb.adjust(1)
    await m.answer("<b>Аккаунты в наличии:</b>\nВыберите позицию:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("select_acc_qty:"))
async def select_acc_qty_menu(call: CallbackQuery):
    is_ok, missing = await check_user_subscriptions(call.from_user.id)
    if not is_ok: return await send_sub_request(call, missing)
    await call.answer()
    pid = int(call.data.split(":")[1])

    conn = await db()
    target_sample = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    if not target_sample:
        await conn.close()
        return await call.message.answer("Позиция не найдена.")

    target_name = target_sample["name"]
    target_price = float(target_sample["price_rub"])

    available_items = await all_rows(
        conn,
        "SELECT id FROM products WHERE kind='account' AND stock>0 AND name=? AND price_rub=?",
        (target_name, target_price)
    )
    await conn.close()

    total_stock = len(available_items)
    if total_stock <= 0:
        return await call.message.answer("Данная позиция только что была распродана.")

    store_disc = await get_store_discount_for_product(target_name)
    btn_title = format_product_button_title(target_name, target_price, store_disc)
    kb = InlineKeyboardBuilder()

    allowed_buttons = [1, 2, 4, 5, 10, 50]
    for qty in allowed_buttons:
        if qty <= total_stock:
            kb.button(text=f"{qty} шт", callback_data=f"buy_group:{pid}:{qty}")

    kb.button(text=f"Купить все ({total_stock} шт)", callback_data=f"buy_group:{pid}:{total_stock}")
    kb.button(text="« Назад в каталог", callback_data="back_to_catalog")
    kb.adjust(2, 2, 2, 1, 1)

    await call.message.answer(
        f"<b>Товар:</b> {btn_title}\n\n"
        f"<b>В наличии:</b> <code>{total_stock}</code> шт.\n"
        "<b>Выберите количество:</b>",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "back_to_catalog")
async def back_to_catalog_btn(call: CallbackQuery):
    await call.answer()
    await call.message.delete()
    await open_catalog(call.message)

@dp.callback_query(F.data.startswith("buy_group:"))
async def buy_group_step(call: CallbackQuery):
    is_ok, missing = await check_user_subscriptions(call.from_user.id)
    if not is_ok: return await send_sub_request(call, missing)
    await call.answer()
    _, pid_str, qty_str = call.data.split(":")
    pid = int(pid_str)
    qty = int(qty_str)

    conn = await db()
    target_sample = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    if not target_sample:
        await conn.close()
        return await call.message.answer("Позиция не найдена.")

    t_name = target_sample["name"]
    t_price = float(target_sample["price_rub"])

    in_stock = await all_rows(conn, "SELECT id FROM products WHERE kind='account' AND stock>0 AND name=? AND price_rub=?", (t_name, t_price))
    await conn.close()

    if len(in_stock) < qty:
        return await call.message.answer(f"Недостаточно товара на складе. Доступно: {len(in_stock)} шт.")

    store_disc = await get_store_discount_for_product(t_name)
    user_promo = await get_user_promo_discount(call.from_user.id)
    total_disc = min(95, store_disc + user_promo)
    multiplier = (100 - total_disc) / 100.0

    base_rub = float(target_sample["price_rub"]) * qty
    base_stars = int(target_sample["price_stars"] or int(target_sample["price_rub"])) * qty
    base_kzt = float(target_sample["price_kzt"] or float(target_sample["price_rub"] * 6.0)) * qty

    final_rub = max(1.0, base_rub * multiplier)
    final_stars = max(1, int(base_stars * multiplier))
    final_kzt = max(1.0, base_kzt * multiplier)

    disc_info_lines = []
    if store_disc > 0:
        disc_info_lines.append(f"🔥 <b>СКИДКА!</b> <code>{store_disc}%</code>")
    if user_promo > 0:
        disc_info_lines.append(f"🏷️ <b>ПРОМО:</b> <code>{user_promo}%</code>")

    disc_text_block = ("\n\n" + "\n".join(disc_info_lines)) if disc_info_lines else ""

    kb_list = [
        [InlineKeyboardButton(text=f"Карта: {final_rub:.0f} ₽", callback_data=f"paygrp:{pid}:{qty}:rub")],
        [InlineKeyboardButton(text=f"Stars: {final_stars} ⭐", callback_data=f"paygrp:{pid}:{qty}:stars")],
        [InlineKeyboardButton(text=f"Kaspi: {final_kzt:.0f} ₸", callback_data=f"paygrp:{pid}:{qty}:kzt")]
    ]
    btn_title = format_product_button_title(t_name, t_price, store_disc)

    await call.message.answer(
        f"<b>Оформление покупки</b>\n\n"
        f"<b>Товар:</b> {btn_title}\n"
        f"<b>Количество:</b> <code>{qty}</code> шт.{disc_text_block}\n\n"
        "Выберите способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list)
    )

@dp.callback_query(F.data.startswith("paygrp:"))
async def process_payment_info_group(call: CallbackQuery, state: FSMContext):
    is_ok, missing = await check_user_subscriptions(call.from_user.id)
    if not is_ok: return await send_sub_request(call, missing)
    await call.answer()
    _, pid_str, qty_str, pay_type = call.data.split(":")
    pid = int(pid_str)
    qty = int(qty_str)

    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    if not prod:
        await conn.close()
        return await call.message.answer("Товар не найден.")

    items = await all_rows(conn, "SELECT id FROM products WHERE kind='account' AND stock>0 AND name=? AND price_rub=?", (prod["name"], prod["price_rub"]))
    if len(items) < qty:
        await conn.close()
        return await call.message.answer("Выбранное количество уже раскупили. Попробуйте выбрать меньшее число.")

    await conn.close()

    store_disc = await get_store_discount_for_product(prod["name"])
    user_promo = await get_user_promo_discount(call.from_user.id)
    total_disc = min(95, store_disc + user_promo)
    multiplier = (100 - total_disc) / 100.0

    await state.update_data(
        product_id=pid,
        qty=qty,
        pay_type=pay_type,
        store_disc=store_disc,
        user_promo=user_promo,
        total_disc=total_disc
    )
    await state.set_state(PaymentState.waiting_for_proof)

    tot_rub = max(1.0, (float(prod['price_rub']) * qty) * multiplier)
    tot_stars = max(1, int((int(prod['price_stars'] or int(prod['price_rub'])) * qty) * multiplier))
    tot_kzt = max(1.0, (float(prod['price_kzt'] or float(prod['price_rub'] * 6.0)) * qty) * multiplier)

    if pay_type == "rub":
        text_msg = (
            "<b>Реквизиты для оплаты:</b>\n\n"
            f"<b>Количество:</b> <code>{qty}</code> шт.\n"
            f"<b>Сумма к переводу:</b> <code>{tot_rub:.0f}</code> ₽\n"
            "<b>Номер счета:</b> <code>+79313716777</code>\n"
            "<b>Банк:</b> Т-Банк\n"
            "<b>Получатель:</b> Наталья / Тимур\n\n"
            "<b>Важно:</b> После оплаты отправьте чек в ответном сообщении."
        )
    elif pay_type == "stars":
        text_msg = (
            "<b>Оплата Telegram Stars:</b>\n\n"
            f"<b>Количество:</b> <code>{qty}</code> шт.\n"
            f"<b>Сумма к переводу:</b> <code>{tot_stars}</code> ⭐\n"
            "<b>Получатель:</b> @kocetu\n\n"
            "<b>Важно:</b> Переведите звёзды и отправьте подтверждающий скриншот в ответном сообщении."
        )
    else:
        text_msg = (
            "<b>Реквизиты для оплаты:</b>\n\n"
            f"<b>Количество:</b> <code>{qty}</code> шт.\n"
            f"<b>Сумма к переводу:</b> <code>{tot_kzt:.0f}</code> ₸\n"
            "<b>Номер карты:</b> <code>4400430024650860</code>\n"
            "<b>Банк:</b> Kaspi\n"
            "<b>Получатель:</b> Айдана.С.\n\n"
            "<b>Важно:</b> После перевода отправьте чек в ответном сообщении."
        )

    await call.message.answer(text_msg)
@dp.message(PaymentState.waiting_for_proof, F.photo | F.document)
async def process_payment_proof(m: Message, state: FSMContext):
    is_ok, missing = await check_user_subscriptions(m.from_user.id)
    if not is_ok: return await send_sub_request(m, missing)
    data = await state.get_data()
    pid = data.get("product_id")
    qty = int(data.get("qty", 1))
    pay_type = data.get("pay_type", "rub")
    store_disc = data.get("store_disc", 0)
    user_promo = data.get("user_promo", 0)
    total_disc = data.get("total_disc", 0)
    multiplier = (100 - total_disc) / 100.0
    
    conn = await db()
    selected_prod = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    if not selected_prod:
        await conn.close()
        await state.clear()
        return await m.answer("Выбранный товар не найден в базе.")

    allocated_sessions = []
    items = await all_rows(
        conn,
        "SELECT id, session_path FROM products WHERE kind='account' AND stock>0 AND name=? AND price_rub=? ORDER BY id ASC LIMIT ?",
        (selected_prod["name"], selected_prod["price_rub"], qty)
    )
    if len(items) < qty:
        await conn.close()
        await state.clear()
        return await m.answer("Недостаточно товара на складе. Заявка отменена.")

    for it in items:
        allocated_sessions.append(it["session_path"])
        await conn.execute("UPDATE products SET stock = 0, sales = sales + 1 WHERE id=?", (it["id"],))

    photo_id = m.photo[-1].file_id if m.photo else m.document.file_id
    if pay_type == "rub":
        amount = max(1.0, (float(selected_prod["price_rub"]) * qty) * multiplier)
        pay_symbol = "₽"
    elif pay_type == "stars":
        amount = max(1, int(((selected_prod["price_stars"] or int(selected_prod["price_rub"])) * qty) * multiplier))
        pay_symbol = "⭐"
    else:
        amount = max(1.0, ((selected_prod["price_kzt"] or float(selected_prod["price_rub"] * 6.0)) * qty) * multiplier)
        pay_symbol = "₸"

    first_sess = allocated_sessions[0] if allocated_sessions else ""
    cur = await conn.execute(
        "INSERT INTO purchases(user_id, product_id, product_name, payment, amount, screenshot_file_id, status, created_at, session_path, qty, session_paths_json, applied_disc, applied_promo) VALUES(?,?,?,?,?,?,'pending',?,?,?,?,?,?)",
        (m.from_user.id, selected_prod["id"], selected_prod["name"], pay_type, amount, photo_id, now_msk(), first_sess, qty, json.dumps(allocated_sessions), store_disc, user_promo)
    )
    purch_id = cur.lastrowid

    await conn.execute("UPDATE users SET active_discount_percent = 0 WHERE id = ?", (m.from_user.id,))
    await conn.commit()
    await conn.close()
    await state.clear()

    await m.answer(
        "<b>Чек отправлен на проверку.</b>\n"
        f"Номер заказа: <b>#{purch_id}</b>\n"
        "Ожидайте подтверждения платежа администратором."
    )

    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Одобрить", callback_data=f"adm_approve:{purch_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"adm_reject:{purch_id}")
        ]
    ])
    
    user_info = f"@{m.from_user.username}" if m.from_user.username else f"ID {m.from_user.id}"
    disp_name = selected_prod["name"]
    flag = get_flag_by_country_or_phone(disp_name)
    
    disc_adm_lines = []
    if store_disc > 0:
        disc_adm_lines.append(f"🔥 <b>Скидка:</b> <code>{store_disc}%</code>")
    if user_promo > 0:
        disc_adm_lines.append(f"🏷️ <b>Промокод:</b> <code>{user_promo}%</code>")

    disc_adm_str = ("\n" + "\n".join(disc_adm_lines)) if disc_adm_lines else ""

    caption = (
        f"<b>Новый заказ #{purch_id}</b>\n\n"
        f"<b>Покупатель:</b> {user_info} (<code>{m.from_user.id}</code>)\n"
        f"<b>Товар:</b> {flag}{disp_name}\n"
        f"<b>Количество:</b> <code>{qty}</code> шт.\n"
        f"<b>Сумма к зачислению:</b> <code>{amount:.0f}</code> {pay_symbol}{disc_adm_str}"
    )
    
    try:
        if m.photo:
            await bot.send_photo(ADMIN_ID, photo_id, caption=caption, reply_markup=adm_kb)
        else:
            await bot.send_document(ADMIN_ID, photo_id, caption=caption, reply_markup=adm_kb)
    except Exception as e:
        logging.error(f"Ошибка отправки чека администратору: {e}")

@dp.callback_query(F.data.startswith("adm_approve:"))
async def approve_purchase(call: CallbackQuery):
    await call.answer("Одобрено")
    purch_id = int(call.data.split(":")[1])
    conn = await db()
    purch = await one(conn, "SELECT * FROM purchases WHERE id=?", (purch_id,))
    
    if not purch or purch["status"] != "pending":
        await conn.close()
        return await call.message.edit_caption(caption=call.message.caption + "\n\n<b>Статус:</b> Уже обработан.")

    qty = purch["qty"] or 1
    
    if purch["payment"] == "rub":
        rub_rank_equivalent = float(purch["amount"])
    elif purch["payment"] == "kzt":
        rub_rank_equivalent = float(purch["amount"]) / 6.0
    elif purch["payment"] == "stars":
        rub_rank_equivalent = float(purch["amount"]) * 0.6
    else:
        rub_rank_equivalent = float(purch["amount"])

    await conn.execute("UPDATE purchases SET status = 'approved' WHERE id=?", (purch_id,))
    await conn.execute("UPDATE users SET total_spent = total_spent + ? WHERE id=?", (rub_rank_equivalent, purch["user_id"]))
    await conn.commit()
    await conn.close()

    await call.message.edit_caption(caption=call.message.caption + "\n\n<b>Статус: ОДОБРЕНО</b>")

    claim_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Забрать аккаунты", callback_data=f"claim_acc:{purch_id}")]
    ])
    await bot.send_message(
        purch["user_id"],
        f"<b>Ваш платеж подтвержден! (Заказ #{purch_id})</b>\n"
        f"Количество аккаунтов: <b>{qty} шт.</b>\n"
        "Нажмите кнопку ниже для получения товара:",
        reply_markup=claim_kb
    )

@dp.callback_query(F.data.startswith("adm_reject:"))
async def reject_purchase(call: CallbackQuery):
    await call.answer("Отклонено")
    purch_id = int(call.data.split(":")[1])
    
    conn = await db()
    purch = await one(conn, "SELECT * FROM purchases WHERE id=?", (purch_id,))
    if purch:
        await conn.execute("UPDATE purchases SET status = 'rejected' WHERE id=?", (purch_id,))
        paths = []
        if purch["session_paths_json"]:
            try: paths = json.loads(purch["session_paths_json"])
            except Exception: pass
        elif purch["session_path"]:
            paths = [purch["session_path"]]
            
        for p_path in paths:
            if p_path:
                await conn.execute("UPDATE products SET stock = 1 WHERE session_path=?", (p_path,))
        await conn.commit()
    await conn.close()

    await call.message.edit_caption(caption=call.message.caption + "\n\n<b>Статус: ОТКЛОНЕНО</b>")
    if purch:
        await bot.send_message(purch["user_id"], "<b>Оплата отклонена администратором.</b>\nЕсли произошла ошибка, свяжитесь с поддержкой: @suppnovera")
@dp.callback_query(F.data.startswith("claim_acc:"))
async def claim_account(call: CallbackQuery):
    await call.answer()
    purch_id = int(call.data.split(":")[1])
    conn = await db()
    purch = await one(conn, "SELECT * FROM purchases WHERE id=?", (purch_id,))
    await conn.close()
    
    if not purch: return await call.message.answer("Заказ не найден.")

    paths = []
    if purch["session_paths_json"]:
        try: paths = json.loads(purch["session_paths_json"])
        except Exception: pass
    if not paths and purch["session_path"]:
        paths = [purch["session_path"]]

    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"

    guide_text = (
        "<b>СПАСИБО ЗА ПОКУПКУ!</b>\n"
        "Пожалуйста, оставьте отзыв: @reviews_novera\n\n"
        "<b>Как снять спамблок?</b> https://t.me/+NCUpCHXKE29hMGYy\n\n"
        "После входа на аккаунт <b>ОБЯЗАТЕЛЬНО</b> установите двухфакторный пароль (2FA) и привяжите почту.\n\n"
        "Если появляется ошибка «Лимит попыток», попробуйте войти позже (через <b>≈15 часов</b>).\n\n"
        "<b>Частая ошибка: Расход на смс</b>\n"
        "Для устранения скачайте:\n"
        "• <b>Android:</b> DevGram (@DevGramRelease)\n"
        "• <b>iOS:</b> Nicegram (AppStore)\n\n"
        "[ <b>Рекомендуется заходить с VPN/Proxy страны аккаунта</b> ]\n\n"
        "Не меняйте имя, юзернейм и аватарку в течение первых суток."
    )
    await call.message.answer(guide_text, disable_web_page_preview=True)
    await asyncio.sleep(2)

    for idx, s_file in enumerate(paths, start=1):
        if s_file and os.path.exists(s_file):
            if len(paths) > 1:
                await call.message.answer(f"<b>Подключение аккаунта #{idx} из {len(paths)}:</b>")
            asyncio.create_task(safe_listen_for_login_code(s_file, call.from_user.id, user_mention))
            await asyncio.sleep(1.5)
        else:
            await call.message.answer("Файл сессии не найден на сервере. Обратитесь в @suppnovera")

@dp.callback_query(F.data.startswith("claim_gift:"))
async def claim_gift_account(call: CallbackQuery):
    await call.answer()
    prod_id = int(call.data.split(":")[1])
    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=?", (prod_id,))
    await conn.close()
    
    if not prod: return await call.message.answer("Подарок не найден.")

    session_file = prod["session_path"]
    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"

    if session_file and os.path.exists(session_file):
        await call.message.answer("<b>Подключение к подарочному аккаунту...</b>")
        asyncio.create_task(safe_listen_for_login_code(session_file, call.from_user.id, user_mention))
    else:
        await call.message.answer("Файл сессии недоступен. Свяжитесь с поддержкой: @suppnovera")

@dp.callback_query(F.data.startswith("more_code:"))
async def req_more_code(call: CallbackQuery):
    await call.answer("Ожидание нового кода")
    session_path = call.data.split(":", 1)[1]
    user_mention = f"@{call.from_user.username}" if call.from_user.username else f"ID {call.from_user.id}"
    await call.message.answer("<b>Ожидание повторного кода авторизации...</b>")
    asyncio.create_task(safe_listen_for_login_code(session_path, call.from_user.id, user_mention))

async def safe_listen_for_login_code(session_path: str, user_id: int, user_mention: str):
    await stop_existing_client(session_path)

    session_name = Path(session_path).stem
    session_dir = str(Path(session_path).parent)
    s_key = str(Path(session_path).resolve())

    client = Client(
        session_name,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=session_dir,
        in_memory=False,
        takeout=False,
        max_concurrent_transmissions=1
    )
    ACTIVE_CLIENTS[s_key] = client
    login_notified = False
    phone_number = "Номер не определен"

    async def code_handler(cli, message):
        nonlocal login_notified
        try:
            msg_text = message.text or message.caption or ""
            if not login_notified and ("устройство" in msg_text.lower() or "вход" in msg_text.lower() or (message.from_user and message.from_user.is_self)):
                login_notified = True
                admin_text = (
                    "<b>Фиксация входа в аккаунт:</b>\n"
                    f"<b>Номер:</b> <code>{phone_number}</code>\n"
                    f"<b>Покупатель:</b> {user_mention}"
                )
                try: await bot.send_message(ADMIN_ID, admin_text)
                except Exception: pass

            if msg_text:
                codes = re.findall(r'\b\d{5,6}\b', msg_text)
                if codes:
                    found_code = codes[0]
                    try:
                        await bot.send_message(user_id, f"<b>Ваш код авторизации:</b> <code>{found_code}</code>")
                        await asyncio.sleep(7)

                        kb_more = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="Запросить еще один код", callback_data=f"more_code:{session_path}")]
                        ])
                        await bot.send_message(user_id, "Код не подошел или истек?", reply_markup=kb_more)
                        
                        if not login_notified:
                            login_notified = True
                            admin_text = (
                                "<b>Фиксация входа в аккаунт:</b>\n"
                                f"<b>Номер:</b> <code>{phone_number}</code>\n"
                                f"<b>Покупатель:</b> {user_mention}"
                            )
                            try: await bot.send_message(ADMIN_ID, admin_text)
                            except Exception: pass

                        asyncio.create_task(send_account_manage_panel(user_id, session_path))
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        client.add_handler(MessageHandler(code_handler, filters.me | filters.service | filters.private))
        await asyncio.wait_for(client.start(), timeout=15.0)
        
        me = await asyncio.wait_for(client.get_me(), timeout=10.0)
        phone_number = f"+{me.phone_number}" if (me and me.phone_number) else "Номер не определен"

        await bot.send_message(
            user_id,
            f"<b>Номер телефона:</b> <code>{phone_number}</code>\n\n"
            "<b>Код придет автоматически!</b> Отправьте запрос на вход в приложении Telegram."
        )
        await asyncio.sleep(450)

    except (asyncio.TimeoutError, TimeoutError):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Поддержка", url="https://t.me/suppnovera")]])
        await bot.send_message(user_id, "<b>Ошибка: превышено время ожидания соединения.</b>\nОбратитесь к оператору @suppnovera.", reply_markup=kb)
    except (AuthKeyUnregistered, UserDeactivated):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Поддержка", url="https://t.me/suppnovera")]])
        await bot.send_message(user_id, "<b>Аккаунт недействителен (слетела авторизация).</b>\nНапишите в поддержку для замены.", reply_markup=kb)
        await bot.send_message(ADMIN_ID, f"Слетел аккаунт при выдаче клиенту <code>{user_id}</code>. Файл: <code>{session_path}</code>")
    except SessionPasswordNeeded:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Поддержка", url="https://t.me/suppnovera")]])
        await bot.send_message(user_id, "<b>На аккаунте установлен пароль 2FA.</b>\nСвяжитесь с поддержкой.", reply_markup=kb)
    except Exception as e:
        logging.error(f"Ошибка в safe_listen_for_login_code: {e}")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Поддержка", url="https://t.me/suppnovera")]])
        await bot.send_message(user_id, "<b>Не удалось связаться с сервером Telegram.</b>\nОбратитесь в поддержку @suppnovera.", reply_markup=kb)
    finally:
        await stop_existing_client(session_path)

async def send_account_manage_panel(user_id: int, session_path: str):
    await asyncio.sleep(5)
    s_id = Path(session_path).name
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Почистить аккаунт", callback_data=f"ask_clean:{s_id}")],
        [InlineKeyboardButton(text="Удалить сессию бота", callback_data=f"ask_delsess:{s_id}")]
    ])
    msg_text = (
        "Спасибо за покупку, пожалуйста оставьте отзыв [ @reviews_novera ]\n\n"
        "<b>Панель управления сессией:</b>"
    )
    try: await bot.send_message(user_id, msg_text, reply_markup=kb)
    except Exception: pass

@dp.callback_query(F.data.startswith("ask_clean:"))
async def ask_clean_acc(call: CallbackQuery):
    await call.answer()
    s_id = call.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, очистить", callback_data=f"do_clean:{s_id}")],
        [InlineKeyboardButton(text="Отменить", callback_data="cancel_action")]
    ])
    await call.message.answer(
        "<b>Подтверждение очистки:</b>\n"
        "Вы действительно хотите очистить аккаунт? (выход со всех каналов и групп, удаление диалогов)",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("ask_delsess:"))
async def ask_del_session(call: CallbackQuery):
    await call.answer()
    s_id = call.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить удаление", callback_data=f"do_delsess:{s_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_action")]
    ])
    await call.message.answer(
        "Вы собираетесь удалить сессию бота с сервера. Подтвердите действие:",
        reply_markup=kb
    )

@dp.callback_query(F.data == "cancel_action")
async def cancel_action_btn(call: CallbackQuery):
    await call.answer("Отменено")
    try: await call.message.delete()
    except Exception: pass

@dp.callback_query(F.data.startswith("do_delsess:"))
async def do_del_session(call: CallbackQuery):
    await call.answer()
    s_name = call.data.split(":")[1]
    found_path = find_session_path(s_name)

    if not found_path:
        return await call.message.edit_text("<b>Сессия не найдена либо уже удалена.</b>")

    await stop_existing_client(str(found_path))

    client = Client(
        found_path.stem,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=str(found_path.parent),
        in_memory=False
    )
    
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        await client.invoke(functions.auth.LogOut())
    except Exception:
        pass
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        
        try: os.remove(found_path)
        except Exception: pass
        clear_session_locks(found_path)

    await call.message.edit_text("<b>Сессия бота успешно завершена и удалена с сервера.</b>")

@dp.callback_query(F.data.startswith("do_clean:"))
async def do_clean_account(call: CallbackQuery):
    await call.answer()
    s_name = call.data.split(":")[1]
    found_path = find_session_path(s_name)

    if not found_path:
        return await call.message.edit_text("<b>Файл сессии не найден.</b>")

    await stop_existing_client(str(found_path))
    progress_msg = await call.message.answer("<b>ОЧИСТКА АККАУНТА</b>\n<code>[░░░░░░░░░░] 0%</code>")

    client = Client(
        found_path.stem,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=str(found_path.parent),
        in_memory=False
    )

    try:
        await asyncio.wait_for(client.connect(), timeout=15.0)

        dialogs = []
        async for d in client.get_dialogs():
            dialogs.append(d)

        total = len(dialogs)
        if total == 0:
            await progress_msg.edit_text("<b>ОЧИСТКА АККАУНТА</b>\n<code>[██████████] 100%</code>\n<i>Диалоги отсутствуют.</i>")
            await client.disconnect()
            return

        done = 0
        last_pct = 0
        for d in dialogs:
            try:
                chat = d.chat
                if chat.type.value in ["group", "supergroup", "channel"]:
                    await client.leave_chat(chat.id)
                else:
                    await client.delete_dialog(chat.id)
            except Exception:
                pass

            done += 1
            pct = int((done / total) * 100)
            if pct - last_pct >= 10 or done == total:
                last_pct = pct
                filled = int(pct / 10)
                bar = "█" * filled + "░" * (10 - filled)
                try: 
                    await progress_msg.edit_text(f"<b>ОЧИСТКА АККАУНТА</b>\n<code>[{bar}] {pct}%</code>")
                except Exception: 
                    pass
            await asyncio.sleep(0.4)

        await progress_msg.edit_text("<b>ОЧИСТКА АККАУНТА</b>\n<code>[██████████] 100%</code>\n<b>Готово! Все чаты очищены.</b>")
    except Exception:
        await progress_msg.edit_text("<b>Не удалось завершить очистку:</b> сессия занята или соединение прервано.")
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        clear_session_locks(found_path)
async def recalculate_user_totals():
    conn = await db()
    sql = """
    UPDATE users
    SET total_spent = COALESCE((
        SELECT SUM(
            CASE 
                WHEN payment = 'rub' THEN amount
                WHEN payment = 'kzt' THEN amount / 6.0
                WHEN payment = 'stars' THEN amount * 0.6
                ELSE amount
            END
        )
        FROM purchases
        WHERE purchases.user_id = users.id AND purchases.status = 'approved'
    ), 0)
    """
    await conn.execute(sql)
    await conn.commit()
    await conn.close()

@dp.message(F.text == "Профиль")
async def show_profile(m: Message):
    is_ok, missing = await check_user_subscriptions(m.from_user.id)
    if not is_ok: return await send_sub_request(m, missing)
    
    await recalculate_user_totals()
    conn = await db()
    user = await one(conn, "SELECT * FROM users WHERE id=?", (m.from_user.id,))
    
    if not user:
        await conn.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, created_at, agreed_terms) VALUES(?,?,?,?,1)",
            (m.from_user.id, m.from_user.username, m.from_user.first_name, now_msk())
        )
        await conn.commit()
        user = await one(conn, "SELECT * FROM users WHERE id=?", (m.from_user.id,))
    await conn.close()

    total_spent = float(user["total_spent"])
    rank_title, bar, pct, need_more, next_threshold = get_rank_info(total_spent)

    if need_more > 0:
        progress_info = f"Прогресс: <code>[{bar}] {pct}%</code>\nДо ранга <b>{next_threshold:.0f}₽</b> осталось: <code>{need_more:.0f}</code> ₽"
    else:
        progress_info = f"Прогресс: <code>[{bar}] 100%</code> (Максимальный ранг достигнут)"

    active_discount_str = ""
    if user["active_discount_percent"] > 0:
        active_discount_str = f"\nСкидка на заказ: <code>{user['active_discount_percent']}%</code>"

    text = (
        "<b>ЛИЧНЫЙ КАБИНЕТ</b>\n\n"
        f"<b>Идентификатор:</b> <code>{m.from_user.id}</code>\n"
        f"<b>Ранг:</b> <b>{rank_title}</b>\n"
        f"<b>Сумма покупок:</b> <code>{total_spent:.0f}</code> ₽\n"
        f"{progress_info}{active_discount_str}\n\n"
        f"<b>Приглашено рефералов:</b> <code>{user['ref_count']}</code> чел."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Политика", callback_data="profile_policy"),
            InlineKeyboardButton(text="Лидеры", callback_data="profile_leaders")
        ],
        [
            InlineKeyboardButton(text="Промокоды", callback_data="profile_enter_promo")
        ]
    ])
    await m.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "profile_enter_promo")
async def profile_enter_promo_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(EnterPromoState.code)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Отмена", callback_data="back_to_profile")]
    ])
    await call.message.edit_text("<b>Активация промокода</b>\n\nВведите промокод в ответном сообщении:", reply_markup=kb)

@dp.message(EnterPromoState.code)
async def process_user_promo_code(m: Message, state: FSMContext):
    raw_code = m.text.strip().upper()
    await state.clear()

    conn = await db()
    promo = await one(conn, "SELECT * FROM promo_codes WHERE UPPER(code)=?", (raw_code,))
    if not promo:
        await conn.close()
        return await m.answer("<b>Промокод не найден или указан неверно.</b>", reply_markup=home_kb(m.from_user.id))

    if promo["current_uses"] >= promo["max_uses"]:
        await conn.close()
        return await m.answer("<b>Лимит активаций этого промокода исчерпан.</b>", reply_markup=home_kb(m.from_user.id))

    already_used = await one(conn, "SELECT id FROM user_promo_uses WHERE user_id=? AND code=?", (m.from_user.id, promo["code"]))
    if already_used:
        await conn.close()
        return await m.answer("<b>Вы уже активировали этот промокод ранее.</b>", reply_markup=home_kb(m.from_user.id))

    await conn.execute("INSERT INTO user_promo_uses(user_id, code, used_at) VALUES(?,?,?)", (m.from_user.id, promo["code"], now_msk()))
    await conn.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE id=?", (promo["id"],))
    await conn.execute("UPDATE users SET active_discount_percent=? WHERE id=?", (promo["discount_percent"], m.from_user.id))
    await conn.commit()
    await conn.close()

    await m.answer(
        f"<b>Промокод «{promo['code']}» активирован!</b>\n"
        f"Вам начислена скидка <b>{promo['discount_percent']}%</b> на следующую покупку.",
        reply_markup=home_kb(m.from_user.id)
    )

@dp.callback_query(F.data == "profile_policy")
async def profile_policy_callback(call: CallbackQuery):
    await call.answer()
    text = (
        "<b>Политика и соглашение сервиса:</b>\n\n"
        "Ознакомьтесь с официальными документами по ссылкам ниже:\n"
        "• <a href='https://telegra.ph/POLITIKA-KONFEDECIALNOSTI-10-19'>Политика конфиденциальности</a>\n"
        "• <a href='https://telegra.ph/POLZOVATELSKOE-SOGLASHENIE-10-19-42'>Пользовательское соглашение</a>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад в профиль", callback_data="back_to_profile")]
    ])
    await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)

@dp.callback_query(F.data == "profile_leaders")
async def profile_leaders_callback(call: CallbackQuery):
    await call.answer()
    await recalculate_user_totals()
    conn = await db()
    
    sql = """
    SELECT 
        u.id, 
        u.username, 
        u.first_name,
        COALESCE(SUM(
            CASE 
                WHEN p.payment = 'rub' THEN p.amount
                WHEN p.payment = 'kzt' THEN p.amount / 6.0
                WHEN p.payment = 'stars' THEN p.amount * 0.6
                ELSE p.amount
            END
        ), 0) as calc_spent,
        COALESCE(SUM(p.qty), 0) as calc_qty
    FROM users u
    JOIN purchases p ON p.user_id = u.id AND p.status = 'approved'
    GROUP BY u.id
    HAVING calc_spent > 0
    ORDER BY calc_spent DESC, calc_qty DESC
    LIMIT 10
    """
    top_users = await all_rows(conn, sql)
    await conn.close()

    if not top_users:
        text = "<b>ТОП 10 ПОКУПАТЕЛЕЙ</b>\n\n<i>Список лидеров пуст. Оформите заказ, чтобы попасть на первое место!</i>"
    else:
        text = "<b>ТОП 10 ПОКУПАТЕЛЕЙ</b>\n\n"
        for idx, u in enumerate(top_users, start=1):
            spent = float(u["calc_spent"])
            qty_bought = int(u["calc_qty"])
            rtitle, _, _, _, _ = get_rank_info(spent)
            
            if u["username"]:
                user_label = f"@{u['username']}"
            elif u["first_name"]:
                user_label = html.escape(u["first_name"])
            else:
                user_label = f"ID {u['id']}"

            text += f"<b>{idx}.</b> {user_label} | <code>{spent:.0f}</code> ₽ | <b>{qty_bought} шт.</b> ({rtitle})\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад в профиль", callback_data="back_to_profile")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "back_to_profile")
async def back_to_profile_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.delete()
    await show_profile(call.message)

@dp.message(F.text == "Отзывы")
async def open_reviews(m: Message):
    is_ok, missing = await check_user_subscriptions(m.from_user.id)
    if not is_ok: return await send_sub_request(m, missing)
    await m.answer(
        "<b>Канал с отзывами:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перейти к отзывам", url="https://t.me/reviews_novera")]
        ])
    )

@dp.message(F.text == "Поддержка")
async def open_support(m: Message):
    is_ok, missing = await check_user_subscriptions(m.from_user.id)
    if not is_ok: return await send_sub_request(m, missing)
    await m.answer(
        "<b>Служба поддержки:</b>\nПо всем вопросам обращайтесь к нашему менеджеру:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Написать в поддержку", url="https://t.me/suppnovera")]
        ])
    )

@dp.message(F.text.in_(["Сезоны раздач", "🎁 Сезоны раздач"]))
async def open_seasons(m: Message):
    is_ok, missing = await check_user_subscriptions(m.from_user.id)
    if not is_ok: return await send_sub_request(m, missing)

    text = (
        "Пока что сезонов раздач нет.\n"
        "информация по ним в нашем канале (@noverashop)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="завершенные сезоны", callback_data="seasons_completed")],
        [InlineKeyboardButton(text="назад", callback_data="seasons_back_home")]
    ])
    await m.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "seasons_completed")
async def completed_seasons_cb(call: CallbackQuery):
    await call.answer()
    text = (
        "<b>сезон 1:</b>\n"
        "партнерская программа\n"
        "выдано: 50 аккаунтов"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="назад", callback_data="seasons_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "seasons_menu")
async def seasons_menu_cb(call: CallbackQuery):
    await call.answer()
    text = (
        "Пока что сезонов раздач нет.\n"
        "информация по ним в нашем канале (@noverashop)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="завершенные сезоны", callback_data="seasons_completed")],
        [InlineKeyboardButton(text="назад", callback_data="seasons_back_home")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "seasons_back_home")
async def seasons_back_home_cb(call: CallbackQuery):
    await call.answer()
    try: await call.message.delete()
    except Exception: pass
    await call.message.answer("<b>Главное меню</b>", reply_markup=home_kb(call.from_user.id))
async def get_earnings_summary() -> dict:
    conn = await db()
    now = now_dt()
    
    dt_hour = (now - timedelta(hours=1)).isoformat()
    dt_day = (now - timedelta(days=1)).isoformat()
    dt_week = (now - timedelta(days=7)).isoformat()
    dt_month = (now - timedelta(days=30)).isoformat()

    calc_sql_rub = """
    COALESCE(SUM(
        CASE 
            WHEN payment = 'rub' THEN amount
            WHEN payment = 'kzt' THEN amount / 6.0
            WHEN payment = 'stars' THEN amount * 0.6
            ELSE amount
        END
    ), 0)
    """
    
    total_rub = (await one(conn, f"SELECT {calc_sql_rub} as s FROM purchases WHERE status='approved'"))["s"]
    month_rub = (await one(conn, f"SELECT {calc_sql_rub} as s FROM purchases WHERE status='approved' AND created_at >= ?", (dt_month,)))["s"]
    week_rub = (await one(conn, f"SELECT {calc_sql_rub} as s FROM purchases WHERE status='approved' AND created_at >= ?", (dt_week,)))["s"]
    day_rub = (await one(conn, f"SELECT {calc_sql_rub} as s FROM purchases WHERE status='approved' AND created_at >= ?", (dt_day,)))["s"]
    hour_rub = (await one(conn, f"SELECT {calc_sql_rub} as s FROM purchases WHERE status='approved' AND created_at >= ?", (dt_hour,)))["s"]

    await conn.close()
    return {
        "total": float(total_rub),
        "month": float(month_rub),
        "week": float(week_rub),
        "day": float(day_rub),
        "hour": float(hour_rub)
    }

async def generate_sales_chart_text(period: str) -> str:
    conn = await db()
    now = now_dt()
    
    if period == "history":
        title = "за всю историю"
        buckets_count = 6
        step_days = 30
        rows = await all_rows(
            conn,
            """
            SELECT 
                created_at,
                (CASE WHEN payment='rub' THEN amount WHEN payment='kzt' THEN amount/6.0 WHEN payment='stars' THEN amount*0.6 ELSE amount END) as val
            FROM purchases WHERE status='approved'
            """
        )
        data_points = [0.0] * buckets_count
        labels = []
        for i in range(buckets_count):
            start_date = now - timedelta(days=(buckets_count - i) * step_days)
            labels.append(start_date.strftime("%d.%m"))
            
        for r in rows:
            try:
                cat = datetime.fromisoformat(r["created_at"])
                diff_days = (now - cat).days
                idx = buckets_count - 1 - (diff_days // step_days)
                if 0 <= idx < buckets_count:
                    data_points[idx] += float(r["val"])
            except Exception:
                pass

    elif period == "month":
        title = "за месяц"
        buckets_count = 6
        step_days = 5
        cutoff = (now - timedelta(days=30)).isoformat()
        rows = await all_rows(
            conn,
            """
            SELECT 
                created_at,
                (CASE WHEN payment='rub' THEN amount WHEN payment='kzt' THEN amount/6.0 WHEN payment='stars' THEN amount*0.6 ELSE amount END) as val
            FROM purchases WHERE status='approved' AND created_at >= ?
            """,
            (cutoff,)
        )
        data_points = [0.0] * buckets_count
        labels = []
        for i in range(buckets_count):
            b_date = now - timedelta(days=(buckets_count - 1 - i) * step_days)
            labels.append(b_date.strftime("%d.%m"))
            
        for r in rows:
            try:
                cat = datetime.fromisoformat(r["created_at"])
                diff_days = (now - cat).days
                idx = buckets_count - 1 - (diff_days // step_days)
                if 0 <= idx < buckets_count:
                    data_points[idx] += float(r["val"])
            except Exception:
                pass

    elif period == "week":
        title = "за неделю"
        buckets_count = 7
        cutoff = (now - timedelta(days=7)).isoformat()
        rows = await all_rows(
            conn,
            """
            SELECT 
                created_at,
                (CASE WHEN payment='rub' THEN amount WHEN payment='kzt' THEN amount/6.0 WHEN payment='stars' THEN amount*0.6 ELSE amount END) as val
            FROM purchases WHERE status='approved' AND created_at >= ?
            """,
            (cutoff,)
        )
        data_points = [0.0] * buckets_count
        labels = []
        for i in range(buckets_count):
            day_dt = now - timedelta(days=(buckets_count - 1 - i))
            labels.append(day_dt.strftime("%d.%m"))
            
        for r in rows:
            try:
                cat = datetime.fromisoformat(r["created_at"])
                diff_days = (now.date() - cat.date()).days
                idx = buckets_count - 1 - diff_days
                if 0 <= idx < buckets_count:
                    data_points[idx] += float(r["val"])
            except Exception:
                pass

    elif period == "day":
        title = "за день"
        buckets_count = 6
        step_hours = 4
        cutoff = (now - timedelta(hours=24)).isoformat()
        rows = await all_rows(
            conn,
            """
            SELECT 
                created_at,
                (CASE WHEN payment='rub' THEN amount WHEN payment='kzt' THEN amount/6.0 WHEN payment='stars' THEN amount*0.6 ELSE amount END) as val
            FROM purchases WHERE status='approved' AND created_at >= ?
            """,
            (cutoff,)
        )
        data_points = [0.0] * buckets_count
        labels = []
        for i in range(buckets_count):
            b_dt = now - timedelta(hours=(buckets_count - 1 - i) * step_hours)
            labels.append(b_dt.strftime("%H:00"))
            
        for r in rows:
            try:
                cat = datetime.fromisoformat(r["created_at"])
                diff_hours = int((now - cat).total_seconds() // 3600)
                idx = buckets_count - 1 - (diff_hours // step_hours)
                if 0 <= idx < buckets_count:
                    data_points[idx] += float(r["val"])
            except Exception:
                pass

    else:
        title = "за час"
        buckets_count = 6
        step_min = 10
        cutoff = (now - timedelta(minutes=60)).isoformat()
        rows = await all_rows(
            conn,
            """
            SELECT 
                created_at,
                (CASE WHEN payment='rub' THEN amount WHEN payment='kzt' THEN amount/6.0 WHEN payment='stars' THEN amount*0.6 ELSE amount END) as val
            FROM purchases WHERE status='approved' AND created_at >= ?
            """,
            (cutoff,)
        )
        data_points = [0.0] * buckets_count
        labels = []
        for i in range(buckets_count):
            b_dt = now - timedelta(minutes=(buckets_count - 1 - i) * step_min)
            labels.append(b_dt.strftime("%H:%M"))
            
        for r in rows:
            try:
                cat = datetime.fromisoformat(r["created_at"])
                diff_min = int((now - cat).total_seconds() // 60)
                idx = buckets_count - 1 - (diff_min // step_min)
                if 0 <= idx < buckets_count:
                    data_points[idx] += float(r["val"])
            except Exception:
                pass

    await conn.close()

    max_val = max(data_points) if data_points else 0.0
    total_period = sum(data_points)

    graph_lines = []
    for lbl, val in zip(labels, data_points):
        if max_val > 0:
            filled = int((val / max_val) * 12)
        else:
            filled = 0
        bar = "█" * filled + "░" * (12 - filled)
        graph_lines.append(f"<code>{lbl}</code> | {bar} <code>{val:.0f}₽</code>")

    chart_rendered = "\n".join(graph_lines)
    return (
        f"<b>📈 График заработка ({title}):</b>\n\n"
        f"{chart_rendered}\n\n"
        f"<b>Итого за выбранный период:</b> <code>{total_period:.0f}</code> ₽"
    )

@dp.message(F.text.in_(["Админ панель", "Панель управления"]))
async def admin_panel(m: Message):
    if not is_admin(m.from_user.id): return
    await m.answer("<b>Панель управления администратора</b>", reply_markup=admin_inline_kb())

@dp.callback_query(F.data == "adm_back_main")
async def adm_back_main_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.clear()
    await call.answer()
    await call.message.edit_text("<b>Панель управления администратора</b>", reply_markup=admin_inline_kb())

@dp.callback_query(F.data.startswith("adm_nav:"))
async def adm_navigation(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    nav = call.data.split(":")[1]
    await call.answer()

    if nav == "stats":
        conn = await db()
        u_cnt = (await one(conn, "SELECT COUNT(*) as c FROM users"))["c"]
        p_cnt = (await one(conn, "SELECT COUNT(*) as c FROM purchases WHERE status='approved'"))["c"]
        season_cnt = (await one(conn, "SELECT COUNT(*) as c FROM season_accounts WHERE is_given=0"))["c"]
        season_given = (await one(conn, "SELECT COUNT(*) as c FROM season_accounts WHERE is_given=1"))["c"]

        total_rub = (await one(conn, "SELECT COALESCE(SUM(amount), 0) as s FROM purchases WHERE status='approved' AND payment='rub'"))["s"]
        total_stars = (await one(conn, "SELECT COALESCE(SUM(amount), 0) as s FROM purchases WHERE status='approved' AND payment='stars'"))["s"]
        total_kzt = (await one(conn, "SELECT COALESCE(SUM(amount), 0) as s FROM purchases WHERE status='approved' AND payment='kzt'"))["s"]

        today_pref = f"{today_msk_prefix()}%"
        today_rub = (await one(conn, "SELECT COALESCE(SUM(amount), 0) as s FROM purchases WHERE status='approved' AND payment='rub' AND created_at LIKE ?", (today_pref,)))["s"]
        today_stars = (await one(conn, "SELECT COALESCE(SUM(amount), 0) as s FROM purchases WHERE status='approved' AND payment='stars' AND created_at LIKE ?", (today_pref,)))["s"]
        today_kzt = (await one(conn, "SELECT COALESCE(SUM(amount), 0) as s FROM purchases WHERE status='approved' AND payment='kzt' AND created_at LIKE ?", (today_pref,)))["s"]
        await conn.close()

        text = (
            "<b>📊 СТАТИСТИКА СЕРВИСА</b>\n\n"
            f"• Пользователей в базе: <b>{u_cnt}</b>\n"
            f"• Успешных покупок: <b>{p_cnt}</b>\n\n"
            "<b>Финансы (Всего):</b>\n"
            f"• <code>{total_rub:.0f}</code> ₽  |  <code>{int(total_stars)}</code> ⭐  |  <code>{total_kzt:.0f}</code> ₸\n\n"
            "<b>Финансы (Сегодня):</b>\n"
            f"• <code>{today_rub:.0f}</code> ₽  |  <code>{int(today_stars)}</code> ⭐  |  <code>{today_kzt:.0f}</code> ₸\n\n"
            "<b>Сезонные награды:</b>\n"
            f"• В наличии: <b>{season_cnt} шт.</b>\n"
            f"• Выдано: <b>{season_given} шт.</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 График заработка", callback_data="chart_period:month")],
            [InlineKeyboardButton(text="💰 Заработок", callback_data="adm_view_earnings")],
            [InlineKeyboardButton(text="« Назад", callback_data="adm_back_main")]
        ])
        await call.message.edit_text(text, reply_markup=kb)

    elif nav == "tech_works":
        enabled, current_text = await get_tech_works_config()
        st_label = "🟢 <b>ВКЛЮЧЕНЫ</b>" if enabled else "🔴 <b>ВЫКЛЮЧЕНЫ</b>"
        text = (
            "<b>🛠 УПРАВЛЕНИЕ ТЕХНИЧЕСКИМИ РАБОТАМИ</b>\n\n"
            f"Текущий статус: {st_label}\n"
            f"Текущий текст оповещения:\n<blockquote>{current_text}</blockquote>\n\n"
            "Выберите действие:"
        )
        buttons = []
        if enabled:
            buttons.append([InlineKeyboardButton(text="Выключить тех работы", callback_data="tech_turn_off")])
        buttons.append([InlineKeyboardButton(text="Задать текст и включить", callback_data="tech_start_flow")])
        buttons.append([InlineKeyboardButton(text="« Назад", callback_data="adm_back_main")])
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    elif nav == "top_ref":
        conn = await db()
        rows = await all_rows(conn, "SELECT id, username, first_name, ref_count, season_claimed FROM users WHERE ref_count > 0 ORDER BY ref_count DESC LIMIT 50")
        await conn.close()
        if not rows:
            text = "<b>🏆 ТОП РЕФЕРАЛОВ</b>\n\n<i>Список пуст.</i>"
        else:
            text = "<b>🏆 ТОП ПОЛЬЗОВАТЕЛЕЙ ПО ПРИГЛАШЕНИЯМ:</b>\n\n"
            for idx, r in enumerate(rows, start=1):
                uname = f"@{r['username']}" if r["username"] else (r["first_name"] or "Без имени")
                text += f"<b>{idx}.</b> {uname} (<code>{r['id']}</code>) — <b>{r['ref_count']} чел.</b>\n"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="adm_back_main")]])
        await call.message.edit_text(text, reply_markup=kb)

    elif nav == "stock":
        conn = await db()
        rows = await all_rows(conn, "SELECT * FROM products WHERE kind='account' ORDER BY id DESC")
        await conn.close()

        grouped = {}
        for p in rows:
            name_display = p["name"]
            price = float(p["price_rub"])
            group_key = f"{name_display}_{price:.0f}"
            if group_key not in grouped:
                grouped[group_key] = {"name": name_display, "price_rub": price, "stock": (1 if p["stock"] > 0 else 0), "sample_id": p["id"]}
            else:
                grouped[group_key]["stock"] += (1 if p["stock"] > 0 else 0)

        kb = InlineKeyboardBuilder()
        for item in grouped.values():
            clean_title = format_product_button_title(item["name"], item["price_rub"])
            status_stock = f"({item['stock']} шт)" if item["stock"] > 0 else "[нет в наличии]"
            kb.button(text=f"{clean_title} {status_stock}", callback_data=f"manage_item:{item['sample_id']}")

        kb.button(text="➕ Создать штучный товар", callback_data="add_product")
        kb.button(text="📦 Загрузить пачку (.session)", callback_data="add_bulk_pack")
        kb.button(text="🗑 Очистить весь склад", callback_data="clear_all_stock_step1")
        kb.button(text="« Назад в админку", callback_data="adm_back_main")
        kb.adjust(1)
        await call.message.edit_text("<b>📦 Управление складом:</b>", reply_markup=kb.as_markup())

    elif nav == "channels":
        conn = await db()
        channels = await all_rows(conn, "SELECT * FROM required_channels ORDER BY id DESC")
        await conn.close()
        current_ts = int(time.time())
        kb = InlineKeyboardBuilder()
        text = "<b>📢 Управление обязательными подписками:</b>\n\n"
        if not channels:
            text += "<i>Список пуст. Вход свободный.</i>"
        else:
            for ch in channels:
                time_str = "Бессрочно" if ch["until_ts"] == 0 else (f"Осталось {(ch['until_ts'] - current_ts) / 3600:.1f} ч." if ch["until_ts"] > current_ts else "Истек")
                text += f"• <b>{ch['title']}</b> (<code>{ch['channel_id']}</code>) — <b>{time_str}</b>\n"
                kb.button(text=f"❌ Удалить: {ch['title'][:18]}", callback_data=f"del_channel:{ch['id']}")
        kb.button(text="➕ Добавить канал", callback_data="add_sub_channel")
        kb.button(text="« Назад", callback_data="adm_back_main")
        kb.adjust(1)
        await call.message.edit_text(text, reply_markup=kb.as_markup())

    elif nav == "gift":
        await state.set_state(GiftAccount.user_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data="adm_back_main")]])
        await call.message.edit_text("<b>🎁 Подарить аккаунт</b>\n\nВведите числовой Telegram ID получателя:", reply_markup=kb)

    elif nav == "season":
        await state.set_state(BulkAddSeason.uploading)
        await state.update_data(count=0)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Завершить загрузку", callback_data="finish_bulk_season")]])
        await call.message.edit_text("<b>📥 Загрузка сезонных аккаунтов</b>\nОтправляйте файлы <code>.session</code>. По завершении нажмите кнопку:", reply_markup=kb)

    elif nav == "discounts":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Сделать скидки", callback_data="adm_disc_action:discounts")],
            [InlineKeyboardButton(text="🎟 Сделать промокод", callback_data="adm_disc_action:promo")],
            [InlineKeyboardButton(text="« Назад", callback_data="adm_back_main")]
        ])
        await call.message.edit_text("<b>🏷 Управление скидками</b>\n\nВыберите действие:", reply_markup=kb)

    elif nav == "broadcast":
        await state.set_state(Broadcast.text)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data="adm_back_main")]])
        await call.message.edit_text("<b>✉️ Рассылка</b>\n\nОтправьте сообщение для рассылки всем пользователям:", reply_markup=kb)

@dp.callback_query(F.data == "adm_view_earnings")
async def adm_view_earnings_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    earn = await get_earnings_summary()
    text = (
        "<b>💰 ЗАРАБОТОК МАГАЗИНА</b>\n\n"
        f"• <b>За всю историю:</b> <code>{earn['total']:.0f}</code> ₽\n"
        f"• <b>За месяц:</b> <code>{earn['month']:.0f}</code> ₽\n"
        f"• <b>За неделю:</b> <code>{earn['week']:.0f}</code> ₽\n"
        f"• <b>За день:</b> <code>{earn['day']:.0f}</code> ₽\n"
        f"• <b>За последний час:</b> <code>{earn['hour']:.0f}</code> ₽\n\n"
        "<i>(Суммы рассчитаны с конвертацией тенге и Telegram Stars в рубли)</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 График заработка", callback_data="chart_period:month")],
        [InlineKeyboardButton(text="« Назад к статистике", callback_data="adm_nav:stats")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("chart_period:"))
async def adm_chart_period_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    period = call.data.split(":")[1]
    chart_text = await generate_sales_chart_text(period)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=("• Вся история •" if period == "history" else "Вся история"), callback_data="chart_period:history"),
            InlineKeyboardButton(text=("• За месяц •" if period == "month" else "За месяц"), callback_data="chart_period:month")
        ],
        [
            InlineKeyboardButton(text=("• За неделю •" if period == "week" else "За неделю"), callback_data="chart_period:week"),
            InlineKeyboardButton(text=("• За день •" if period == "day" else "За день"), callback_data="chart_period:day")
        ],
        [
            InlineKeyboardButton(text=("• За час •" if period == "hour" else "За час"), callback_data="chart_period:hour")
        ],
        [
            InlineKeyboardButton(text="« Назад к статистике", callback_data="adm_nav:stats")
        ]
    ])
    await call.message.edit_text(chart_text, reply_markup=kb)

@dp.callback_query(F.data == "tech_start_flow")
async def tech_start_flow_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(TechWorksState.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Отмена", callback_data="adm_nav:tech_works")]
    ])
    await call.message.edit_text("<b>ТЕХ РАБОТЫ</b>\n\nВведите текст, который будет отображаться пользователям во время тех работ (форматирование сохраняется):", reply_markup=kb)

@dp.message(TechWorksState.text)
async def tech_input_text(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    raw_html = m.html_text or html.escape(m.text or "")
    await state.update_data(tech_text=raw_html)
    await state.set_state(TechWorksState.confirm)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data="tech_confirm_yes"),
            InlineKeyboardButton(text="Нет", callback_data="tech_confirm_no")
        ]
    ])
    await m.answer(
        f"<b>Предпросмотр сообщения:</b>\n\n{raw_html}\n\n<b>ввод бота на тех работы;</b>",
        reply_markup=kb
    )

@dp.callback_query(TechWorksState.confirm, F.data == "tech_confirm_yes")
async def tech_confirm_yes_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    data = await state.get_data()
    tech_text = data.get("tech_text", "🔧 <b>Ведутся технические работы. Пожалуйста, подождите.</b>")
    await set_tech_works_config(True, tech_text)
    await state.clear()
    await call.answer("Тех работы включены")
    await call.message.edit_text("✅ <b>Бот переведён в режим технических работ.</b>\nТеперь на любую команду и кнопку обычным пользователям отправляется установленный текст.", reply_markup=admin_inline_kb())

@dp.callback_query(TechWorksState.confirm, F.data == "tech_confirm_no")
async def tech_confirm_no_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.clear()
    await call.answer("Отменено")
    await call.message.edit_text("Включение технических работ отменено.", reply_markup=admin_inline_kb())

@dp.callback_query(F.data == "tech_turn_off")
async def tech_turn_off_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await set_tech_works_config(False)
    await call.answer("Тех работы отключены")
    await call.message.edit_text("🔴 <b>Технические работы отключены.</b>\nБот работает в обычном штатном режиме.", reply_markup=admin_inline_kb())

# Все остальные методы администрирования, загрузки товаров и сессий
from aiogram import Router
# Подключение остального функционала админки
@dp.callback_query(F.data == "clear_all_stock_step1")
async def clear_all_stock_step1_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, ОЧИСТИТЬ СКЛАД", callback_data="clear_all_stock_step2")],
        [InlineKeyboardButton(text="« Отмена", callback_data="adm_nav:stock")]
    ])
    await call.message.edit_text(
        "<b>ВНИМАНИЕ! Шаг 1 из 2:</b>\n\n"
        "Вы собираетесь полностью удалить <b>ВСЕ</b> товары со склада и из каталога.\n"
        "Все файлы <code>.session</code> будут удалены с сервера безвозвратно.\n\n"
        "Вы уверены, что хотите продолжить?",
        reply_markup=kb
    )

@dp.callback_query(F.data == "clear_all_stock_step2")
async def clear_all_stock_step2_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 ПОДТВЕРЖДАЮ ПОЛНОЕ УДАЛЕНИЕ", callback_data="clear_all_stock_final")],
        [InlineKeyboardButton(text="« Отмена", callback_data="adm_nav:stock")]
    ])
    await call.message.edit_text(
        "<b>ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ! Шаг 2 из 2:</b>\n\n"
        "Это действие невозможно отменить.\n"
        "Каталог и склад станут абсолютно пустыми.\n\n"
        "Подтвердите удаление:",
        reply_markup=kb
    )

@dp.callback_query(F.data == "clear_all_stock_final")
async def clear_all_stock_final_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    conn = await db()
    all_prods = await all_rows(conn, "SELECT session_path FROM products WHERE kind='account'")
    
    del_files_count = 0
    for p in all_prods:
        s_path = p["session_path"]
        if s_path and os.path.exists(s_path):
            try:
                os.remove(s_path)
                del_files_count += 1
            except Exception:
                pass
        if s_path:
            clear_session_locks(Path(s_path))

    await conn.execute("DELETE FROM products")
    await conn.commit()
    await conn.close()

    await call.message.edit_text(
        f"<b>Склад полностью очищен!</b>\n\n"
        f"Удалены все позиции из каталога и списано файлов: <b>{del_files_count} шт.</b>",
        reply_markup=admin_inline_kb()
    )

@dp.callback_query(F.data.startswith("adm_disc_action:"))
async def adm_disc_action_choice(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    action = call.data.split(":")[1]
    await call.answer()

    if action == "discounts":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Скидки на все", callback_data="make_disc:all")],
            [InlineKeyboardButton(text="Скидка на выбранные товары", callback_data="make_disc:selected")],
            [InlineKeyboardButton(text="« Назад", callback_data="adm_nav:discounts")]
        ])
        await call.message.edit_text("<b>Выберите тип скидки:</b>", reply_markup=kb)

    elif action == "promo":
        await state.set_state(CreatePromoState.code)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data="adm_nav:discounts")]])
        await call.message.edit_text("<b>Создание промокода</b>\n\nВведите название промокода (например: <code>SKIDUSA</code>):", reply_markup=kb)

@dp.message(CreatePromoState.code)
async def create_promo_code_step(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    code = m.text.strip().upper()
    await state.update_data(promo_code=code)
    await state.set_state(CreatePromoState.percent)
    await m.answer(f"Промокод: <code>{code}</code>\n\nУкажите процент скидки (число от 1 до 99):")

@dp.message(CreatePromoState.percent)
async def create_promo_pct_step(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        pct = int(m.text.strip())
        if not (1 <= pct <= 99): raise ValueError
    except ValueError:
        return await m.answer("Введите целое число от 1 до 99:")
    await state.update_data(promo_percent=pct)
    await state.set_state(CreatePromoState.max_uses)
    await m.answer(f"Скидка: <b>{pct}%</b>\n\nСколько пользователей могут активировать промокод:")

@dp.message(CreatePromoState.max_uses)
async def create_promo_uses_step(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        uses = int(m.text.strip())
        if uses <= 0: raise ValueError
    except ValueError:
        return await m.answer("Введите целое число больше нуля:")
    await state.update_data(promo_uses=uses)
    data = await state.get_data()
    text = (
        "<b>Подтвердите создание:</b>\n\n"
        f"• <b>Промо:</b> <code>{data['promo_code']}</code>\n"
        f"• <b>Скидка:</b> <code>{data['promo_percent']}%</code>\n"
        f"• <b>Пользователей могут применить:</b> <code>{data['promo_uses']}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data="confirm_create_promo")],
        [InlineKeyboardButton(text="Отмена", callback_data="adm_nav:discounts")]
    ])
    await state.set_state(CreatePromoState.confirm)
    await m.answer(text, reply_markup=kb)

@dp.callback_query(CreatePromoState.confirm, F.data == "confirm_create_promo")
async def confirm_create_promo_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    data = await state.get_data()
    conn = await db()
    await conn.execute(
        "INSERT INTO promo_codes(code, discount_percent, max_uses, current_uses, created_at) VALUES(?,?,?,0,?)",
        (data["promo_code"], data["promo_percent"], data["promo_uses"], now_msk())
    )
    await conn.commit()
    await conn.close()
    await state.clear()
    await call.answer("Промокод создан")
    await call.message.edit_text(f"Промокод <code>{data['promo_code']}</code> успешно создан!", reply_markup=admin_inline_kb())

@dp.callback_query(F.data == "make_disc:all")
async def make_disc_all_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(CreateDiscountState.percent)
    await state.update_data(target_type="all", target_name="Все товары")
    await call.message.edit_text("<b>Скидки на все:</b>\n\nСколько процентов скидка? (от 1 до 99):")

@dp.callback_query(F.data == "make_disc:selected")
async def make_disc_selected_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    conn = await db()
    rows = await all_rows(conn, "SELECT DISTINCT name, price_rub FROM products WHERE kind='account' AND stock>0")
    await conn.close()

    if not rows:
        return await call.message.edit_text("На складе нет товаров в наличии.", reply_markup=admin_inline_kb())

    kb = InlineKeyboardBuilder()
    for r in rows:
        title = format_product_button_title(r["name"], r["price_rub"])
        kb.button(text=title, callback_data=f"set_item_disc:{r['name']}")
    kb.button(text="« Отмена", callback_data="adm_nav:discounts")
    kb.adjust(1)
    await call.message.edit_text("<b>Выберите товар для скидки:</b>", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("set_item_disc:"))
async def set_item_disc_chosen(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    item_name = call.data.replace("set_item_disc:", "")
    await state.set_state(CreateDiscountState.percent)
    await state.update_data(target_type="item", target_name=item_name)
    await call.answer()
    await call.message.edit_text(f"Выбран товар: <b>{item_name}</b>\n\nСколько процентов скидка? (от 1 до 99):")

@dp.message(CreateDiscountState.percent)
async def disc_percent_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        pct = int(m.text.strip())
        if not (1 <= pct <= 99): raise ValueError
    except ValueError:
        return await m.answer("Введите целое число от 1 до 99:")
    await state.update_data(discount_percent=pct)
    await state.set_state(CreateDiscountState.hours)
    await m.answer(f"Скидка: <b>{pct}%</b>\n\nНа сколько времени действует скидка в часах? (например: <code>24</code>):")

@dp.message(CreateDiscountState.hours)
async def disc_hours_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        hours = float(m.text.replace(",", "."))
        if hours <= 0: raise ValueError
    except ValueError:
        return await m.answer("Введите число часов больше нуля:")
    await state.update_data(discount_hours=hours)
    data = await state.get_data()
    target_str = "На все товары" if data["target_type"] == "all" else f"Товар: {data['target_name']}"
    text = (
        "<b>Подтвердите запуск скидки:</b>\n\n"
        f"• <b>Объект:</b> <b>{target_str}</b>\n"
        f"• <b>Скидка:</b> <code>{data['discount_percent']}%</code>\n"
        f"• <b>Время:</b> <code>{data['discount_hours']} ч.</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data="confirm_apply_discount")],
        [InlineKeyboardButton(text="Отмена", callback_data="adm_nav:discounts")]
    ])
    await state.set_state(CreateDiscountState.confirm)
    await m.answer(text, reply_markup=kb)

@dp.callback_query(CreateDiscountState.confirm, F.data == "confirm_apply_discount")
async def confirm_apply_discount_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    data = await state.get_data()
    until_ts = int(time.time() + (data["discount_hours"] * 3600))
    conn = await db()
    await conn.execute(
        "INSERT INTO global_discounts(target_type, target_name, discount_percent, until_ts, created_at) VALUES(?,?,?,?,?)",
        (data["target_type"], data.get("target_name"), data["discount_percent"], until_ts, now_msk())
    )
    await conn.commit()
    await conn.close()
    await state.clear()
    await call.answer("Скидка запущена")
    await call.message.edit_text("Временная скидка успешно запущена в магазине!", reply_markup=admin_inline_kb())

@dp.callback_query(F.data.startswith("manage_item:"))
async def manage_shop_item(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    pid = int(call.data.split(":")[1])

    conn = await db()
    prod = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    if not prod:
        await conn.close()
        return await call.message.answer("Позиция не найдена.")

    total_stock_row = await one(conn, "SELECT SUM(CASE WHEN stock>0 THEN 1 ELSE 0 END) as s FROM products WHERE name=? AND price_rub=?", (prod["name"], prod["price_rub"]))
    total_stock = total_stock_row["s"] or 0
    await conn.close()

    status_str = f"<b>{total_stock} шт.</b>" if total_stock > 0 else "<b>Исчерпан (0 шт.)</b>"
    flag = get_flag_by_country_or_phone(prod["name"])
    text = (
        "<b>Параметры позиции:</b>\n\n"
        f"<b>Наименование:</b> {flag}<code>{prod['name']}</code>\n"
        f"<b>В наличии:</b> {status_str}\n"
        f"<b>Цены:</b> <code>{float(prod['price_rub']):.0f}</code> ₽ | <code>{int(prod['price_stars'] or 0)}</code> ⭐ | <code>{float(prod['price_kzt'] or 0.0):.0f}</code> ₸"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пополнить запасы (.session)", callback_data=f"restock_item:{pid}")],
        [InlineKeyboardButton(text="Изменить цены", callback_data=f"editprice_item:{pid}")],
        [InlineKeyboardButton(text="Удалить карточку товара", callback_data=f"del_shop_all:{pid}")],
        [InlineKeyboardButton(text="« Назад к складу", callback_data="adm_nav:stock")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("del_shop_all:"))
async def del_shop_all_cmd(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split(":")[1])
    conn = await db()
    sample = await one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    if sample:
        rows = await all_rows(conn, "SELECT session_path FROM products WHERE name=? AND price_rub=?", (sample["name"], sample["price_rub"]))
        for r in rows:
            if r["session_path"] and os.path.exists(r["session_path"]):
                try: os.remove(r["session_path"])
                except Exception: pass
        await conn.execute("DELETE FROM products WHERE name=? AND price_rub=?", (sample["name"], sample["price_rub"]))
        await conn.commit()
        await call.answer("Позиция и сессии удалены со склада", show_alert=True)
    await conn.close()
    await call.message.delete()
    call.data = "adm_nav:stock"
    await adm_navigation(call, None)

@dp.callback_query(F.data.startswith("editprice_item:"))
async def editprice_item_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    pid = int(call.data.split(":")[1])
    
    conn = await db()
    sample = await one(conn, "SELECT name, price_rub FROM products WHERE id=?", (pid,))
    await conn.close()

    if not sample:
        return await call.message.answer("Позиция не найдена.")

    await state.update_data(target_name=sample["name"], old_price_rub=sample["price_rub"])
    await state.set_state(EditPriceGroup.pricing)
    await call.message.answer(
        f"<b>Изменение цен для позиции:</b> <code>{sample['name']}</code>\n\n"
        "Введите значения в формате:\n<code>100₽, 100 звезд, 600 тг</code>"
    )

@dp.message(EditPriceGroup.pricing)
async def process_edit_pricing(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    p_rub, p_stars, p_kzt, _ = parse_pricing_line(m.text)
    if p_rub == 0 and p_kzt == 0:
        return await m.answer("Не удалось разобрать строку. Пример ввода: <code>50₽, 50 звезд, 300 тг</code>")

    data = await state.get_data()
    t_name = data["target_name"]
    old_price = data.get("old_price_rub")

    conn = await db()
    await conn.execute(
        "UPDATE products SET price_rub=?, price_stars=?, price_kzt=? WHERE name=? AND price_rub=?",
        (float(p_rub), int(p_stars), float(p_kzt), t_name, old_price)
    )
    await conn.commit()
    await conn.close()
    await state.clear()
    await m.answer(f"<b>Цены для позиции {t_name} обновлены!</b>", reply_markup=admin_inline_kb())

@dp.callback_query(F.data.startswith("restock_item:"))
async def restock_item_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    pid = int(call.data.split(":")[1])

    conn = await db()
    sample = await one(conn, "SELECT name, price_rub, price_stars, price_kzt, description FROM products WHERE id=?", (pid,))
    await conn.close()

    if not sample:
        return await call.message.answer("Позиция не найдена.")

    await state.update_data(
        target_name=sample["name"],
        price_rub=float(sample["price_rub"]),
        price_stars=int(sample["price_stars"] or 0),
        price_kzt=float(sample["price_kzt"] or 0.0),
        description=sample["description"] or "",
        count=0
    )
    await state.set_state(RestockProduct.uploading)

    finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Завершить загрузку", callback_data="finish_restock")]
    ])
    await call.message.answer(
        f"<b>Пополнение карточки:</b> <code>{sample['name']}</code>\n"
        "Отправляйте файлы <code>.session</code>. По завершении нажмите кнопку:",
        reply_markup=finish_kb
    )

@dp.message(RestockProduct.uploading, F.document)
async def process_restock_file(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"session_{secrets.token_hex(4)}.session"
    save_path = Path("sessions") / file_name

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
        pass
    finally:
        if client and client.is_connected:
            try: await client.disconnect()
            except Exception: pass

    prefix = extract_only_prefix(full_phone or file_name)

    data = await state.get_data()
    item_name = data.get("target_name")
    p_rub = float(data.get("price_rub", 0.0))
    p_stars = int(data.get("price_stars", 0))
    p_kzt = float(data.get("price_kzt", 0.0))
    desc = data.get("description", "")

    conn = await db()
    await conn.execute(
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone, description) "
        "VALUES('account', ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?)",
        (item_name, p_rub, p_stars, p_kzt, now_msk(), file_id, str(save_path), prefix, desc)
    )
    await conn.commit()
    await conn.close()

    new_count = data.get("count", 0) + 1
    await state.update_data(count=new_count)

@dp.callback_query(RestockProduct.uploading, F.data == "finish_restock")
async def finish_restock_btn(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cnt = data.get("count", 0)
    await state.clear()
    await call.message.edit_text(f"<b>Запасы пополнены:</b> добавлено <b>{cnt} шт.</b>")
    await call.message.answer("Панель управления", reply_markup=admin_inline_kb())

@dp.message(GiftAccount.user_id)
async def gift_acc_user_id(m: Message, state: FSMContext):
    try: target_id = int(m.text.strip())
    except ValueError: return await m.answer("Введите корректный числовой ID:")
    await state.update_data(target_user_id=target_id)
    await state.set_state(GiftAccount.session_file)
    await m.answer("<b>Шаг 2:</b> Отправьте файл <code>.session</code> документом:")

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
        "<b>Подтверждение отправки подарка:</b>\n\n"
        f"<b>Получатель:</b> <code>{data['target_user_id']}</code>\n"
        f"<b>Файл:</b> <code>{Path(save_path).name}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить", callback_data="gift_confirm_send")],
        [InlineKeyboardButton(text="Отмена", callback_data="adm_back_main")]
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
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone) VALUES('account', 'Подарок', 0, 0, 0, 0, 1, ?, ?, ?, '')",
        (now_msk(), file_id, session_path)
    )
    prod_id = cur.lastrowid
    await conn.commit()
    await conn.close()
    
    await state.clear()
    await call.message.edit_text("<b>Подарок отправлен пользователю.</b>", reply_markup=admin_inline_kb())
    
    gift_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Забрать аккаунт", callback_data=f"claim_gift:{prod_id}")]
    ])
    try: 
        await bot.send_message(target_id, "<b>Вам начислен подарочный аккаунт от администрации.</b>\nДля входа нажмите кнопку:", reply_markup=gift_kb)
    except Exception as e: 
        await call.message.answer(f"Не удалось доставить уведомление получателю: <code>{e}</code>")

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
        pass
    finally:
        if client and client.is_connected:
            try: await client.disconnect()
            except Exception: pass

    prefix = extract_only_prefix(full_phone or file_name)

    conn = await db()
    await conn.execute(
        "INSERT INTO season_accounts(phone, session_path, file_id, is_given, created_at) VALUES(?, ?, ?, 0, ?)",
        (prefix, str(save_path), file_id, now_msk())
    )
    await conn.commit(); await conn.close()

    data = await state.get_data()
    c = data.get("count", 0) + 1
    await state.update_data(count=c)

@dp.callback_query(BulkAddSeason.uploading, F.data == "finish_bulk_season")
async def finish_bulk_season_h(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cnt = data.get("count", 0)
    await state.clear()
    await call.message.edit_text(f"<b>Пул наград пополнен:</b> добавлено <b>{cnt} шт.</b>", reply_markup=admin_inline_kb())

@dp.callback_query(F.data == "add_bulk_pack")
async def start_bulk_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(BulkAddProduct.uploading)
    await state.update_data(files=[], groups=set())
    
    finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Завершить загрузку пачки", callback_data="finish_bulk_upload")]
    ])
    await call.message.edit_text(
        "<b>Массовая загрузка аккаунтов</b>\n"
        "Отправляйте файлы <code>.session</code>. Бот автоматически определит страну на русском языке.\n"
        "После отправки всех файлов нажмите кнопку ниже:",
        reply_markup=finish_kb
    )
    await call.answer()

@dp.message(BulkAddProduct.uploading, F.document)
async def process_bulk_file(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"session_{secrets.token_hex(4)}.session"
    save_path = Path("sessions") / file_name
    
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
        pass
    finally:
        if client and client.is_connected:
            try: await client.disconnect()
            except Exception: pass

    prefix, iso, cname_ru = extract_phone_and_country(full_phone or file_name)
    group_label = f"{cname_ru} ({prefix})"

    data = await state.get_data()
    files_list = data.get("files", [])
    groups_set = set(data.get("groups", []))
    
    files_list.append({"file_id": file_id, "path": str(save_path), "group": group_label, "phone": prefix, "name": file_name})
    groups_set.add(group_label)
    await state.update_data(files=files_list, groups=list(groups_set))

@dp.callback_query(BulkAddProduct.uploading, F.data == "finish_bulk_upload")
async def finish_bulk_upload_h(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    groups = data.get("groups", [])
    if not groups:
        return await call.answer("Вы не загрузили ни одного файла.", show_alert=True)
        
    await state.update_data(remaining_groups=list(groups), price_map={})
    await state.set_state(BulkAddProduct.pricing)
    
    next_grp = groups[0]
    await call.message.answer(
        f"Укажите цены для группы <b>{next_grp}</b>:\n\n"
        "<b>Формат:</b> <code>100₽, 100 звезд, 600 тг, без сб / сб</code>\n"
        "<b>Пример:</b> <code>50₽, 50 звезд, 300 тг, без сб</code>"
    )
    await call.answer()

@dp.message(BulkAddProduct.pricing)
async def process_bulk_pricing(m: Message, state: FSMContext):
    p_rub, p_stars, p_kzt, is_sb = parse_pricing_line(m.text)
    if p_rub == 0 and p_kzt == 0:
        return await m.answer("Не удалось разобрать строку. Пример: <code>100₽, 100 звезд, 600 тг, без сб</code>")

    data = await state.get_data()
    remaining = data["remaining_groups"]
    price_map = data.get("price_map", {})
    
    curr_grp = remaining.pop(0)
    final_name = f"{curr_grp} [СБ]" if is_sb else curr_grp
    price_map[curr_grp] = {"rub": float(p_rub), "stars": int(p_stars), "kzt": float(p_kzt), "final_name": final_name}
    
    if remaining:
        await state.update_data(remaining_groups=remaining, price_map=price_map)
        next_grp = remaining[0]
        await m.answer(
            f"Укажите цены для группы <b>{next_grp}</b>:\n"
            "<b>Формат:</b> <code>100₽, 100 звезд, 600 тг, без сб / сб</code>"
        )
    else:
        files = data["files"]
        conn = await db()
        count_added = 0
        
        for f_item in files:
            grp = f_item["group"]
            cfg = price_map.get(grp, {"rub": 0.0, "stars": 0, "kzt": 0.0, "final_name": grp})
            
            await conn.execute(
                "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone) VALUES('account', ?, ?, ?, ?, 1, 0, ?, ?, ?, ?)",
                (cfg["final_name"], float(cfg["rub"]), int(cfg["stars"]), float(cfg["kzt"]), now_msk(), f_item["file_id"], f_item["path"], f_item["phone"])
            )
            count_added += 1
            
        await conn.commit(); await conn.close()
        await state.clear()
        await m.answer(f"<b>Успешно добавлено аккаунтов на склад:</b> <b>{count_added} шт.</b>", reply_markup=admin_inline_kb())

@dp.callback_query(F.data == "add_product")
async def add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AddProduct.name)
    await call.message.edit_text("<b>Шаг 1:</b> Введите понятное название на русском (например: <code>США (+1)</code>, <code>Канада (+1) [СБ]</code>):")
    await call.answer()

@dp.message(AddProduct.name)
async def add_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await state.set_state(AddProduct.description)
    await m.answer("<b>Шаг 2:</b> Введите описание товара (или отправьте <code>-</code>):")

@dp.message(AddProduct.description)
async def add_description(m: Message, state: FSMContext):
    desc = "" if m.text.strip() == "-" else m.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AddProduct.price_rub)
    await m.answer("<b>Шаг 3:</b> Укажите цену в рублях (₽):")

@dp.message(AddProduct.price_rub)
async def add_rub(m: Message, state: FSMContext):
    try: price = float(m.text.replace(",", "."))
    except ValueError: return await m.answer("Введите корректное числовое значение:")
    await state.update_data(price_rub=price)
    await state.set_state(AddProduct.price_stars)
    await m.answer("<b>Шаг 4:</b> Укажите цену в Telegram Stars (⭐):")

@dp.message(AddProduct.price_stars)
async def add_stars(m: Message, state: FSMContext):
    try: stars = int(m.text.strip())
    except ValueError: return await m.answer("Введите целое число звёзд:")
    await state.update_data(price_stars=stars)
    await state.set_state(AddProduct.price_kzt)
    await m.answer("<b>Шаг 5:</b> Укажите цену в тенге (₸):")

@dp.message(AddProduct.price_kzt)
async def add_kzt(m: Message, state: FSMContext):
    try: price = float(m.text.replace(",", "."))
    except ValueError: return await m.answer("Введите корректное числовое значение:")
    await state.update_data(price_kzt=price)
    await state.set_state(AddProduct.account_file)
    await m.answer("<b>Шаг 6:</b> Отправьте файл <code>.session</code> документом:")

@dp.message(AddProduct.account_file, F.document)
async def add_account_file(m: Message, state: FSMContext):
    file_id = m.document.file_id
    file_name = m.document.file_name or f"session_{secrets.token_hex(4)}.session"
    save_path = Path("sessions") / file_name
    
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, save_path)
    
    d = await state.get_data()
    product_name = d["name"]
    p_rub = float(d["price_rub"])
    p_stars = int(d.get("price_stars", 0))
    p_kzt = float(d.get("price_kzt", 0.0))

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
        pass
    finally:
        if client and client.is_connected:
            try: await client.disconnect()
            except Exception: pass

    prefix = extract_only_prefix(full_phone or file_name)

    conn = await db()
    await conn.execute(
        "INSERT INTO products(kind, name, price_rub, price_stars, price_kzt, stock, sales, created_at, file_id, session_path, phone, description) VALUES('account',?,?,?,?,1,0,?,?,?,?,?)",
        (product_name, p_rub, p_stars, p_kzt, now_msk(), file_id, str(save_path), prefix, d.get("description", ""))
    )
    await conn.commit(); await conn.close()
    
    await state.clear()
    await m.answer(f"<b>Товар «{product_name}» успешно создан.</b>", reply_markup=admin_inline_kb())

@dp.callback_query(F.data == "add_sub_channel")
async def add_sub_channel_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AddSubChannel.channel)
    await call.message.edit_text(
        "<b>Добавление обязательного канала:</b>\n\n"
        "Отправьте <b>ID канала</b> (например: <code>-1001234567890</code>) или <b>юзернейм</b> (<code>@channel</code>).\n"
        "<i>Бот должен обладать правами администратора в канале.</i>"
    )

@dp.message(AddSubChannel.channel)
async def add_sub_channel_ident(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    ident = m.text.strip()
    chat_id = int(ident) if (ident.startswith("-") or ident.isdigit()) else ident
    
    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or ident
        invite_link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else "")
        await state.update_data(channel_id=str(chat.id), title=title, invite_link=invite_link)
        await state.set_state(AddSubChannel.hours)
        await m.answer(
            f"Канал найден: <b>{title}</b>\n\n"
            "Укажите срок обязательной подписки в часах (отправьте <code>0</code> для постоянной проверки):"
        )
    except Exception as e:
        await m.answer(f"Не удалось подключиться к каналу: <code>{e}</code>\nПроверьте права бота.")

@dp.message(AddSubChannel.hours)
async def add_sub_channel_hours(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        hours = float(m.text.replace(",", "."))
        if hours < 0: raise ValueError
    except ValueError:
        return await m.answer("Введите корректное число часов:")

    until_ts = int(time.time() + (hours * 3600)) if hours > 0 else 0
    data = await state.get_data()
    
    conn = await db()
    await conn.execute(
        "INSERT INTO required_channels(channel_id, title, invite_link, until_ts, created_at) VALUES(?,?,?,?,?)",
        (data["channel_id"], data["title"], data["invite_link"], until_ts, now_msk())
    )
    await conn.commit(); await conn.close()
    await state.clear()
    
    dur_str = f"на {hours} ч." if hours > 0 else "бессрочно"
    await m.answer(f"Канал <b>{data['title']}</b> успешно добавлен ({dur_str}).", reply_markup=admin_inline_kb())

@dp.callback_query(F.data.startswith("del_channel:"))
async def del_sub_channel_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    ch_id = int(call.data.split(":")[1])
    conn = await db()
    await conn.execute("DELETE FROM required_channels WHERE id=?", (ch_id,))
    await conn.commit(); await conn.close()
    await call.answer("Канал удален")
    call.data = "adm_nav:channels"
    await adm_navigation(call, state)

@dp.message(Broadcast.text)
async def broadcast_finish(m: Message, state: FSMContext):
    await state.clear()
    conn = await db()
    users = await all_rows(conn, "SELECT id FROM users")
    await conn.close()
    
    count, blocked = 0, 0
    status_msg = await m.answer("<b>Рассылка запущена...</b>")
    for u in users:
        try:
            await bot.copy_message(chat_id=u["id"], from_chat_id=m.chat.id, message_id=m.message_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            blocked += 1
            
    await status_msg.edit_text(
        "<b>Рассылка завершена</b>\n\n"
        f"• Доставлено: <b>{count}</b>\n"
        f"• Заблокировали бота: <b>{blocked}</b>",
        reply_markup=admin_inline_kb()
    )

async def check_single_session_validity(session_path_str: str) -> bool:
    if not session_path_str or not os.path.exists(session_path_str):
        return False

    session_path = Path(session_path_str)
    clear_session_locks(session_path)

    client = Client(
        session_path.stem,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=str(session_path.parent),
        in_memory=False
    )
    
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        me = await asyncio.wait_for(client.get_me(), timeout=8.0)
        return bool(me and me.id)
    except (AuthKeyUnregistered, UserDeactivated):
        return False
    except Exception:
        return True
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        clear_session_locks(session_path)

async def hourly_session_checker():
    while True:
        try:
            await asyncio.sleep(3600)
            logging.info("Запуск ежечасной проверки сессий на складе...")
            conn = await db()
            active_prods = await all_rows(conn, "SELECT id, name, session_path FROM products WHERE kind='account' AND stock>0")
            
            dropped_count = 0
            for prod in active_prods:
                s_path = prod["session_path"]
                is_valid = await check_single_session_validity(s_path)
                if not is_valid:
                    dropped_count += 1
                    await conn.execute("DELETE FROM products WHERE id=?", (prod["id"],))
                    if s_path and os.path.exists(s_path):
                        try: os.remove(s_path)
                        except Exception: pass
                    logging.warning(f"Удален слетевший аккаунт #{prod['id']} ({prod['name']}).")

            if dropped_count > 0:
                await conn.commit()
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"<b>Аудит склада:</b> списано и удалено слетевших аккаунтов: <b>{dropped_count} шт.</b>"
                    )
                except Exception:
                    pass

            await conn.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Ошибка в фоновом чекере сессий: {e}")

async def main():
    await init_db()
    asyncio.create_task(hourly_session_checker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
