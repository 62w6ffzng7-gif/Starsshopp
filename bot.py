# language: Python, file: bot.py, target: Python 3.10+
# *Магазин звезд: 15 штук можно покупать бесконечно, 25 и 50 отключены*
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
ADMIN_USERNAME = "moscow_1488"

# Цены за пакеты. Убрали "stock", теперь 15-ка доступна всегда.
PACKAGES = {
    15: {"price": 35, "available": True},
    25: {"price": 50, "available": False},
    50: {"price": 100, "available": False},
}
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
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- БД ---
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

# --- Проверка на админа ---
async def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# --- Главное меню ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ Купить звёзды", callback_data="menu_buy")
    kb.button(text="ℹ️ О магазине", callback_data="menu_about")
    kb.button(text="🛠 Поддержка", callback_data="menu_support")
    kb.adjust(1)
    
    text = (
        f"👋 <b>Добро пожаловать в StarShop!</b> 🌟\n\n"
        f"🚀 Здесь ты можешь купить звёзды Telegram по самым выгодным ценам!\n"
        f"🔥 Мы работаем <b>быстро, честно и с душой</b>.\n\n"
        f"👇 Выбирай нужный раздел и погнали!"
    )
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# --- О магазине ---
@dp.callback_query(F.data == "menu_about")
async def show_about(callback: CallbackQuery):
    text = (
        "🏪 <b>О нашем магазине StarShop!</b> 💎\n\n"
        "Мы — команда, которая делает твой Telegram ярче без удара по кошельку! 💸\n\n"
        "📈 <b>Почему выбирают нас:</b>\n"
        "✅ <b>Дикие цены:</b> 15 звёзд за 30 рублей — это дешевле, чем где-либо!\n"
        "✅ <b>Скорость:</b> админ выдаёт звёзды вручную за пару минут. ⚡️\n"
        "✅ <b>Надежность:</b> никакого скама. Только честная работа. 🤝\n"
        "✅ <b>Поддержка:</b> мы всегда на связи и готовы помочь. ❤️\n\n"
        "Сделай свой профиль круче прямо сейчас! 🔥"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Связаться с нами", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# --- Поддержка ---
@dp.callback_query(F.data == "menu_support")
async def show_support(callback: CallbackQuery):
    text = (
        "🛠 <b>Служба поддержки StarShop</b> 🤝\n\n"
        "Если у тебя возникли вопросы, проблемы с оплатой или звёзды не пришли — мы всегда рядом!\n\n"
        f"👨‍💻 Наш админ: @{ADMIN_USERNAME}\n"
        "⏰ <b>Время работы:</b> 24/7 (стараемся отвечать моментально).\n\n"
        "Пиши, не стесняйся! Мы всё решим. ❤️"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Написать админу", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# --- Меню покупки ---
@dp.callback_query(F.data == "menu_buy")
async def show_buy_menu(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for amount, data in PACKAGES.items():
        if data["available"]:
            text = f"🌟 {amount} звёзд — {data['price']}₽"
            kb.button(text=text, callback_data=f"select_{amount}")
        else:
            kb.button(text=f"❌ {amount} звёзд (Нет в наличии)", callback_data="out_of_stock")
    
    kb.button(text="🔙 В главное меню", callback_data="back_to_menu")
    kb.adjust(1)
    
    text = (
        "🛒 <b>Выбери пакет звёзд!</b> ✨\n\n"
        "Сколько звёзд ты хочешь приобрести сегодня? 👇\n"
        "<i>(Внимание: пакеты 25 и 50 временно недоступны!)</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "out_of_stock")
async def out_of_stock(callback: CallbackQuery):
    await callback.answer("😢 Ой! Этого пакета сейчас нет в наличии. Загляни позже!", show_alert=True)

# --- Выбор пакета и подтверждение ---
@dp.callback_query(F.data.startswith("select_"))
async def confirm_purchase(callback: CallbackQuery):
    amount = int(callback.data.split("_")[1])
    
    if not PACKAGES[amount]["available"]:
        await callback.answer("Этот пакет недоступен.", show_alert=True)
        return
        
    price = PACKAGES[amount]["price"]
    
    text = (
        f"🤔 <b>Вы уверены, что хотите купить {amount} звёзд за {price}₽?</b>\n\n"
        "Пожалуйста, подтверди свой выбор. 👇\n"
        "<i>(После подтверждения ты получишь номер заказа и код).</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, покупаю!", callback_data=f"confirm_{amount}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="menu_buy")
        ]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# --- Создание заказа ---
@dp.callback_query(F.data.startswith("confirm_"))
async def create_order(callback: CallbackQuery):
    amount = int(callback.data.split("_")[1])
    
    if not PACKAGES[amount]["available"]:
        await callback.answer("😢 Упс! Этот пакет недоступен.", show_alert=True)
        return
        
    price = PACKAGES[amount]["price"]
    user_id = callback.from_user.id
    username = callback.from_user.username or "нет_юзернейма"
    secret = generate_secret_code()
    
    async with aiosqlite.connect("shop.db") as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, amount, price, secret_code, status) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, amount, price, secret, "created")
        )
        order_id = cursor.lastrowid
        await db.commit()

    kb_user = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Я оплатил", callback_data=f"paid_{order_id}")],
        [InlineKeyboardButton(text="👨‍💻 Написать админу", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    
    text_user = (
        f"🎉 <b>Ура! Заказ успешно создан!</b> 🎊\n\n"
        f"📦 Номер заказа: <code>{order_id}</code>\n"
        f"🔑 Секретный код: <code>{secret}</code>\n"
        f"💎 Товар: {amount} звёзд\n"
        f"💰 К оплате: <b>{price}₽</b>\n\n"
        f"⚠️ <b>Сохрани код! Он понадобится для выдачи.</b>\n"
        f"<i>(Реквизиты для оплаты уточняй у админа).</i>\n\n"
        f"👇 Нажми кнопку, когда переведёшь деньги:"
    )
    
    await callback.message.edit_text(text_user, reply_markup=kb_user, parse_mode="HTML")
    
    # Уведомление админу
    kb_admin = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"admin_approve_{order_id}"),
            InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"admin_reject_{order_id}")
        ]
    ])
    
    text_admin = (
        f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_id}!</b> 💰\n\n"
        f"👤 Покупатель: @{username} (ID: <code>{user_id}</code>)\n"
        f"🌟 Товар: {amount} звёзд\n"
        f"💵 Сумма: {price}₽\n"
        f"🔑 Код: <code>{secret}</code>\n\n"
        f"Проверь оплату и выдай звёзды! 👇"
    )
    
    await bot.send_message(ADMIN_ID, text_admin, reply_markup=kb_admin, parse_mode="HTML")
    await callback.answer()

# --- Пользователь нажал "Я оплатил" ---
@dp.callback_query(F.data.startswith("paid_"))
async def user_paid(callback: CallbackQuery):
    order_id = callback.data.split("_")[1]
    text = (
        f"⏳ <b>Ожидай подтверждения!</b> 🙏\n\n"
        f"Админ уже проверяет твой заказ #{order_id}. Обычно это занимает до 15 минут. ⏱\n\n"
        f"<i>Если что-то пошло не так, пиши: @{ADMIN_USERNAME}</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer("Ожидай подтверждения! 🔥", show_alert=True)
    await bot.send_message(ADMIN_ID, f"💰 @{callback.from_user.username} нажал «Я оплатил» по заказу <b>#{order_id}</b>.", parse_mode="HTML")

# --- АДМИН: Подтверждение ---
@dp.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("🚫 У тебя нет прав! Это кнопка только для админа.", show_alert=True)
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
            await callback.answer("Этот заказ уже выполнен.", show_alert=True)
            return
            
        await db.execute("UPDATE orders SET status = 'approved' WHERE id = ?", (order_id,))
        await db.commit()

    text_user = (
        f"🎉 <b>УРА! Заказ #{order_id} выполнен!</b> 🥳\n\n"
        f"✨ На твой аккаунт было отправлено <b>{amount} звёзд</b>.\n\n"
        f"Спасибо за покупку! Будем рады видеть тебя снова. ❤️\n"
        f"👨‍💻 Поддержка: @{ADMIN_USERNAME}"
    )
    await bot.send_message(user_id, text_user, parse_mode="HTML")
    
    await callback.message.edit_text(
        f"{callback.message.text}\n\n✅ <b>СТАТУС: ВЫПОЛНЕН УСПЕШНО</b> 🎊",
        parse_mode="HTML"
    )
    await callback.answer("Звёзды выданы! ✨")

# --- АДМИН: Отклонение ---
@dp.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("🚫 У тебя нет прав! Это кнопка только для админа.", show_alert=True)
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
            await callback.answer("Этот заказ уже отклонен.", show_alert=True)
            return
            
        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()

    text_user = (
        f"😔 <b>Заказ #{order_id} отклонен.</b>\n\n"
        f"Админ не нашел подтверждения оплаты. 🙅‍♂️\n"
        f"Если ты уверен, что оплатил, срочно пиши: @{ADMIN_USERNAME}\n\n"
        f"<i>Попытка мошенничества приведет к бану! ⛔️</i>"
    )
    await bot.send_message(user_id, text_user, parse_mode="HTML")
    
    await callback.message.edit_text(
        f"{callback.message.text}\n\n❌ <b>СТАТУС: ОТКЛОНЕН</b>",
        parse_mode="HTML"
    )
    await callback.answer("Заказ отклонен.")

# --- Возврат в меню ---
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ Купить звёзды", callback_data="menu_buy")
    kb.button(text="ℹ️ О магазине", callback_data="menu_about")
    kb.button(text="🛠 Поддержка", callback_data="menu_support")
    kb.adjust(1)
    
    text = (
        f"👋 <b>Главное меню StarShop!</b> 🌟\n\n"
        f"👇 Выбирай, что тебя интересует:"
    )
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

async def main():
    await init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    print("[*] StarShop Pro 2.1 запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
