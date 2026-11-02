from telebot.types import ReplyKeyboardMarkup, KeyboardButton
def get_company_type_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("🏢 Юридическое лицо"),
        KeyboardButton("💼 Индивидуальный предприниматель"),
        KeyboardButton("👤 Самозанятый"),
        KeyboardButton("⬅️ Назад")
    )
    return keyboard

def get_skip_back_keyboard():
    """Клавивтура с кнопкой назад"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton('⬅️ Назад'),
        KeyboardButton('⏭️ Пропустить'),
    )
    return keyboard

def get_final_company_keyboard():
    """Клавиатура для завершения регистрации компании"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(
        KeyboardButton("✅ Завершить регистрацию компании"),
        KeyboardButton("✏️ Редактировать данные"),
        KeyboardButton("❌ Отмена")
    )
    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add('⬅️ Назад')
    return keyboard

def get_edit_company_keyboard(company_type=None):
    """Клавиатура для редактирования данных компании"""
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    # Основные данные
    buttons_row1 = [KeyboardButton("✏️ Редактировать название"), KeyboardButton("✏️ Редактировать ИНН")]
    keyboard.row(*buttons_row1)

    buttons_row2 = [KeyboardButton("✏️ Редактировать КПП"), KeyboardButton("✏️ Редактировать ФИО директора")]
    keyboard.row(*buttons_row2)

    # Кнопка ОГРН показывается только для юрлиц и ИП
    buttons_row3 = []
    if company_type in ['legal', 'individual']:
        buttons_row3.append(KeyboardButton("✏️ Редактировать ОГРН"))
    buttons_row3.append(KeyboardButton("✏️ Редактировать адрес"))
    keyboard.row(*buttons_row3)

    # Оставшиеся кнопки
    keyboard.row(KeyboardButton("✏️ Редактировать банковские реквизиты"), KeyboardButton("✏️ Редактировать контакты"))
    keyboard.row(KeyboardButton("📎 Редактировать документы"))

    # Подтверждение
    keyboard.row(KeyboardButton("✅ Подтвердить регистрацию"))

    return keyboard

def get_edit_contacts_keyboard():
    """Клавиатура для редактирования контактов"""
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    keyboard.row(KeyboardButton("📞 Редактировать телефон"), KeyboardButton("📧 Редактировать email"))
    keyboard.row(KeyboardButton("⬅️ Назад"))

    return keyboard

def get_edit_bank_keyboard():
    """Клавиатура для редактирования банковских реквизитов"""
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    keyboard.row(KeyboardButton("🏦 Редактировать БИК"), KeyboardButton("🏦 Редактировать расчетный счет"))
    keyboard.row(KeyboardButton("🏦 Редактировать корр. счет"), KeyboardButton("🏦 Редактировать ОКПО"))
    keyboard.row(KeyboardButton("⬅️ Назад"))

    return keyboard




