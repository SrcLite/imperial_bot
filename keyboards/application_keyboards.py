from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def get_management_application():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📥 Создать заявку"),
        KeyboardButton("📋 Активные заявки"),
        KeyboardButton("📊 Предложения по заявкам"),
        KeyboardButton("✅ Принятые заявки"),
        KeyboardButton("📋 Заявки на подтверждение"),
        KeyboardButton("🕹 Главное меню")
    )
    return keyboard


def get_application_type_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📦 СТАНДАРТНАЯ (с фиксированной ставкой)"),
        KeyboardButton("🏷️ ЗАПРОС СТАВОК (Аукцион)")
    )
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard


def get_route_management_keyboard(has_loading=False, has_unloading=False):
    """Возвращает клавиатуру для управления маршрутом с множественными точками"""
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)

    # Показываем кнопку завершения только если есть и погрузка и выгрузка
    if has_loading and has_unloading:
        keyboard.add(KeyboardButton("✅ Завершить маршрут"))

    keyboard.add(
        KeyboardButton("[➕] Добавить точку погрузки"),
        KeyboardButton("[➕] Добавить точку выгрузки")
    )

    # Показываем кнопку удаления только если есть точки
    if has_loading or has_unloading:
        keyboard.add(KeyboardButton("❌ Удалить точку"))

    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard


def get_cargo_type_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    keyboard.add(
        KeyboardButton("✅ Обычный"),
        KeyboardButton("🥪 Скоропортящийся"),
        KeyboardButton("⚠️ Опасный")
    )
    keyboard.add(
        KeyboardButton("🔔 Хрупкий"),
        KeyboardButton("📱 ТНП"),
        KeyboardButton("🔌 Бытовая техника")
    )
    keyboard.add(
        KeyboardButton("🧪 Бытовая химия"),
        KeyboardButton("📝 ПРОЧЕЕ")
    )
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard


def get_vehicle_type_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📦 Тент"),
        KeyboardButton("🧊 Рефрижератор"),
        KeyboardButton("🌡️ Изотермический"),
        KeyboardButton("🚚 Любой закрытый")
    )
    keyboard.add(
        KeyboardButton("🚛 Открытая платформа"),
        KeyboardButton("📄 Промтоварный")
    )
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard


def get_notes_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("⬅️ Назад"), KeyboardButton("⏭️ Пропустить"))
    return keyboard


def get_payment_terms_keyboard():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(
    KeyboardButton("⬅️ Назад"),
        KeyboardButton("⏭️ Пропустить")
    )
    return keyboard


def get_application_preview_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("🟦 ✅ СОЗДАТЬ ЗАЯВКУ"),
        KeyboardButton("⚪ ✏️ Редактировать")
    )
    keyboard.add(KeyboardButton("⚪ 🗑️ Отменить"))
    return keyboard


def get_edit_application_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("✏️ Тип заявки"),
        KeyboardButton("✏️ Маршрут"),
        KeyboardButton("✏️ Характер груза"),
        KeyboardButton("✏️ Вес и объем")
    )
    keyboard.add(
        KeyboardButton("✏️ Транспорт"),
        KeyboardButton("✏️ Оплата"),
        KeyboardButton("✏️ Примечания"),
        KeyboardButton("📋 Просмотр заявки")
    )
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard


def get_application_executor_keyboard(application_id):
    """Клавиатура для перевозчика при просмотре заявки"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 ОЗНАКОМИТЬСЯ", callback_data=f"view_application_{application_id}"),
        InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_application_{application_id}")
    )
    return keyboard


def get_application_response_keyboard(application_id):
    """Клавиатура для ответа на заявку (после ознакомления)"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💵 ОСТАВИТЬ СТАВКУ", callback_data=f"bid_application_{application_id}"),
        InlineKeyboardButton("✅ ПРИНЯТЬ ЗАЯВКУ", callback_data=f"accept_application_{application_id}"),
        InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_application_{application_id}")
    )
    return keyboard