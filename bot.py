# language: Python, file: bot.py, target: Python 3.10+
# *Магазин Starsshop: Финальная версия + Оплата Криптой (CryptoBot)*
# *зависимости: aiogram, aiosqlite, flask, aiohttp*

import asyncio
import logging
import random
import string
import aiosqlite
import os
import threading
import aiohttp
from datetime import datetime, timedelta
from flask import Flask
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, 
                           LabeledPrice, PreCheckoutQuery, Message, BotCommand)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "9040235874:AAGSGvWV-nwd4kn32OADEn0ob_zp_M8tHKw")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_USERNAME = "moscow_1488"
IMAGE_URL = "https://github.com/62w6ffzng7-gif/Starsshopp/raw/main/IMG_1577.jpeg"

# ТОКЕН ОТ @CryptoBot (Crypto Pay -> Create App)
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "314128:AA3GvM6yWgMQqrM8y1hwjf2Lv6w9MXvOReo") 
CRYPTO_API_URL = "https://pay.crypt.bot/api"

USERNAMES_DB = {
    "@ynqnw5": 25,
}
# ==============================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class UserStates(StatesGroup):
    waiting_for_topup_amount = State()
    waiting_for_review = State()
    waiting_for_promo = State()
    waiting_for_broadcast = State()

app = Flask(__name__)
@app.route('/')
def health(): return "Starsshop is running ✨", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# --- БД ---
async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            balance INTEGER DEFAULT 0,
            last_bonus TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item TEXT, price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, item TEXT, code TEXT, status TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_activations (user_id INTEGER PRIMARY KEY, promo_code TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_stats (promo_code TEXT PRIMARY KEY, uses INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            item_name TEXT, 
            item_data TEXT, 
            is_sold INTEGER DEFAULT 0
        )""")
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT balance, last_bonus FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                await db.commit()
                return 0, None
            return row[0], row[1]

async def add_balance(user_id, amount):
    await get_user(user_id)
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def add_history(user_id, item, price):
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("INSERT INTO history (user_id, item, price) VALUES (?, ?, ?)", (user_id, item, price))
        await db.commit()

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# --- Отправка меню с картинкой ---
async def send_menu_with_photo(chat_id, text, keyboard, message_id=None):
    try:
        if message_id:
            try: 
                await bot.delete_message(chat_id, message_id)
            except: 
                pass
        
        await bot.send_photo(
            chat_id=chat_id,
            photo=IMAGE_URL,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"⚠️ Ошибка отправки фото: {e}")
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

def get_main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить звёзды", callback_data="menu_buy")
    kb.button(text="👑 Купить юзернейм", callback_data="menu_usernames")
    kb.button(text="👤 Профиль", callback_data="menu_profile")
    kb.button(text="📖 Помощь", callback_data="menu_help")
    kb.button(text="📞 Связь с админом", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    return kb.as_markup()

async def set_commands():
    commands = [BotCommand(command="start", description="Открыть магазин")]
    await bot.set_my_commands(commands)

# --- Интеграция с CryptoBot ---
async def create_crypto_invoice(amount_usdt: float, description: str, payload: str):
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {
        "asset": "USDT",
        "amount": str(amount_usdt),
        "description": description,
        "payload": payload,
        "allow_comments": False,
        "allow_anonymous": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{CRYPTO_API_URL}/createInvoice", headers=headers, json=data) as resp:
            result = await resp.json()
            if result.get("ok"):
                return result["result"]["bot_invoice_url"], result["result"]["invoice_id"]
            else:
                logging.error(f"CryptoBot error: {result}")
                return None, None

async def check_crypto_invoice(invoice_id: int):
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CRYPTO_API_URL}/getInvoices?invoice_ids={invoice_id}", headers=headers) as resp:
            result = await resp.json()
            if result.get("ok") and result["result"]["items"]:
                return result["result"]["items"][0]["status"] == "paid"
    return False

# --- Главное меню ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await get_user(message.from_user.id)
    caption = (
        "👋 <b>Добро пожаловать в Starsshop!</b> 🌟\n\n"
        "💎 Здесь ты можешь купить звёзды за рубли/крипту или крутые юзернеймы за баланс.\n"
        "🚀 Быстро, выгодно и безопасно!\n\n"
        "💖 Мы очень рады видеть тебя здесь. Выбирай раздел и погнали:\n"
    )
    await send_menu_with_photo(message.chat.id, caption, get_main_menu_kb())

# --- Профиль и Бонус ---
@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance, last_bonus = await get_user(call.from_user.id)
    history_text = ""
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT item, price FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 3", (call.from_user.id,)) as cursor:
            rows = await cursor.fetchall()
            history_text = "\n".join([f"• {item} — {price} ⭐" for item, price in rows]) if rows else "Покупок пока нет. 😉"
            
    bonus_available = True
    if last_bonus:
        last_dt = datetime.fromisoformat(last_bonus)
        if datetime.now() - last_dt < timedelta(days=1):
            bonus_available = False

    kb_builder = InlineKeyboardBuilder()
    kb_builder.button(text="💳 Пополнить баланс", callback_data="topup_start")
    kb_builder.button(text="🎟 Ввести промокод", callback_data="enter_promo")
    if bonus_available:
        kb_builder.button(text="🎁 Забрать бонус (+1 ⭐)", callback_data="claim_bonus")
    else:
        kb_builder.button(text="⏳ Бонус уже получен", callback_data="bonus_wait")
    kb_builder.button(text="🔙 Назад", callback_data="back_to_start")
    kb_builder.adjust(1)
    
    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n"
        f"💰 Баланс звёзд: <b>{balance} ⭐</b>\n\n"
        f"📜 <b>История покупок:</b>\n{history_text}\n\n"
        f"<i>Баланс нужен для покупки юзернеймов!</i> 💖"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb_builder.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "claim_bonus")
async def claim_bonus(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    balance, last_bonus = await get_user(user_id)
    if last_bonus and datetime.now() - datetime.fromisoformat(last_bonus) < timedelta(days=1):
        await call.answer("⏳ Бонус уже получен сегодня!", show_alert=True)
        return
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + 1, last_bonus = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
        await db.commit()
    await add_history(user_id, "Бонус", 1)
    await call.answer("🎉 Ты получил 1 звезду!", show_alert=True)
    await show_profile(call, state)

@dp.callback_query(F.data == "bonus_wait")
async def bonus_wait(call: CallbackQuery):
    await call.answer("⏳ Приходи завтра!", show_alert=True)

# --- Покупка звезд ---
@dp.callback_query(F.data == "menu_buy")
async def buy_stars_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 звёзд — 30₽ / ~0.35$", callback_data="select_stars_15")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    text = "🛒 <b>Выбери пакет звёзд:</b>\n\n🌟 Оплата доступна в рублях (карта/СБП) или в криптовалюте (USDT)."
    await send_menu_with_photo(call.message.chat.id, text, kb.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("select_stars_"))
async def choose_payment_method(call: CallbackQuery, state: FSMContext):
    await state.clear()
    amount = int(call.data.split("_")[2])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Оплатить рублями", callback_data=f"pay_rub_{amount}")],
        [InlineKeyboardButton(text="🪙 Оплатить криптой (USDT)", callback_data=f"pay_crypto_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")]
    ])
    text = f"💳 <b>Как вы хотите купить {amount} звёзд?</b>\n\nВыберите удобный способ оплаты:"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

# --- Оплата РУБЛЯМИ ---
@dp.callback_query(F.data.startswith("pay_rub_"))
async def pay_with_rub(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, f"{amount} звёзд (Рубли)", code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    text = (
        f"🎉 <b>Заказ #{order_id} создан!</b>\n\n"
        f"📦 Товар: {amount} звёзд\n"
        f"💰 Оплата: Рубли (СБП/Карта)\n"
        f"🔑 <b>Код заказа: <code>{code}</code></b>\n\n"
        f"👇 Напиши менеджеру и отправь этот код для оплаты:\n"
        f"<b>@{ADMIN_USERNAME}</b>"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"),
             InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ (РУБЛИ) #{order_id}</b>\nКлиент: @{username}\nТовар: {amount} звёзд\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

# --- Оплата КРИПТОЙ ---
@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_with_crypto(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id
    
    usdt_amount = round(amount * 0.023, 2)
    
    await call.message.edit_caption(caption="⏳ <b>Создаем счет в CryptoBot...</b>", parse_mode="HTML")
    
    payload = f"crypto_topup_{user_id}_{amount}"
    pay_url, invoice_id = await create_crypto_invoice(usdt_amount, f"Покупка {amount} звёзд", payload)
    
    if not pay_url:
        await call.message.answer("❌ Ошибка создания счета. Попробуйте позже.")
        return

    # ДОБАВЛЕНА КНОПКА ОТМЕНЫ
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 Перейти к оплате", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Я оплатил (Проверить)", callback_data=f"check_crypto_{invoice_id}_{amount}_{user_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")]
    ])
    
    text = (
        f"🪙 <b>Счет на оплату создан!</b>\n\n"
        f"К оплате: <b>{usdt_amount} USDT</b>\n"
        f"Товар: <b>{amount} звёзд</b>\n\n"
        f"1. Нажми «Перейти к оплате»\n"
        f"2. Оплати в CryptoBot\n"
        f"3. Вернись и нажми «Я оплатил»"
    )
    await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_payment(call: CallbackQuery):
    _, _, invoice_id, amount, user_id = call.data.split("_")
    invoice_id = int(invoice_id)
    amount = int(amount)
    user_id = int(user_id)
    
    await call.answer("⏳ Проверяем оплату...")
    is_paid = await check_crypto_invoice(invoice_id)
    
    if is_paid:
        await add_balance(user_id, amount)
        await add_history(user_id, f"{amount} звёзд (Крипта)", amount)
        
        async with aiosqlite.connect("shop.db") as db:
            async with db.execute("SELECT id, item_data FROM stock WHERE item_name = ? AND is_sold = 0 LIMIT 1", (f"{amount} звёзд",)) as cursor:
                stock_item = await cursor.fetchone()

            if stock_item:
                stock_id, item_data = stock_item
                await db.execute("UPDATE stock SET is_sold = 1 WHERE id = ?", (stock_id,))
                await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, "crypto", f"{amount} звёзд", "-", "done"))
                await db.commit()
                
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_start")]])
                text = (
                    f"🎉 <b>Оплата прошла! Заказ выполнен автоматически.</b>\n\n"
                    f"📦 Товар: {amount} звёзд\n"
                    f"🔑 <b>Ваши данные:</b> <code>{item_data}</code>\n\n"
                    f"💖 Спасибо за покупку!"
                )
                await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
                return

        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 В профиль", callback_data="menu_profile")]])
        text = f"🎉 <b>Успешно оплачено!</b>\n\nТебе начислено <b>{amount} ⭐</b> на баланс."
        await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    else:
        await call.answer("❌ Оплата еще не поступила. Подожди минуту и попробуй снова.", show_alert=True)

# --- Админ кнопки ---
@dp.callback_query(F.data.startswith("adm_done_"))
async def admin_done(call: CallbackQuery):
    if call.from_user.username != ADMIN_USERNAME: 
        return await call.answer("Нет прав", show_alert=True)
    order_id = call.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET status = 'done' WHERE id = ?", (order_id,))
        await db.commit()
        async with db.execute("SELECT user_id, item FROM orders WHERE id = ?", (order_id,)) as c:
            row = await c.fetchone()
            if row:
                await bot.send_message(row[0], f"🎉 <b>Заказ #{order_id} выполнен!</b>\n📦 {row[1]}", parse_mode="HTML")
    await call.message.edit_text(f"{call.message.text}\n\n✅ ВЫПОЛНЕНО", parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject(call: CallbackQuery):
    if call.from_user.username != ADMIN_USERNAME: 
        return await call.answer("Нет прав", show_alert=True)
    order_id = call.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()
    await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕНО", parse_mode="HTML")
    await call.answer()

# --- Покупка юзернеймов ---
@dp.callback_query(F.data == "menu_usernames")
async def show_usernames(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"select_uname_{uname}")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    text = "👑 <b>Эксклюзивные юзернеймы</b>\n\nВыбери ник."
    await send_menu_with_photo(call.message.chat.id, text, kb.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("select_uname_"))
async def confirm_uname(call: CallbackQuery, state: FSMContext):
    await state.clear()
    uname = call.data.replace("select_uname_", "")
    price = USERNAMES_DB[uname]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покупаю", callback_data=f"confirm_uname_{uname}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_usernames")]
    ])
    text = f"🤔 <b>Вы уверены, что хотите купить {uname} за {price} ⭐?</b>"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_uname_"))
async def process_uname_order(call: CallbackQuery):
    uname = call.data.replace("confirm_uname_", "")
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    price = USERNAMES_DB[uname]
    
    balance, _ = await get_user(user_id)
    if balance < price:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 В профиль", callback_data="menu_profile")]])
        text = f"❌ <b>Недостаточно звёзд!</b>\nБаланс: {balance} ⭐. Нужно: {price} ⭐."
        await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
        return

    await add_balance(user_id, -price)
    await add_history(user_id, f"Юзернейм {uname}", price)
    
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT id, item_data FROM stock WHERE item_name = ? AND is_sold = 0 LIMIT 1", (uname,)) as cursor:
            stock_item = await cursor.fetchone()

        if stock_item:
            stock_id, item_data = stock_item
            await db.execute("UPDATE stock SET is_sold = 1 WHERE id = ?", (stock_id,))
            cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, uname, code, "done"))
            order_id = cursor.lastrowid
            await db.commit()
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_start")]])
            text = f"🎉 <b>Заказ #{order_id} выполнен автоматически!</b>\n📦 {uname}\n🔑 <b>Данные:</b> <code>{item_data}</code>"
            await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
            return
            
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, uname, code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]])
    text = f"🎉 <b>Заказ #{order_id} создан!</b>\n📦 Юзернейм: {uname}\n🔑 Код: <code>{code}</code>"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"), InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ ЮЗЕРНЕЙМА #{order_id}</b>\nКлиент: @{username}\nТовар: {uname}\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "enter_promo")
async def enter_promo(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]])
    await send_menu_with_photo(call.message.chat.id, "🎟 Введи промокод в чат:", kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_promo)
async def process_promo(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    if code != "STARTOP2026":
        await message.answer("❌ Такого промокода нет.")
        await state.clear()
        return
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id FROM promo_activations WHERE user_id = ?", (user_id,)) as cursor:
            if await cursor.fetchone():
                await message.answer("❌ Ты уже активировал этот промокод.")
                await state.clear()
                return
        async with db.execute("SELECT uses FROM promo_stats WHERE promo_code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            uses = row[0] if row else 0
        if uses >= 10:
            await message.answer("❌ Лимит активаций исчерпан.")
            await state.clear()
            return
        await db.execute("INSERT INTO promo_activations (user_id, promo_code) VALUES (?, ?)", (user_id, code))
        if row:
            await db.execute("UPDATE promo_stats SET uses = uses + 1 WHERE promo_code = ?", (code,))
        else:
            await db.execute("INSERT INTO promo_stats (promo_code, uses) VALUES (?, 1)", (code,))
        await db.commit()
    await add_balance(user_id, 10)
    await add_history(user_id, f"Промокод {code}", 10)
    await message.answer("🎉 Промокод активирован! +10 ⭐")
    await state.clear()

@dp.callback_query(F.data == "topup_start")
async def topup_start(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_profile")]])
    text = "💳 <b>Пополнение баланса</b>\nНапишите в чат цифру от 25 до 1000:"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await state.set_state(UserStates.waiting_for_topup_amount)
    await call.answer()

@dp.message(UserStates.waiting_for_topup_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (25 <= int(message.text) <= 1000):
        return await message.answer("❌ Введи число от 25 до 1000.")
    amount = int(message.text)
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Оплатить рублями", callback_data=f"pay_rub_{amount}")],
        [InlineKeyboardButton(text="🪙 Оплатить криптой (USDT)", callback_data=f"pay_crypto_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]
    ])
    text = f"💳 <b>Как вы хотите оплатить {amount} звёзд?</b>"
    await send_menu_with_photo(message.chat.id, text, kb)
    await message.answer("👇 Жми на кнопку!")

@dp.callback_query(F.data == "menu_help")
async def show_help(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "📖 <b>Помощь</b>\n\n🌟 Покупка звёзд: Рубли или Крипта (USDT).\n👑 Покупка юзернеймов: За баланс звёзд."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Админ", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(call: CallbackQuery, state: FSMContext):
    await state.clear() 
    await send_menu_with_photo(call.message.chat.id, "👋 <b>Главное меню</b>", get_main_menu_kb(), call.message.message_id)
    await call.answer()

async def main():
    await init_db()
    await set_commands()
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"[*] Starsshop запущен. Ожидание платежей...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
