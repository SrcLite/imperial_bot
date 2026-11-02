from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def get_edit_data_keyboard():
    """Расширенная клавиатура для редактирования всех полей логиста"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👤 Редактировать имя"), KeyboardButton("👤 Редактировать фамилию"))
    keyboard.row(KeyboardButton("👤 Редактировать отчество"), KeyboardButton("💼 Редактировать должность"))
    keyboard.row(KeyboardButton("📞 Редактировать телефон"), KeyboardButton("📧 Редактировать email"))
    keyboard.row(KeyboardButton("🎂 Редактировать дату рождения"))
    keyboard.row(KeyboardButton("📘 Редактировать серию паспорта"), KeyboardButton("📘 Редактировать номер паспорта"))
    keyboard.row(KeyboardButton("📅 Редактировать дату выдачи паспорта"))
    keyboard.row(KeyboardButton("📍 Редактировать адрес регистрации"), KeyboardButton("🔢 Редактировать код АТИ"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard


def get_edit_photo_keyboard():
    """Клавиатура для редактирования фотографий"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("🔄 Добавить фотографии"))
    keyboard.row(KeyboardButton("📁 Удалить все фото"))
    keyboard.row(KeyboardButton("⬅️ Назад в профиль"))

    return keyboard


def get_profile_editing_keyboard():
    """Клавиатура для редактирования профиля"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    keyboard.row(KeyboardButton("✏️ Редактировать данные"))
    # keyboard.row(KeyboardButton("📷 Показать мои фото"))
    keyboard.row(KeyboardButton("🕹 Главное меню"))

    return keyboard
