# language: Python, file: bot.py, target: Python 3.10+
# *магазин звезд + Flask-сервер (чтобы Render не ругался и держал его 24/7)*
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
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "9040235874:AAGSGvWV-nwd4kn32OADEn0ob_zp_M8tHKw")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5870776717"))
ADMIN_USERNAME = "moscow_1488"
PRICE_PER_15 = 30
STARS_AMOUNT = 15
# ==============================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Flask-заглушка для Render ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running", 200

def run_flask():
    # Render по умолчанию передает порт в переменной PORT
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- Логика бота ---
def generate_secret_code():
    chars = string.ascii_uppercase + string.digits
    return '-'.join(''.join(random.choices(chars, k=4)) for _ in range(2))

async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                amount INTEGER,
                price INTEGER,
                secret_code TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✨ Купить {STARS_AMOUNT} звёзд", callback_data="buy_stars")
    kb.button(text="ℹ️ О магазине", callback_data="about")
    kb.button(text="📖 Правила", callback_data="rules")
    kb.button(text="👤 Мой профиль", callback_data="profile")
    kb.button(text="👨‍💻 Связь с админом", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    
    text = (
        f"👋 <b>Добро пожаловать в StarShop!</b>\n\n"
        f"🌟 Самый выгодный магазин звёзд Telegram.\n"
        f"💎 <b>{STARS_AMOUNT} звёзд</b> всего за <b>{PRICE_PER_15}₽</b>!\n\n"
        f"⚡️ Мгновенная выдача и надежность.\n"
        f"Выбирай действие ниже 👇"
    )
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "about")
async def show_about(callback: CallbackQuery):
    text = (
        "🏪 <b>О магазине StarShop</b>\n\n"
        "Мы — команда, которая предоставляет быстрый и безопасный сервис по покупке звёзд Telegram по самым низким ценам.\n\n"
        "📈 <b>Почему выбирают нас:</b>\n"
        "✅ Цена: 15 звёзд за 30 рублей.\n"
        "✅ Скорость: выдача в течение 15 минут.\n"
        "✅ Надежность: мы работаем честно.\n\n"
        f"👨‍💻 По всем вопросам: @{ADMIN_USERNAME}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Написать админу", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "rules")
async def show_rules(callback: CallbackQuery):
    text = (
        "📖 <b>Правила магазина:</b>\n\n"
        "1️⃣ Оплата производится в рублях.\n"
        "2️⃣ После оплаты вы получаете номер заказа и секретный код.\n"
        "3️⃣ Администратор проверяет заказ и выдает звёзды вручную (до 15 минут).\n"
        "4️⃣ Если звёзды не пришли, свяжитесь с поддержкой.\n\n"
        f"🛡 По всем вопросам пишите: @{ADMIN_USERNAME}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Написать админу", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✨ Купить {STARS_AMOUNT} звёзд", callback_data="buy_stars")
    kb.button(text="ℹ️ О магазине", callback_data="about")
    kb.button(text="📖 Правила", callback_data="rules")
    kb.button(text="👤 Мой профиль", callback_data="profile")
    kb.button(text="👨‍💻 Связь с админом", url=f"https://t.me/{ADMIN_USERNAME}")
    kb.adjust(1)
    
    text = f"👋 <b>Главное меню StarShop</b>\n\n🌟 Выбери нужное действие:"
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "buy_stars")
async def process_buy(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or "нет_юзернейма"
    secret = generate_secret_code()
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, amount, price, secret_code, status) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, STARS_AMOUNT, PRICE_PER_15, secret, "created")
        )
        order_id = cursor.lastrowid
        await db.commit()

    kb_user = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Я оплатил", callback_data=f"paid_{order_id}")],
        [InlineKeyboardButton(text="👨‍💻 Написать админу", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    
    text_user = (
        f"🧾 <b>Заказ успешно создан!</b>\n\n"
        f"📦 Номер вашего заказа: <code>{order_id}</code>\n"
        f"🔑 Секретный код: <code>{secret}</code>\n\n"
        f"💰 К оплате: <b>{PRICE_PER_15}₽</b> за {STARS_AMOUNT} звёзд.\n"
        f"<i>(Реквизиты для оплаты уточняйте у админа)</i>\n\n"
        f"⚠️ <b>Сохраните номер и секретный код!</b>\n\n"
        f"После оплаты нажмите кнопку ниже 👇"
    )
    
    await callback.message.edit_text(text_user, reply_markup=kb_user, parse_mode="HTML")
    
    kb_admin = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Сделал заказ", callback_data=f"admin_approve_{order_id}"),
            InlineKeyboardButton(text="❌ Не сделал заказ", callback_data=f"admin_reject_{order_id}")
        ]
    ])
    
    text_admin = (
        f"🔔 <b>Новый заказ #{order_id}</b>\n\n"
        f"👤 Покупатель: @{username} (ID: <code>{user_id}</code>)\n"
        f"🌟 Товар: {STARS_AMOUNT} звёзд\n"
        f"💵 Сумма: {PRICE_PER_15}₽\n"
        f"🔑 Код: <code>{secret}</code>\n\n"
        f"Проверьте оплату:"
    )
    
    await bot.send_message(ADMIN_ID, text_admin, reply_markup=kb_admin, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("paid_"))
async def user_paid(callback: CallbackQuery):
    order_id = callback.data.split("_")[1]
    text = f"⏳ <b>Ожидайте подтверждения!</b>\n\nЗаказ #{order_id} на проверке.\n\n<i>Вопросы: @{ADMIN_USERNAME}</i>"
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer("Ожидайте подтверждения", show_alert=True)
    await bot.send_message(ADMIN_ID, f"💰 @{callback.from_user.username} нажал «Я оплатил» по заказу <b>#{order_id}</b>.", parse_mode="HTML")

@dp.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав.", show_alert=True)
        return
    order_id = callback.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id, amount, status FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            await callback.answer("Заказ не найден.", show_alert=True)
            return
        user_id, amount, status = row
        if status == "approved":
            await callback.answer("Заказ уже выполнен.", show_alert=True)
            return
        await db.execute("UPDATE orders SET status = 'approved' WHERE id = ?", (order_id,))
        await db.commit()

    text_user = f"🎉 <b>Заказ #{order_id} выполнен!</b>\n\n✨ Начислено <b>{amount} звёзд</b>.\n\nСпасибо за покупку!\n👨‍💻 Поддержка: @{ADMIN_USERNAME}"
    await bot.send_message(user_id, text_user, parse_mode="HTML")
    await callback.message.edit_text(f"{callback.message.text}\n\n✅ <b>СТАТУС: ВЫПОЛНЕН</b>", parse_mode="HTML")
    await callback.answer("Звёзды выданы.")

@dp.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав.", show_alert=True)
        return
    order_id = callback.data.split("_")[2]
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT user_id, status FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            await callback.answer("Заказ не найден.", show_alert=True)
            return
        user_id, status = row
        if status == "rejected":
            await callback.answer("Заказ уже отклонен.", show_alert=True)
            return
        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()

    text_user = f"❌ <b>Заказ #{order_id} отклонен.</b>\n\nОплата не найдена.\nЕсли вы уверены, что оплатили, пишите: @{ADMIN_USERNAME}"
    await bot.send_message(user_id, text_user, parse_mode="HTML")
    await callback.message.edit_text(f"{callback.message.text}\n\n❌ <b>СТАТУС: ОТКЛОНЕН</b>", parse_mode="HTML")
    await callback.answer("Заказ отклонен.")

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'approved'", (callback.from_user.id,)) as cursor:
            count = (await cursor.fetchone())[0]
            
    text = f"👤 <b>Твой профиль:</b>\n\n🆔 ID: <code>{callback.from_user.id}</code>\n🌟 Куплено звёзд: {count * STARS_AMOUNT}\n💸 Покупок: {count}\n\n👨‍💻 Поддержка: @{ADMIN_USERNAME}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# --- Запуск всего вместе ---
async def main():
    await init_db()
    # Запускаем Flask в фоновом потоке (чтобы Render видел веб-сервер)
    threading.Thread(target=run_flask, daemon=True).start()
    print("[*] StarShop Pro запущен (Web Service mode)")
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())