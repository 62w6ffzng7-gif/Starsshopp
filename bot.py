# language: Python, file: bot.py, target: Python 3.10+
# *Магазин Starsshop: Финальная версия (Исправлены промокоды, убраны лишние ники)*

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
from aiogram.filters import Command, CommandStart
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

CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "314128:AA3GvM6yWgMQqrM8y1hwjf2Lv6w9MXvOReo") 
CRYPTO_API_URL = "https://pay.crypt.bot/api"
BOT_USERNAME = "Starsshop337_bot"

# Оставил только твой юзернейм
USERNAMES_DB = {
    "@ynqnw5": 25
}

PROMOCODES = {
    "STARTOP2026": 15,
    "NEWYEAR2026": 25,
    "WELCOME": 5,
    "CRYPTOFAN": 20,
    "STARSSHOP": 25,
    "FREESTARS": 10
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
    waiting_for_bet_crash = State()
    waiting_for_bet_coin = State()

app = Flask(__name__)
@app.route('/')
def health(): return "Starsshop is running ✨", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

active_crash_messages = set()

# --- БД ---
async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, last_bonus TIMESTAMP,
            referrer_id INTEGER, win_streak INTEGER DEFAULT 0
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item TEXT, price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, item TEXT, code TEXT, status TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_activations (user_id INTEGER, promo_code TEXT, PRIMARY KEY (user_id, promo_code))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS stock (id INTEGER PRIMARY KEY AUTOINCREMENT, item_name TEXT, item_data TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT balance, last_bonus, referrer_id, win_streak FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                await db.commit()
                return 0, None, None, 0
            return row[0], row[1], row[2], row[3]

async def add_balance(user_id, amount):
    await get_user(user_id)
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def update_win_streak(user_id, streak):
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET win_streak = ? WHERE user_id = ?", (streak, user_id))
        await db.commit()

async def add_history(user_id, item, price):
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("INSERT INTO history (user_id, item, price) VALUES (?, ?, ?)", (user_id, item, price))
        await db.commit()

def generate_code(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def send_menu_with_photo(chat_id, text, keyboard, message_id=None):
    try:
        if message_id:
            try: await bot.delete_message(chat_id, message_id)
            except: pass
        await bot.send_photo(chat_id=chat_id, photo=IMAGE_URL, caption=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка фото: {e}")
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

def get_main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить Звёзды", callback_data="btn_buy_stars")
    kb.button(text="👑 Купить Юзернейм", callback_data="btn_buy_uname")
    kb.button(text="🎮 Мини-Игры", callback_data="btn_games")
    kb.button(text="👥 Реферальная Система", callback_data="btn_ref") 
    kb.button(text="👤 Мой Профиль", callback_data="btn_profile")
    kb.button(text="📖 Помощь", callback_data="btn_help")
    kb.button(text="📞 Связь с Менеджером", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    return kb.as_markup()

async def set_commands(): await bot.set_my_commands([BotCommand(command="start", description="Открыть магазин")])

async def create_crypto_invoice(amount_usdt: float, description: str, payload: str):
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {"asset": "USDT", "amount": str(amount_usdt), "description": description, "payload": payload}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{CRYPTO_API_URL}/createInvoice", headers=headers, json=data) as resp:
            result = await resp.json()
            if result.get("ok"): return result["result"]["bot_invoice_url"], result["result"]["invoice_id"]
    return None, None

async def check_crypto_invoice(invoice_id: int):
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CRYPTO_API_URL}/getInvoices?invoice_ids={invoice_id}", headers=headers) as resp:
            result = await resp.json()
            if result.get("ok") and result["result"]["items"]:
                return result["result"]["items"][0]["status"] == "paid"
    return False

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
            if referrer_id != user_id:
                async with aiosqlite.connect("shop.db") as db:
                    async with db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
                        row = await cursor.fetchone()
                        if not row or row[0] is None:
                            await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
                            await db.commit()
                            await bot.send_message(referrer_id, f"🎉 <b>У тебя новый реферал!</b>\n👤 {message.from_user.first_name}\n💎 Как только он купит звёзды, ты получишь 10%!", parse_mode="HTML")
        except: pass

    await get_user(user_id)
    caption = (
        "👋 <b>Добро пожаловать в Starsshop!</b> 🌟\n\n"
        "💎 Здесь ты можешь купить звёзды по выгодному курсу или приобрести эксклюзивные юзернеймы.\n"
        "🚀 Все операции проводятся моментально и безопасно!\n\n"
        "👇 Выбирай нужный раздел и начинай:"
    )
    await send_menu_with_photo(message.chat.id, caption, get_main_menu_kb())

# --- ИГРЫ ---
@dp.callback_query(F.data == "btn_games")
async def show_games(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance, _, _, _ = await get_user(call.from_user.id)
    text = (
        "🎮 <b>Добро пожаловать в Мини-Игры!</b> 🎰\n\n"
        f"💰 Твой текущий баланс: <b>{balance} ⭐</b>\n\n"
        "🔥 Здесь ты можешь испытать настоящую удачу и приумножить свои звёзды!\n\n"
        "👇 <b>Доступные игры:</b>\n"
        "🚀 <b>Краш</b> — Ракета летит, множитель растет. Успей забрать до взрыва! (от 5 ⭐)\n"
        "🪙 <b>Монетка</b> — Орел или Решка. Угадай сторону и умножь ставку в 2 раза! (от 10 ⭐)\n\n"
        "Выбирай игру и испытывай фортуну! 🍀"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Играть в Краш", callback_data="game_crash_start")],
        [InlineKeyboardButton(text="🪙 Играть в Монетку", callback_data="game_coin_start")],
        [InlineKeyboardButton(text="🔙 Назад в Меню", callback_data="nav_back_main")]
    ])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "game_crash_start")
async def crash_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_bet_crash)
    text = "🚀 <b>Краш</b>\n\nВведи сумму ставки в звёздах (от 5 до 50):\n\n<i>Максимальный множитель — x3.0. Успей забрать!</i> 💥"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="nav_games")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_bet_crash)
async def crash_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ <b>Ошибка!</b> Введи число (цифрами).")
    bet = int(message.text)
    if bet < 5 or bet > 50: return await message.answer("❌ <b>Ошибка!</b> Ставка должна быть от 5 до 50 ⭐.")
    
    user_id = message.from_user.id
    balance, _, _, _ = await get_user(user_id)
    if balance < bet: return await message.answer(f"❌ <b>Ошибка!</b> Недостаточно звезд на балансе. У тебя {balance} ⭐.")
    
    await state.clear()
    await add_balance(user_id, -bet)
    
    crash_point = round(random.uniform(1.1, 3.0), 1)
    msg = await message.answer(f"🚀 <b>Ракета взлетает!</b>\nМножитель: <b>x1.0</b>")
    active_crash_messages.add(msg.message_id)
    await asyncio.sleep(1)
    
    current_multiplier = 1.0
    while current_multiplier < crash_point:
        if msg.message_id not in active_crash_messages: return
        current_multiplier += 0.1
        if current_multiplier >= crash_point: break
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"💰 Забрать x{current_multiplier:.1f}", callback_data=f"crash_take_{bet}_{current_multiplier:.1f}_{msg.message_id}")]])
        try: await msg.edit_text(f"🚀 <b>Ракета летит!</b>\nМножитель: <b>x{current_multiplier:.1f}</b>\n\n<i>Успей забрать!</i>", reply_markup=kb, parse_mode="HTML")
        except: pass
        await asyncio.sleep(0.6)
    
    if msg.message_id in active_crash_messages:
        active_crash_messages.remove(msg.message_id)
        try: await msg.edit_text(f"💥 <b>БУМ! Ракета взорвалась на x{crash_point:.1f}</b>\n\n😢 Ты потерял <b>{bet} ⭐</b>.\n\nНе расстраивайся, попробуй еще раз! 🍀", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎮 В Игры", callback_data="nav_games")]]), parse_mode="HTML")
        except: pass

@dp.callback_query(F.data.startswith("crash_take_"))
async def crash_take(call: CallbackQuery):
    _, _, bet_str, mult_str, msg_id_str = call.data.split("_")
    bet, mult, msg_id = int(bet_str), float(mult_str), int(msg_id_str)
    if msg_id not in active_crash_messages: return await call.answer("❌ Эта игра уже завершена!", show_alert=True)
    active_crash_messages.remove(msg_id)
    
    win_amount = int(bet * mult)
    profit = win_amount - bet
    await add_balance(call.from_user.id, win_amount) 
    await add_history(call.from_user.id, "Выигрыш в Краш", win_amount)
    
    text = f"💰 <b>Ты успел забрать!</b>\n\nМножитель: <b>x{mult:.1f}</b>\nТвой выигрыш: <b>{win_amount} ⭐</b>\nЧистая прибыль: <b>+{profit} ⭐</b>\n\nОтличная реакция! 🎉"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Играть Еще", callback_data="game_crash_start")], [InlineKeyboardButton(text="🎮 В Игры", callback_data="nav_games")]])
    try:
        await call.message.delete()
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    except: pass
    await call.answer("💸 Деньги зачислены!")

@dp.callback_query(F.data == "game_coin_start")
async def coin_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_bet_coin)
    text = "🪙 <b>Монетка</b>\n\nВведи сумму ставки в звёздах (от 10 до 100):\n\n<i>Угадай сторону и умножь ставку в 2 раза!</i> 💰"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="nav_games")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_bet_coin)
async def coin_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ <b>Ошибка!</b> Введи число.")
    bet = int(message.text)
    if bet < 10 or bet > 100: return await message.answer("❌ <b>Ошибка!</b> Ставка от 10 до 100 ⭐.")
    
    user_id = message.from_user.id
    balance, _, _, _ = await get_user(user_id)
    if balance < bet: return await message.answer(f"❌ <b>Ошибка!</b> Недостаточно звезд.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🦅 Орел", callback_data=f"coin_side_eagle_{bet}")],
        [InlineKeyboardButton(text="🪙 Решка", callback_data=f"coin_side_tails_{bet}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="nav_games")]
    ])
    text = f"💸 Твоя ставка: <b>{bet} ⭐</b>\n\nВыбери сторону монетки:"
    await send_menu_with_photo(message.chat.id, text, kb)
    await message.answer("👇 Жми на кнопку!")

@dp.callback_query(F.data.startswith("coin_side_"))
async def coin_play(call: CallbackQuery, state: FSMContext):
    _, _, choice, bet_str = call.data.split("_")
    bet = int(bet_str)
    user_id = call.from_user.id
    
    balance, _, _, win_streak = await get_user(user_id)
    if balance < bet: return await call.answer("❌ Недостаточно звезд!", show_alert=True)
    
    await state.clear()
    await add_balance(user_id, -bet)
    
    msg = await call.message.edit_text("🪙 <b>Монетка подбрасывается...</b> ⏳", parse_mode="HTML")
    await asyncio.sleep(1)
    await call.message.edit_text("🪙 <b>Летит...</b> 🌀", parse_mode="HTML")
    await asyncio.sleep(1)
    
    if win_streak >= 2:
        win = False
        await update_win_streak(user_id, 0)
    else:
        win = random.random() < 0.45 
    
    result_side = choice if win else ("tails" if choice == "eagle" else "eagle")
    side_name = "🦅 Орел" if result_side == "eagle" else "🪙 Решка"
    
    if win:
        win_amount = bet * 2
        await add_balance(user_id, win_amount)
        await add_history(user_id, "Выигрыш в Монетку", win_amount)
        await update_win_streak(user_id, win_streak + 1)
        text = f"🎉 <b>ПОБЕДА!</b>\n\nВыпало: {side_name}\n💰 Ты выиграл <b>{win_amount} ⭐</b> (x2)!\n\nФортуна на твоей стороне! 🍀"
    else:
        text = f"😢 <b>ПРОИГРЫШ</b>\n\nВыпало: {side_name}\nТы потерял <b>{bet} ⭐</b>.\n\nНе везет? Попробуй еще раз, удача любит настойчивых! 💪"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🪙 Играть Еще", callback_data="game_coin_start")], [InlineKeyboardButton(text="🎮 В Игры", callback_data="nav_games")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "btn_topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="btn_profile")]])
    text = "💳 <b>Пополнение баланса</b>\n\nНапиши в чат, сколько звезд ты хочешь купить (от 1 до 10000):"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await state.set_state(UserStates.waiting_for_topup_amount)
    await call.answer()

@dp.message(UserStates.waiting_for_topup_amount)
async def process_topup(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 10000):
        return await message.answer("❌ <b>Ошибка!</b> Введи число от 1 до 10000.")
    
    amount = int(message.text)
    await state.clear()
    
    prices = [LabeledPrice(label="Пополнение баланса", amount=amount)]
    try:
        await bot.send_invoice(
            chat_id=message.from_user.id,
            title=f"Пополнение на {amount} ⭐",
            description=f"Зачисление {amount} звезд на ваш внутренний баланс.",
            payload=f"topup_{amount}",
            provider_token="", 
            currency="XTR", 
            prices=prices
        )
        await message.answer("☝️ Выше выставлен счет. Оплатите его, чтобы зачислить звезды.")
    except Exception as e:
        await message.answer(f"❌ <b>Ошибка выставления счета:</b>\n<code>{e}</code>")

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("topup_"):
        amount = int(payload.split("_")[1])
        user_id = message.from_user.id
        username = message.from_user.username or "нет_юзернейма"
        
        await add_balance(user_id, amount)
        await add_history(user_id, f"Пополнение на {amount} ⭐", amount)
        
        await message.answer(
            f"✅ <b>Успех! Баланс пополнен на {amount} ⭐</b>\n\n"
            "Спасибо за покупку! Теперь вы можете потратить их в играх или на юзернеймы.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 В Профиль", callback_data="btn_profile")]]),
            parse_mode="HTML"
        )
        
        if ADMIN_ID != 0:
            try:
                await bot.send_message(
                    ADMIN_ID, 
                    f"🔔 <b>НОВОЕ ПОПОЛНЕНИЕ БАЛАНСА!</b>\n\n"
                    f"👤 Клиент: @{username} (ID: <code>{user_id}</code>)\n"
                    f"💰 Сумма: <b>{amount} ⭐</b>\n\n"
                    f"<i>Звезды успешно зачислены на баланс бота.</i>",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление админу: {e}")

# ==========================================
# --- ПРОМОКОДЫ (ПОЛНОСТЬЮ ИСПРАВЛЕНО) ---
# ==========================================
@dp.callback_query(F.data == "btn_promo")
async def promo_start(call: CallbackQuery, state: FSMContext):
    # Обязательно очищаем стейт перед установкой нового
    await state.clear() 
    await state.set_state(UserStates.waiting_for_promo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="btn_profile")]])
    text = "🎟 <b>Активация промокода</b>\n\nОтправь мне промокод в чат, и я начислю тебе бонусные звезды! ✨"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_promo)
async def process_promo(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    
    if code == "/CANCEL":
        await state.clear()
        return await message.answer("❌ Отменено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В Профиль", callback_data="btn_profile")]]))

    # Проверка на существование кода
    if code not in PROMOCODES:
        await message.answer("❌ <b>Ошибка! Такого промокода не существует.</b> 😢")
        await state.clear() # Сбрасываем, чтобы не спамил
        return
        
    bonus_amount = PROMOCODES[code]
        
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id FROM promo_activations WHERE user_id = ? AND promo_code = ?", (user_id, code)) as cursor:
            if await cursor.fetchone():
                await message.answer("❌ <b>Ошибка! Ты уже активировал этот код.</b> 🙅‍♂️")
                await state.clear()
                return
        await db.execute("INSERT INTO promo_activations (user_id, promo_code) VALUES (?, ?)", (user_id, code))
        await db.commit()
        
    await add_balance(user_id, bonus_amount)
    await add_history(user_id, f"Промокод {code}", bonus_amount)
    
    await message.answer(
        f"🎉 <b>Успех! Промокод активирован!</b>\n\n"
        f"💰 Тебе начислено <b>+{bonus_amount} ⭐</b> на баланс.\n\n"
        "Спасибо, что ты с нами! 💖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 В Профиль", callback_data="btn_profile")]]),
        parse_mode="HTML"
    )
    await state.clear()

@dp.callback_query(F.data == "btn_ref")
async def ref_system(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = call.from_user.id
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)) as cursor:
            ref_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT user_id FROM users WHERE referrer_id = ? ORDER BY user_id DESC LIMIT 5", (user_id,)) as cursor:
            ref_ids = await cursor.fetchall()

    ref_list_text = ""
    if ref_ids:
        for (r_id,) in ref_ids:
            try:
                user_info = await bot.get_chat(r_id)
                ref_list_text += f"👤 {user_info.first_name}\n"
            except: ref_list_text += f"👤 ID: {r_id}\n"
    else: ref_list_text = "Пока никого нет. 😢"

    text = (
        "👥 <b>Реферальная Система</b>\n\n"
        "Приглашай друзей и получай <b>10%</b> от их покупок звёзд!\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n<code>{ref_link}</code>\n\n"
        f"📊 <b>Твои рефералы:</b> {ref_count} чел.\n----------------\n{ref_list_text}\n----------------\n\n"
        "👇 Жми кнопку ниже, чтобы поделиться ссылкой!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text=Заходи в лучший магазин звёзд!")], [InlineKeyboardButton(text="🔙 Назад", callback_data="nav_back_main")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "btn_profile")
async def profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance, last_bonus, _, _ = await get_user(call.from_user.id)
    history_text = ""
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT item, price FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 3", (call.from_user.id,)) as cursor:
            rows = await cursor.fetchall()
            history_text = "\n".join([f"• {item} — {price} ⭐" for item, price in rows]) if rows else "Покупок пока нет. 😉"
            
    bonus_available = True
    if last_bonus:
        last_dt = datetime.fromisoformat(last_bonus)
        if datetime.now() - last_dt < timedelta(days=1): bonus_available = False

    kb_builder = InlineKeyboardBuilder()
    kb_builder.button(text="💳 Пополнить Баланс", callback_data="btn_topup")
    kb_builder.button(text="🎟 Ввести Промокод", callback_data="btn_promo")
    if bonus_available: kb_builder.button(text="🎁 Забрать Бонус (+1 ⭐)", callback_data="btn_claim_bonus")
    else: kb_builder.button(text="⏳ Бонус Уже Получен", callback_data="btn_bonus_wait")
    kb_builder.button(text="🔙 Назад", callback_data="nav_back_main")
    kb_builder.adjust(1)
    
    text = (
        f"👤 <b>Твой Профиль</b>\n\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n"
        f"💰 Баланс звёзд: <b>{balance} ⭐</b>\n\n"
        f"📜 <b>История покупок:</b>\n{history_text}\n\n"
        f"<i>Баланс нужен для покупки юзернеймов и игр!</i> 💖"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb_builder.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "btn_claim_bonus")
async def claim_bonus(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    balance, last_bonus, _, _ = await get_user(user_id)
    if last_bonus and datetime.now() - datetime.fromisoformat(last_bonus) < timedelta(days=1):
        return await call.answer("❌ Ошибка! Бонус уже получен сегодня. Приходи завтра!", show_alert=True)
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + 1, last_bonus = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
        await db.commit()
    await add_history(user_id, "Бонус", 1)
    await call.answer("🎉 Успех! Ты получил 1 звезду!", show_alert=True)
    await profile(call, state)

@dp.callback_query(F.data == "btn_bonus_wait")
async def bonus_wait(call: CallbackQuery):
    await call.answer("❌ Ошибка! Бонус можно брать раз в 24 часа.", show_alert=True)

@dp.callback_query(F.data == "btn_buy_stars")
async def buy_stars(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 Звёзд — 30₽", callback_data="pay_select_15")
    kb.button(text="🔙 Назад", callback_data="nav_back_main")
    kb.adjust(1)
    text = "🛒 <b>Пакет звёзд:</b>\n\n🌟 Выбери удобный способ оплаты. Все операции моментальные!"
    await send_menu_with_photo(call.message.chat.id, text, kb.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "pay_select_15")
async def choose_pay(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇷🇺 Оплатить Рублями (30₽)", callback_data="pay_rub_15")], [InlineKeyboardButton(text="🪙 Оплатить Криптой (33₽)", callback_data="pay_crypto_15")], [InlineKeyboardButton(text="❌ Отмена", callback_data="nav_back_main")]])
    text = "💳 <b>Как вы хотите оплатить 15 звёзд?</b>"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "pay_rub_15")
async def pay_rub(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    price_rub = 30
    
    _, _, referrer_id, _ = await get_user(user_id)
    if referrer_id:
        await add_balance(referrer_id, 1)
        try: await bot.send_message(referrer_id, "🎉 Твой друг совершил покупку! Тебе начислено +1 ⭐", parse_mode="HTML")
        except: pass

    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, "15 звёзд (Рубли)", code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Написать Менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]])
    text = f"✅ <b>Успех! Заказ #{order_id} создан!</b>\n\n📦 Товар: 15 звёзд\n💰 К оплате: <b>{price_rub}₽</b>\n🔑 Код заказа: <code>{code}</code>\n\n👇 Напиши менеджеру и отправь этот код:\n<b>@{ADMIN_USERNAME}</b>"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"), InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]])
        await bot.send_message(ADMIN_ID, f"🔔 <b>НОВЫЙ ЗАКАЗ (РУБЛИ) #{order_id}</b>\n\n👤 Клиент: @{username}\n🆔 ID: <code>{user_id}</code>\n📦 Товар: 15 звёзд\n💰 К оплате: {price_rub}₽\n🔑 Код: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "pay_crypto_15")
async def pay_crypto(call: CallbackQuery):
    await call.message.edit_caption(caption="⏳ Создаем счет...", parse_mode="HTML")
    pay_url, invoice_id = await create_crypto_invoice(0.36, "15 звёзд", "crypto_15")
    if not pay_url: return await call.message.answer("❌ Ошибка.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🪙 Оплатить", url=pay_url)], [InlineKeyboardButton(text="🔄 Проверить", callback_data=f"check_crypto_{invoice_id}_15")], [InlineKeyboardButton(text="❌ Отмена", callback_data="nav_back_main")]])
    await call.message.edit_caption(caption="✅ Счет создан. Оплати и нажми проверить.", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto(call: CallbackQuery):
    _, _, invoice_id, amount = call.data.split("_")
    if await check_crypto_invoice(int(invoice_id)):
        await add_balance(call.from_user.id, int(amount))
        await add_history(call.from_user.id, f"{amount} звёзд (Крипта)", int(amount))
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 В Профиль", callback_data="btn_profile")]])
        await send_menu_with_photo(call.message.chat.id, f"🎉 <b>Оплата прошла!</b>\nЗачислено {amount} ⭐", kb, call.message.message_id)
    else:
        await call.answer("❌ Еще не оплачено.", show_alert=True)

@dp.callback_query(F.data == "btn_buy_uname")
async def show_unames(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    # Тут теперь только один твой ник
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"uname_sel_{uname}")
    kb.button(text="🔙 Назад", callback_data="nav_back_main")
    kb.adjust(1)
    await send_menu_with_photo(call.message.chat.id, "👑 <b>Эксклюзивные Юзернеймы</b>\n\nВыбери ник.", kb.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("uname_sel_"))
async def confirm_uname(call: CallbackQuery):
    uname = call.data.replace("uname_sel_", "")
    price = USERNAMES_DB[uname]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Купить", callback_data=f"uname_buy_{uname}")], [InlineKeyboardButton(text="❌ Отмена", callback_data="btn_buy_uname")]])
    await send_menu_with_photo(call.message.chat.id, f"🤔 Купить <b>{uname}</b> за {price} ⭐?", kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("uname_buy_"))
async def buy_uname(call: CallbackQuery):
    uname = call.data.replace("uname_buy_", "")
    price = USERNAMES_DB[uname]
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    
    balance, _, _, _ = await get_user(user_id)
    if balance < price:
        return await call.answer("❌ Недостаточно звезд!", show_alert=True)

    await add_balance(user_id, -price)
    await add_history(user_id, f"Ник {uname}", price)
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, uname, code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]])
    await send_menu_with_photo(call.message.chat.id, f"✅ <b>Заказ #{order_id} создан!</b>\n📦 {uname}\n🔑 Код: <code>{code}</code>", kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"), InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ ЮЗЕРНЕЙМА #{order_id}</b>\nКлиент: @{username}\nТовар: {uname}\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "btn_help")
async def help_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📖 <b>Центр Помощи Starsshop</b>\n\n"
        "🌟 <b>Покупка Звёзд:</b> Выбираешь пакет, оплачиваешь рублями или криптой. Звезды моментально падают на баланс.\n\n"
        "👑 <b>Покупка Юзернеймов:</b> Нужны звезды на балансе. Покупаешь ник, получаешь код, пишешь менеджеру.\n\n"
        "👥 <b>Реферальная Система:</b> Приглашай друзей и получай 10% с их покупок!\n\n"
        "🎮 <b>Мини-Игры:</b> Краш и Монетка. Испытай удачу!\n\n"
        f"💬 <b>Менеджер:</b> @{ADMIN_USERNAME}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Написать Админу", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="nav_back_main")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "nav_back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear() 
    await send_menu_with_photo(call.message.chat.id, "👋 <b>Главное Меню</b>", get_main_menu_kb(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "nav_games")
async def back_games(call: CallbackQuery, state: FSMContext):
    await state.clear() 
    await show_games(call, state)

@dp.callback_query(F.data.startswith("adm_done_"))
async def admin_done(call: CallbackQuery):
    if call.from_user.username != ADMIN_USERNAME: return await call.answer("Нет прав", show_alert=True)
    order_id = call.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET status = 'done' WHERE id = ?", (order_id,))
        await db.commit()
        async with db.execute("SELECT user_id, item FROM orders WHERE id = ?", (order_id,)) as c:
            row = await c.fetchone()
            if row: await bot.send_message(row[0], f"🎉 <b>Заказ #{order_id} выполнен!</b>\n📦 {row[1]}", parse_mode="HTML")
    await call.message.edit_text(f"{call.message.text}\n\n✅ ВЫПОЛНЕНО", parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject(call: CallbackQuery):
    if call.from_user.username != ADMIN_USERNAME: return await call.answer("Нет прав", show_alert=True)
    order_id = call.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()
    await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕНО", parse_mode="HTML")
    await call.answer()

async def main():
    await init_db()
    await set_commands()
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"[*] Starsshop запущен. Ожидание действий.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
