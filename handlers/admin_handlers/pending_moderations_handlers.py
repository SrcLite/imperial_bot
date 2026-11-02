from datetime import datetime
from keyboards.admin_keyboards import (
    get_approve_reject_user_keyboard,
    get_approve_reject_company_keyboard,
    get_approve_reject_edit_keyboard,
    get_approve_reject_delete_keyboard,
    get_approve_reject_delete_photos_keyboard,
    get_approve_reject_company_edit_keyboard,
    get_approve_reject_delete_company_photos_keyboard
)

# Глобальный словарь для хранения активных заявок
pending_moderations = {}

role_names = {
    'admin': '👑 Администратор',
    'logist': '📊 Логист',
    'executor': '🚛 Перевозчик',
    'external_admin': '👑 Администратор',
    'external_logist': '📊 Логист',
    'external_executor': '🚛 Перевозчик'
}

field_names = {
    'first_name': 'Имя',
    'last_name': 'Фамилия',
    'patronymic': 'Отчество',
    'position': 'Должность',
    'phone': 'Телефон',
    'email': 'Email',
    'birth_date': 'Дата рождения',
    'passport_series': 'Серия паспорта',
    'passport_number': 'Номер паспорта',
    'passport_issue_date': 'Дата выдачи паспорта',
    'registration_address': 'Адрес регистрации',
    'ati_code': 'Код АТИ',
    'role': 'Роль'
}

company_field_names = {
    'name': 'Название компании',
    'company_type': 'Тип компании',
    'inn': 'ИНН',
    'kpp': 'КПП',
    'ogrn': 'ОГРН',
    'director_first_name': 'Имя директора',
    'director_last_name': 'Фамилия директора',
    'legal_address': 'Юридический адрес',
    'contact_phone': 'Контактный телефон',
    'contact_email': 'Контактный email',
    'tax_system': 'Система налогообложения',
    'note': 'Примечание',
    'bik': 'БИК',
    'payment_account': 'Расчетный счет',
    'correspondent_account': 'Корреспондентский счет',
    'okpo': 'ОКПО'
}

tax_to_text_map = {
    'osn': '📊 ОСНО',
    'usn': '📊 УСН',
    'eshn': '📊 ЕСХН',
    'psn': '📊 ПСН',
    'npd': '📊 НПД',
    'ausn': '📊 АУСН'
}

type_to_text_map = {
    'legal': '🏛️ Юридическое лицо',
    'individual': '👤 ИП',
    'self_employed': '💼 Самозанятый'
}


def add_pending_moderation(moderation_type, entity_id, data=None):
    """Добавляет заявку в список ожидающих модерации"""
    key = f"{moderation_type}_{entity_id}"
    pending_moderations[key] = {
        'type': moderation_type,
        'entity_id': entity_id,
        'data': data,
        'created_at': datetime.now()
    }


def remove_pending_moderation(moderation_type, entity_id):
    """Удаляет заявку из списка ожидающих модерации"""
    key = f"{moderation_type}_{entity_id}"
    if key in pending_moderations:
        del pending_moderations[key]


def get_all_pending_moderations():
    """Возвращает все активные заявки"""
    return pending_moderations


def send_pending_moderations(bot, db, chat_id):
    """Отправляет все активные заявки администратору"""
    pending = get_all_pending_moderations()

    if not pending:
        bot.send_message(chat_id, "✅ На данный момент активных заявок нет.")
        return

    bot.send_message(chat_id, f"📋 Активные заявки на модерацию ({len(pending)}):")

    for key, moderation in pending.items():
        moderation_type = moderation['type']
        entity_id = moderation['entity_id']
        data = moderation['data']

        try:
            if moderation_type == 'user_registration':
                send_user_registration_moderation(bot, db, chat_id, entity_id)
            elif moderation_type == 'company_registration':
                send_company_registration_moderation(bot, db, chat_id, entity_id)
            elif moderation_type == 'user_edit':
                send_user_edit_moderation(bot, db, chat_id, entity_id, data)
            elif moderation_type == 'company_edit':
                send_company_edit_moderation(bot, db, chat_id, entity_id, data)
            elif moderation_type == 'user_delete':
                send_user_delete_moderation(bot, db, chat_id, entity_id, data)
            elif moderation_type == 'user_photos_delete':
                send_user_photos_delete_moderation(bot, db, chat_id, entity_id)
            elif moderation_type == 'company_photos_delete':
                send_company_photos_delete_moderation(bot, db, chat_id, entity_id, data)
        except Exception as e:
            print(f"Ошибка при отправке заявки {key}: {e}")
            bot.send_message(chat_id, f"❌ Ошибка при загрузке заявки {key}")


def send_user_registration_moderation(bot, db, chat_id, user_id):
    """Отправляет заявку на регистрацию пользователя"""
    user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    if not user:
        bot.send_message(chat_id, "❌ Пользователь не найден")
        return

    company = db.fetch_one("SELECT name FROM companies WHERE id = ?", (user['company_id'],))
    company_name = company['name'] if company else "Не указана"

    message_text = format_user_moderation_message(user, company_name)
    bot.send_message(chat_id, message_text,
                     reply_markup=get_approve_reject_user_keyboard(user_id))


def send_company_registration_moderation(bot, db, chat_id, company_id):
    """Отправляет заявку на регистрацию компании"""
    company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
    if not company:
        bot.send_message(chat_id, "❌ Компания не найдена")
        return

    message_text = format_company_moderation_message(company)
    bot.send_message(chat_id, message_text,
                     reply_markup=get_approve_reject_company_keyboard(company_id))


def send_user_edit_moderation(bot, db, chat_id, user_id, data):
    """Отправляет заявку на редактирование пользователя"""
    user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    if not user:
        bot.send_message(chat_id, "❌ Пользователь не найден")
        return

    field = data.get('field')
    new_value = data.get('new_value')
    editor_id = data.get('editor_id')

    old_value = user.get(field, 'Не указано')

    # Форматируем значения для отображения
    if field == 'role':
        old_value_display = role_names.get(old_value, old_value)
        new_value_display = role_names.get(new_value, new_value)
        parameter = field_names.get(field, field)
    else:
        old_value_display = old_value
        new_value_display = new_value
        parameter = field_names.get(field, field)

    message_text = f"""
📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ ДАННЫХ**

👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
🆔 **Telegram ID:** {user_id}
🏢 **Роль:** {role_names.get(user['role'], user['role'])}

📋 **Изменяемое поле:** {parameter}
📄 **Старое значение:** {old_value_display}
🔄 **Новое значение:** {new_value_display}

⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

Для подтверждения или отклонения изменения используйте панель администратора.
"""

    bot.send_message(chat_id, message_text,
                     reply_markup=get_approve_reject_edit_keyboard(user_id, new_value, field, editor_id))


def send_company_edit_moderation(bot, db, chat_id, company_id, data):
    """Отправляет заявку на редактирование компании"""
    company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
    if not company:
        bot.send_message(chat_id, "❌ Компания не найдена")
        return

    field = data.get('field')
    new_value = data.get('new_value')
    editor_id = data.get('editor_id')

    # Получаем старое значение
    if field in ['bik', 'payment_account', 'correspondent_account', 'okpo']:
        bank_details = db.fetch_one("SELECT * FROM company_bank_details WHERE company_id = ?", (company_id,))
        old_value = bank_details.get(field, 'Не указано') if bank_details else 'Не указано'
    else:
        old_value = company.get(field, 'Не указано')

    # Форматируем значения для отображения
    if field == 'company_type':
        old_value_display = type_to_text_map.get(old_value, old_value)
        new_value_display = type_to_text_map.get(new_value, new_value)
        parameter = company_field_names.get(field, field)
    elif field == 'tax_system':
        old_value_display = tax_to_text_map.get(old_value, old_value)
        new_value_display = tax_to_text_map.get(new_value, new_value)
        parameter = company_field_names.get(field, field)
    else:
        old_value_display = old_value
        new_value_display = new_value
        parameter = company_field_names.get(field, field)

    # Получаем информацию о редакторе
    editor = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (editor_id,))
    editor_name = f"{editor.get('first_name', '')} {editor.get('last_name', '')}" if editor else "Неизвестно"

    message_text = f"""
📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ ДАННЫХ КОМПАНИИ**

🏢 **Компания:** {company['name']}
👤 **Запросил:** {editor_name}
🆔 **Telegram ID редактора:** {editor_id}

📋 **Изменяемое поле:** {parameter}
📄 **Старое значение:** {old_value_display}
🔄 **Новое значение:** {new_value_display}

⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

Для подтверждения или отклонения изменения используйте кнопки ниже.
"""

    bot.send_message(chat_id, message_text,
                     reply_markup=get_approve_reject_company_edit_keyboard(company_id, new_value, field, editor_id))


def send_user_delete_moderation(bot, db, chat_id, user_id, data):
    """Отправляет заявку на удаление пользователя"""
    user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    if not user:
        bot.send_message(chat_id, "❌ Пользователь не найден")
        return

    # Получаем информацию о том, кто запросил удаление
    requester_info = db.fetch_one(
        "SELECT u.username FROM users u WHERE u.telegram_id = ?",
        (user.get('deletion_requested_by', data),)
    )
    username = requester_info['username'] if requester_info else "неизвестно"

    message_text = (
        f"❗️ Запрос на удаление пользователя {user['first_name']}, Telegram ID:{user['telegram_id']}!!!\n"
        f"Username: @{user.get('username', 'N/A')}, 💼 Должность: {role_names.get(user['role'], user['role'])}\n\n"
        f"Запросил @{username}"
    )

    bot.send_message(chat_id, message_text,
                     reply_markup=get_approve_reject_delete_keyboard(user_id, data))


def send_user_photos_delete_moderation(bot, db, chat_id, user_id):
    """Отправляет заявку на удаление фотографий пользователя"""
    user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    if not user:
        bot.send_message(chat_id, "❌ Пользователь не найден")
        return

    message_text = f"""
📝 **ЗАЯВКА НА УДАЛЕНИЕ ФОТОГРАФИЙ**

👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
🆔 **Telegram ID:** {user_id}
🏢 **Роль:** {role_names.get(user['role'], user['role'])}

❗️ **Запросил удаление всех своих фотографий.**

⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

Для подтверждения или отклонения используйте кнопки ниже.
"""

    bot.send_message(chat_id, message_text,
                     reply_markup=get_approve_reject_delete_photos_keyboard(user_id))


def send_company_photos_delete_moderation(bot, db, chat_id, user_id, data):
    """Отправляет заявку на удаление фотографий компании"""
    company_id = data.get('company_id')
    company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
    user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))

    if not company or not user:
        bot.send_message(chat_id, "❌ Компания или пользователь не найден")
        return

    message_text = f"""
📝 **ЗАЯВКА НА УДАЛЕНИЕ ФОТОГРАФИЙ**

👤 **Компания:** {company.get('name', '')}
🆔 **ИНН:** {company.get('inn', '')}
🏢 **Директор:** {company.get('director_first_name', '')} {company.get('director_last_name', '')}

❗️ **Запросил удаление всех фотографий компании: {user.get('username', '')}**

⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

Для подтверждения или отклонения используйте кнопки ниже.
"""

    bot.send_message(chat_id, message_text,
                     reply_markup=get_approve_reject_delete_company_photos_keyboard(company_id, user_id))


def format_user_moderation_message(user, company_name):
    """Форматирует сообщение для модерации пользователя"""
    role_descriptions = {
        "logist": "👨‍💼 Логист",
        "external_logist": "👔 Внешний логист",
        "executor": "🚛 Перевозчик",
        "admin": "👑 Администратор"
    }

    return f"""
🆕 **НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ ПОЛЬЗОВАТЕЛЯ**

👤 **Данные пользователя:**
• **ФИО:** {user['last_name']} {user['first_name']} {user.get('patronymic', '')}
• **Телеграм:** @{user.get('username', 'Не указан')}
• **Телефон:** {user.get('phone', 'Не указан')}
• **Email:** {user.get('email', 'Не указан')}
• **Дата рождения:** {user.get('birth_date', 'Не указана')}

📘 **Паспортные данные:**
• **Серия/Номер:** {user.get('passport_series', 'Не указана')} {user.get('passport_number', 'Не указан')}
• **Дата выдачи:** {user.get('passport_issue_date', 'Не указана')}

🔢 **Код АТИ:** {user.get('ati_code', 'Не указан')}

🏢 **Компания:** {company_name}
👔 **Роль:** {role_descriptions.get(user.get('role'), user.get('role', 'Не указана'))}

⏰ **Дата подачи заявки:** {user.get('created_at', 'Не указана')}

Выберите действие:
"""


def format_company_moderation_message(company):
    """Форматирует сообщение для модерации компании"""
    company_type_map = {
        'legal': 'Юридическое лицо',
        'individual': 'Индивидуальный предприниматель',
        'self_employed': 'Самозанятый'
    }

    tax_system_map = {
        'osn': 'ОСНО',
        'usn': 'УСН',
        'eshn': 'ЕСХН',
        'psn': 'ПСН',
        'npd': 'НПД',
        'ausn': 'АУСН'
    }

    return f"""
🆕 **НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ КОМПАНИИ**

🏢 **Данные компании:**
• Название: {company['name']}
• Тип: {company_type_map.get(company['company_type'], company['company_type'])}
• ИНН: {company.get('inn', 'Не указан')}
• КПП: {company.get('kpp', 'Не указан')}
• ОГРН: {company.get('ogrn', 'Не указан')}

👤 **Руководитель:**
• ФИО: {company.get('director_last_name', '')} {company.get('director_first_name', '')} {company.get('director_patronymic', '')}

📍 **Юридический адрес:** {company.get('legal_address', 'Не указан')}
💳 **Система налогообложения:** {tax_system_map.get(company.get('tax_system'), 'Не указана')}
📞 **Телефон:** {company.get('contact_phone', 'Не указан')}
📧 **Email:** {company.get('contact_email', 'Не указан')}

⏰ **Дата подачи заявки:** {company.get('created_at', 'Не указана')}

Выберите действие:
"""