#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import sqlite3
import uuid
import datetime
import json
import asyncio
from decimal import Decimal, ROUND_HALF_UP
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ---------- НАСТРОЙКИ ----------
BOT_TOKEN = "8657892794:AAFyUMdC6uu_ljJc0JZOwBgGQB9Afhp13wQ"
ADMIN_USERNAME = "xchooz"
ADMIN_ID = 8900888739                     # Ваш ID (администратор)
CHANNEL_LINK = "https://t.me/+nfXD24RzOjFlZTEy"
TRANSITION_BOT = "@vxcursed_bot"

PAYMENT_CARD = "+79637013160"
PAYMENT_DETAILS = "T-Bank (Тинькофф) карта 2200 1234 5678 9012"

PRICES = {
    100: 163,
    250: 392,
    500: 773,
    1000: 1626,
    2500: 3914,
}

STAR_PRICE_PER_UNIT = Decimal('1.56')
REFERRAL_BONUS_PERCENT = 5

# ---------- БАЗА ДАННЫХ ----------
def init_db():
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        referral_code TEXT UNIQUE,
        referred_by INTEGER,
        balance INTEGER DEFAULT 0,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER,
        type TEXT,
        amount INTEGER,
        price INTEGER,
        status TEXT,
        receiver_id INTEGER,
        receiver_username TEXT,
        created_at TEXT,
        paid_at TEXT,
        completed_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        new_user_id INTEGER,
        bonus INTEGER,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('star_price', '1.56')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_bonus', '5')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_details', ?)", (PAYMENT_DETAILS,))
    conn.commit()
    conn.close()

init_db()

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_user(user_id):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def create_user(user_id, username, full_name, referred_by=None):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    ref_code = str(uuid.uuid4())[:8]
    c.execute(
        "INSERT INTO users (user_id, username, full_name, referral_code, referred_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, full_name, ref_code, referred_by, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return ref_code

def get_referral_code(user_id):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_referrer_id(ref_code):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_balance(user_id):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def add_balance(user_id, amount):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def create_order(user_id, order_type, amount, price, receiver_id=None, receiver_username=None):
    order_id = str(uuid.uuid4())
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (order_id, user_id, type, amount, price, status, receiver_id, receiver_username, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
        (order_id, user_id, order_type, amount, price, receiver_id, receiver_username, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return order_id

def get_order(order_id):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_order_status(order_id, status, paid_at=None, completed_at=None):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    if status == 'paid':
        c.execute("UPDATE orders SET status = ?, paid_at = ? WHERE order_id = ?", (status, datetime.datetime.now().isoformat(), order_id))
    elif status == 'completed':
        c.execute("UPDATE orders SET status = ?, completed_at = ? WHERE order_id = ?", (status, datetime.datetime.now().isoformat(), order_id))
    else:
        c.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id))
    conn.commit()
    conn.close()

def get_pending_orders():
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE status = 'pending' ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_orders_by_user(user_id, status=None):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    if status:
        c.execute("SELECT * FROM orders WHERE user_id = ? AND status = ? ORDER BY created_at DESC", (user_id, status))
    else:
        c.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_orders(limit=50):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
    completed = c.fetchone()[0]
    c.execute("SELECT SUM(price) FROM orders WHERE status = 'completed'")
    total_income = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    conn.close()
    return {'completed': completed, 'total_income': total_income, 'users': total_users}

def get_setting(key):
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- КОМАНДА /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    full_name = user.full_name or ''

    if not get_user(user_id):
        ref_code = context.args[0] if context.args else None
        referrer_id = get_referrer_id(ref_code) if ref_code else None
        create_user(user_id, username, full_name, referrer_id)
        if referrer_id:
            add_balance(referrer_id, 50)
            conn = sqlite3.connect('starfall.db')
            c = conn.cursor()
            c.execute(
                "INSERT INTO referrals (referrer_id, new_user_id, bonus, created_at) VALUES (?, ?, ?, ?)",
                (referrer_id, user_id, 50, datetime.datetime.now().isoformat())
            )
            conn.commit()
            conn.close()

    keyboard = [
        [InlineKeyboardButton("⭐ Купить себе", callback_data="buy_self")],
        [InlineKeyboardButton("🎁 Подарить", callback_data="gift")],
        [InlineKeyboardButton("👑 Купить Premium", callback_data="buy_premium_self")],
        [InlineKeyboardButton("🎁 Подарить Premium", callback_data="gift_premium")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")],
        [InlineKeyboardButton("📢 Наш канал", url=CHANNEL_LINK)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "✨ Добро пожаловать в StarFall!\n\n"
        "У нас вы можете купить:\n"
        "⭐️ Telegram Stars\n"
        "👑 Telegram Premium\n"
        "Дешевле чем в приложении и без верификации!\n\n"
        "Рекомендуем подписаться на наш закрытый канал!\n"
        f"Переходник: {TRANSITION_BOT}",
        reply_markup=reply_markup
    )

# ---------- ОБРАБОТЧИК КНОПОК ----------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "buy_self":
        await show_buy_stars(query, user_id, gift=False)
    elif data == "gift":
        await query.edit_message_text(
            "🎁 Отправьте мне @username пользователя, которому хотите подарить звёзды.\n"
            "Например: @xchooz\n\n"
            "Затем выберите количество звёзд из меню ниже."
        )
        context.user_data['gift_mode'] = True
        context.user_data['gift_receiver'] = None
        await send_buy_stars_menu(update, user_id, gift=True)
    elif data == "buy_premium_self":
        await buy_premium(query, user_id, gift=False)
    elif data == "gift_premium":
        await query.edit_message_text(
            "🎁 Отправьте мне @username пользователя, которому хотите подарить Premium."
        )
        context.user_data['gift_premium_mode'] = True
        context.user_data['gift_receiver'] = None
        await send_buy_premium_menu(update, user_id, gift=True)
    elif data == "referral":
        await show_referral(query, context)
    elif data == "support":
        await query.edit_message_text(
            "📩 Напишите ваше сообщение в ответ на это сообщение, и я перешлю его администратору."
        )
        context.user_data['support_mode'] = True
    elif data.startswith("stars_pkg_"):
        parts = data.split("_")
        amount = int(parts[2])
        price = PRICES.get(amount)
        if not price:
            await query.edit_message_text("❌ Ошибка: такой пакет не найден.")
            return
        gift = context.user_data.get('gift_mode', False)
        if gift:
            receiver = context.user_data.get('gift_receiver')
            if not receiver:
                await query.edit_message_text("❌ Сначала укажите получателя (отправьте @username).")
                return
            order_id = create_order(user_id, 'stars', amount, price, receiver_username=receiver)
            await show_order(query, user_id, order_id, context, receiver=receiver)
        else:
            order_id = create_order(user_id, 'stars', amount, price, receiver_id=user_id, receiver_username=query.from_user.username or query.from_user.first_name)
            await show_order(query, user_id, order_id, context)
    elif data.startswith("premium_pkg_"):
        price = 399  # фиксированно за месяц
        gift = context.user_data.get('gift_premium_mode', False)
        if gift:
            receiver = context.user_data.get('gift_receiver')
            if not receiver:
                await query.edit_message_text("❌ Сначала укажите получателя (отправьте @username).")
                return
            order_id = create_order(user_id, 'premium', 30, price, receiver_username=receiver)
            await show_order(query, user_id, order_id, context, receiver=receiver)
        else:
            order_id = create_order(user_id, 'premium', 30, price, receiver_id=user_id, receiver_username=query.from_user.username or query.from_user.first_name)
            await show_order(query, user_id, order_id, context)
    elif data.startswith("confirm_order_"):
        order_id = data.replace("confirm_order_", "")
        order = get_order(order_id)
        if not order:
            await query.edit_message_text("❌ Заказ не найден.")
            return
        update_order_status(order_id, 'completed')
        buyer_id = order[1]
        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=f"✅ Ваш заказ #{order_id[:8]} успешно выполнен!\n🎉 {order[3]} {'звёзд' if order[2]=='stars' else 'месяцев Premium'} зачислены."
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить пользователя {buyer_id}: {e}")
        await query.edit_message_text(f"✅ Заказ #{order_id[:8]} подтверждён и выполнен.")
    elif data.startswith("cancel_order_"):
        order_id = data.replace("cancel_order_", "")
        update_order_status(order_id, 'cancelled')
        order = get_order(order_id)
        if order:
            buyer_id = order[1]
            try:
                await context.bot.send_message(
                    chat_id=buyer_id,
                    text=f"❌ Ваш заказ #{order_id[:8]} был отменён администратором."
                )
            except:
                pass
        await query.edit_message_text(f"❌ Заказ #{order_id[:8]} отменён.")
    elif data.startswith("notify_paid_"):
        order_id = data.replace("notify_paid_", "")
        order = get_order(order_id)
        if not order:
            await query.edit_message_text("❌ Заказ не найден.")
            return
        update_order_status(order_id, 'paid')
        await query.edit_message_text(
            "✅ Вы отметили оплату. Администратор проверит транзакцию и подтвердит заказ в ближайшее время.\n"
            "Спасибо за покупку!"
        )
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💰 Пользователь @{query.from_user.username or query.from_user.first_name} сообщил об оплате заказа `{order_id}`.\nПроверьте поступление средств."
                )
            except:
                pass
    elif data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("⭐ Купить себе", callback_data="buy_self")],
            [InlineKeyboardButton("🎁 Подарить", callback_data="gift")],
            [InlineKeyboardButton("👑 Купить Premium", callback_data="buy_premium_self")],
            [InlineKeyboardButton("🎁 Подарить Premium", callback_data="gift_premium")],
            [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
            [InlineKeyboardButton("🆘 Поддержка", callback_data="support")],
            [InlineKeyboardButton("📢 Наш канал", url=CHANNEL_LINK)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "✨ Добро пожаловать в StarFall!\n\n"
            "У нас вы можете купить:\n"
            "⭐️ Telegram Stars\n"
            "👑 Telegram Premium\n"
            "Дешевле чем в приложении и без верификации!\n\n"
            "Рекомендуем подписаться на наш закрытый канал!\n"
            f"Переходник: {TRANSITION_BOT}",
            reply_markup=reply_markup
        )

# ---------- ФУНКЦИИ МЕНЮ ----------
async def show_buy_stars(query, user_id, gift=False):
    keyboard = []
    for amount, price in PRICES.items():
        keyboard.append([InlineKeyboardButton(f"{amount} ⭐ — {price}₽", callback_data=f"stars_pkg_{amount}")])
    keyboard.append([InlineKeyboardButton("✏️ Ввести своё количество", callback_data="custom_stars")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "⭐️ Telegram Stars\n\nДля покупки звёзд себе выбери пакет или отправь своё количество мне в чат.\n\nМожно купить от 50 до 1,000,000 ⭐️ за раз."
    if gift:
        text = "🎁 Подарок – выберите пакет звёзд для получателя."
    await query.edit_message_text(text, reply_markup=reply_markup)

async def send_buy_stars_menu(update, user_id, gift=False):
    keyboard = []
    for amount, price in PRICES.items():
        keyboard.append([InlineKeyboardButton(f"{amount} ⭐ — {price}₽", callback_data=f"stars_pkg_{amount}")])
    keyboard.append([InlineKeyboardButton("✏️ Ввести своё количество", callback_data="custom_stars")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "⭐️ Telegram Stars\n\nВыберите пакет или отправьте своё количество в чат.\n\nМожно купить от 50 до 1,000,000 ⭐️."
    if gift:
        text = "🎁 Подарок – выберите пакет звёзд."
    await update.effective_message.reply_text(text, reply_markup=reply_markup)

async def buy_premium(query, user_id, gift=False):
    keyboard = [
        [InlineKeyboardButton("👑 1 месяц Premium — 399₽", callback_data="premium_pkg_1m")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👑 Telegram Premium\n\nВыберите срок подписки."
    if gift:
        text = "🎁 Подарок Premium – выберите срок."
    await query.edit_message_text(text, reply_markup=reply_markup)

async def send_buy_premium_menu(update, user_id, gift=False):
    keyboard = [
        [InlineKeyboardButton("👑 1 месяц Premium — 399₽", callback_data="premium_pkg_1m")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👑 Telegram Premium\n\nВыберите срок подписки."
    if gift:
        text = "🎁 Подарок Premium – выберите срок."
    await update.effective_message.reply_text(text, reply_markup=reply_markup)

# ---------- ПОКАЗ ЗАКАЗА ----------
async def show_order(query, user_id, order_id, context, receiver=None):
    order = get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Ошибка создания заказа.")
        return
    amount = order[3]
    price = order[4]
    receiver_str = f"@{receiver}" if receiver else "вы"
    text = (
        f"✅ Заказ создан\n\n"
        f"Номер заказа: `{order_id}`\n"
        f"Сумма к оплате: {price}.00₽\n\n"
        f"Вы покупаете: {amount} {'звёзд' if order[2]=='stars' else 'месяцев Premium'}\n"
        f"Получатель: {receiver_str}\n\n"
        f"Совершая оплату, вы подтверждаете, что покупаете Telegram Stars/Telegram Premium для себя или в подарок своим друзьям и НЕ оплачиваете товары в других сервисах в пользу незнакомых лиц.\n\n"
        f"💳 Реквизиты для оплаты:\n"
        f"Карта T‑Банк: {PAYMENT_CARD}\n"
        f"СБП по номеру телефона: {PAYMENT_CARD}\n\n"
        f"После перевода нажмите кнопку «Я оплатил»."
    )
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"notify_paid_{order_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    if ADMIN_ID:
        admin_text = (
            f"🆕 НОВЫЙ ЗАКАЗ\n"
            f"Номер: `{order_id}`\n"
            f"Пользователь: @{query.from_user.username or query.from_user.first_name}\n"
            f"Товар: {amount} {'звёзд' if order[2]=='stars' else 'Premium'}\n"
            f"Сумма: {price} ₽\n"
            f"Получатель: {receiver_str}\n"
            f"Статус: ожидает оплаты"
        )
        keyboard_admin = [
            [InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_order_{order_id}")],
            [InlineKeyboardButton("❌ Отклонить заказ", callback_data=f"cancel_order_{order_id}")]
        ]
        reply_admin = InlineKeyboardMarkup(keyboard_admin)
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=reply_admin, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Не удалось уведомить админа: {e}")

# ---------- РЕФЕРАЛКА ----------
async def show_referral(query, context):
    user_id = query.from_user.id
    ref_code = get_referral_code(user_id)
    if not ref_code:
        conn = sqlite3.connect('starfall.db')
        c = conn.cursor()
        ref_code = str(uuid.uuid4())[:8]
        c.execute("UPDATE users SET referral_code = ? WHERE user_id = ?", (ref_code, user_id))
        conn.commit()
        conn.close()
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    balance = get_balance(user_id)
    text = (
        f"👥 Реферальная система\n\n"
        f"Ваша реферальная ссылка:\n`{ref_link}`\n\n"
        f"За каждого приведённого друга вы получаете бонус 50 ₽ на счёт.\n"
        f"Ваш текущий баланс бонусов: {balance} ₽\n\n"
        f"Бонусы можно использовать для оплаты следующих покупок."
    )
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ---------- ПОДДЕРЖКА ----------
async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('support_mode'):
        user_text = update.message.text
        if ADMIN_ID:
            await context.bot.send_message(
                ADMIN_ID,
                f"📩 Сообщение от @{update.effective_user.username or update.effective_user.first_name}:\n\n{user_text}"
            )
        await update.message.reply_text("✅ Ваше сообщение отправлено администратору. Мы ответим вам в ближайшее время.")
        context.user_data['support_mode'] = False

# ---------- ОБРАБОТКА ВВОДА КОЛИЧЕСТВА ЗВЁЗД ----------
async def handle_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Пожалуйста, введите число (количество звёзд).")
        return
    amount = int(text)
    if amount < 50 or amount > 1000000:
        await update.message.reply_text("❌ Количество должно быть от 50 до 1,000,000.")
        return
    price = Decimal(amount) * Decimal(get_setting('star_price'))
    price = price.quantize(Decimal('0'), rounding=ROUND_HALF_UP)
    price = int(price)
    gift = context.user_data.get('gift_mode', False)
    if gift:
        receiver = context.user_data.get('gift_receiver')
        if not receiver:
            await update.message.reply_text("❌ Сначала укажите получателя (отправьте @username).")
            return
        order_id = create_order(update.effective_user.id, 'stars', amount, price, receiver_username=receiver)
        await send_order_confirmation(update, context, order_id, receiver)
    else:
        order_id = create_order(update.effective_user.id, 'stars', amount, price, receiver_id=update.effective_user.id)
        await send_order_confirmation(update, context, order_id)

# ---------- ПОДТВЕРЖДЕНИЕ ЗАКАЗА ЧЕРЕЗ СООБЩЕНИЕ ----------
async def send_order_confirmation(update, context, order_id, receiver=None):
    order = get_order(order_id)
    if not order:
        await update.message.reply_text("❌ Ошибка создания заказа.")
        return
    amount = order[3]
    price = order[4]
    receiver_str = f"@{receiver}" if receiver else "вы"
    text = (
        f"✅ Заказ создан\n\n"
        f"Номер заказа: `{order_id}`\n"
        f"Сумма к оплате: {price}.00₽\n\n"
        f"Вы покупаете: {amount} звёзд\n"
        f"Получатель: {receiver_str}\n\n"
        f"💳 Реквизиты для оплаты:\n"
        f"Карта T‑Банк: {PAYMENT_CARD}\n"
        f"СБП по номеру телефона: {PAYMENT_CARD}\n\n"
        f"После перевода нажмите кнопку «Я оплатил»."
    )
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"notify_paid_{order_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    if ADMIN_ID:
        admin_text = (
            f"🆕 НОВЫЙ ЗАКАЗ\n"
            f"Номер: `{order_id}`\n"
            f"Пользователь: @{update.effective_user.username or update.effective_user.first_name}\n"
            f"Товар: {amount} звёзд\n"
            f"Сумма: {price} ₽\n"
            f"Получатель: {receiver_str}\n"
            f"Статус: ожидает оплаты"
        )
        keyboard_admin = [
            [InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_order_{order_id}")],
            [InlineKeyboardButton("❌ Отклонить заказ", callback_data=f"cancel_order_{order_id}")]
        ]
        reply_admin = InlineKeyboardMarkup(keyboard_admin)
        await context.bot.send_message(ADMIN_ID, admin_text, reply_markup=reply_admin, parse_mode='Markdown')

# ---------- ОБРАБОТКА ПОЛУЧАТЕЛЯ ДЛЯ ПОДАРКОВ ----------
async def handle_gift_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('gift_mode') or context.user_data.get('gift_premium_mode'):
        username = update.message.text.strip()
        if not username.startswith('@'):
            username = '@' + username
        context.user_data['gift_receiver'] = username
        await update.message.reply_text(f"✅ Получатель установлен: {username}\nТеперь выберите пакет.")
        if context.user_data.get('gift_mode'):
            await send_buy_stars_menu(update, update.effective_user.id, gift=True)
        elif context.user_data.get('gift_premium_mode'):
            await send_buy_premium_menu(update, update.effective_user.id, gift=True)

# ---------- АДМИН-КОМАНДЫ ----------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return
    stats = get_stats()
    text = (
        f"🔧 Админ-панель\n\n"
        f"📊 Статистика:\n"
        f"Всего заказов выполнено: {stats['completed']}\n"
        f"Общий доход: {stats['total_income']} ₽\n"
        f"Всего пользователей: {stats['users']}\n\n"
        f"Последние 5 заказов:\n"
    )
    orders = get_all_orders(5)
    if orders:
        for ord in orders:
            text += f"`{ord[0][:8]}` | {ord[2]} | {ord[3]}шт. | {ord[4]}₽ | {ord[5]}\n"
    else:
        text += "Нет заказов."
    text += "\nИспользуйте команды:\n"
    text += "/stats – подробная статистика\n"
    text += "/set_price <цена> – изменить стоимость 1 звезды\n"
    text += "/set_payment <реквизиты> – изменить реквизиты\n"
    text += "/list_orders – все заказы\n"
    text += "/export – экспорт базы (JSON)"
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    stats = get_stats()
    text = (
        f"📊 Подробная статистика:\n"
        f"✅ Выполнено заказов: {stats['completed']}\n"
        f"💰 Общий доход: {stats['total_income']} ₽\n"
        f"👥 Пользователей: {stats['users']}\n"
    )
    await update.message.reply_text(text)

async def set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /set_price <цена за 1 звезду>")
        return
    try:
        price = Decimal(context.args[0])
    except:
        await update.message.reply_text("❌ Некорректное число.")
        return
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("UPDATE settings SET value = ? WHERE key = 'star_price'", (str(price),))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Цена за 1 звезду установлена: {price} ₽")

async def set_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /set_payment <реквизиты>")
        return
    details = ' '.join(context.args)
    conn = sqlite3.connect('starfall.db')
    c = conn.cursor()
    c.execute("UPDATE settings SET value = ? WHERE key = 'payment_details'", (details,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Реквизиты обновлены: {details}")

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    orders = get_all_orders(50)
    if not orders:
        await update.message.reply_text("Заказов нет.")
        return
    text = "📋 Последние 50 заказов:\n\n"
    for ord in orders:
        text += f"`{ord[0][:8]}` | {ord[2]} | {ord[3]}шт. | {ord[4]}₽ | {ord[5]}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def export_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    conn = sqlite3.connect('starfall.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    data = {}
    for table in ['users', 'orders', 'referrals', 'settings']:
        c.execute(f"SELECT * FROM {table}")
        rows = c.fetchall()
        data[table] = [dict(row) for row in rows]
    conn.close()
    with open('export.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    await update.message.reply_document(document=open('export.json', 'rb'), filename='export.json')

# ---------- MAIN ----------
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("set_price", set_price))
    application.add_handler(CommandHandler("set_payment", set_payment))
    application.add_handler(CommandHandler("list_orders", list_orders))
    application.add_handler(CommandHandler("export", export_db))

    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stars_amount))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gift_receiver))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support))

    print("🚀 Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling()

if __name__ == "__main__":
    main()