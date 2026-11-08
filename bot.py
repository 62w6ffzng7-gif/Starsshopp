# language: Python, file: bot.py, target: Python 3.10+
# *Магазин: везде смайлики, 15 звезд в наличии, 25/50 нет, отзывы, кнопки админа*
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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
    waiting_for_review = State()

app = Flask(__name__)
@app.route('/')
def health(): return "Shop is running", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# --- БД ---
async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            item TEXT,
            code TEXT,
            status TEXT
        )""")
        await db.commit()

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# --- Главное меню ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить звёзды", callback_data="menu_buy")
    kb.button(text="👑 Купить юзернейм", callback_data="menu_usernames")
    kb.button(text="📖 Помощь", callback_data="menu_help")
    kb.button(text="📞 Связь с админом", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    
    caption = (
        "👋 <b>Добро пожаловать в StarShop!</b> 🌟\n\n"
        "✨ Твой лучший проводник в мир Telegram-звёзд и красивых юзернеймов! 🚀\n"
        "💖 У нас быстро, выгодно и безопасно!\n\n"
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

# --- Покупка звезд ---
@dp.callback_query(F.data == "menu_buy")
async def buy_stars_menu(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 15 звёзд — 30₽", callback_data="select_stars_15")
    kb.button(text="❌ 25 звёзд (Нет в наличии)", callback_data="out_of_stock")
    kb.button(text="❌ 50 звёзд (Нет в наличии)", callback_data="out_of_stock")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    await call.message.edit_caption(caption="🛒 <b>Выбери пакет звёзд:</b>\n\n<i>Пока доступен только стартовый пакет! 😉</i>", reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "out_of_stock")
async def out_of_stock(call: CallbackQuery):
    await call.answer("😢 Ой! Этого пакета сейчас нет в наличии. Выбери 15 звёзд!", show_alert=True)

@dp.callback_query(F.data.startswith("select_stars_"))
async def confirm_stars(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    price = {15: 30, 25: 50, 50: 95}[amount]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покупаю", callback_data=f"confirm_stars_{amount}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")]
    ])
    await call.message.edit_caption(
        caption=f"🤔 <b>Вы уверены, что хотите купить {amount} звёзд за {price}₽?</b> 💫",
        reply_markup=kb, parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_stars_"))
async def process_stars_order(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    item_name = f"{amount} звёзд"
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, item_name, code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    await call.message.edit_caption(
        caption=f"🎉 <b>Заказ #{order_id} успешно создан!</b>\n\n"
                f"📦 Товар: {item_name}\n"
                f"🔑 <b>Секретный код: <code>{code}</code></b>\n\n"
                f"💬 Напиши нашему менеджеру и отправь ему этот код, чтобы оплатить и получить звёзды:\n"
                f"👉 <b>@{ADMIN_USERNAME}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]
        ]), parse_mode="HTML"
    )
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"),
             InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n👤 Клиент: @{username}\n🎁 Товар: {item_name}\n🔑 Код: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

# --- Покупка Юзернеймов ---
@dp.callback_query(F.data == "menu_usernames")
async def show_usernames(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for uname, price in USERNAMES_DB.items():
        kb.button(text=f"👑 {uname} — {price} ⭐", callback_data=f"select_uname_{uname}")
    kb.button(text="🔙 Назад", callback_data="back_to_start")
    kb.adjust(1)
    await call.message.edit_caption(caption="👑 <b>Эксклюзивные юзернеймы</b>\n\n🌟 Выбери ник, который хочешь забрать себе:", reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("select_uname_"))
async def confirm_uname(call: CallbackQuery):
    uname = call.data.replace("select_uname_", "")
    price = USERNAMES_DB[uname]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покупаю", callback_data=f"confirm_uname_{uname}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_usernames")]
    ])
    await call.message.edit_caption(
        caption=f"🤔 <b>Вы уверены, что хотите купить юзернейм {uname} за {price} ⭐?</b> 💎",
        reply_markup=kb, parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_uname_"))
async def process_uname_order(call: CallbackQuery):
    uname = call.data.replace("confirm_uname_", "")
    user_id = call.from_user.id
    username = call.from_user.username or "нет_юзернейма"
    code = generate_code()
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute("INSERT INTO orders (user_id, username, item, code, status) VALUES (?, ?, ?, ?, ?)", (user_id, username, f"Юзернейм {uname}", code, "pending"))
        order_id = cursor.lastrowid
        await db.commit()

    await call.message.edit_caption(
        caption=f"🎉 <b>Заказ #{order_id} успешно создан!</b>\n\n"
                f"📦 Товар: Юзернейм {uname}\n"
                f"🔑 <b>Секретный код: <code>{code}</code></b>\n\n"
                f"💬 Напиши нашему менеджеру и отправь ему этот код:\n"
                f"👉 <b>@{ADMIN_USERNAME}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Написать менеджеру", url=f"https://t.me/{ADMIN_USERNAME}")]
        ]), parse_mode="HTML"
    )
    
    if ADMIN_ID != 0:
        kb_admin = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"adm_done_{order_id}"),
             InlineKeyboardButton(text="❌ Не выполнил", callback_data=f"adm_reject_{order_id}")]
        ])
        await bot.send_message(ADMIN_ID, f"🔔 <b>ЗАКАЗ ЮЗЕРНЕЙМА #{order_id}</b>\n\n👤 Клиент: @{username}\n🎁 Товар: {uname}\n🔑 Код: <code>{code}</code>", reply_markup=kb_admin, parse_mode="HTML")
    await call.answer()

# --- Кнопки админа ---
@dp.callback_query(F.data.startswith("adm_done_"))
async def admin_done(call: CallbackQuery):
    if call.from_user.username != ADMIN_USERNAME: 
        return await call.answer("У вас нет прав! 🚫", show_alert=True)
    
    order_id = call.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET status = 'done' WHERE id = ?", (order_id,))
        await db.commit()
        async with db.execute("SELECT user_id, item FROM orders WHERE id = ?", (order_id,)) as c:
            row = await c.fetchone()
            if row:
                await bot.send_message(
                    row[0], 
                    f"🎉 <b>Ура! Заказ #{order_id} выполнен!</b> 🥳\n\n"
                    f"📦 Товар: {row[1]}\n\n"
                    f"⭐ <b>Напишите, пожалуйста, отзыв о нашем сервисе.</b>\n"
                    f"Просто отправьте сообщение в этот чат с вашим мнением! Нам очень важно 💖",
                    parse_mode="HTML"
                )
    await call.message.edit_text(f"{call.message.text}\n\n✅ <b>ВЫПОЛНЕНО</b>", parse_mode="HTML")
    await call.answer("Клиенту отправлено уведомление! ✨")

@dp.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject(call: CallbackQuery):
    if call.from_user.username != ADMIN_USERNAME: 
        return await call.answer("У вас нет прав! 🚫", show_alert=True)
    
    order_id = call.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()
        async with db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,)) as c:
            row = await c.fetchone()
            if row:
                await bot.send_message(row[0], f"❌ <b>Заказ #{order_id} отклонен.</b>\n\nЕсли вы оплатили, напишите менеджеру: @{ADMIN_USERNAME} 🙏", parse_mode="HTML")
    await call.message.edit_text(f"{call.message.text}\n\n❌ <b>ОТКЛОНЕНО</b>", parse_mode="HTML")
    await call.answer("Отклонено.")

# --- Прием отзыва ---
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
        "1️⃣ Выбираешь товар (звёзды или юзернейм). 🌟\n"
        "2️⃣ Бот спрашивает подтверждение и выдает <b>секретный код</b>. 🔑\n"
        f"3️⃣ Пишешь нашему менеджеру (@{ADMIN_USERNAME}), скидываешь код. 💬\n"
        "4️⃣ Договариваетесь об оплате, и менеджер выдает товар. 🎁\n"
        "5️⃣ После выдачи вы можете оставить отзыв прямо в боте. ⭐\n\n"
        "Это сделано для безопасности, чтобы никто не украл ваш заказ. 🛡"
    )
    await call.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Админ", url=f"https://t.me/{ADMIN_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]]), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌟 Купить звёзды", callback_data="menu_buy")
    kb.button(text="👑 Купить юзернейм", callback_data="menu_usernames")
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
