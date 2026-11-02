from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telebot import types



def get_select_role_keyboard():
    """Клавиатура для выбора роли при первом запуске"""
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True,
        row_width=2
    )
    button_transporter = KeyboardButton('🚛 Я ПЕРЕВОЗЧИК')
    button_cargo_owner = KeyboardButton('📦 Я ГРУЗОВЛАДЕЛЕЦ')
    button_1 = KeyboardButton('👑 Я АДМИНИСТРАТОР')
    keyboard.add(button_transporter, button_cargo_owner, button_1)
    return keyboard

def get_terms_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    button_read = InlineKeyboardButton("📖 Ознакомиться", callback_data="read_terms")
    keyboard.add(button_read)
    return keyboard


def get_registration_agreement_keyboard():
    """ Клавиатура для согласия с условиями платформы"""
    keyboard = InlineKeyboardMarkup(row_width=1)

    button_agree = InlineKeyboardButton("✅ Принять условия", callback_data="agree_terms")
    button_reject = InlineKeyboardButton('❌ ОТКЛОНИТЬ', callback_data="reject_terms")

    keyboard.add(button_agree, button_reject)

    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(
        KeyboardButton("⬅️ Назад")
    )

def get_document_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.row(KeyboardButton("📷 Сделать фото"))
    keyboard.row( KeyboardButton("📁 Выбрать из галереи"))
    keyboard.row( KeyboardButton("⬅️ Назад"), KeyboardButton("⏭️ Пропустить"))
    return keyboard


def get_photo_source_keyboard():
    """Клавиатура для выбора источника фото"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(
        KeyboardButton("📷 Сделать фото"),
        KeyboardButton("📁 Выбрать из галереи"),
        KeyboardButton("⬅️ Назад")
    )
    return keyboard

def get_final_registration_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(
        KeyboardButton("✅ Отправить на подтверждение"),
        KeyboardButton("✏️ Редактировать данные"),
        KeyboardButton("❌ Отмена")
    )
    return keyboard

def get_company_selection_keyboard(companies):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)

    for company in companies:
        keyboard.add(KeyboardButton(f"🏢 {company['name']}"))

    keyboard.add(
        KeyboardButton("🔍Поиск по ИНН"),
        KeyboardButton("🟢 Зарегистрировать новую компанию"),
        KeyboardButton("⬅️ Назад к выбору роли")
    )
    return keyboard

def get_founded_company_selection_keyboard(company):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    keyboard.add(KeyboardButton(f"🏢 {company['name']}"))
    keyboard.add(
        KeyboardButton("🔍Поиск по ИНН"),
        KeyboardButton("🟢 Зарегистрировать новую компанию"),
        KeyboardButton("⬅️ Назад к выбору роли")
    )
    return keyboard

def get_reg_company_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    keyboard.add(KeyboardButton("🟢 Зарегистрировать новую компанию"))

    return keyboard

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены для форм"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("❌ Отмена"))
    return keyboard

def get_skip_back_keyboard():
    """Клавивтура с кнопкой назад"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton('⬅️ Назад'),
        KeyboardButton('⏭️ Пропустить')
    )
    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton('⬅️ Назад')
    )
    return keyboard

def get_edit_passport_keyboard():
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("📘 Редактировать серию паспорта"), KeyboardButton("📘 Редактировать номер паспорта"))
    keyboard.row(KeyboardButton("📅 Редактировать дату выдачи"), KeyboardButton('📍 Редактировать адрес регистрации'))
    keyboard.row(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_edit_contacts_keyboard():
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("📞 Редактировать телефон"), KeyboardButton("📧 Редактировать email"))
    keyboard.row(KeyboardButton("🎂 Редактировать дату рождения"))
    keyboard.row(KeyboardButton("⬅️ Назад"))
    return keyboard

def get_edit_name_keyboard():
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👤 Редактировать имя"), KeyboardButton("👤 Редактировать фамилию"))
    keyboard.row(KeyboardButton("👤 Редактировать отчество"))
    keyboard.row(KeyboardButton("⬅️ Назад"))
    return keyboard

