# language: Python, file: bot.py, target: Python 3.10+
# *Магазин Starsshop: Мини-игры (Краш, Монетка), Реферальная система, Оплата криптой*

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

USERNAMES_DB = {"@ynqnw5": 50}

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
    waiting_for_coin_choice = State()

app = Flask(__name__)
@app.route('/')
def health(): return "Starsshop is running ✨", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# --- БД ---
async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, last_bonus TIMESTAMP,
            referrer_id INTEGER, win_streak INTEGER DEFAULT 0
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item TEXT, price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, item TEXT, code TEXT, status TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_activations (user_id INTEGER PRIMARY KEY, promo_code TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_stats (promo_code TEXT PRIMARY KEY, uses INTEGER DEFAULT 0)""")
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

# --- Универсальная отправка ---
async def send_menu_with_photo(chat_id, text, keyboard, message_id=None):
    try:
        if message_id:
            try: await bot.delete_message(chat_id, message_id)
            except: pass
        await bot.send_photo(chat_id=chat_id, photo=IMAGE_URL, caption=text, reply_markup=keyboard, parse_mode="HTML")
    except:
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

def get_main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить Звёзды", callback_data="menu_buy")
    kb.button(text="👑 Купить Юзернейм", callback_data="menu_usernames")
    kb.button(text="🎮 Мини-Игры", callback_data="menu_games") # Новая вкладка
    kb.button(text="👥 Реферальная Система", callback_data="menu_ref_system") 
    kb.button(text="👤 Мой Профиль", callback_data="menu_profile")
    kb.button(text="📖 Помощь", callback_data="menu_help")
    kb.button(text="📞 Связь с Менеджером", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    return kb.as_markup()

async def set_commands(): await bot.set_my_commands([BotCommand(command="start", description="Открыть магазин")])

# --- CryptoBot ---
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

# --- Главное меню ---
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
        "💎 Здесь ты можешь купить звёзды за рубли/крипту или крутые юзернеймы за баланс.\n"
        "🚀 Быстро, выгодно и безопасно!\n\n"
        "💖 Мы очень рады видеть тебя здесь. Выбирай раздел и погнали:\n"
    )
    await send_menu_with_photo(message.chat.id, caption, get_main_menu_kb())

# --- Вкладка МИНИ-ИГРЫ ---
@dp.callback_query(F.data == "menu_games")
async def show_games(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance, _, _, _ = await get_user(call.from_user.id)
    
    text = (
        "🎮 <b>Добро пожаловать в Мини-Игры!</b> 🎰\n\n"
        f"💰 Твой баланс: <b>{balance} ⭐</b>\n\n"
        "🔥 Здесь ты можешь испытать удачу и приумножить свои звёзды!\n\n"
        "👇 <b>Доступные игры:</b>\n"
        "🚀 <b>Краш</b> — Множитель растет, успей забрать!\n"
        "🪙 <b>Монетка</b> — Орел или Решка, удвой ставку!\n\n"
        "Выбирай игру и испытывай фортуну! 🍀"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Играть в Краш", callback_data="game_crash")],
        [InlineKeyboardButton(text="🪙 Играть в Монетку", callback_data="game_coin")],
        [InlineKeyboardButton(text="🔙 Назад в Меню", callback_data="back_to_start")]
    ])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

# ==========================================
# --- ИГРА 1: КРАШ (CRASH) ---
# ==========================================
@dp.callback_query(F.data == "game_crash")
async def crash_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_bet_crash)
    text = (
        "🚀 <b>Краш (Crash)</b>\n\n"
        "Введи сумму ставки в звёздах (от 5 до 50):\n\n"
        "<i>Чем дольше летит ракета, тем больше множитель. Но она может взорваться в любой момент!</i> 💥"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_games")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_bet_crash)
async def crash_process_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ <b>Ошибка!</b> Введи число (цифрами).")
    bet = int(message.text)
    if bet < 5 or bet > 50:
        return await message.answer("❌ <b>Ошибка!</b> Ставка должна быть от 5 до 50 ⭐.")
    
    user_id = message.from_user.id
    balance, _, _, win_streak = await get_user(user_id)
    if balance < bet:
        return await message.answer("❌ <b>Ошибка!</b> Недостаточно звезд на балансе.")
    
    await state.clear()
    await add_balance(user_id, -bet) # Списываем ставку
    
    # --- ПОДКРУТКА (Анти-чит) ---
    # Если выиграл 2 раза подряд, следующий краш лопается почти сразу (на x1.1)
    if win_streak >= 2:
        crash_point = random.uniform(1.1, 1.2)
        await update_win_streak(user_id, 0) # Сбрасываем серию
    else:
        # Базовый шанс: ракета может лопнуть от 1.1 до 5.0
        crash_point = random.uniform(1.1, 5.0)
    
    # Запускаем анимацию и игру
    msg = await message.answer(f"🚀 <b>Ракета взлетает!</b>\nМножитель: <b>x1.0</b>")
    await asyncio.sleep(1)
    
    current_multiplier = 1.0
    while current_multiplier < crash_point:
        current_multiplier += 0.2
        if current_multiplier >= crash_point:
            break
        
        # Обновляем сообщение (имитация полета)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"💰 Забрать x{current_multiplier:.1f}", callback_data=f"crash_cashout_{bet}_{current_multiplier:.1f}")]])
        try:
            await msg.edit_text(f"🚀 <b>Ракета летит!</b>\nМножитель: <b>x{current_multiplier:.1f}</b>\n\n<i>Успей забрать!</i>", reply_markup=kb, parse_mode="HTML")
        except: pass
        await asyncio.sleep(0.5)
    
    # Если не успел забрать (лопнула)
    try:
        await msg.edit_text(
            f"💥 <b>БУМ! Ракета взорвалась на x{crash_point:.1f}</b>\n\n"
            f"😢 Ты потерял <b>{bet} ⭐</b>.\n\n"
            "Не расстраивайся, попробуй еще раз! 🍀",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎮 В Игры", callback_data="menu_games")]]),
            parse_mode="HTML"
        )
    except: pass

@dp.callback_query(F.data.startswith("crash_cashout_"))
async def crash_cashout(call: CallbackQuery, state: FSMContext):
    _, _, bet_str, mult_str = call.data.split("_")
    bet = int(bet_str)
    mult = float(mult_str)
    
    win_amount = int(bet * mult)
    profit = win_amount - bet
    
    await add_balance(call.from_user.id, win_amount) # Возвращаем ставку + выигрыш
    await add_history(call.from_user.id, "Выигрыш в Краш", win_amount)
    
    # Увеличиваем счетчик побед для подкрутки
    _, _, _, win_streak = await get_user(call.from_user.id)
    await update_win_streak(call.from_user.id, win_streak + 1)
    
    text = (
        f"💰 <b>Ты успел забрать!</b>\n\n"
        f"Множитель: <b>x{mult:.1f}</b>\n"
        f"Твой выигрыш: <b>{win_amount} ⭐</b>\n"
        f"Чистая прибыль: <b>+{profit} ⭐</b>\n\n"
        "Отличная реакция! 🎉"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Играть Еще", callback_data="game_crash")], [InlineKeyboardButton(text="🎮 В Игры", callback_data="menu_games")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer("💸 Деньги зачислены!")

# ==========================================
# --- ИГРА 2: МОНЕТКА (COIN) ---
# ==========================================
@dp.callback_query(F.data == "game_coin")
async def coin_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_bet_coin)
    text = (
        "🪙 <b>Монетка</b>\n\n"
        "Введи сумму ставки в звёздах (от 5 до 50):\n\n"
        "<i>Угадай сторону монетки и умножь ставку в 2 раза!</i> 💰"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_games")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_bet_coin)
async def coin_process_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ <b>Ошибка!</b> Введи число.")
    bet = int(message.text)
    if bet < 5 or bet > 50:
        return await message.answer("❌ <b>Ошибка!</b> Ставка от 5 до 50 ⭐.")
    
    user_id = message.from_user.id
    balance, _, _, _ = await get_user(user_id)
    if balance < bet:
        return await message.answer("❌ <b>Ошибка!</b> Недостаточно звезд.")
    
    await state.update_data(bet=bet)
    await state.set_state(UserStates.waiting_for_coin_choice)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🦅 Орел", callback_data="coin_choice_eagle")],
        [InlineKeyboardButton(text="🪙 Решка", callback_data="coin_choice_tails")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_games")]
    ])
    text = f"💸 Твоя ставка: <b>{bet} ⭐</b>\n\nВыбери сторону монетки:"
    await send_menu_with_photo(message.chat.id, text, kb)
    await message.answer("👇 Жми на кнопку!")

@dp.callback_query(F.data.startswith("coin_choice_"))
async def coin_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get('bet', 5)
    choice = call.data.split("_")[2] # eagle или tails
    user_id = call.from_user.id
    
    balance, _, _, win_streak = await get_user(user_id)
    if balance < bet:
        await call.answer("❌ Недостаточно звезд!", show_alert=True)
        return
    
    await state.clear()
    await add_balance(user_id, -bet) # Списываем ставку
    
    await call.message.edit_text("🪙 <b>Монетка подбрасывается...</b> ⏳", parse_mode="HTML")
    await asyncio.sleep(2) # Анимация полета
    
    # --- ПОДКРУТКА (Анти-чит) ---
    # Базовый шанс победы 45%. Если выиграл 2 раза подряд - принудительный проигрыш.
    if win_streak >= 2:
        win = False
        await update_win_streak(user_id, 0)
    else:
        win = random.random() < 0.45 # 45% шанс на победу
    
    result_side = choice if win else ("tails" if choice == "eagle" else "eagle")
    side_name = "🦅 Орел" if result_side == "eagle" else "🪙 Решка"
    
    if win:
        win_amount = bet * 2
        await add_balance(user_id, win_amount)
        await add_history(user_id, "Выигрыш в Монетку", win_amount)
        await update_win_streak(user_id, win_streak + 1)
        
        text = (
            f"🎉 <b>ПОБЕДА!</b>\n\n"
            f"Выпало: {side_name}\n"
            f"💰 Ты выиграл <b>{win_amount} ⭐</b> (x2)!\n\n"
            "Фортуна на твоей стороне! 🍀"
        )
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🪙 Играть Еще", callback_data="game_coin")], [InlineKeyboardButton(text="🎮 В Игры", callback_data="menu_games")]]), parse_mode="HTML")
    else:
        text = (
            f"😢 <b>ПРОИГРЫШ</b>\n\n"
            f"Выпало: {side_name}\n"
            f"Ты потерял <b>{bet} ⭐</b>.\n\n"
            "Не везет? Попробуй еще раз, удача любит настойчивых! 💪"
        )
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🪙 Играть Еще", callback_data="game_coin")], [InlineKeyboardButton(text="🎮 В Игры", callback_data="menu_games")]]), parse_mode="HTML")
    await call.answer()

# ==========================================
# --- ОСТАЛЬНОЙ ФУНКЦИОНАЛ (Без изменений) ---
# ==========================================

@dp.callback_query(F.data == "menu_ref_system")
async def show_ref_system(call: CallbackQuery, state: FSMContext):
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
            except:
                ref_list_text += f"👤 Пользователь (ID: {r_id})\n"
    else:
        ref_list_text = "Пока никого нет. 😢"

    text = (
        "👥 <b>Реферальная Система</b>\n\n"
        "Приглашай друзей и получай <b>10%</b> от их покупок звёзд!\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n<code>{ref_link}</code>\n\n"
        f"📊 <b>Твои рефералы:</b> {ref_count} чел.\n"
        "----------------\n"
        f"{ref_list_text}\n"
        "----------------\n\n"
        "👇 Жми кнопку ниже, чтобы поделиться ссылкой!"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=Заходи в лучший магазин звёзд!")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance, last_bonus, referrer_id, _ = await get_user(call.from_user.id)
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
    kb_builder.button(text="💳 Пополнить Баланс", callback_data="topup_start")
    kb_builder.button(text="🎟 Ввести Промокод", callback_data="enter_promo")
    if bonus_available:
        kb_builder.button(text="🎁 Забрать Бонус (+1 ⭐)", callback_data="claim_bonus")
    else:
        kb_builder.button(text="⏳ Бонус Уже Получен", callback_data="bonus_wait")
    kb_builder.button(text="🔙 Назад", callback_data="back_to_start")
    kb_builder.adjust(1)
    
    text = (
        f"👤 <b>Твой Профиль</b>\n\n"
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
    balance, last_bonus, _, _ = await get_user(user_id)
    if last_bonus and datetime.now() - datetime.fromisoformat(last_bonus) < timedelta(days=1):
        await call.answer("❌ Ошибка! Бонус уже получен сегодня. Приходи завтра! ⏳", show_alert=True)
        return
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + 1, last_bonus = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
        await db.commit()
    await add_history(user_id, "Бонус", 1)
    await call.answer("🎉 Успех! Ты получил 1 звезду на баланс! ⭐", show_alert=True)
    await show_profile(call, state)

@dp.callback_query(F.data == "bonus_wait")
async def bonus_wait(call: CallbackQuery):
    await call.answer("❌ Ошибка! Бонус можно брать раз в 24 часа. Возвращайся позже! ⏳", show_alert=True)

@dp.callback_query(F.data == "menu_buy")
async def buy_stars_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 Звёзд — 30₽", callback_data="select_stars_15")
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
        [InlineKeyboardButton(text="🇷🇺 Оплатить Рублями (30₽)", callback_data=f"pay_rub_{amount}")],
        [InlineKeyboardButton(text="🪙 Оплатить Криптой (~33₽)", callback_data=f"pay_crypto_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")]
    ])
    text = f"💳 <b>Как вы хотите купить {amount} звёзд?</b>"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("pay_rub_"))
async def pay_with_rub(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    price_rub = 30 if amount == 15 else amount * 2
    
    _, _, referrer_id, _ = await get_user(user_id)
    if referrer_id:
        ref_bonus = int(amount * 0.10)
        if ref_bonus > 0:
            await add_balance(referrer_id, ref_bonus)
            try: await bot.send_message(referrer_id, f"🎉 <b>Твой друг совершил покупку!</b>\n💰 Тебе начислено <b>{ref_bonus} ⭐</b> за реферала!", parse_mode="HTML")
            except: pass

    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, f"{amount} звёзд (Рубли)", code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Написать Менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]])
    text = (
        f"✅ <b>Успех! Заказ #{order_id} создан!</b>\n\n"
        f"📦 Товар: {amount} звёзд\n"
        f"💰 Оплата: <b>{price_rub}₽</b> (СБП/Карта)\n"
        f"🔑 <b>Код заказа: <code>{code}</code></b>\n\n"
        f"👇 Напиши менеджеру и отправь этот код:\n"
        f"<b>@{ADMIN_USERNAME}</b>"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"), InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ (РУБЛИ) #{order_id}</b>\nКлиент: @{username}\nТовар: {amount} звёзд\nК оплате: {price_rub}₽\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_with_crypto(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id
    usdt_amount = 0.36 if amount == 15 else round((amount * 2.2) / 90, 2)
    
    _, _, referrer_id, _ = await get_user(user_id)
    if referrer_id:
        ref_bonus = int(amount * 0.10)
        if ref_bonus > 0:
            await add_balance(referrer_id, ref_bonus)
            try: await bot.send_message(referrer_id, f"🎉 <b>Твой друг оплатил криптой!</b>\n💰 Тебе начислено <b>{ref_bonus} ⭐</b> за реферала!", parse_mode="HTML")
            except: pass

    await call.message.edit_caption(caption="⏳ <b>Создаем счет в CryptoBot...</b>", parse_mode="HTML")
    payload = f"crypto_topup_{user_id}_{amount}"
    pay_url, invoice_id = await create_crypto_invoice(usdt_amount, f"Покупка {amount} звёзд", payload)
    
    if not pay_url:
        await call.message.answer("❌ <b>Ошибка!</b> Не удалось создать счет.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 Перейти к оплате", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Я оплатил (Проверить)", callback_data=f"check_crypto_{invoice_id}_{amount}_{user_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")]
    ])
    text = f"✅ <b>Счет создан!</b>\n\nК оплате: <b>{usdt_amount} USDT</b>\nТовар: <b>{amount} звёзд</b>\n\n1. Оплати\n2. Нажми проверить"
    await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_payment(call: CallbackQuery):
    _, _, invoice_id, amount, user_id = call.data.split("_")
    invoice_id, amount, user_id = int(invoice_id), int(amount), int(user_id)
    
    await call.answer("⏳ Проверяем оплату...")
    if await check_crypto_invoice(invoice_id):
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
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В Меню", callback_data="back_to_start")]])
                await send_menu_with_photo(call.message.chat.id, f"🎉 <b>Оплата прошла!</b>\n📦 {amount} звёзд\n🔑 <code>{item_data}</code>", kb, call.message.message_id)
                return
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 В Профиль", callback_data="menu_profile")]])
        await send_menu_with_photo(call.message.chat.id, f"🎉 <b>Оплата прошла!</b>\nТебе начислено <b>{amount} ⭐</b>.", kb, call.message.message_id)
    else:
        await call.answer("❌ Оплата еще не поступила.", show_alert=True)

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

@dp.callback_query(F.data == "menu_usernames")
async def show_usernames(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"select_uname_{uname}")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    await send_menu_with_photo(call.message.chat.id, "👑 <b>Эксклюзивные Юзернеймы</b>\n\nВыбери ник.", kb.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("select_uname_"))
async def confirm_uname(call: CallbackQuery, state: FSMContext):
    await state.clear()
    uname = call.data.replace("select_uname_", "")
    price = USERNAMES_DB[uname]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Да, Покупаю", callback_data=f"confirm_uname_{uname}")], [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_usernames")]])
    await send_menu_with_photo(call.message.chat.id, f"🤔 <b>Купить {uname} за {price} ⭐?</b>", kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_uname_"))
async def process_uname_order(call: CallbackQuery):
    uname = call.data.replace("confirm_uname_", "")
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    price = USERNAMES_DB[uname]
    
    balance, _, _, _ = await get_user(user_id)
    if balance < price:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 В Профиль", callback_data="menu_profile")]])
        await send_menu_with_photo(call.message.chat.id, f"❌ <b>Ошибка! Недостаточно звёзд!</b>\nБаланс: {balance} ⭐. Нужно: {price} ⭐.", kb, call.message.message_id)
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
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В Меню", callback_data="back_to_start")]])
            await send_menu_with_photo(call.message.chat.id, f"🎉 <b>Успех! Заказ #{order_id} выполнен!</b>\n📦 {uname}\n🔑 <b>Данные:</b> <code>{item_data}</code>", kb, call.message.message_id)
            return
            
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, uname, code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Написать Менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]])
    await send_menu_with_photo(call.message.chat.id, f"✅ <b>Заказ #{order_id} создан!</b>\n📦 {uname}\n🔑 Код: <code>{code}</code>", kb, call.message.message_id)
    
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
        await message.answer("❌ <b>Ошибка! Такого промокода нет.</b> 😢")
        await state.clear()
        return
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id FROM promo_activations WHERE user_id = ?", (user_id,)) as cursor:
            if await cursor.fetchone():
                await message.answer("❌ <b>Ошибка! Ты уже активировал этот промокод.</b> 🙅‍♂️")
                await state.clear()
                return
        async with db.execute("SELECT uses FROM promo_stats WHERE promo_code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            uses = row[0] if row else 0
        if uses >= 10:
            await message.answer("❌ <b>Ошибка! Лимит активаций исчерпан.</b> 😔")
            await state.clear()
            return
        await db.execute("INSERT INTO promo_activations (user_id, promo_code) VALUES (?, ?)", (user_id, code))
        if row: await db.execute("UPDATE promo_stats SET uses = uses + 1 WHERE promo_code = ?", (code,))
        else: await db.execute("INSERT INTO promo_stats (promo_code, uses) VALUES (?, 1)", (code,))
        await db.commit()
    await add_balance(user_id, 10)
    await add_history(user_id, f"Промокод {code}", 10)
    await message.answer("🎉 <b>Успех! Промокод активирован!</b> 💰 +10 ⭐", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "topup_start")
async def topup_start(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_profile")]])
    await send_menu_with_photo(call.message.chat.id, "💳 <b>Пополнение Баланса</b>\nНапиши цифру от 25 до 1000:", kb, call.message.message_id)
    await state.set_state(UserStates.waiting_for_topup_amount)
    await call.answer()

@dp.message(UserStates.waiting_for_topup_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (25 <= int(message.text) <= 1000):
        return await message.answer("❌ <b>Ошибка! Введи число от 25 до 1000.</b>")
    amount = int(message.text)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇷🇺 Рублями", callback_data=f"pay_rub_{amount}")], [InlineKeyboardButton(text="🪙 Криптой (USDT)", callback_data=f"pay_crypto_{amount}")], [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]])
    await send_menu_with_photo(message.chat.id, f"💳 <b>Оплатить {amount} звёзд?</b>", kb)
    await message.answer("👇 Жми на кнопку!")

@dp.callback_query(F.data == "menu_help")
async def show_help(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "📖 <b>Помощь</b>\n\n🌟 Покупка звёзд: Рубли или Крипта.\n👑 Покупка юзернеймов: За баланс.\n👥 Рефералка: 10% с покупок.\n🎮 Игры: Краш и Монетка."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Админ", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(call: CallbackQuery, state: FSMContext):
    await state.clear() 
    await send_menu_with_photo(call.message.chat.id, "👋 <b>Главное Меню</b>", get_main_menu_kb(), call.message.message_id)
    await call.answer()

async def main():
    await init_db()
    await set_commands()
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"[*] Starsshop запущен. Игры активны.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
