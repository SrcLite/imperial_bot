from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_approve_reject_company_keyboard(entity_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_company_{entity_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_company_{entity_id}")
    )
    return keyboard

def get_approve_reject_company_edit_keyboard(company_id, field, new_value, editor_id):
    """Inline клавиатура для модерации изменений компании"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve-company-edit-{company_id}-{field}-{new_value}-{editor_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject-company-edit-{company_id}-{field}-{new_value}-{editor_id}")
    )
    return keyboard

def get_id_request_approve_reject_company_edit_keyboard(request_id):
    """
    Inline клавиатура для модерации изменений компании по ID запроса
    """
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve-company-edit-req-{request_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject-company-edit-req-{request_id}")
    )
    return keyboard


def get_approve_reject_delete_company_photos_keyboard(company_id, user_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_delete_company_photos_{company_id}_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_delete_company_photos_{company_id}_{user_id}")
    )
    return keyboard

def get_approve_reject_delete_photos_keyboard(user_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_delete_photos_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_delete_photos_{user_id}")
    )
    return keyboard

def get_approve_reject_user_keyboard(entity_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_user_{entity_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_user_{entity_id}")
    )
    return keyboard

def get_approve_reject_delete_keyboard(entity_id, deleter_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_delete_{entity_id}_{deleter_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_delete_{entity_id}_{deleter_id}")
    )
    return keyboard

def get_cancel_moderation_keyboard(entity_id, entity_type):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_moderation_{entity_type}_{entity_id}")
    )
    return keyboard

def get_approve_reject_edit_keyboard(entity_id, new_value, field, editor_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve-edit-{entity_id}-{new_value}-{field}-{editor_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject-edit-{entity_id}-{new_value}-{field}-{editor_id}")
    )
    return keyboard


def get_user_management_keyboard(user_role):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    if user_role == 'logist':
        keyboard.add(KeyboardButton("🚛 Управление перевозчиками"))
    elif user_role == 'external_logist':
        keyboard.add(KeyboardButton("🚛 Управление перевозчиками"))
    elif user_role == 'external_admin':
        keyboard.add(KeyboardButton("📊 Управление логистами"))
        keyboard.add(KeyboardButton("🚛 Управление перевозчиками"))  # Только добавление
    else:  # admin
        keyboard.add(KeyboardButton("📊 Управление логистами"))
        keyboard.add(KeyboardButton("🚛 Управление перевозчиками"))
        keyboard.add(KeyboardButton("👥 Управление пользователями сторонних компаний"))

    keyboard.add(KeyboardButton("🕹 Главное меню"))
    return keyboard

def get_logist_management_keyboard():
    """Клавиатура для управления логистами"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("👤 Добавить логиста"),
        KeyboardButton("📋 Список логистов")
    )
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_email_keyboard():
    """Клавиатура для выбора email"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📧 logist@impe-rial.ru"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_executor_management_external():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(''))

def get_logist_confirmation_keyboard():
    """Клавиатура для подтверждения добавления логиста"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("✏️ Редактировать имя"), KeyboardButton("✏️ Редактировать телефон"))
    keyboard.row(KeyboardButton("✏️ Редактировать email"), KeyboardButton('✏️ Редактировать Telegram ID'))
    keyboard.add(KeyboardButton("✅ Подтвердить добавление"))
    return keyboard

def get_specific_logist_management_keyboard():
    """Клавиатура для управления конкретным логистом"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("✏️ Редактировать данные"))
    keyboard.add(KeyboardButton("🗑️ Удалить логиста"))
    keyboard.add(KeyboardButton("⬅️ Назад к списку"))
    return keyboard

def get_extended_editing_keyboard():
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

def get_extended_editing_external_user_keyboard():
    """Расширенная клавиатура для редактирования всех полей логиста"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👤 Редактировать имя"), KeyboardButton("👤 Редактировать фамилию"))
    keyboard.row(KeyboardButton("👤 Редактировать отчество"), KeyboardButton("💼 Редактировать должность"))
    keyboard.row(KeyboardButton("📞 Редактировать телефон"), KeyboardButton("📧 Редактировать email"))
    keyboard.row(KeyboardButton("🎂 Редактировать дату рождения"))
    keyboard.row(KeyboardButton("📘 Редактировать серию паспорта"), KeyboardButton("📘 Редактировать номер паспорта"))
    keyboard.row(KeyboardButton("📅 Редактировать дату выдачи паспорта"), KeyboardButton("🏢 Редактировать компанию"))
    keyboard.row(KeyboardButton("📍 Редактировать адрес регистрации"), KeyboardButton("🔢 Редактировать код АТИ"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_role_keyboard():
    """Клавиатура для выбора роли"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📊 Логист"))
    keyboard.add(KeyboardButton("🚛 Перевозчик"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_skip_back_keyboard():
    """Клавиатура с кнопками Пропустить и Назад"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("⏭️ Пропустить"), KeyboardButton("⬅️ Назад"))
    return keyboard

def get_confirmation_keyboard():
    """Клавиатура для подтверждения удаления"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(
        KeyboardButton("✅ Да, удалить"),
        KeyboardButton("❌ Нет, отменить")
    )
    return keyboard

def get_logist_editing_keyboard():
    """Клавиатура для выбора поля редактирования"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(
        KeyboardButton("👤 Редактировать имя"),
        KeyboardButton("💼 Редактировать должность")
    )
    keyboard.row(
        KeyboardButton("📞 Редактировать телефон"),
        KeyboardButton("📧 Редактировать email")
    )
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_back_keyboard():
    """Простая клавиатура с кнопкой Назад"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_executor_management_keyboard():
    """Клавиатура для управления перевозчиками"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("👤 Добавить перевозчика"),
                 KeyboardButton("📋 Список перевозчиков"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_external_user_management_keyboard():
    """Клавиатура для управления сторонними пользователями"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📋 Список пользователей"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_executor_company_selection_keyboard(companies):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)

    for company in companies:
        keyboard.add(KeyboardButton(f"🏢 {company['name']}"))

    keyboard.add(
        KeyboardButton("🔍Поиск по ИНН"),
        KeyboardButton("⬅️ Назад")
    )
    return keyboard

def get_executor_confirmation_keyboard(role):
    """Клавиатура для подтверждения данных перевозчика"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("✏️ Редактировать ФИО"), KeyboardButton("✏️ Редактировать контакты"))
    keyboard.row(KeyboardButton("✏️ Редактировать паспорт"), KeyboardButton("✏️ Редактировать код АТИ"))
    if role == "admin":
        keyboard.row(KeyboardButton('✏️ Редактировать компанию'))
    keyboard.row(KeyboardButton("✅ Подтвердить добавление"))
    return keyboard

def get_edit_executor_name_keyboard():
    """Клавиатура для редактирования ФИО перевозчика"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("👤 Редактировать имя"))
    keyboard.add(KeyboardButton("👤 Редактировать фамилию"))
    keyboard.add(KeyboardButton("👤 Редактировать отчество"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_edit_executor_contacts_keyboard():
    """Клавиатура для редактирования контактов перевозчика"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💼 Редактировать должность"))
    keyboard.add(KeyboardButton("📞 Редактировать телефон"))
    keyboard.add(KeyboardButton("📧 Редактировать email"))
    keyboard.add(KeyboardButton("🎂 Редактировать дату рождения"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_edit_executor_passport_keyboard():
    """Клавиатура для редактирования паспортных данных перевозчика"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📘 Редактировать серию паспорта"))
    keyboard.add(KeyboardButton("📘 Редактировать номер паспорта"))
    keyboard.add(KeyboardButton("📅 Редактировать дату выдачи"))
    keyboard.add(KeyboardButton("📍 Редактировать адрес регистрации"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_specific_executor_management_keyboard():
    """Клавиатура для управления конкретным перевозчиком"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("✏️ Редактировать данные"))
    keyboard.add(KeyboardButton("🗑️ Удалить перевозчика"))
    keyboard.add(KeyboardButton("⬅️ Назад к списку"))
    return keyboard
def get_specific_external_user_management_keyboard():
    """Клавиатура для управления конкретным перевозчиком"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("✏️ Редактировать данные"))
    keyboard.add(KeyboardButton("🗑️ Удалить пользователя"))
    keyboard.add(KeyboardButton("⬅️ Назад к списку"))
    return keyboard
def get_admin_company_selection_keyboard(companies):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)

    for company in companies:
        keyboard.add(KeyboardButton(f"🏢 {company['name']}"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_exteranl_confirmation_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)

    keyboard.add()

# def get_admin_settings_keyboard(role):
#     keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
#     if role == 'admin':
#         keyboard.row(KeyboardButton('🏢 Редактировать компании'))
#
