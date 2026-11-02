from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.registration_user_keyboards import get_registration_agreement_keyboard

def get_main_menu(role):
    """ Главное меню в зависимости от роли"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if role == "admin":
        buttons = [
            KeyboardButton('📋 Управление заявками'),
            KeyboardButton("👥 Управление пользователями"),
            KeyboardButton("📊 Статистика"),
            KeyboardButton("⚙️ Настройки"),
            KeyboardButton("💵 Управление подпиской")
        ]
    elif role == "logist" or role == "external_logist":
        buttons = [
            KeyboardButton("📥 Создать заявку"),
            KeyboardButton("📋 Активные заявки"),
            KeyboardButton("📊 Предложения по заявкам"),
            KeyboardButton("✅ Принятые заявки"),
            KeyboardButton("📋 Заявки на подтверждение"),
            KeyboardButton("👥 Управление пользователями"),
            KeyboardButton("📊 Статистика"),
            KeyboardButton("⚙️ Настройки"),
        ]
    elif role == 'executor' or role == 'external_executor':
        buttons = [
            KeyboardButton("🔔 Новые заявки"),
            KeyboardButton("🚨 Срочные заявки"),
            KeyboardButton("✅ Мои принятые заявки"),
            KeyboardButton("🔍 Фильтры заявок"),
            KeyboardButton("📊 Статистика"),
            KeyboardButton("⚙️ Настройки")
        ]
    elif role == "external_admin":
        buttons = [
            KeyboardButton("📥 Создать заявку"),
            KeyboardButton("📋 Активные заявки"),
            KeyboardButton("📊 Предложения по заявкам"),
            KeyboardButton("👥 Управление пользователями"),
            KeyboardButton("📊 Статистика"),
            KeyboardButton("⚙️ Настройки")
        ]
    else:
        return get_registration_agreement_keyboard()
    if role in ['external_admin', 'external_logist', 'external_executor']:
        buttons += [
            (KeyboardButton("💳 Моя подписка")),
            (KeyboardButton("💵Прайс-лист"))
             ]
    keyboard.add(*buttons)
    return keyboard

def get_start_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(
        KeyboardButton("🤖 Посмотреть, как работает бот"),
        KeyboardButton("🖊 Начать регистрацию")
    )
    return keyboard

def get_back_menu():
    back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
    back_kb.add(KeyboardButton("🖊 Начать регистрацию"))
    return back_kb

def get_subscription_keyboard():
    """Клавиатура для управления подпиской"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💳 Оплатить подписку"))
    keyboard.add(KeyboardButton("📋 Информация о подписке"))
    keyboard.add(KeyboardButton("📞 Связаться с поддержкой"))
    keyboard.add(KeyboardButton("⬅️ На главную"))

    return keyboard