# language: Python, file: bot.py, target: Python 3.10+
# *Полный магазин: фото, реакции, баланс, юзернеймы, себе/другу, XTR*
# *зависимости: aiogram, aiosqlite, flask*

import asyncio
import logging
import random
import string
import aiosqlite
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, 
                           FSInputFile, LabeledPrice, PreCheckoutQuery, Message)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "9040235874:AAGSGvWV-nwd4kn32OADEn0ob_zp_M8tHKw")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_USERNAME = "moscow_1488"
IMAGE_URL = "https://github.com/62w6ffzng7-gif/Starsshopp/raw/main/IMG_1577.jpeg"

# База юзернеймов (название: цена в звездах)
USERNAMES_DB = {
    "@ynqnw5": 25,
}
# ==============================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class UserStates(StatesGroup):
    waiting_for_topup_amount = State()

app = Flask(__name__)
@app.route('/')
def health(): return "Shop is running", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# --- База данных ---
async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item TEXT, price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                await db.commit()
                return 0
            return row[0]

async def add_balance(user_id, amount):
    await get_user(user_id)
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def add_history(user_id, item, price):
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("INSERT INTO history (user_id, item, price) VALUES (?, ?, ?)", (user_id, item, price))
        await db.commit()

# --- Главное меню ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await get_user(message.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить звёзды", callback_data="menu_buy")
    kb.button(text="👑 Купить юзернейм", callback_data="menu_usernames")
    kb.button(text="👤 Профиль", callback_data="menu_profile")
    kb.button(text="📖 Помощь", callback_data="menu_help")
    kb.button(text="📞 Связь с админом", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    
    caption = (
        "👋 <b>Добро пожаловать в StarShop!</b> 🌟\n\n"
        "Твой лучший проводник в мир Telegram-звёзд и красивых юзернеймов. 🚀\n"
        "У нас быстро, выгодно и безопасно!\n\n"
        "👇 Выбирай раздел и погнали:"
    )
    try:
        await message.answer_photo(photo=IMAGE_URL, caption=caption, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await message.answer(caption, reply_markup=kb.as_markup(), parse_mode="HTML")
    
    try:
        await bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[types.ReactionTypeEmoji(emoji="❤️")])
    except Exception:
        pass

# --- Меню покупки звезд ---
@dp.callback_query(F.data == "menu_buy")
async def buy_stars_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Себе", callback_data="buy_self")],
        [InlineKeyboardButton(text="🎁 Другу", callback_data="buy_friend")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await call.message.edit_caption(caption="💫 <b>Для кого ты хочешь купить звёзды?</b>\n\nВыбери вариант ниже 👇", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.in_(["buy_self", "buy_friend"]))
async def select_package(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 звёзд — 30 ⭐", callback_data="invoice_stars_15")
    kb.button(text="❌ 25 звёзд (Нет в наличии)", callback_data="out_of_stock")
    kb.button(text="❌ 50 звёзд (Нет в наличии)", callback_data="out_of_stock")
    kb.button(text="🔙 Назад", callback_data="menu_buy")
    kb.adjust(1)
    
    target = "себе" if call.data == "buy_self" else "другу"
    await call.message.edit_caption(caption=f"🛒 <b>Отлично, покупаем {target}!</b>\n\nВыбери пакет:", reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "out_of_stock")
async def out_of_stock(call: CallbackQuery):
    await call.answer("😢 К сожалению, этого пакета сейчас нет в наличии. Выбери 15 звёзд!", show_alert=True)

@dp.callback_query(F.data.startswith("invoice_stars_"))
async def send_stars_invoice(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    prices = {15: 30, 25: 50, 50: 95} # Цены в рублях
    price = prices[amount]
    
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"Покупка {amount} звёзд",
        description=f"Зачисление {amount} звёзд на ваш аккаунт.",
        payload=f"buy_stars_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} звёзд", amount=price)],
    )
    await call.answer()

# --- Меню Юзернеймов ---
@dp.callback_query(F.data == "menu_usernames")
async def show_usernames(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"buy_uname_{uname}")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    await call.message.edit_caption(caption="👑 <b>Эксклюзивные юзернеймы</b>\n\nВыбери ник. Оплата списывается с твоего баланса звёзд!", reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("buy_uname_"))
async def confirm_uname(call: CallbackQuery):
    uname = call.data.replace("buy_uname_", "")
    price = USERNAMES_DB[uname]
    secret = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💸 Оплатить {price} ⭐", callback_data=f"confirm_uname_{uname}_{secret}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_usernames")]
    ])
    await call.message.edit_caption(caption=f"🤔 <b>Вы точно хотите купить {uname} за {price} звёзд?</b>\n\nСумма спишется с баланса.", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_uname_"))
async def process_uname_payment(call: CallbackQuery):
    parts = call.data.split("_")
    uname, secret = parts[2], parts[3]
    price = USERNAMES_DB[uname]
    balance = await get_user(call.from_user.id)
    
    if balance >= price:
        await add_balance(call.from_user.id, -price)
        await add_history(call.from_user.id, f"Юзернейм {uname}", price)
        await call.message.edit_caption(
            caption=f"🎉 <b>Успешно!</b>\n\nТы купил {uname}.\n👇 Напиши менеджеру для передачи прав.\n\n🔑 <b>Секретный код: <code>{secret}</code></b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]]), parse_mode="HTML"
        )
        if ADMIN_ID != 0:
            await bot.send_message(ADMIN_ID, f"🔔 <b>ПРОДАН ЮЗЕРНЕЙМ!</b>\nКлиент: @{call.from_user.username}\nТовар: {uname}\nКод: <code>{secret}</code>", parse_mode="HTML")
    else:
        await call.message.edit_caption(caption=f"❌ <b>Недостаточно средств!</b>\nБаланс: {balance} ⭐. Нужно: {price} ⭐.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Пополнить", callback_data="topup_start")]]), parse_mode="HTML")
    await call.answer()

# --- Профиль ---
@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    balance = await get_user(call.from_user.id)
    history_text = ""
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT item, price FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 3", (call.from_user.id,)) as cursor:
            rows = await cursor.fetchall()
            history_text = "\n".join([f"• {item} — {price} ⭐" for item, price in rows]) if rows else "Покупок пока нет."
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup_start")], 
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await call.message.edit_caption(
        caption=f"👤 <b>Твой профиль</b>\n\n"
                f"🆔 ID: <code>{call.from_user.id}</code>\n"
                f"💰 Баланс: <b>{balance} ⭐</b>\n\n"
                f"📜 <b>Последние покупки:</b>\n{history_text}\n\n"
                f"<i>Баланс нужен для покупки юзернеймов.</i>",
        reply_markup=kb, parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data == "topup_start")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_caption(
        caption="💳 <b>Пополнение баланса</b>\n\n"
                "Сколько звёзд вы хотите пополнить?\n"
                "Напишите в чат цифру (например: <code>50</code>):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]]), parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_for_topup_amount)
    await call.answer()

@dp.message(UserStates.waiting_for_topup_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Пожалуйста, введи число (цифрами).")
    amount = int(message.text)
    if amount < 15:
        return await message.answer("❌ Минимальное пополнение — 15 звёзд.")
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Оплатить {amount} ⭐", callback_data=f"invoice_topup_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]
    ])
    await message.answer(f"🤔 <b>Вы точно хотите перевести {amount} звёзд боту?</b>\n\nНажми кнопку ниже, чтобы перевести звёзды через официальный инвойс Telegram.", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("invoice_topup_"))
async def send_topup_invoice(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    await bot.send_invoice(chat_id=call.from_user.id, title=f"Пополнение на {amount} ⭐", description="Пополнение баланса.", payload=f"topup_{amount}", provider_token="", currency="XTR", prices=[LabeledPrice(label="Пополнение", amount=amount)])
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    amount = message.successful_payment.total_amount
    if payload.startswith("buy_stars_"):
        stars = int(payload.split("_")[2])
        await add_history(message.from_user.id, f"Покупка {stars} звёзд", amount)
        await message.answer(f"✅ Оплата прошла! Вы купили {stars} звёзд за {amount} ⭐. Админ выдаст их вам.")
    elif payload.startswith("topup_"):
        topup = int(payload.split("_")[1])
        await add_balance(message.from_user.id, topup)
        await add_history(message.from_user.id, "Пополнение", amount)
        await message.answer(f"✅ Баланс пополнен на {topup} ⭐.")

@dp.callback_query(F.data == "menu_help")
async def show_help(call: CallbackQuery):
    text = (
        "📖 <b>Помощь</b>\n\n"
        "🌟 <b>Звёзды:</b> Покупка через официальный инвойс Telegram (XTR).\n"
        f"👑 <b>Юзернеймы:</b> Покупка за баланс. После покупки пиши @{ADMIN_USERNAME} и скидывай секретный код.\n"
        "💳 <b>Баланс:</b> Нужен для покупки юзернеймов."
    )
    await call.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Админ", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]]), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить звёзды", callback_data="menu_buy")
    kb.button(text="👑 Купить юзернейм", callback_data="menu_usernames")
    kb.button(text="👤 Профиль", callback_data="menu_profile")
    kb.button(text="📖 Помощь", callback_data="menu_help")
    kb.button(text="📞 Связь с админом", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    await call.message.edit_caption(caption="👋 <b>Главное меню</b>\n\n👇 Выбирай нужный раздел:", reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

async def main():
    await init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"[*] StarShop запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
