# language: Python, file: bot.py, target: Python 3.10+
# *Звёзды за рубли, Юзернеймы за баланс, Пополнение XTR (25-1000), Отзывы, Секретные коды*
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
                           LabeledPrice, PreCheckoutQuery, Message)
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

class UserStates(StatesGroup):
    waiting_for_topup_amount = State()
    waiting_for_review = State()

app = Flask(__name__)
@app.route('/')
def health(): return "Shop is running", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# --- БД ---
async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item TEXT, price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, item TEXT, code TEXT, status TEXT)""")
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

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

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
        "💎 Здесь ты можешь купить звёзды за рубли или крутые юзернеймы за баланс.\n"
        "🚀 Быстро, выгодно и безопасно!\n\n"
        "👇 Выбирай раздел:"
    )
    try:
        await message.answer_photo(photo=IMAGE_URL, caption=caption, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await message.answer(caption, reply_markup=kb.as_markup(), parse_mode="HTML")
    
    try:
        await bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[types.ReactionTypeEmoji(emoji="❤️")])
    except Exception:
        pass

# --- Покупка звезд (ЗА РУБЛИ) ---
@dp.callback_query(F.data == "menu_buy")
async def buy_stars_menu(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 звёзд — 30₽", callback_data="select_stars_15")
    kb.button(text="❌ 25 звёзд (Скоро будет)", callback_data="out_of_stock")
    kb.button(text="❌ 50 звёзд (Скоро будет)", callback_data="out_of_stock")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    await call.message.edit_caption(caption="🛒 <b>Выбери пакет звёзд:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "out_of_stock")
async def out_of_stock(call: CallbackQuery):
    await call.answer("⏳ Этот пакет скоро появится в наличии!", show_alert=True)

@dp.callback_query(F.data.startswith("select_stars_"))
async def confirm_stars(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покупаю", callback_data=f"confirm_stars_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")]
    ])
    await call.message.edit_caption(caption=f"🤔 <b>Вы уверены, что хотите купить {amount} звёзд за 30₽?</b>", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_stars_"))
async def process_stars_order(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, f"{amount} звёзд", code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    await call.message.edit_caption(
        caption=f"🎉 <b>Заказ #{order_id} создан!</b>\n\n"
                f"📦 Товар: {amount} звёзд\n"
                f"💰 Сумма: 30₽\n"
                f"🔑 <b>Секретный код: <code>{code}</code></b>\n\n"
                f"👇 Напиши нашему менеджеру и отправь этот код:\n"
                f"<b>@{ADMIN_USERNAME}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]
        ]), parse_mode="HTML"
    )
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"),
             InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>НОВЫЙ ЗАКАЗ ЗВЁЗД #{order_id}</b>\nКлиент: @{username}\nТовар: {amount} звёзд за 30₽\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

# --- Покупка Юзернеймов (ЗА БАЛАНС) ---
@dp.callback_query(F.data == "menu_usernames")
async def show_usernames(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"select_uname_{uname}")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    await call.message.edit_caption(caption="👑 <b>Эксклюзивные юзернеймы</b>\n\nВыбери ник. Оплата списывается с твоего баланса звёзд!", reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("select_uname_"))
async def confirm_uname(call: CallbackQuery):
    uname = call.data.replace("select_uname_", "")
    price = USERNAMES_DB[uname]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покупаю", callback_data=f"confirm_uname_{uname}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_usernames")]
    ])
    await call.message.edit_caption(caption=f"🤔 <b>Вы уверены, что хотите купить юзернейм {uname} за {price} ⭐?</b>", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_uname_"))
async def process_uname_order(call: CallbackQuery):
    uname = call.data.replace("confirm_uname_", "")
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    price = USERNAMES_DB[uname]
    
    balance = await get_user(user_id)
    if balance < price:
        return await call.message.edit_caption(
            caption=f"❌ <b>Недостаточно звёзд на балансе!</b>\n\nБаланс: {balance} ⭐. Нужно: {price} ⭐.\nПополни баланс в профиле!", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 В профиль", callback_data="menu_profile")]]), 
            parse_mode="HTML"
        )

    await add_balance(user_id, -price)
    await add_history(user_id, f"Юзернейм {uname}", price)
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, f"Юзернейм {uname}", code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    await call.message.edit_caption(
        caption=f"🎉 <b>Заказ #{order_id} создан!</b>\n\n"
                f"📦 Товар: Юзернейм {uname}\n"
                f"🔑 <b>Секретный код: <code>{code}</code></b>\n\n"
                f"👇 Напиши нашему менеджеру и отправь этот код, чтобы забрать ник:\n"
                f"<b>@{ADMIN_USERNAME}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]
        ]), parse_mode="HTML"
    )
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"),
             InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ ЮЗЕРНЕЙМА #{order_id}</b>\nКлиент: @{username}\nТовар: {uname}\nСписано: {price} ⭐\nКод: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

# --- Кнопки админа ---
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
    await call.answer("Уведомление отправлено!")

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

# --- Профиль и Пополнение (XTR) ---
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
                f"💰 Баланс звёзд: <b>{balance} ⭐</b>\n\n"
                f"📜 <b>История покупок:</b>\n{history_text}\n\n"
                f"<i>Баланс нужен для покупки юзернеймов!</i>",
        reply_markup=kb, parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data == "topup_start")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_caption(
        caption="💳 <b>Пополнение баланса</b>\n\n"
                "Сколько звёзд вы хотите купить на баланс?\n"
                "Напишите в чат цифру от 25 до 1000 (например: <code>50</code>):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_topup")]]), parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_for_topup_amount)
    await call.answer()

# ИСПРАВЛЕННАЯ ОТМЕНА ПОПОЛНЕНИЯ
@dp.callback_query(F.data == "cancel_topup")
async def cancel_topup(call: CallbackQuery, state: FSMContext):
    await state.clear() # Сбрасываем ожидание ввода
    await call.message.edit_caption(caption="👋 <b>Главное меню</b>\n\n👇 Выбирай нужный раздел:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")]]), parse_mode="HTML")
    await call.answer("Действие отменено")

@dp.message(UserStates.waiting_for_topup_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Пожалуйста, введи число (цифрами).")
        
    amount = int(message.text)
    
    # ИСПРАВЛЕНО: Теперь от 25 до 1000, и сбрасываем состояние при ошибке
    if amount < 25 or amount > 1000:
        await state.clear()
        return await message.answer(
            "❌ Минимальное пополнение — 25 звёзд, максимальное — 1000. Введи другое число (например, 50):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Попробовать снова", callback_data="topup_start")]])
        )
    
    await state.clear()
    
    await message.answer(
        f"🤔 <b>Вы точно хотите пополнить баланс на {amount} ⭐?</b>\n\n"
        f"Нажми кнопку ниже, чтобы оплатить через официальный инвойс Telegram.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Оплатить {amount} ⭐", callback_data=f"invoice_topup_{amount}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_profile")]
        ]), parse_mode="HTML"
    )

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

# --- Прием отзывов ---
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
    if current_state is None:
        await state.set_state(UserStates.waiting_for_review)
        await process_review(message, state)

# --- Помощь и Навигация ---
@dp.callback_query(F.data == "menu_help")
async def show_help(call: CallbackQuery):
    text = (
        "📖 <b>Как это работает?</b>\n\n"
        "🌟 <b>Покупка звёзд:</b> Выбираешь пакет (15 звёзд = 30₽). Бот дает код. Пишешь менеджеру, переводишь рубли, получаешь звёзды.\n\n"
        "👑 <b>Покупка юзернеймов:</b> Нужны звёзды на балансе. Если их нет, сначала пополняешь баланс (в профиле). Потом покупаешь ник за звёзды и получаешь код для менеджера.\n\n"
        f"💬 <b>Менеджер:</b> @{ADMIN_USERNAME}"
    )
    await call.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Админ", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]]), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(call: CallbackQuery, state: FSMContext):
    await state.clear() # Сбрасываем состояния на всякий случай
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
