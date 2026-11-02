import json
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardRemove
from keyboards.main_menus import get_main_menu
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state

rating_temp_data = {}


def register_settings_rating_handlers(bot, db):
    """Регистрирует обработчики для управления рейтингом"""

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_rating_category')
    def handle_rating_category(message):
        """Обработчик выбора категории рейтинга"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)
        if not user and user['status'] != 'active':
            bot.send_message(
                user_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🕹 Выберите действие из меню:",
                reply_markup=get_main_menu(db.get_user_role(user_id)['role'])
            )
            set_user_state(user_id, '')
            return

        elif message.text == "👤 Перевозчики":
            show_executor_rules(bot, db, user_id, chat_id)

        elif message.text == "👔 Логисты":
            show_logist_rules(bot, db, user_id, chat_id)

    def show_executor_rules(bot, db, user_id, chat_id):
        """Показывает правила для перевозчиков"""
        rules = db.fetch_all("""
            SELECT * FROM rating_rules 
            WHERE rule_type = 'executor' 
            ORDER BY 
                CASE 
                    WHEN rule_name LIKE 'Принятие заявки%' THEN 1
                    WHEN rule_name LIKE 'Завершение заявки%' THEN 2
                    WHEN rule_name LIKE 'Отклонение%' THEN 3
                    WHEN rule_name LIKE 'Отзыв заявки%' THEN 4
                    ELSE 5
                END
        """)

        if not rules:
            # Если правил нет, создаем стандартные
            create_default_rules(db)
            rules = db.fetch_all("SELECT * FROM rating_rules WHERE rule_type = 'executor'")

        rules_text = "⭐ **Правила для перевозчиков**\n\n"
        rules_text += "Настройте бонусы и штрафы для перевозчиков:\n\n"

        for rule in rules:
            status = "✅ Активно" if rule['is_active'] else "❌ Неактивно"
            sign = "+" if rule['value'] >= 0 else "-"
            rules_text += f"**{rule['rule_name']}**\n"
            rules_text += f"  {rule['rule_description']}\n"
            rules_text += f"  Значение: {sign}{abs(rule['value'])} баллов\n"
            rules_text += f"  Статус: {status}\n\n"

        # Сохраняем правила во временные данные
        if user_id not in rating_temp_data:
            rating_temp_data[user_id] = {}

        rating_temp_data[user_id]['current_rules'] = rules
        rating_temp_data[user_id]['rule_type'] = 'executor'
        rating_temp_data[user_id]['rule_dict'] = {}  # Словарь для быстрого поиска

        # Создаем словарь для быстрого поиска правила по тексту кнопки
        for rule in rules:
            status = "✅" if rule['is_active'] else "❌"
            sign = "+" if rule['value'] >= 0 else "-"
            button_text = f"{status} {rule['rule_name']} ({sign}{abs(rule['value'])})"
            rating_temp_data[user_id]['rule_dict'][button_text] = rule

        bot.send_message(
            chat_id,
            rules_text,
            reply_markup=get_rules_list_keyboard(rules),
            parse_mode='Markdown'
        )
        set_user_state(user_id, 'waiting_for_rule_selection')

    def show_logist_rules(bot, db, user_id, chat_id):
        """Показывает правила для логистов"""
        rules = db.fetch_all("""
            SELECT * FROM rating_rules 
            WHERE rule_type = 'logist' 
            ORDER BY 
                CASE 
                    WHEN rule_name LIKE 'Завершение заявки%' THEN 1
                    ELSE 2
                END
        """)

        if not rules:
            # Если правил нет, создаем стандартные
            create_default_rules(db)
            rules = db.fetch_all("SELECT * FROM rating_rules WHERE rule_type = 'logist'")

        rules_text = "⭐ **Правила для логистов**\n\n"
        rules_text += "Настройте бонусы и штрафы для логистов:\n\n"

        for rule in rules:
            status = "✅ Активно" if rule['is_active'] else "❌ Неактивно"
            sign = "+" if rule['value'] >= 0 else "-"
            rules_text += f"**{rule['rule_name']}**\n"
            rules_text += f"  {rule['rule_description']}\n"
            rules_text += f"  Значение: {sign}{abs(rule['value'])} баллов\n"
            rules_text += f"  Статус: {status}\n\n"

        # Сохраняем правила во временные данные
        if user_id not in rating_temp_data:
            rating_temp_data[user_id] = {}

        rating_temp_data[user_id]['current_rules'] = rules
        rating_temp_data[user_id]['rule_type'] = 'logist'
        rating_temp_data[user_id]['rule_dict'] = {}  # Словарь для быстрого поиска

        # Создаем словарь для быстрого поиска правила по тексту кнопки
        for rule in rules:
            status = "✅" if rule['is_active'] else "❌"
            sign = "+" if rule['value'] >= 0 else "-"
            button_text = f"{status} {rule['rule_name']} ({sign}{abs(rule['value'])})"
            rating_temp_data[user_id]['rule_dict'][button_text] = rule

        bot.send_message(
            chat_id,
            rules_text,
            reply_markup=get_rules_list_keyboard(rules),
            parse_mode='Markdown'
        )
        set_user_state(user_id, 'waiting_for_rule_selection')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_rule_selection')
    def handle_rule_selection(message):
        """Обработчик выбора правила"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "⭐ **Управление рейтингом**\n\n"
                "Здесь вы можете настроить бонусы и штрафы для рейтинговой системы.\n\n"
                "Выберите категорию для настройки:",
                reply_markup=get_rating_management_keyboard(),
                parse_mode='Markdown'
            )
            set_user_state(user_id, 'waiting_for_rating_category')
            return

        # Проверяем, выбрано ли существующее правило
        if (user_id in rating_temp_data and
                'rule_dict' in rating_temp_data[user_id] and
                message.text in rating_temp_data[user_id]['rule_dict']):
            rule = rating_temp_data[user_id]['rule_dict'][message.text]
            rating_temp_data[user_id]['selected_rule'] = rule
            show_rule_details(bot, db, user_id, chat_id, rule)
            return

        bot.send_message(chat_id, "❌ Пожалуйста, выберите правило из списка.")

    def show_rule_details(bot, db, user_id, chat_id, rule):
        """Показывает детали правила и варианты редактирования"""
        status = "✅ Активно" if rule['is_active'] else "❌ Неактивно"
        sign = "+" if rule['value'] >= 0 else "-"

        rule_text = f"📋 **Детали правила**\n\n"
        rule_text += f"**Название:** {rule['rule_name']}\n"
        rule_text += f"**Описание:** {rule['rule_description']}\n"
        rule_text += f"**Тип:** {'Перевозчик' if rule['rule_type'] == 'executor' else 'Логист'}\n"
        rule_text += f"**Значение:** {sign}{abs(rule['value'])} баллов\n"
        rule_text += f"**Статус:** {status}\n"
        rule_text += f"**Дата создания:** {rule['created_at']}\n"

        bot.send_message(
            chat_id,
            rule_text,
            reply_markup=get_rule_edit_keyboard(rule['id']),
            parse_mode='Markdown'
        )
        set_user_state(user_id, 'waiting_for_rule_action')

    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_rule_'))
    def handle_rule_action(call):
        """Обработчик действий с правилом"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        data_parts = call.data.split('_')
        action = data_parts[2]
        rule_id = int(data_parts[3])

        # Получаем правило из базы
        rule = db.fetch_one("SELECT * FROM rating_rules WHERE id = ?", (rule_id,))
        if not rule:
            bot.answer_callback_query(call.id, "❌ Правило не найдено")
            return

        if action == 'value':
            # Редактирование значения
            # Сохраняем текущий rule_type перед изменением данных
            if user_id in rating_temp_data and 'rule_type' in rating_temp_data[user_id]:
                current_rule_type = rating_temp_data[user_id]['rule_type']
            else:
                current_rule_type = rule['rule_type']

            rating_temp_data[user_id] = {
                'editing_rule_id': rule_id,
                'editing_field': 'value',
                'rule_type': current_rule_type  # Сохраняем тип правила
            }

            bot.send_message(
                chat_id,
                f"💰 **Изменение значения правила**\n\n"
                f"Текущее значение: {rule['value']} баллов\n\n"
                f"Введите новое значение (можно использовать отрицательные числа для штрафов):",
                reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад"))
            )
            set_user_state(user_id, 'waiting_for_rule_value')
            bot.answer_callback_query(call.id)

        elif action == 'toggle':
            # Переключение активности
            new_status = 0 if rule['is_active'] else 1
            db.execute_query(
                "UPDATE rating_rules SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
                (new_status, rule_id)
            )

            status_text = "активировано" if new_status else "деактивировано"
            bot.answer_callback_query(call.id, f"✅ Правило {status_text}")

            # Обновляем сообщение
            rule = db.fetch_one("SELECT * FROM rating_rules WHERE id = ?", (rule_id,))
            show_rule_details(bot, db, user_id, chat_id, rule)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_rule_value')
    def handle_rule_value_input(message):
        """Обработчик ввода нового значения правила"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            # Восстанавливаем необходимые данные для возврата
            if user_id in rating_temp_data and 'editing_rule_id' in rating_temp_data[user_id]:
                rule_id = rating_temp_data[user_id]['editing_rule_id']
                rule = db.fetch_one("SELECT * FROM rating_rules WHERE id = ?", (rule_id,))
                if rule:
                    # Сохраняем правило перед показом деталей
                    rating_temp_data[user_id]['selected_rule'] = rule
                    show_rule_details(bot, db, user_id, chat_id, rule)
            return

        try:
            value = float(message.text.replace(',', '.'))

            if user_id in rating_temp_data and 'editing_rule_id' in rating_temp_data[user_id]:
                rule_id = rating_temp_data[user_id]['editing_rule_id']

                db.execute_query(
                    "UPDATE rating_rules SET value = ?, updated_at = datetime('now') WHERE id = ?",
                    (value, rule_id)
                )

                # Очищаем только поля редактирования, сохраняя rule_type
                rule_type = rating_temp_data[user_id].get('rule_type')

                # Очищаем временные данные, но сохраняем rule_type
                if user_id in rating_temp_data:
                    # Сохраняем тип правила
                    temp_rule_type = rating_temp_data[user_id].get('rule_type')

                    # Полностью очищаем запись пользователя
                    rating_temp_data[user_id] = {}

                    # Если был сохранен тип правила, сохраняем его
                    if temp_rule_type:
                        rating_temp_data[user_id]['rule_type'] = temp_rule_type

                # Показываем обновленное правило
                rule = db.fetch_one("SELECT * FROM rating_rules WHERE id = ?", (rule_id,))
                bot.send_message(chat_id, f"✅ Значение обновлено: {value} баллов")

                # Сохраняем правило перед показом деталей
                rating_temp_data[user_id]['selected_rule'] = rule
                show_rule_details(bot, db, user_id, chat_id, rule)

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректное число.")

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_rules_list')
    def handle_back_to_rules_list(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Проверяем наличие данных пользователя
        if user_id not in rating_temp_data:
            bot.answer_callback_query(call.id, "❌ Сессия истекла")
            return

        # Получаем тип правила из данных или определяем по наличию правила
        rule_type = None

        if 'rule_type' in rating_temp_data[user_id]:
            rule_type = rating_temp_data[user_id]['rule_type']
        elif 'selected_rule' in rating_temp_data[user_id]:
            # Если есть выбранное правило, берем тип из него
            rule_type = rating_temp_data[user_id]['selected_rule']['rule_type']
        else:
            # Если тип неизвестен, пробуем определить из базы данных
            # Получаем первое правило нужного типа (перевозчик или логист)
            executor_rules = db.fetch_one("SELECT rule_type FROM rating_rules WHERE rule_type = 'executor' LIMIT 1")
            if executor_rules:
                rule_type = 'executor'
            else:
                rule_type = 'logist'

        # Удаляем сообщение с деталями правила
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass

        # Возвращаемся к списку правил
        if rule_type == 'executor':
            show_executor_rules(bot, db, user_id, chat_id)
        else:
            show_logist_rules(bot, db, user_id, chat_id)

        bot.answer_callback_query(call.id)


def get_rating_management_keyboard():
    """Создает клавиатуру для управления рейтингом"""
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(
        KeyboardButton("👤 Перевозчики"),
        KeyboardButton("👔 Логисты"),
        KeyboardButton("⬅️ Назад")
    )
    return keyboard


def get_rules_list_keyboard(rules):
    """Создает клавиатуру со списком правил"""
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)

    for rule in rules:
        status = "✅" if rule['is_active'] else "❌"
        sign = "+" if rule['value'] >= 0 else "-"
        keyboard.add(KeyboardButton(f"{status} {rule['rule_name']} ({sign}{abs(rule['value'])})"))

    keyboard.add(
        KeyboardButton("⬅️ Назад")
    )
    return keyboard


def get_rule_edit_keyboard(rule_id):
    """Создает инлайн-клавиатуру для редактирования правила"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✏️ Изменить значение", callback_data=f"edit_rule_value_{rule_id}"),
        InlineKeyboardButton("🔄 Вкл/Выкл", callback_data=f"edit_rule_toggle_{rule_id}"),
        InlineKeyboardButton("⬅️ Назад к списку", callback_data="back_to_rules_list")
    )
    return keyboard


def create_default_rules(db):
    """Создает стандартные правила рейтинга"""

    # Правила для перевозчиков
    executor_rules = [
        {
            'rule_type': 'executor',
            'rule_name': 'Принятие заявки',
            'rule_description': 'Бонус за принятие заявки перевозчиком',
            'value': 5.0
        },
        {
            'rule_type': 'executor',
            'rule_name': 'Завершение заявки',
            'rule_description': 'Бонус за успешное завершение заявки',
            'value': 10.0
        },
        {
            'rule_type': 'executor',
            'rule_name': 'Отклонение заявки',
            'rule_description': 'Штраф за отклонение заявки после принятия',
            'value': -5.0
        },
        {
            'rule_type': 'executor',
            'rule_name': 'Отзыв заявки',
            'rule_description': 'Штраф за отзыв заявки у принявшего её перевозчика',
            'value': -10.0
        }
    ]

    # Правила для логистов
    logist_rules = [
        {
            'rule_type': 'logist',
            'rule_name': 'Завершение заявки',
            'rule_description': 'Бонус за подтверждение завершения заявки',
            'value': 5.0
        }
    ]

    # Вставляем правила в базу
    for rule in executor_rules + logist_rules:
        db.execute_query(
            """INSERT OR IGNORE INTO rating_rules 
            (rule_type, rule_name, rule_description, value, is_active, created_at) 
            VALUES (?, ?, ?, ?, 1, datetime('now'))""",
            (rule['rule_type'], rule['rule_name'], rule['rule_description'], rule['value'])
        )