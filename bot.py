# language: Python, file: bot.py, target: Python 3.10+
# *Магазин Starsshop: Финальная версия (Исправлен Краш и Монетка)*

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

USERNAMES_DB = {"@ynqnw5": 25}
PROMOCODES = {"STARTOP2026": 15, "NEWYEAR2026": 25, "WELCOME": 5, "CRYPTOFAN": 20, "STARSSHOP": 25, "FREESTARS": 10}
# ==============================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class UserStates(StatesGroup):
    waiting_for_topup_amount = State()
    waiting_for_promo = State()
    # Игры
    waiting_for_bet_crash = State()
    waiting_for_bet_coin = State()
    waiting_for_coin_choice = State()

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
    await get_user(message.from_user.id)
    caption = "👋 <b>Добро пожаловать в Starsshop!</b> 🌟\n\n💎 Здесь ты можешь купить звёзды или юзернеймы.\n🚀 Быстро, выгодно и безопасно!"
    await send_menu_with_photo(message.chat.id, caption, get_main_menu_kb())

# ==========================================
# --- ИГРЫ ---
# ==========================================
@dp.callback_query(F.data == "btn_games")
async def show_games(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance, _, _, _ = await get_user(call.from_user.id)
    text = (
        "🎮 <b>Мини-Игры</b> 🎰\n\n"
        f"💰 Твой баланс: <b>{balance} ⭐</b>\n\n"
        "🚀 <b>Краш</b> — Успей забрать до взрыва! (от 5 ⭐)\n"
        "🪙 <b>Монетка</b> — Орел или Решка, удвой ставку! (от 10 ⭐)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Краш", callback_data="game_crash_start")],
        [InlineKeyboardButton(text="🪙 Монетка", callback_data="game_coin_start")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="nav_back_main")]
    ])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

# --- ИГРА 1: КРАШ (ИСПРАВЛЕН) ---
@dp.callback_query(F.data == "game_crash_start")
async def crash_start(call: CallbackQuery, state: FSMContext):
    # Устанавливаем именно состояние КРАША
    await state.set_state(UserStates.waiting_for_bet_crash)
    text = "🚀 <b>Краш</b>\n\nВведи сумму ставки (от 5 до 50):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="nav_games")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_bet_crash)
async def crash_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Введи число.")
    bet = int(message.text)
    if bet < 5 or bet > 50: return await message.answer("❌ Ставка от 5 до 50 ⭐.")
    
    user_id = message.from_user.id
    balance, _, _, _ = await get_user(user_id)
    if balance < bet: return await message.answer("❌ Недостаточно звезд.")
    
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
        try: await msg.edit_text(f"🚀 <b>Ракета летит!</b>\nМножитель: <b>x{current_multiplier:.1f}</b>", reply_markup=kb, parse_mode="HTML")
        except: pass
        await asyncio.sleep(0.6)
    
    if msg.message_id in active_crash_messages:
        active_crash_messages.remove(msg.message_id)
        try: await msg.edit_text(f"💥 <b>БУМ! x{crash_point:.1f}</b>\n😢 Потеряно <b>{bet} ⭐</b>.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎮 В Игры", callback_data="nav_games")]]), parse_mode="HTML")
        except: pass

@dp.callback_query(F.data.startswith("crash_take_"))
async def crash_take(call: CallbackQuery):
    _, _, bet_str, mult_str, msg_id_str = call.data.split("_")
    bet, mult, msg_id = int(bet_str), float(mult_str), int(msg_id_str)
    
    if msg_id not in active_crash_messages: return await call.answer("❌ Игра завершена!", show_alert=True)
    active_crash_messages.remove(msg_id)
    
    win_amount = int(bet * mult)
    await add_balance(call.from_user.id, win_amount) 
    await add_history(call.from_user.id, "Краш", win_amount)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Еще", callback_data="game_crash_start")], [InlineKeyboardButton(text="🎮 В Игры", callback_data="nav_games")]])
    try:
        await call.message.delete()
        await call.message.answer(f"💰 <b>Забрал на x{mult:.1f}!</b>\nВыигрыш: <b>{win_amount} ⭐</b>.", reply_markup=kb, parse_mode="HTML")
    except: pass
    await call.answer("💸 Зачислено!")

# --- ИГРА 2: МОНЕТКА (ИСПРАВЛЕНА) ---
@dp.callback_query(F.data == "game_coin_start")
async def coin_start(call: CallbackQuery, state: FSMContext):
    # Устанавливаем именно состояние МОНЕТКИ
    await state.set_state(UserStates.waiting_for_bet_coin)
    text = "🪙 <b>Монетка</b>\n\nВведи сумму ставки (от 10 до 100):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="nav_games")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_bet_coin)
async def coin_bet(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Введи число.")
    bet = int(message.text)
    if bet < 10 or bet > 100: return await message.answer("❌ Ставка от 10 до 100 ⭐.")
    
    user_id = message.from_user.id
    balance, _, _, _ = await get_user(user_id)
    if balance < bet: return await message.answer("❌ Недостаточно звезд.")
    
    await state.update_data(coin_bet=bet)
    await state.set_state(UserStates.waiting_for_coin_choice)
    
    text = f"💸 Твоя ставка: <b>{bet} ⭐</b>\n\nНапиши в чат одно слово:\n🦅 <b>Орел</b>\n🪙 <b>Решка</b>"
    await message.answer(text, parse_mode="HTML")

@dp.message(UserStates.waiting_for_coin_choice)
async def coin_play(message: types.Message, state: FSMContext):
    user_choice = message.text.strip().lower()
    
    if user_choice not in ["орел", "решка"]:
        return await message.answer("❌ <b>Ошибка!</b> Напиши ровно одно слово: <b>Орел</b> или <b>Решка</b>.")
    
    data = await state.get_data()
    bet = data.get('coin_bet', 0)
    await state.clear()
    
    if bet <= 0: return await message.answer("❌ Ошибка. Начните заново.")
    
    user_id = message.from_user.id
    balance, _, _, win_streak = await get_user(user_id)
    if balance < bet: return await message.answer("❌ Недостаточно звезд.")
    
    await add_balance(user_id, -bet)
    
    msg = await message.answer("🪙", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("🪙 <b>Монетка крутится...</b> ⏳", parse_mode="HTML")
    await asyncio.sleep(2)
    
    if win_streak >= 2:
        win = False
        await update_win_streak(user_id, 0)
    else:
        win = random.random() < 0.45 
    
    result_side = random.choice(["орел", "решка"])
    side_name = "🦅 Орел" if result_side == "орел" else "🪙 Решка"
    
    if not win and result_side == user_choice:
        result_side = "решка" if user_choice == "орел" else "орел"
        side_name = "🦅 Орел" if result_side == "орел" else "🪙 Решка"
        
    if win and result_side == user_choice:
        win_amount = bet * 2
        await add_balance(user_id, win_amount)
        await add_history(user_id, "Монетка", win_amount)
        await update_win_streak(user_id, win_streak + 1)
        text = f"🎉 <b>ПОБЕДА!</b>\n\nВыпало: {side_name}\n💰 Ты выиграл <b>{win_amount} ⭐</b>!\n\nФортуна на твоей стороне! 🍀"
    else:
        text = f"😢 <b>ПРОИГРЫШ</b>\n\nВыпало: {side_name}\nТы потерял <b>{bet} ⭐</b>.\n\nНе везет? Попробуй еще раз! 💪"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🪙 Играть Еще", callback_data="game_coin_start")], [InlineKeyboardButton(text="🎮 В Игры", callback_data="nav_games")]])
    await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")

# ==========================================
# --- ПОПОЛНЕНИЕ ---
# ==========================================
@dp.callback_query(F.data == "btn_topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="btn_profile")]])
    await send_menu_with_photo(call.message.chat.id, "💳 <b>Пополнение</b>\nНапиши сколько звезд купить (от 1 до 10000):", kb, call.message.message_id)
    await state.set_state(UserStates.waiting_for_topup_amount)
    await call.answer()

@dp.message(UserStates.waiting_for_topup_amount)
async def process_topup(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 10000):
        return await message.answer("❌ Введи число от 1 до 10000.")
    
    amount = int(message.text)
    await state.clear()
    
    prices = [LabeledPrice(label="Пополнение", amount=amount)]
    try:
        await bot.send_invoice(
            chat_id=message.from_user.id,
            title=f"Пополнение на {amount} ⭐",
            description=f"Зачисление {amount} звезд.",
            payload=f"topup_{amount}",
            provider_token="", 
            currency="XTR", 
            prices=prices
        )
        await message.answer("☝️ Выше выставлен счет. Оплатите его.")
    except Exception as e:
        await message.answer(f"❌ <b>Ошибка:</b>\n<code>{e}</code>")

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
        await add_history(user_id, f"Пополнение", amount)
        
        await message.answer(f"✅ <b>Баланс пополнен на {amount} ⭐</b>", parse_mode="HTML")
        
        if ADMIN_ID != 0:
            try:
                await bot.send_message(
                    ADMIN_ID, 
                    f"🔔 <b>ПОПОЛНЕНИЕ!</b>\n👤 @{username} (ID: <code>{user_id}</code>)\n💰 Сумма: <b>{amount} ⭐</b>",
                    parse_mode="HTML"
                )
            except: pass

# ==========================================
# --- ПРОМОКОДЫ ---
# ==========================================
@dp.callback_query(F.data == "btn_promo")
async def promo_start(call: CallbackQuery, state: FSMContext):
    await state.clear() 
    await state.set_state(UserStates.waiting_for_promo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="btn_profile")]])
    await send_menu_with_photo(call.message.chat.id, "🎟 <b>Введи промокод в чат:</b>", kb, call.message.message_id)
    await call.answer()

@dp.message(UserStates.waiting_for_promo)
async def process_promo(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    
    if code == "/CANCEL":
        await state.clear()
        return await message.answer("❌ Отменено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В Профиль", callback_data="btn_profile")]]))

    if code not in PROMOCODES:
        await message.answer("❌ <b>Неверный промокод.</b>")
        await state.clear()
        return
        
    bonus_amount = PROMOCODES[code]
        
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id FROM promo_activations WHERE user_id = ? AND promo_code = ?", (user_id, code)) as cursor:
            if await cursor.fetchone():
                await message.answer("❌ <b>Вы уже активировали этот код.</b>")
                await state.clear()
                return
        await db.execute("INSERT INTO promo_activations (user_id, promo_code) VALUES (?, ?)", (user_id, code))
        await db.commit()
        
    await add_balance(user_id, bonus_amount)
    await add_history(user_id, f"Промокод {code}", bonus_amount)
    
    await message.answer(
        f"🎉 <b>Промокод активирован!</b>\n💰 +{bonus_amount} ⭐",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 В Профиль", callback_data="btn_profile")]]),
        parse_mode="HTML"
    )
    await state.clear()

# ==========================================
# --- ПРОФИЛЬ И РЕФЕРАЛКА ---
# ==========================================
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
    else: ref_list_text = "Никого нет. 😢"

    text = (
        "👥 <b>Рефералка</b>\n\n"
        "Приглашай друзей и получай <b>10%</b>!\n\n"
        f"🔗 <code>{ref_link}</code>\n\n"
        f"📊 Рефералов: {ref_count}\n----------------\n{ref_list_text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text=Заходи в магазин!")], [InlineKeyboardButton(text="🔙 Назад", callback_data="nav_back_main")]])
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
            history_text = "\n".join([f"• {item} — {price} ⭐" for item, price in rows]) if rows else "Покупок нет. 😉"
            
    bonus_available = True
    if last_bonus:
        last_dt = datetime.fromisoformat(last_bonus)
        if datetime.now() - last_dt < timedelta(days=1): bonus_available = False

    kb_builder = InlineKeyboardBuilder()
    kb_builder.button(text="💳 Пополнить", callback_data="btn_topup")
    kb_builder.button(text="🎟 Промокод", callback_data="btn_promo")
    if bonus_available: kb_builder.button(text="🎁 Бонус (+1 ⭐)", callback_data="btn_claim_bonus")
    else: kb_builder.button(text="⏳ Бонус получен", callback_data="btn_bonus_wait")
    kb_builder.button(text="🔙 Назад", callback_data="nav_back_main")
    kb_builder.adjust(1)
    
    text = f"👤 <b>Профиль</b>\n\n🆔 <code>{call.from_user.id}</code>\n💰 Баланс: <b>{balance} ⭐</b>\n\n📜 <b>История:</b>\n{history_text}"
    await send_menu_with_photo(call.message.chat.id, text, kb_builder.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "btn_claim_bonus")
async def claim_bonus(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    balance, last_bonus, _, _ = await get_user(user_id)
    if last_bonus and datetime.now() - datetime.fromisoformat(last_bonus) < timedelta(days=1):
        return await call.answer("❌ Уже получен сегодня.", show_alert=True)
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + 1, last_bonus = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
        await db.commit()
    await add_history(user_id, "Бонус", 1)
    await call.answer("🎉 +1 звезда!", show_alert=True)
    await profile(call, state)

@dp.callback_query(F.data == "btn_bonus_wait")
async def bonus_wait(call: CallbackQuery):
    await call.answer("❌ Жди 24 часа.", show_alert=True)

@dp.callback_query(F.data == "btn_buy_stars")
async def buy_stars(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 Звёзд — 30₽", callback_data="pay_select_15")
    kb.button(text="🔙 Назад", callback_data="nav_back_main")
    kb.adjust(1)
    text = "🛒 <b>Пакет звёзд:</b>\n\nВыбери способ оплаты."
    await send_menu_with_photo(call.message.chat.id, text, kb.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "pay_select_15")
async def choose_pay(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇷🇺 Рублями (30₽)", callback_data="pay_rub_15")], [InlineKeyboardButton(text="🪙 Криптой (33₽)", callback_data="pay_crypto_15")], [InlineKeyboardButton(text="❌ Отмена", callback_data="nav_back_main")]])
    text = "💳 <b>Способ оплаты:</b>"
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
        try: await bot.send_message(referrer_id, "🎉 Твой друг купил звёзды! +1 ⭐", parse_mode="HTML")
        except: pass

    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, "15 звёзд (Рубли)", code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]])
    text = f"✅ <b>Заказ #{order_id}</b>\n💰 К оплате: 30₽\n🔑 Код: <code>{code}</code>\n\nНапиши менеджеру."
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"), InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ (РУБЛИ) #{order_id}</b>\nКлиент: @{username}\nТовар: 15 звёзд\nК оплате: 30₽\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
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
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"uname_sel_{uname}")
    kb.button(text="🔙 Назад", callback_data="nav_back_main")
    kb.adjust(1)
    await send_menu_with_photo(call.message.chat.id, "👑 <b>Юзернеймы</b>\n\nВыбери ник.", kb.as_markup(), call.message.message_id)
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
    await send_menu_with_photo(call.message.chat.id, f"✅ <b>Заказ #{order_id}</b>\n👑 {uname}\n🔑 Код: <code>{code}</code>", kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"), InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ ЮЗЕРНЕЙМА #{order_id}</b>\nКлиент: @{username}\nТовар: {uname}\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "btn_help")
async def help_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "📖 <b>Помощь</b>\n\n🌟 Покупка: Рубли/Крипта.\n👑 Ники: За звезды.\n👥 Рефералка: 10%.\n🎮 Игры: Краш и Монетка."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Админ", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="nav_back_main")]])
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
    print(f"[*] Starsshop запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
