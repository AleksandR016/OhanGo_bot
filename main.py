from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import asyncio
import aiosqlite
import datetime
import re
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
DB_NAME = "delivery_bot.db"
PHONE_REGEX = r'^(\+?\d{1,3}?[- .]?)?(\(?\d{3}\)?[- .]?)?\d{3}[- .]?\d{4}$'


class OrderStates(StatesGroup):
    name = State()
    phone = State()
    service_type = State()
    from_location = State()
    to_location = State()
    item_description = State()
    contact_phone = State()
    confirm = State()


bot = Bot(token="7530190553:AAHP8VlgrlYOIaRfGxGhU3aL6ekuY56YSgI")
dp = Dispatcher(storage=MemoryStorage())


# Инициализация БД
async def init_db():
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                registration_date TEXT DEFAULT CURRENT_TIMESTAMP
            )''')

            await db.execute('''CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                from_location TEXT,
                to_location TEXT,
                item_description TEXT,
                contact_phone TEXT NOT NULL,
                order_date TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'new',
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            await db.commit()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")


async def add_user(user_id: int, name: str, phone: str):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, name, phone)
                VALUES (?, ?, ?)
            ''', (user_id, name, phone))
            await db.commit()
    except Exception as e:
        logger.error(f"Error adding user: {e}")


async def add_order(user_data: dict):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''
                INSERT INTO orders (
                    user_id, service_type, from_location, 
                    to_location, item_description, contact_phone
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_data['user_id'],
                user_data['service_type'],
                user_data.get('from_location'),
                user_data.get('to_location'),
                user_data.get('item_description'),
                user_data['contact_phone']
            ))
            await db.commit()
    except Exception as e:
        logger.error(f"Error adding order: {e}")


async def get_user_orders(user_id: int):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute('''
                SELECT order_id, service_type, order_date, status 
                FROM orders WHERE user_id = ? ORDER BY order_date DESC
            ''', (user_id,))
            return await cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        return []


# Клавиатуры
def make_service_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🍔 Доставка еды")
    builder.button(text="📦 Доставка вещей")
    builder.button(text="🚗 Курьерская служба")
    builder.button(text="❌ Отменить заказ")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def make_yes_no_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Подтвердить")
    builder.button(text="❌ Отменить")
    return builder.as_markup(resize_keyboard=True)


def make_cancel_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ Отменить заказ")]],
        resize_keyboard=True
    )


def make_contact_request_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def make_location_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="📍 Отправить местоположение", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


# Валидация данных
def is_valid_phone(phone: str) -> bool:
    return re.match(PHONE_REGEX, phone) is not None


def is_valid_name(name: str) -> bool:
    return 2 <= len(name) <= 50 and all(c.isalpha() or c.isspace() for c in name)


def is_valid_location(location: str) -> bool:
    return len(location) >= 5


# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        "👋 Добро пожаловать в сервис доставки OhanGo!\n"
        "Для оформления заказа нам потребуется некоторая информация.\n"
        "Пожалуйста, введите ваше имя:",
        reply_markup=make_cancel_keyboard()
    )
    await state.set_state(OrderStates.name)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📌 <b>Доступные команды:</b>\n"
        "/start - начать новый заказ\n"
        "/help - показать справку\n"
        "/myorders - показать мои заказы\n\n"
        "Вы можете отменить заказ в любой момент, нажав соответствующую кнопку."
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(Command("myorders"))
async def cmd_my_orders(message: Message):
    orders = await get_user_orders(message.from_user.id)
    if not orders:
        await message.answer("У вас пока нет заказов.")
        return

    orders_text = ["📋 <b>Ваши последние заказы:</b>"]
    for order in orders[:5]:  # Показываем только 5 последних заказов
        order_date = datetime.datetime.strptime(order[2], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
        orders_text.append(
            f"🔹 #{order[0]} {order[1]} - {order_date} ({order[3]})"
        )

    await message.answer("\n".join(orders_text), parse_mode="HTML")


# Обработчики состояний
@dp.message(OrderStates.name)
async def process_name(message: Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        return

    if not is_valid_name(message.text):
        await message.answer("Пожалуйста, введите корректное имя (только буквы и пробелы, 2-50 символов).")
        return

    await state.update_data(name=message.text)
    await message.answer(
        "Теперь введите ваш номер телефона или нажмите кнопку ниже:",
        reply_markup=make_contact_request_keyboard()
    )
    await state.set_state(OrderStates.phone)


@dp.message(OrderStates.phone)
async def process_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        return

    phone = message.contact.phone_number if message.contact else message.text

    if not is_valid_phone(phone):
        await message.answer("Пожалуйста, введите корректный номер телефона.")
        return

    await state.update_data(phone=phone)
    await message.answer(
        "Выберите тип услуги:",
        reply_markup=make_service_keyboard()
    )
    await state.set_state(OrderStates.service_type)


@dp.message(OrderStates.service_type)
async def process_service_type(message: Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        return

    service_types = ["🍔 Доставка еды", "📦 Доставка вещей", "🚗 Курьерская служба"]
    if message.text not in service_types:
        await message.answer("Пожалуйста, выберите тип услуги из предложенных вариантов.")
        return

    await state.update_data(service_type=message.text)

    if message.text == "🚗 Курьерская служба":
        await message.answer(
            "Пожалуйста, опишите, что нужно сделать курьеру:",
            reply_markup=make_cancel_keyboard()
        )
        await state.set_state(OrderStates.item_description)
    else:
        await message.answer(
            "Откуда нужно забрать? (укажите адрес или нажмите кнопку для отправки местоположения):",
            reply_markup=make_location_keyboard()
        )
        await state.set_state(OrderStates.from_location)


@dp.message(OrderStates.from_location)
async def process_from_location(message: Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        return

    location = None
    if message.location:
        location = f"GPS: {message.location.latitude}, {message.location.longitude}"
    else:
        location = message.text

    if not is_valid_location(location):
        await message.answer("Пожалуйста, укажите более точное местоположение (минимум 5 символов).")
        return

    await state.update_data(from_location=location)
    await message.answer(
        "Куда нужно доставить? (укажите адрес или нажмите кнопку для отправки местоположения):",
        reply_markup=make_location_keyboard()
    )
    await state.set_state(OrderStates.to_location)


@dp.message(OrderStates.to_location)
async def process_to_location(message: Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        return

    location = None
    if message.location:
        location = f"GPS: {message.location.latitude}, {message.location.longitude}"
    else:
        location = message.text

    if not is_valid_location(location):
        await message.answer("Пожалуйста, укажите более точное местоположение (минимум 5 символов).")
        return

    await state.update_data(to_location=location)
    await message.answer(
        "Опишите, что нужно доставить (например, '2 пиццы и напитки'):",
        reply_markup=make_cancel_keyboard()
    )
    await state.set_state(OrderStates.item_description)


@dp.message(OrderStates.item_description)
async def process_item_description(message: Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        return

    if len(message.text) < 3:
        await message.answer("Пожалуйста, укажите более подробное описание.")
        return

    await state.update_data(item_description=message.text)
    await message.answer(
        "Введите номер телефона для связи (можно тот же):",
        reply_markup=make_contact_request_keyboard()
    )
    await state.set_state(OrderStates.contact_phone)


@dp.message(OrderStates.contact_phone)
async def process_contact_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        return

    phone = None
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text

    if not is_valid_phone(phone):
        await message.answer("Пожалуйста, введите корректный номер телефона.")
        return

    await state.update_data(contact_phone=phone)

    # Получаем все данные
    data = await state.get_data()

    # Формируем текст заказа
    order_text = (
        "📝 <b>Проверьте данные заказа:</b>\n\n"
        f"👤 <b>Имя:</b> {data['name']}\n"
        f"📱 <b>Телефон:</b> {data['phone']}\n"
        f"🔧 <b>Услуга:</b> {data['service_type']}\n"
    )

    if 'from_location' in data:
        order_text += f"📍 <b>Откуда:</b> {data['from_location']}\n"
    if 'to_location' in data:
        order_text += f"🏁 <b>Куда:</b> {data['to_location']}\n"
    if 'item_description' in data:
        order_text += f"📦 <b>Описание:</b> {data['item_description']}\n"

    order_text += f"📞 <b>Контактный телефон:</b> {phone}\n\n"
    order_text += "Все верно?"

    await message.answer(
        order_text,
        parse_mode="HTML",
        reply_markup=make_yes_no_keyboard()
    )
    await state.set_state(OrderStates.confirm)


@dp.message(OrderStates.confirm)
async def process_confirmation(message: Message, state: FSMContext):
    if message.text not in ["✅ Подтвердить", "❌ Отменить"]:
        await message.answer("Пожалуйста, выберите один из предложенных вариантов.")
        return

    if message.text == "❌ Отменить":
        await state.clear()
        await message.answer(
            "Заказ отменен. Вы можете начать заново с команды /start",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Подтверждение заказа
    data = await state.get_data()
    data['user_id'] = message.from_user.id

    # Сохраняем пользователя и заказ
    await add_user(user_id=data['user_id'], name=data['name'], phone=data['phone'])
    await add_order(data)

    # Отправляем подтверждение
    await message.answer(
        "✅ <b>Ваш заказ принят!</b>\n\n"
        "Мы свяжемся с вами в ближайшее время.\n"
        "Вы можете посмотреть свои заказы с помощью команды /myorders",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

    # Очищаем состояние
    await state.clear()


# Обработка отмены из любого состояния
@dp.message(StateFilter(OrderStates), lambda message: message.text == "❌ Отменить заказ")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Заказ отменен. Вы можете начать новый заказ с команды /start",
        reply_markup=ReplyKeyboardRemove()
    )


# Запуск бота
async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())