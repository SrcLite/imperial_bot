from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_rate_keyboard():
    """Клавиатура для управления тарифами"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton('📋 Просмотреть тарифы'),
        KeyboardButton('✏️ Изменить тарифы'),
        KeyboardButton('🕹 Главное меню')
    )
    return keyboard

def get_edit_rate_keyboard():
    """Инлайн-клавиатура для выбора тарифа для редактирования"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton('💰 С НДС 22%', callback_data='edit_rate_vat'),
        InlineKeyboardButton('💰 Без НДС', callback_data='edit_rate_no_vat'),
        InlineKeyboardButton('💰 Оплата на карту', callback_data='edit_rate_card'),
        InlineKeyboardButton('🌟 Льготный период', callback_data='edit_rate_trial'),
        InlineKeyboardButton('❌ Отмена', callback_data='cancel_edit_rate')
    )
    return keyboard
