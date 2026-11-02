from telebot.types import ReplyKeyboardMarkup, KeyboardButton


def get_setting_keyboard(role):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if role == 'admin':
        keyboard.add(KeyboardButton('🏢 Управление компаниями'),
                    KeyboardButton('⭐ Настройка рейтинга'), KeyboardButton('📋 Модерация заявок'),
                    KeyboardButton('📈 Настройка аномалий'), KeyboardButton('📤 Экспорт в Google Таблицы'))
    elif role == 'external_admin':
        keyboard.add(KeyboardButton('🏢 Управление компаниями'))
    keyboard.add(KeyboardButton('👤 Мой профиль'))
    keyboard.add(KeyboardButton('🏆 Рейтинг'))
    keyboard.add(KeyboardButton('🕹 Главное меню'))
    return keyboard

def get_settings_company_keyboard(role):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton('🏢 Моя компания'))
    if role == 'admin':
        keyboard.add(KeyboardButton('📋 Список компаний'))
    keyboard.add(KeyboardButton('⬅️ Назад'))
    return keyboard

def get_edit_company_photo_keyboard():
    """Клавиатура для редактирования фотографий"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    # keyboard.row(KeyboardButton("📷 Показать мои фото"))
    keyboard.row(KeyboardButton("🔄 Добавить фотографии"))
    keyboard.row(KeyboardButton("📁 Удалить все фото"))
    keyboard.row(KeyboardButton("⬅️ Назад"))

    return keyboard

def get_settings_company_selection_keyboard(companies):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)

    for company in companies:
        keyboard.add(KeyboardButton(f"🏢 {company['name']}"))

    keyboard.add(
        KeyboardButton("🔍Поиск по ИНН"),
        KeyboardButton("⬅️ Назад ")
    )
    return keyboard

# def get_settings_moderation_keyboard():
#     keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
#     keyboard.add(KeyboardButton('👤 Активные заявки пользователей'), KeyboardButton('🏢 Активные заявки компаний'),
#                  KeyboardButton('⬅️ Назад'))
#     return keyboard


def get_company_edit_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    buttons = [
        "🏢 Название компании",
        "📋 Тип компании",
        "🔢 ИНН",
        "🔢 КПП",
        "🔢 ОГРН",
        "👤 ФИО директора",
        "📍 Юридический адрес",
        "📞 Контактный телефон",
        "📧 Контактный email",
        "📝 Примечание",
        "💰 БИК",
        "💰 Расчетный счёт",
        "💰 Корреспондентский счёт",
        "💰 ОКПО",
        "📷 Показать фото",
        "⬅️ Назад"

    ]

    # Добавляем кнопки в клавиатуру
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.row(KeyboardButton(buttons[i]), KeyboardButton(buttons[i + 1]))
        else:
            keyboard.add(KeyboardButton(buttons[i]))

    return keyboard

def get_company_type_keyboard():
    """Клавиатура для выбора типа компании"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "🏛️ Юридическое лицо",
        "👤 ИП",
        "💼 Самозанятый",
        "⬅️ Назад к редактированию"
    ]
    for button in buttons:
        keyboard.add(KeyboardButton(button))
    return keyboard

def get_tax_system_keyboard():
    """Клавиатура для выбора системы налогообложения"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📊 ОСНО",
        "📊 УСН",
        "📊 ЕСХН",
        "📊 ПСН",
        "📊 НПД",
        "📊 АУСН",
        "⬅️ Назад к редактированию"
    ]
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.row(KeyboardButton(buttons[i]), KeyboardButton(buttons[i + 1]))
        else:
            keyboard.add(KeyboardButton(buttons[i]))
    return keyboard

def get_company_confirmation_keyboard():
    """Клавиатура для подтверждения действий с компанией"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "✅ Подтвердить",
        "❌ Отменить",
        "⬅️ Назад к редактированию"
    ]
    for button in buttons:
        keyboard.add(KeyboardButton(button))
    return keyboard
