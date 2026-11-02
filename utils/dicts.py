
role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }

CARGO_TYPE_MAPPING = {
    "✅ Обычный": "common",
    "🥪 Скоропортящийся": "perishable",
    "⚠️ Опасный": "dangerous",
    "🔔 Хрупкий": "fragile",
    "📱 ТНП": "consumer-goods",
    "🔌 Бытовая техника": "appliances",
    "🧪 Бытовая химия": "household-chemicals",
    "📝 ПРОЧЕЕ": "another"
}

# Словарь для категории груза (без эмодзи)
CARGO_CATEGORY_MAPPING = {
    "📦 Паллеты": "pallets",
    "🏗️ Стройматериалы": "building-materials",
    "🥫 Продукты": "products",
    "📦 Ящики/коробки": "boxes",
    "📝 ПРОЧЕЕ": "another"
}

# Словарь для метода погрузки (без эмодзи)
LOADING_METHOD_MAPPING = {
    "🧱 Задняя": "back",
    "⬆️ Верхняя": "top",
    "🚪 Боковая": "side",
    "🎪 С полной растентовкой": "full"
}

# Словарь для типа кузова (без эмодзи)
VEHICLE_TYPE_MAPPING = {
    "📦 Тент": "tent",
    "🧊 Рефрижератор": "fridge",
    "🌡️ Изотермический": "isotermic",
    "🚚 Любой закрытый": "close",
    "🚛 Открытая платформа": "open",
    "📄 Промтоварный": "prom"
}

logist_rating_rules = {
    'completion_rate': ' Доля выполненных заявок',
    'selection_rate' : 'Доля заявок с выбранным перевозчиком',
    'response_diversity': 'Разнообразие откликов',
    'completion_speed': 'Скорость выполнения заявок',
    'budget_size': 'Средний бюджет заявок',
}

executor_rating_rules = {
    'selection_rate': 'Доля выбранных откликов',
    'completion_rate': 'Доля выполненных заявок',
    'response_activity': 'Активность откликов',
    'completion_speed': 'Скорость выполнения',
    'logist_diversity': 'Разнообразие логистов'

}

role_rating_type = {
    'admin': 'logist',
    'external_admin': 'logist',
    'logist': 'logist',
    'external_logist': 'logist',
    'executor': 'executor',
    'external_executor': 'executor'
}

company_type_map = {
        'legal': '🏢 Юридическое лицо (ООО/АО)',
        'individual': '👨‍💼 Индивидуальный предприниматель (ИП)',
        'self_employed': '👤 Самозанятый'
    }

user_fields_display = {
    'id': '🆔 ID',
    'telegram_id': '📱 Telegram ID',
    'company_name': '🏢 Название компании',
    'role': '💼 Должность',
    'first_name': '👤 Имя',
    'last_name': '👤 Фамилия',
    'patronymic': '👤 Отчество',
    'full_name': '👤 ФИО',
    'phone': '📞 Телефон',
    'email': '📧 Email',
    'birth_date': '🎂 Дата рождения',
    'passport_series': '📘 Серия паспорта',
    'passport_number': '📘 Номер паспорта',
    'passport_issue_date': '📅 Дата выдачи паспорта',
    'registration_address': '📍 Адрес регистрации',
    'ati_code': '🔢 Код АТИ'
}

company_fields_display = {
    'id': '🆔 ID компании',
    'name': '🏢 Название (краткое)',
    'name_full': '🏢 Полное наименование',
    'company_type': '📋 Тип компании',
    'inn': '🔢 ИНН',
    'kpp': '🔢 КПП',
    'ogrn': '🔢 ОГРН',
    'address': '📍 Юридический адрес',
    'contact_phone': '📞 Контактный телефон',
    'contact_email': '📧 Контактный email',
    'note': '📝 Примечание',
    'status': '📊 Статус',
    'management_name': '👤 Руководитель (ФИО)',
    'management_post': '👔 Должность руководителя',
    'bik': '💰 БИК',
    'payment_account': '💰 Расчетный счет',
    'correspondent_account': '💰 Корреспондентский счет',
    'okpo': '💰 ОКПО'

}

subscription_type_map = {
    'trial': '🎁 Пробная',
    'paid': '📄 Обычная'
}

subscription_status_map = {
    'active': '✅ Активна',
    'expired': '🕐 Истекла',
    'cancelled': '❌ Отменена'
}


CARGO_TYPE_REVERSE_MAPPING = {v: k for k, v in CARGO_TYPE_MAPPING.items()}
CARGO_CATEGORY_REVERSE_MAPPING = {v: k for k, v in CARGO_CATEGORY_MAPPING.items()}
LOADING_METHOD_REVERSE_MAPPING = {v: k for k, v in LOADING_METHOD_MAPPING.items()}
VEHICLE_TYPE_REVERSE_MAPPING = {v: k for k, v in VEHICLE_TYPE_MAPPING.items()}