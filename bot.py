# language: Python, file: bot.py, target: Python 3.10+
# *Магазин Starsshop: Бонусы, Рассылка, Автовыдача, БЕЗ ИГР*

import asyncio
import logging
import random
import string
import aiosqlite
import os
import threading
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

USERNAMES_DB = {
    "@ynqnw5": 25,
}
# ==============================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Оставили только нужные состояния (игры удалены)
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
        # Убрали win_streak и lose_streak
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

# --- Универсальная отправка меню с картинкой ---
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

# --- Функция формирования главного меню ---
def get_main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить звёзды", callback_data="menu_buy")
    kb.button(text="👑 Купить юзернейм", callback_data="menu_usernames")
    kb.button(text="👤 Профиль", callback_data="menu_profile")
    kb.button(text="📖 Помощь", callback_data="menu_help")
    kb.button(text="📞 Связь с админом", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    return kb.as_markup()

# --- Установка нативного меню команд ---
async def set_commands():
    commands = [
        BotCommand(command="start", description="Открыть магазин")
    ]
    await bot.set_my_commands(commands)

# --- Главное меню (/start) ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await get_user(message.from_user.id)
    
    caption = (
        "👋 <b>Добро пожаловать в Starsshop!</b> 🌟\n\n"
        "💎 Здесь ты можешь купить звёзды за рубли или крутые юзернеймы за баланс.\n"
        "🚀 Быстро, выгодно и безопасно!\n\n"
        "💖 Мы очень рады видеть тебя здесь. Выбирай раздел и погнали:\n"
    )
    await send_menu_with_photo(message.chat.id, caption, get_main_menu_kb())
    
    try:
        await bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[types.ReactionTypeEmoji(emoji="❤️")])
    except Exception:
        pass

# --- Профиль и Ежедневный Бонус ---
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
    
    if last_bonus:
        last_dt = datetime.fromisoformat(last_bonus)
        if datetime.now() - last_dt < timedelta(days=1):
            await call.answer("⏳ Ты уже забирал бонус сегодня! Приходи завтра.", show_alert=True)
            return
            
    now_str = datetime.now().isoformat()
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + 1, last_bonus = ? WHERE user_id = ?", (now_str, user_id))
        await db.commit()
    
    await add_history(user_id, "Ежедневный бонус", 1)
    await call.answer("🎉 Ты получил 1 звезду! Приходи завтра снова.", show_alert=True)
    await show_profile(call, state)

@dp.callback_query(F.data == "bonus_wait")
async def bonus_wait(call: CallbackQuery):
    await call.answer("⏳ Бонус можно брать раз в 24 часа. Возвращайся позже!", show_alert=True)

# --- Покупка звезд ---
@dp.callback_query(F.data == "menu_buy")
async def buy_stars_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 звёзд — 30₽", callback_data="select_stars_15")
    kb.button(text="❌ 25 звёзд (Скоро будет)", callback_data="out_of_stock")
    kb.button(text="❌ 50 звёзд (Скоро будет)", callback_data="out_of_stock")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    
    text = "🛒 <b>Выбери пакет звёзд:</b>\n\n🌟 Все пакеты выдаются моментально! ⚡️"
    await send_menu_with_photo(call.message.chat.id, text, kb.as_markup(), call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "out_of_stock")
async def out_of_stock(call: CallbackQuery):
    await call.answer("⏳ Этот пакет скоро появится в наличии! Не грусти 😢", show_alert=True)

@dp.callback_query(F.data.startswith("select_stars_"))
async def confirm_stars(call: CallbackQuery, state: FSMContext):
    await state.clear()
    amount = int(call.data.split("_")[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покупаю", callback_data=f"confirm_stars_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")]
    ])
    text = f"🤔 <b>Вы уверены, что хотите купить {amount} звёзд за 30₽?</b>\n\nНажми кнопку ниже для подтверждения! 💫"
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_stars_"))
async def process_stars_order(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    item_name = f"{amount} звёзд"
    
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT id, item_data FROM stock WHERE item_name = ? AND is_sold = 0 LIMIT 1", (item_name,)) as cursor:
            stock_item = await cursor.fetchone()
            
        if stock_item:
            stock_id, item_data = stock_item
            await db.execute("UPDATE stock SET is_sold = 1 WHERE id = ?", (stock_id,))
            cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, item_name, code, "done"))
            order_id = cursor.lastrowid
            await db.commit()
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_start")]])
            text = (
                f"🎉 <b>Заказ #{order_id} выполнен автоматически!</b>\n\n"
                f"📦 Товар: {item_name}\n"
                f"🔑 <b>Ваши данные:</b> <code>{item_data}</code>\n\n"
                f"💖 Спасибо за покупку!"
            )
            await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
            return
            
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, item_name, code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    
    text = (
        f"🎉 <b>Заказ #{order_id} создан!</b>\n\n"
        f"📦 Товар: {item_name}\n"
        f"💰 Сумма: 30₽\n"
        f"🔑 <b>Секретный код: <code>{code}</code></b>\n\n"
        f"👇 Напиши нашему менеджеру и отправь этот код:\n"
        f"<b>@{ADMIN_USERNAME}</b>\n\n"
        f"💖 Спасибо за твой выбор!"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"),
             InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\nКлиент: @{username}\nТовар: {item_name}\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

# --- Покупка Юзернеймов ---
@dp.callback_query(F.data == "menu_usernames")
async def show_usernames(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"select_uname_{uname}")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    
    text = "👑 <b>Эксклюзивные юзернеймы</b>\n\nВыбери ник, который хочешь забрать себе. Оплата списывается с твоего баланса звёзд! 💎"
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
    text = f"🤔 <b>Вы уверены, что хотите купить юзернейм {uname} за {price} ⭐?</b>\n\nСумма спишется с баланса."
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
        text = f"❌ <b>Недостаточно звёзд на балансе!</b>\n\nБаланс: {balance} ⭐. Нужно: {price} ⭐.\nПополни баланс в профиле! 🙏"
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
            text = (
                f"🎉 <b>Заказ #{order_id} выполнен автоматически!</b>\n\n"
                f"📦 Юзернейм: {uname}\n"
                f"🔑 <b>Данные для входа/смены:</b> <code>{item_data}</code>\n\n"
                f"✨ Поздравляем с покупкой!"
            )
            await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
            return
            
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, uname, code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    
    text = (
        f"🎉 <b>Заказ #{order_id} создан!</b>\n\n"
        f"📦 Товар: Юзернейм {uname}\n"
        f"🔑 <b>Секретный код: <code>{code}</code></b>\n\n"
        f"👇 Напиши нашему менеджеру и отправь этот код, чтобы забрать ник:\n"
        f"<b>@{ADMIN_USERNAME}</b>\n\n"
        f"✨ Поздравляем с покупкой!"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"),
             InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ ЮЗЕРНЕЙМА #{order_id}</b>\nКлиент: @{username}\nТовар: {uname}\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

# --- Кнопки админа (Заказы) ---
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
                await bot.send_message(
                    row[0], 
                    f"🎉 <b>Ура! Заказ #{order_id} успешно выполнен!</b> 🥳\n\n"
                    f"📦 Товар: {row[1]}\n\n"
                    f"⭐ <b>Пожалуйста, оставьте отзыв о нашем сервисе!</b>\n"
                    f"Просто напишите ваше мнение прямо в этот чат. Нам очень важно знать, как мы работаем! 💖",
                    parse_mode="HTML"
                )
    await call.message.edit_text(f"{call.message.text}\n\n✅ <b>ВЫПОЛНЕНО</b>", parse_mode="HTML")
    await call.answer("Уведомление отправлено! 🌟")

@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject(call: CallbackQuery):
    if call.from_user.username != ADMIN_USERNAME: 
        return await call.answer("Нет прав", show_alert=True)
    
    order_id = call.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()
        async with db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,)) as c:
            row = await c.fetchone()
            if row:
                await bot.send_message(
                    row[0], 
                    f"❌ <b>Заказ #{order_id} отклонен.</b>\n\n"
                    f"Если вы оплатили, напишите менеджеру: @{ADMIN_USERNAME}", 
                    parse_mode="HTML"
                )
    await call.message.edit_text(f"{call.message.text}\n\n❌ <b>ОТКЛОНЕНО</b>", parse_mode="HTML")
    await call.answer("Клиенту отправлен отказ.")

# --- Промокоды ---
@dp.callback_query(F.data == "enter_promo")
async def enter_promo(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]
    ])
    text = (
        "🎟 <b>Активация промокода</b>\n\n"
        "Отправь мне промокод в чат, и я начислю тебе бонусные звезды! ✨\n\n"
        "⚠️ <i>Один промокод можно активировать только один раз.</i>"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer("✍️ Введи промокод в чат!")

@dp.message(UserStates.waiting_for_promo)
async def process_promo(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    
    if code != "STARTOP2026":
        await message.answer("❌ Такого промокода не существует или он уже недействителен. 😢", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В профиль", callback_data="menu_profile")]]))
        await state.clear()
        return
        
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id FROM promo_activations WHERE user_id = ?", (user_id,)) as cursor:
            if await cursor.fetchone():
                await message.answer("❌ Ты уже активировал этот промокод. 🙅‍♂️", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В профиль", callback_data="menu_profile")]]))
                await state.clear()
                return
                
        async with db.execute("SELECT uses FROM promo_stats WHERE promo_code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            uses = row[0] if row else 0
            
        if uses >= 10:
            await message.answer("❌ Лимит активаций этого промокода исчерпан (10/10). 😔", 
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В профиль", callback_data="menu_profile")]]))
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
    
    await message.answer(
        "🎉 <b>Промокод успешно активирован!</b>\n\n"
        "💰 Тебе начислено <b>10 ⭐</b>.\n"
        "Спасибо, что ты с нами! 💖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 В профиль", callback_data="menu_profile")]]),
        parse_mode="HTML"
    )
    await state.clear()

# --- Пополнение (Инвойсы) ---
@dp.callback_query(F.data == "topup_start")
async def topup_start(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_profile")]
    ])
    text = (
        "💳 <b>Пополнение баланса</b>\n\n"
        "Сколько звёзд вы хотите купить на баланс?\n"
        "Напишите в чат цифру от 25 до 1000 (например: <code>50</code>):"
    )
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await state.set_state(UserStates.waiting_for_topup_amount)
    await call.answer("✍️ Введи сумму в чат или нажми Назад")

@dp.callback_query(F.data == "cancel_topup")
async def cancel_topup(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_profile(call, state)

@dp.message(UserStates.waiting_for_topup_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Пожалуйста, введи число (цифрами).")
        
    amount = int(message.text)
    
    if amount < 25 or amount > 1000:
        return await message.answer("❌ Минимальное пополнение — 25 звёзд, максимальное — 1000. Введи другое число:")
    
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Оплатить {amount} ⭐", callback_data=f"invoice_topup_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]
    ])
    
    text = (
        f"🤔 <b>Вы точно хотите пополнить баланс на {amount} ⭐?</b>\n\n"
        f"Нажми кнопку ниже, чтобы оплатить через официальный инвойс Telegram."
    )
    await send_menu_with_photo(message.chat.id, text, kb)
    await message.answer("👇 Жми на кнопку для оплаты или Отмена!")

@dp.callback_query(F.data.startswith("invoice_topup_"))
async def send_topup_invoice(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"Пополнение на {amount} ⭐",
        description="Пополнение внутреннего баланса.",
        payload=f"topup_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Пополнение", amount=amount)],
    )
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    amount = message.successful_payment.total_amount
    
    if payload.startswith("topup_"):
        topup = int(payload.split("_")[1])
        await add_balance(message.from_user.id, topup)
        await add_history(message.from_user.id, "Пополнение баланса", amount)
        await message.answer(f"✅ <b>Баланс пополнен на {topup} ⭐!</b>\nТеперь можешь купить юзернейм.", parse_mode="HTML")

# --- АДМИН: РАССЫЛКА ---
@dp.message(Command("send"))
async def start_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(UserStates.waiting_for_broadcast)
    await message.answer("📢 <b>Режим рассылки.</b>\n\nОтправь мне текст сообщения, и я разошлю его всем пользователям бота.\nДля отмены введи /cancel.")

@dp.message(UserStates.waiting_for_broadcast)
async def do_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    
    if message.text == "/cancel":
        await message.answer("❌ Рассылка отменена.")
        return
        
    text_to_send = message.html_text
    await message.answer("⏳ Начинаю рассылку...")
    
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            
    success = 0
    errors = 0
    for (user_id,) in users:
        try:
            await bot.send_message(user_id, text_to_send, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            errors += 1
            
    await message.answer(f"✅ <b>Рассылка завершена!</b>\nУспешно: {success}\nОшибок: {errors}")

# --- Отзывы ---
@dp.message(UserStates.waiting_for_review)
async def process_review(message: types.Message, state: FSMContext):
    review_text = message.text
    user_id = message.from_user.id
    username = message.from_user.username or "нет_юзернейма"
    
    if ADMIN_ID != 0:
        await bot.send_message(
            ADMIN_ID, 
            f"💬 <b>НОВЫЙ ОТЗЫВ!</b>\n\n"
            f"👤 От: @{username} (ID: <code>{user_id}</code>)\n\n"
            f"💌 Текст отзыва:\n<i>{review_text}</i>",
            parse_mode="HTML"
        )
    
    await message.answer(
        f"🙏 <b>Спасибо за ваш отзыв!</b> 💖\n\n"
        f"Нам очень важно ваше мнение. Приходите еще! ✨",
        parse_mode="HTML"
    )
    await state.clear()

@dp.message(F.text & ~F.text.startswith("/"))
async def catch_reviews(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == UserStates.waiting_for_review.state:
        await process_review(message, state)

# --- Помощь и Навигация ---
@dp.callback_query(F.data == "menu_help")
async def show_help(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📖 <b>Как это работает?</b>\n\n"
        "🌟 <b>Покупка звёзд:</b> Выбираешь пакет (15 звёзд = 30₽). Бот дает код. Пишешь менеджеру, переводишь рубли, получаешь звёзды.\n\n"
        "👑 <b>Покупка юзернеймов:</b> Нужны звёзды на балансе. Если их нет, сначала пополняешь баланс (в профиле). Потом покупаешь ник за звёзды и получаешь код для менеджера.\n\n"
        f"💬 <b>Менеджер:</b> @{ADMIN_USERNAME}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Админ", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]])
    await send_menu_with_photo(call.message.chat.id, text, kb, call.message.message_id)
    await call.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(call: CallbackQuery, state: FSMContext):
    await state.clear() 
    await send_menu_with_photo(call.message.chat.id, "👋 <b>Главное меню Starsshop</b>\n\n👇 Выбирай нужный раздел:", get_main_menu_kb(), call.message.message_id)
    await call.answer()

async def main():
    await init_db()
    await set_commands()
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"[*] Starsshop запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
