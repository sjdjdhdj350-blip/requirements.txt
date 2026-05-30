import asyncio
import random
from datetime import datetime, timedelta
import aiosqlite
import threading
from flask import Flask, render_template_string
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "8741870887:AAFg0Mh1MfuL4QE1Q772vEIrf3OGkGAylPc"
ADMIN_IDS = [8378911475, 8224769867, 8292372344]

# ====================== FLASK MINI-WEBSITE ======================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kazik Game - Status</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            color: #eee;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            max-width: 500px;
            width: 90%;
        }
        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #f39c12, #e74c3c);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .status-badge {
            display: inline-block;
            padding: 10px 25px;
            border-radius: 50px;
            font-size: 1.2em;
            font-weight: bold;
            margin: 20px 0;
            animation: pulse 2s infinite;
        }
        .online {
            background: rgba(46, 204, 113, 0.2);
            border: 2px solid #2ecc71;
            color: #2ecc71;
        }
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.4); }
            50% { box-shadow: 0 0 0 15px rgba(46, 204, 113, 0); }
        }
        .info { margin-top: 25px; line-height: 1.8; opacity: 0.8; }
        .emoji { font-size: 3em; margin-bottom: 15px; }
    </style>
    <script>
        // Авто-обновление каждые 5 минут для поддержания активности
        setTimeout(function() {
            location.reload();
        }, 300000);
    </script>
</head>
<body>
    <div class="container">
        <div class="emoji">🎰</div>
        <h1>Kazik Game Bot</h1>
        <div class="status-badge online">⚡ БОТ АКТИВЕН</div>
        <div class="info">
            <p>🤖 Telegram бот работает</p>
            <p>🕐 Время сервера: {{ server_time }}</p>
            <p>📊 Статус: все системы в норме</p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    """Главная страница для keep-alive"""
    return render_template_string(
        HTML_TEMPLATE,
        server_time=datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    )

@app.route('/ping')
def ping():
    """Эндпоинт для UptimeRobot и других мониторингов"""
    return "OK", 200

@app.route('/health')
def health():
    """Расширенная проверка здоровья"""
    return {
        "status": "healthy",
        "bot": "running",
        "timestamp": datetime.now().isoformat()
    }

def run_flask():
    """Запуск Flask в отдельном потоке"""
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

# ====================== END FLASK ======================

class UserState(StatesGroup):
    donate_amount = State()
    bet_amount = State()
    game_type = State()
    menu_msg_id = State()
    support_msg = State()

class AdminState(StatesGroup):
    reply_msg = State()
    target_user_id = State()

async def init_db():
    async with aiosqlite.connect("kazik.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 1000.0,
                registration_date TEXT,
                last_bonus TEXT
            )
        """)
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect("kazik.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def add_user(user_id, username):
    async with aiosqlite.connect("kazik.db") as db:
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, registration_date, last_bonus) VALUES (?, ?, ?, ?)",
            (user_id, username, now, "1970-01-01T00:00:00")
        )
        await db.commit()

async def update_balance(user_id, amount):
    async with aiosqlite.connect("kazik.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_bonus_time(user_id, time_str):
    async with aiosqlite.connect("kazik.db") as db:
        await db.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (time_str, user_id))
        await db.commit()

def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="💰 Донат", callback_data="menu_donate"),
         InlineKeyboardButton(text="🎁 Бонус", callback_data="menu_bonus")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu_support")]
    ])

def kb_back():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")]
    ])

def kb_games():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Рулетка", callback_data="game_start_slots"),
         InlineKeyboardButton(text="💣 Мины", callback_data="game_start_mines")],
        [InlineKeyboardButton(text="🃏 Джокер", callback_data="game_start_joker"),
         InlineKeyboardButton(text="🎲 Кубики", callback_data="game_start_dice")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")]
    ])

def kb_admin_donate(user_id, amount):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_conf_{user_id}_{amount}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_decl_{user_id}_{amount}")]
    ])

def kb_dice_choice():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Четное", callback_data="dice_even"),
         InlineKeyboardButton(text="Нечетное", callback_data="dice_odd")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_games")]
    ])

def kb_slots(symbols, show_back=False):
    kb = [
        [InlineKeyboardButton(text=symbols[0], callback_data="ignore"),
         InlineKeyboardButton(text=symbols[1], callback_data="ignore"),
         InlineKeyboardButton(text=symbols[2], callback_data="ignore")]
    ]
    if show_back:
        kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_games")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def kb_mines(mines_data, current_coeff=None, bank=None):
    kb = []
    for row in range(5):
        row_btns = []
        for col in range(5):
            idx = row * 5 + col
            status = mines_data['grid'][idx]
            text_btn = "❓"
            if status == 1:
                text_btn = "✔"
            elif status == 2:
                text_btn = "💣"
            elif status == 3:
                text_btn = "💥"
            
            cb_data = f"mine_click_{idx}" if status == 0 else "ignore"
            row_btns.append(InlineKeyboardButton(text=text_btn, callback_data=cb_data))
        kb.append(row_btns)
    
    if current_coeff is not None and bank is not None and mines_data['state'] == 'playing':
        kb.append([InlineKeyboardButton(text=f"💸 Забрать {bank:.2f}", callback_data="mine_collect")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_games")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def kb_joker(step, bank):
    kb = []
    row_btns = []
    for i in range(3):
        row_btns.append(InlineKeyboardButton(text="🎴", callback_data=f"joker_click_{i}"))
    kb.append(row_btns)
    if step > 0:
        kb.append([InlineKeyboardButton(text=f"💸 Забрать {bank:.2f}", callback_data="joker_collect")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_games")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    await add_user(message.from_user.id, message.from_user.username)
    msg = await message.answer("Добро пожаловать в Kazik Game!", reply_markup=kb_main())
    await state.update_data(menu_msg_id=msg.message_id)

@dp.callback_query(F.data == "menu_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(menu_msg_id=call.message.message_id)
    await call.message.edit_text("Добро пожаловать в Kazik Game!", reply_markup=kb_main())

@dp.callback_query(F.data == "ignore")
async def ignore_callback(call: CallbackQuery):
    await call.answer()

@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    text = f"👤 Профиль\n\nID: {user[0]}\nЛогин: @{user[1]}\nБаланс: {user[2]:.2f} монет"
    await call.message.edit_text(text, reply_markup=kb_back())

@dp.callback_query(F.data == "menu_bonus")
async def show_bonus(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    last_bonus = datetime.fromisoformat(user[4])
    now = datetime.now()
    if now - last_bonus >= timedelta(days=1):
        bonus = random.randint(50, 500)
        await update_balance(call.from_user.id, bonus)
        await set_bonus_time(call.from_user.id, now.isoformat())
        await call.message.edit_text(f"🎁 Вы получили бонус: {bonus} монет!", reply_markup=kb_back())
    else:
        left = timedelta(days=1) - (now - last_bonus)
        h, rem = divmod(left.seconds, 3600)
        m, s = divmod(rem, 60)
        await call.message.edit_text(f"⏳ Следующий бонус будет доступен через {h}ч {m}м {s}с.", reply_markup=kb_back())

@dp.callback_query(F.data == "menu_support")
async def show_support(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.support_msg)
    await state.update_data(menu_msg_id=call.message.message_id)
    text = "🆘 Поддержка\n\nНапишите ваше сообщение для администрации.\nСвязь напрямую: @kloxow"
    await call.message.edit_text(text, reply_markup=kb_back())

@dp.message(UserState.support_msg)
async def process_support(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    msg_id = data.get("menu_msg_id")
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📩 Новое сообщение от {message.from_user.id} (@{message.from_user.username}):\n\n{message.text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Ответить", callback_data=f"ans_sup_{message.from_user.id}")]
                ])
            )
        except Exception:
            pass
            
    await bot.edit_message_text("✅ Ваше сообщение отправлено администрации.", chat_id=message.chat.id, message_id=msg_id, reply_markup=kb_back())
    await state.set_state(None)

@dp.callback_query(F.data.startswith("ans_sup_"))
async def admin_reply_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    user_id = int(call.data.split("_")[2])
    await state.set_state(AdminState.reply_msg)
    await state.update_data(target_user_id=user_id)
    await call.message.reply("Введите текст ответа пользователю:")
    await call.answer()

@dp.message(AdminState.reply_msg)
async def admin_reply_process(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("target_user_id")
    try:
        await bot.send_message(user_id, f"💬 Ответ от администрации:\n\n{message.text}")
        await message.reply("✅ Ответ успешно отправлен.")
    except Exception:
        await message.reply("❌ Ошибка отправки. Возможно, пользователь заблокировал бота.")
    await state.set_state(None)

@dp.callback_query(F.data == "menu_donate")
async def start_donate(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.donate_amount)
    await state.update_data(menu_msg_id=call.message.message_id)
    await call.message.edit_text("💰 Донат\n\nВведите сумму пополнения (число):", reply_markup=kb_back())

@dp.message(UserState.donate_amount)
async def process_donate(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    msg_id = data.get("menu_msg_id")
    
    raw_text = message.text.replace(',', '.')
    try:
        amount = float(raw_text)
        if amount <= 0:
            raise ValueError
            
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id, 
                    f"Заявка на пополнение от {message.from_user.id} (@{message.from_user.username})\nСумма: {amount}",
                    reply_markup=kb_admin_donate(message.from_user.id, amount)
                )
            except Exception:
                pass
                
        await bot.edit_message_text("✅ Заявка на пополнение отправлена администрации.", chat_id=message.chat.id, message_id=msg_id, reply_markup=kb_back())
    except ValueError:
        await bot.edit_message_text("❌ Неверная сумма. Введите корректное число.", chat_id=message.chat.id, message_id=msg_id, reply_markup=kb_back())
    await state.set_state(None)

@dp.callback_query(F.data.startswith("admin_conf_"))
async def admin_confirm(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    parts = call.data.split("_")
    user_id = int(parts[2])
    amount = float(parts[3])
    await update_balance(user_id, amount)
    try:
        await bot.send_message(user_id, f"✅ Ваш баланс пополнен на {amount} монет!")
    except Exception:
        pass
    await call.message.edit_text(f"Заявка на {amount} от {user_id} ПОДТВЕРЖДЕНА.")

@dp.callback_query(F.data.startswith("admin_decl_"))
async def admin_decline(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    parts = call.data.split("_")
    user_id = int(parts[2])
    amount = float(parts[3])
    try:
        await bot.send_message(user_id, f"❌ Ваша заявка на пополнение {amount} монет отклонена.")
    except Exception:
        pass
    await call.message.edit_text(f"Заявка на {amount} от {user_id} ОТКЛОНЕНА.")

@dp.callback_query(F.data == "menu_games")
async def show_games(call: CallbackQuery):
    await call.message.edit_text("🎮 Выберите игру:", reply_markup=kb_games())

@dp.callback_query(F.data.startswith("game_start_"))
async def pre_game_bet(call: CallbackQuery, state: FSMContext):
    game = call.data.split("_")[2]
    await state.set_state(UserState.bet_amount)
    await state.update_data(game_type=game, menu_msg_id=call.message.message_id)
    await call.message.edit_text("Введите сумму ставки (число):", reply_markup=kb_back())

@dp.message(UserState.bet_amount)
async def process_bet(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    msg_id = data.get("menu_msg_id")
    game = data.get("game_type")
    
    raw_text = message.text.replace(',', '.')
    try:
        bet = float(raw_text)
        if bet <= 0:
            raise ValueError
        
        user = await get_user(message.from_user.id)
        if user[2] < bet:
            await bot.edit_message_text("❌ Недостаточно средств на балансе.", chat_id=message.chat.id, message_id=msg_id, reply_markup=kb_back())
            await state.set_state(None)
            return
            
        await state.update_data(current_bet=bet)
        await state.set_state(None)
        
        if game == "slots":
            await play_slots(message.chat.id, msg_id, bet, message.from_user.id)
        elif game == "mines":
            await start_mines(message.chat.id, msg_id, bet, message.from_user.id, state)
        elif game == "joker":
            await start_joker(message.chat.id, msg_id, bet, message.from_user.id, state)
        elif game == "dice":
            await start_dice(message.chat.id, msg_id, bet)
            
    except ValueError:
        await bot.edit_message_text("❌ Неверная ставка. Введите корректное число.", chat_id=message.chat.id, message_id=msg_id, reply_markup=kb_back())
        await state.set_state(None)

async def play_slots(chat_id, msg_id, bet, user_id):
    await update_balance(user_id, -bet)
    symbols_pool = ['🍒', '🍋', '🍇', '7️⃣', '🍉', '🔔']
    
    for _ in range(6):
        temp_res = [random.choice(symbols_pool) for _ in range(3)]
        try:
            await bot.edit_message_text(
                f"🎰 Рулетка\nСтавка: {bet:.2f}\nКрутим барабаны...",
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=kb_slots(temp_res, show_back=False)
            )
        except Exception:
            pass
        await asyncio.sleep(1.0)
        
    res = [random.choice(symbols_pool) for _ in range(3)]
    
    if res == ['7️⃣', '7️⃣', '7️⃣']:
        win = bet * 4
        text = f"🎰 Рулетка\nСтавка: {bet:.2f}\n\n🎉 ДЖЕКПОТ! Вы выиграли {win:.2f} монет!"
        await update_balance(user_id, win)
    elif res[0] == res[1] == res[2]:
        win = bet * 2
        text = f"🎰 Рулетка\nСтавка: {bet:.2f}\n\n✅ Победа! Вы выиграли {win:.2f} монет!"
        await update_balance(user_id, win)
    else:
        text = f"🎰 Рулетка\nСтавка: {bet:.2f}\n\n❌ Проигрыш. Повезет в следующий раз."
        
    await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb_slots(res, show_back=True))

MINES_COEFFS = [1.0, 1.33, 1.65, 2.1, 2.7, 3.4, 4.2, 5.2, 6.5, 8.0, 10.0, 12.5, 15.0, 18.0, 22.0, 27.0, 35.0, 45.0, 60.0, 80.0]

async def start_mines(chat_id, msg_id, bet, user_id, state):
    await update_balance(user_id, -bet)
    mine_positions = random.sample(range(25), 6)
    mines_data = {
        'grid': [0]*25,
        'mines': mine_positions,
        'opened': 0,
        'bet': bet,
        'state': 'playing'
    }
    await state.update_data(mines_data=mines_data, menu_msg_id=msg_id)
    text = f"💣 Мины\nСтавка: {bet:.2f}\nКоэффициент: 1.00\nНажмите на клетку!"
    await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb_mines(mines_data, 1.0, bet))

@dp.callback_query(F.data.startswith("mine_click_"))
async def process_mine_click(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mines_data = data.get("mines_data")
    if not mines_data or mines_data['state'] != 'playing':
        return
        
    idx = int(call.data.split("_")[2])
    
    if idx in mines_data['mines']:
        mines_data['state'] = 'lost'
        for i in range(25):
            if i in mines_data['mines']:
                mines_data['grid'][i] = 2
        mines_data['grid'][idx] = 3
        await state.update_data(mines_data=mines_data)
        await call.message.edit_text(f"💥 БУМ! Вы наступили на мину и проиграли {mines_data['bet']} монет.", reply_markup=kb_mines(mines_data))
        await state.set_state(None)
    else:
        mines_data['grid'][idx] = 1
        mines_data['opened'] += 1
        coeff = MINES_COEFFS[mines_data['opened']]
        bank = mines_data['bet'] * coeff
        await state.update_data(mines_data=mines_data)
        
        if mines_data['opened'] == 19:
            mines_data['state'] = 'won'
            await update_balance(call.from_user.id, bank)
            await call.message.edit_text(f"🏆 Вы открыли все безопасные клетки! Выигрыш: {bank:.2f}", reply_markup=kb_mines(mines_data))
            await state.set_state(None)
        else:
            await call.message.edit_text(f"💣 Мины\nСтавка: {mines_data['bet']:.2f}\nТекущий кэф: {coeff:.2f}\nБанк: {bank:.2f}", reply_markup=kb_mines(mines_data, coeff, bank))

@dp.callback_query(F.data == "mine_collect")
async def collect_mines(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mines_data = data.get("mines_data")
    if not mines_data or mines_data['state'] != 'playing':
        return
    coeff = MINES_COEFFS[mines_data['opened']]
    bank = mines_data['bet'] * coeff
    await update_balance(call.from_user.id, bank)
    mines_data['state'] = 'won'
    for i in range(25):
        if i in mines_data['mines']:
            mines_data['grid'][i] = 2
    await call.message.edit_text(f"💸 Вы забрали {bank:.2f} монет!", reply_markup=kb_mines(mines_data))
    await state.set_state(None)

JOKER_COEFFS = [1.0, 1.66, 2.5, 3.8, 5.5, 8.0, 10.0]

async def start_joker(chat_id, msg_id, bet, user_id, state):
    await update_balance(user_id, -bet)
    joker_data = {
        'bet': bet,
        'step': 0,
        'state': 'playing'
    }
    await state.update_data(joker_data=joker_data, menu_msg_id=msg_id)
    text = f"🃏 Джокер\nСтавка: {bet:.2f}\nШаг: 0\nГде спрятана смерть?"
    await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb_joker(0, bet))

@dp.callback_query(F.data.startswith("joker_click_"))
async def process_joker_click(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    joker_data = data.get("joker_data")
    if not joker_data or joker_data['state'] != 'playing':
        return
        
    is_death = random.random() <= 0.34
    
    if is_death:
        joker_data['state'] = 'lost'
        await call.message.edit_text(f"💀 Вы вытянули смерть! Проигрыш ставки {joker_data['bet']:.2f}.", reply_markup=kb_back())
        await state.set_state(None)
    else:
        joker_data['step'] += 1
        if joker_data['step'] >= len(JOKER_COEFFS) - 1:
            joker_data['step'] = len(JOKER_COEFFS) - 1
            
        coeff = JOKER_COEFFS[joker_data['step']]
        bank = joker_data['bet'] * coeff
        
        if joker_data['step'] == len(JOKER_COEFFS) - 1:
            await update_balance(call.from_user.id, bank)
            await call.message.edit_text(f"🏆 Максимальный выигрыш! Вы получили {bank:.2f}", reply_markup=kb_back())
            await state.set_state(None)
        else:
            await state.update_data(joker_data=joker_data)
            await call.message.edit_text(f"🃏 Джокер\nУспех! Карты перемешаны.\nТекущий кэф: {coeff:.2f}\nБанк: {bank:.2f}", reply_markup=kb_joker(joker_data['step'], bank))

@dp.callback_query(F.data == "joker_collect")
async def collect_joker(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    joker_data = data.get("joker_data")
    if not joker_data or joker_data['state'] != 'playing':
        return
    coeff = JOKER_COEFFS[joker_data['step']]
    bank = joker_data['bet'] * coeff
    await update_balance(call.from_user.id, bank)
    await call.message.edit_text(f"💸 Вы забрали {bank:.2f} монет!", reply_markup=kb_back())
    await state.set_state(None)

async def start_dice(chat_id, msg_id, bet):
    text = f"🎲 Кубики\nСтавка: {bet:.2f}\nВыберите исход броска:"
    await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb_dice_choice())

@dp.callback_query(F.data.startswith("dice_"))
async def process_dice(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("current_bet", 0)
    if bet <= 0:
        return
        
    await update_balance(call.from_user.id, -bet)
    choice = call.data.split("_")[1]
    
    await call.message.edit_text("🎲 Бросаем кубики...")
    
    dice_msg = await bot.send_dice(call.message.chat.id, emoji="🎲")
    await asyncio.sleep(4.0)
    
    result = dice_msg.dice.value
    await dice_msg.delete()
    
    is_even = result % 2 == 0
    win = False
    if (choice == "even" and is_even) or (choice == "odd" and not is_even):
        win = True
        
    choice_ru = "Четное" if choice == "even" else "Нечетное"
    text = f"🎲 Выпало: {result}\nВаш выбор: {choice_ru}\n\n"
    
    if win:
        prize = bet * 2
        await update_balance(call.from_user.id, prize)
        text += f"✅ Победа! Вы выиграли {prize:.2f} монет."
    else:
        text += f"❌ Проигрыш."
        
    await call.message.edit_text(text, reply_markup=kb_back())
    await state.set_state(None)

async def main():
    await init_db()
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🌐 Flask веб-сайт запущен на порту 8080")
    
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
