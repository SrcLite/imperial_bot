import json
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove

from utils.dicts import CARGO_CATEGORY_MAPPING, CARGO_TYPE_MAPPING, VEHICLE_TYPE_MAPPING, \
    CARGO_CATEGORY_REVERSE_MAPPING, CARGO_TYPE_REVERSE_MAPPING, VEHICLE_TYPE_REVERSE_MAPPING
from utils.filters import get_filter_stats, ExecutorFilters

# Глобальный словарь для хранения состояний пользователей
filter_states = {}


def register_executor_filter_handlers(bot, db):
    """Регистрирует обработчики фильтров"""

    @bot.message_handler(func=lambda message: message.text == "🔍 Фильтры заявок")
    def handle_filter_menu(message):
        """Меню фильтров - отправляет новое сообщение"""
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

        # Проверяем, что пользователь - перевозчик
        user = db.fetch_one(
            "SELECT role FROM users WHERE telegram_id = ? AND status = 'active'",
            (user_id,)
        )

        if not user or user['role'] not in ['executor', 'external_executor']:
            bot.send_message(chat_id, "❌ Эта функция доступна только перевозчикам.")
            return

        # Отправляем новое сообщение с меню фильтров
        show_filter_menu(bot, db, user_id, chat_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('cargo_type_'))
    def handle_cargo_type_selection(call):
        """Обработка выбора типа груза"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        data_parts = call.data.split('_')
        print(f"call.data: {call.data}, parts: {data_parts}")

        # Минимальное количество частей - 3 (cargo, type, действие)
        if len(data_parts) < 3:
            bot.answer_callback_query(call.id, "❌ Ошибка в данных")
            return

        # Извлекаем действие (третья часть)
        action = data_parts[2]

        # Для действий add и remove нужен четвертый параметр (ключ фильтра)
        # Для действий select_all, clear, back четвертый параметр не нужен
        filter_key = None
        if len(data_parts) >= 4 and action in ['add', 'remove']:
            filter_key = data_parts[3]

        filters = ExecutorFilters(db, user_id)
        current_types = filters.filters.get('cargo_type', [])

        if action == 'add' and filter_key:
            if filter_key not in current_types:
                current_types.append(filter_key)
                filters.update_filter('cargo_type', current_types)
        elif action == 'remove' and filter_key:
            if filter_key in current_types:
                current_types.remove(filter_key)
                filters.update_filter('cargo_type', current_types)
        elif action == 'select-all':
            filters.update_filter('cargo_type', list(CARGO_TYPE_MAPPING.values()))
        elif action == 'clear':
            filters.update_filter('cargo_type', [])
        elif action == 'back':
            show_filter_menu(bot, db, user_id, chat_id, message_id)
            bot.answer_callback_query(call.id)
            return
        else:
            bot.answer_callback_query(call.id, "❌ Неизвестное действие")
            return

        show_cargo_type_filter(bot, db, chat_id, filters, message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('cargo_category_'))
    def handle_cargo_category_selection(call):
        """Обработка выбора категории груза"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        data_parts = call.data.split('_')
        print(f"call.data: {call.data}, parts: {data_parts}")

        if len(data_parts) < 3:
            bot.answer_callback_query(call.id, "❌ Ошибка в данных")
            return

        action = data_parts[2]

        filter_key = None
        if len(data_parts) >= 4 and action in ['add', 'remove']:
            filter_key = data_parts[3]

        filters = ExecutorFilters(db, user_id)
        current_categories = filters.filters.get('cargo_category', [])

        if action == 'add' and filter_key:
            if filter_key not in current_categories:
                current_categories.append(filter_key)
                filters.update_filter('cargo_category', current_categories)
        elif action == 'remove' and filter_key:
            if filter_key in current_categories:
                current_categories.remove(filter_key)
                filters.update_filter('cargo_category', current_categories)
        elif action == 'select-all':
            filters.update_filter('cargo_category', list(CARGO_CATEGORY_MAPPING.values()))
        elif action == 'clear':
            filters.update_filter('cargo_category', [])
        elif action == 'back':
            show_filter_menu(bot, db, user_id, chat_id, message_id)
            bot.answer_callback_query(call.id)
            return
        else:
            bot.answer_callback_query(call.id, "❌ Неизвестное действие")
            return

        show_cargo_category_filter(bot, db, chat_id, filters, message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('vehicle_type_'))
    def handle_vehicle_type_selection(call):
        """Обработка выбора типа транспорта"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        data_parts = call.data.split('_')
        print(f"call.data: {call.data}, parts: {data_parts}")

        if len(data_parts) < 3:
            bot.answer_callback_query(call.id, "❌ Ошибка в данных")
            return

        action = data_parts[2]

        filter_key = None
        if len(data_parts) >= 4 and action in ['add', 'remove']:
            filter_key = data_parts[3]

        filters = ExecutorFilters(db, user_id)
        current_vehicles = filters.filters.get('vehicle_type', [])

        if action == 'add' and filter_key:
            if filter_key not in current_vehicles:
                current_vehicles.append(filter_key)
                filters.update_filter('vehicle_type', current_vehicles)
        elif action == 'remove' and filter_key:
            if filter_key in current_vehicles:
                current_vehicles.remove(filter_key)
                filters.update_filter('vehicle_type', current_vehicles)
        elif action == 'select-all':
            filters.update_filter('vehicle_type', list(VEHICLE_TYPE_MAPPING.values()))
        elif action == 'clear':
            filters.update_filter('vehicle_type', [])
        elif action == 'back':
            show_filter_menu(bot, db, user_id, chat_id, message_id)
            bot.answer_callback_query(call.id)
            return
        else:
            bot.answer_callback_query(call.id, "❌ Неизвестное действие")
            return

        show_vehicle_type_filter(bot, db, chat_id, filters, message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('app_type_'))
    def handle_application_type_selection(call):
        """Обработка выбора типа заявки"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        data_parts = call.data.split('_')
        print(f"call.data: {call.data}, parts: {data_parts}")

        if len(data_parts) < 3:
            bot.answer_callback_query(call.id, "❌ Ошибка в данных")
            return

        action = data_parts[2]

        app_type = None
        if len(data_parts) >= 4 and action in ['add', 'remove']:
            app_type = data_parts[3]

        filters = ExecutorFilters(db, user_id)
        current_types = filters.filters.get('application_type', [])

        if action == 'add' and app_type:
            if app_type not in current_types:
                current_types.append(app_type)
                filters.update_filter('application_type', current_types)
        elif action == 'remove' and app_type:
            if app_type in current_types:
                current_types.remove(app_type)
                filters.update_filter('application_type', current_types)
        elif action == 'select-all':
            filters.update_filter('application_type', ['fixed', 'auction'])
        elif action == 'clear':
            filters.update_filter('application_type', [])
        elif action == 'back':
            show_filter_menu(bot, db, user_id, chat_id, message_id)
            bot.answer_callback_query(call.id)
            return
        else:
            bot.answer_callback_query(call.id, "❌ Неизвестное действие")
            return

        show_application_type_filter(bot, db, chat_id, filters, message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'apply_filters')
    def handle_apply_filters(call):
        """Применение фильтров"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        filters = ExecutorFilters(db, user_id)
        total_apps = get_filter_stats(db, user_id, filters.filters)

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"✅ **ФИЛЬТРЫ ПРИМЕНЕНЫ**\n\n📊 **Найдено заявок:** {total_apps}\n\nТеперь в разделе '🔔 Новые заявки' будут отображаться только подходящие под ваши фильтры заявки.",
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'reset_filters')
    def handle_reset_filters(call):
        """Сброс всех фильтров"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        filters = ExecutorFilters(db, user_id)
        filters.reset_filters()

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✅ **ВСЕ ФИЛЬТРЫ СБРОШЕНЫ**\n\nВсе фильтры установлены в значения по умолчанию.",
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'filter_stats')
    def handle_filter_stats(call):
        """Показать статистику"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        filters = ExecutorFilters(db, user_id)
        total_apps = get_filter_stats(db, user_id, filters.filters)

        all_apps = db.fetch_one(
            "SELECT COUNT(*) as total FROM applications WHERE status IN ('active', 'urgent')"
        )

        bot.answer_callback_query(
            call.id,
            f"📊 Статистика: {total_apps} из {all_apps['total']} заявок",
            show_alert=True
        )

    @bot.callback_query_handler(func=lambda call: call.data == 'close_filters')
    def handle_close_filters(call):
        """Закрыть меню фильтров - удалить сообщение"""
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception as e:
            print(f"❌ Ошибка удаления сообщения: {e}")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_filters')
    def handle_back_to_filters(call):
        """Вернуться к меню фильтров"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        show_filter_menu(bot, db, user_id, chat_id, message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('filter_'))
    def handle_filter_select(call):
        """Выбор фильтра для настройки"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        filter_key = call.data.split('_', 1)[1]

        filters = ExecutorFilters(db, user_id)

        if filter_key == 'cargo_type':
            show_cargo_type_filter(bot, db, chat_id, filters, message_id)
        elif filter_key == 'vehicle_type':
            show_vehicle_type_filter(bot, db, chat_id, filters, message_id)
        elif filter_key == 'capacity_range':
            ask_capacity_range(bot, chat_id, user_id)
        elif filter_key == 'volume_range':
            ask_volume_range(bot, chat_id, user_id)
        elif filter_key == 'price_range':
            ask_price_range(bot, chat_id, user_id)
        elif filter_key == 'loading_date':
            ask_loading_date(bot, chat_id, user_id)
        elif filter_key == 'loading_city':
            show_city_filter(bot, db, chat_id, filters, message_id, 'loading_city')
        elif filter_key == 'unloading_city':
            show_city_filter(bot, db, chat_id, filters, message_id, 'unloading_city')
        elif filter_key == 'application_type':
            show_application_type_filter(bot, db, chat_id, filters, message_id)
        elif filter_key == 'show_active_only':
            toggle_boolean_filter(bot, db, chat_id, user_id, 'show_active_only', message_id)
        elif filter_key == 'show_without_response':
            toggle_boolean_filter(bot, db, chat_id, user_id, 'show_without_response', message_id)

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith('loading_city_') or call.data.startswith('unloading_city_'))
    def handle_city_selection(call):
        """Обработка выбора городов"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        data = call.data
        data_parts = data.split('_')
        print(f"call.data: {call.data}, parts: {data_parts}")

        filter_key = 'loading_city' if data.startswith('loading_city_') else 'unloading_city'

        if len(data_parts) < 3:
            bot.answer_callback_query(call.id, "❌ Ошибка в данных")
            return

        action = data_parts[2]

        filters = ExecutorFilters(db, user_id)
        current_cities = filters.filters.get(filter_key, [])

        if action == 'add':
            # Запрашиваем ввод городов
            ask_city(bot, chat_id, user_id, filter_key)
            bot.answer_callback_query(call.id)
            return

        elif action == 'remove' and len(data_parts) > 3:
            city_to_remove = '_'.join(data_parts[3:])
            if city_to_remove in current_cities:
                current_cities.remove(city_to_remove)
                filters.update_filter(filter_key, current_cities)

        elif action == 'clear':
            filters.update_filter(filter_key, [])

        elif action == 'back':
            show_filter_menu(bot, db, user_id, chat_id, message_id)
            bot.answer_callback_query(call.id)
            return
        else:
            bot.answer_callback_query(call.id, "❌ Неизвестное действие")
            return

        # Показываем обновленный список городов
        show_city_filter(bot, db, chat_id, filters, message_id, filter_key)
        bot.answer_callback_query(call.id)

    # Регистрируем текстовые обработчики


def show_filter_menu(bot, db, user_id, chat_id, message_id=None):
    """Показывает меню фильтров с отображением текущих значений на русском"""
    user = db.fetch_one(
        "SELECT role FROM users WHERE telegram_id = ? AND status = 'active'",
        (user_id,)
    )

    if not user or user['role'] not in ['executor', 'external_executor']:
        bot.send_message(chat_id, "❌ Эта функция доступна только перевозчикам.")
        return

    filters = ExecutorFilters(db, user_id)

    # Отладочная информация
    print(f"🔍 Отладка фильтров для пользователя {user_id}:")
    print(f"  Все фильтры: {json.dumps(filters.filters, ensure_ascii=False, indent=2)}")

    # Проверяем конкретные поля
    check_fields = ['capacity_min', 'capacity_max', 'volume_min', 'volume_max',
                    'price_min', 'price_max', 'loading_date_from', 'loading_date_to']
    for field in check_fields:
        value = filters.filters.get(field)
        print(f"  {field}: {value} (тип: {type(value).__name__})")

    # Создаем клавиатуру с фильтрами
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Основные фильтры с группировкой
    filters_config = [
        # Груз
        ('cargo_type', '📦 Тип груза'),

        # Транспорт
        ('vehicle_type', '🚛 Тип транспорта'),
        ('capacity_range', '⚖️ Грузоподъемность'),
        ('volume_range', '📏 Объем кузова'),

        # Финансы
        ('price_range', '💰 Диапазон цен'),
        ('application_type', '📝 Тип заявки'),

        # Локация
        ('loading_city', '🏙️ Город погрузки'),
        ('unloading_city', '🏙️ Город выгрузки'),

        # Время
        ('loading_date', '📅 Дата погрузки'),
    ]

    # Добавляем кнопки фильтров
    for filter_key, filter_name in filters_config:
        try:
            # Для диапазонных фильтров используем специальную логику
            if filter_key in ['capacity_range', 'volume_range', 'price_range']:
                # Получаем min и max значения
                min_key = filter_key.replace('_range', '_min')
                max_key = filter_key.replace('_range', '_max')
                min_val = filters.filters.get(min_key)
                max_val = filters.filters.get(max_key)

                print(f"  {filter_key}: min={min_val}, max={max_val}")

                # Используем get_filter_display
                current_value = filters.get_filter_display(filter_key, None)
            elif filter_key == 'loading_date':
                date_from = filters.filters.get('loading_date_from')
                date_to = filters.filters.get('loading_date_to')
                print(f"  loading_date: from={date_from}, to={date_to}")
                current_value = filters.get_filter_display(filter_key, None)
            else:
                filter_value = filters.filters.get(filter_key)
                current_value = filters.get_filter_display(filter_key, filter_value)

            print(f"  Кнопка {filter_key}: {filter_name} = {current_value}")

            # Создаем текст кнопки
            button_text = f"{filter_name}\n{current_value}"

            # Обрезаем текст если слишком длинный
            if len(button_text) > 40:
                button_text = button_text[:37] + "..."

            keyboard.add(
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"filter_{filter_key}"
                )
            )
        except Exception as e:
            print(f"❌ Ошибка создания кнопки для фильтра {filter_key}: {e}")
            import traceback
            traceback.print_exc()
            keyboard.add(
                InlineKeyboardButton(
                    f"{filter_name}\n❌ Ошибка",
                    callback_data=f"filter_{filter_key}"
                )
            )

    # Разделительная строка
    keyboard.row(InlineKeyboardButton("─" * 20, callback_data="noop"))

    # Кнопки действий
    keyboard.row(
        InlineKeyboardButton("🔄 Применить", callback_data="apply_filters"),
        InlineKeyboardButton("🗑️ Сбросить все", callback_data="reset_filters")
    )

    keyboard.row(
        InlineKeyboardButton("📊 Статистика", callback_data="filter_stats"),
        InlineKeyboardButton("❌ Закрыть", callback_data="close_filters")
    )

    # Получаем статистику
    total_apps = get_filter_stats(db, user_id, filters.filters)

    message_text = f"🔍 **НАСТРОЙКИ ФИЛЬТРОВ**\n\n📊 **Найдено заявок:** {total_apps}\n\nВыберите фильтр для настройки:"

    if message_id:
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"❌ Ошибка редактирования сообщения: {e}")
            bot.send_message(chat_id, message_text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, message_text, reply_markup=keyboard, parse_mode='Markdown')

def show_cargo_type_filter(bot, db, chat_id, filters, message_id):
    """Показывает выбор типа груза, редактируя существующее сообщение"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    selected_types = filters.filters.get('cargo_type', [])

    for display_text, key in CARGO_TYPE_MAPPING.items():
        is_selected = key in selected_types or display_text in selected_types

        if is_selected:
            text = f"✅ {display_text}"
            callback = f"cargo_type_remove_{key}"
        else:
            text = f"🔘 {display_text}"
            callback = f"cargo_type_add_{key}"

        keyboard.add(InlineKeyboardButton(text, callback_data=callback))

    keyboard.row(
        InlineKeyboardButton("✅ Выбрать все", callback_data="cargo_type_select-all"),
        InlineKeyboardButton("🗑️ Очистить", callback_data="cargo_type_clear")
    )
    keyboard.row(InlineKeyboardButton("🔙 Назад", callback_data="back_to_filters"))

    selected_display_texts = []
    for key in selected_types:
        if key in CARGO_TYPE_REVERSE_MAPPING:
            selected_display_texts.append(CARGO_TYPE_REVERSE_MAPPING[key])
        else:
            selected_display_texts.append(key)

    selected_text = ", ".join(selected_display_texts[:3])
    if len(selected_display_texts) > 3:
        selected_text += f" и ещё {len(selected_display_texts) - 3}"

    message_text = f"📦 **ВЫБОР ТИПА ГРУЗА**\n\n**Выбрано:** {selected_text if selected_display_texts else '❌ Не выбрано'}\n\nВыберите типы грузов, которые вам подходят:"

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"❌ Ошибка редактирования сообщения типа груза: {e}")


def show_cargo_category_filter(bot, db, chat_id, filters, message_id):
    """Показывает выбор категории груза, редактируя существующее сообщение"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    selected_categories = filters.filters.get('cargo_category', [])

    for display_text, key in CARGO_CATEGORY_MAPPING.items():
        is_selected = key in selected_categories or display_text in selected_categories

        if is_selected:
            text = f"✅ {display_text}"
            callback = f"cargo_category_remove_{key}"
        else:
            text = f"🔘 {display_text}"
            callback = f"cargo_category_add_{key}"

        keyboard.add(InlineKeyboardButton(text, callback_data=callback))

    keyboard.row(
        InlineKeyboardButton("✅ Выбрать все", callback_data="cargo_category_select-all"),
        InlineKeyboardButton("🗑️ Очистить", callback_data="cargo_category_clear")
    )
    keyboard.row(InlineKeyboardButton("🔙 Назад", callback_data="back_to_filters"))

    selected_display_texts = []
    for key in selected_categories:
        if key in CARGO_CATEGORY_REVERSE_MAPPING:
            selected_display_texts.append(CARGO_CATEGORY_REVERSE_MAPPING[key])
        else:
            selected_display_texts.append(key)

    selected_text = ", ".join(selected_display_texts[:3])
    if len(selected_display_texts) > 3:
        selected_text += f" и ещё {len(selected_display_texts) - 3}"

    message_text = f"📊 **ВЫБОР КАТЕГОРИИ ГРУЗА**\n\n**Выбрано:** {selected_text if selected_display_texts else '❌ Не выбрано'}\n\nВыберите категории грузов:"

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"❌ Ошибка редактирования сообщения категории груза: {e}")


def show_vehicle_type_filter(bot, db, chat_id, filters, message_id):
    """Показывает выбор типа транспорта, редактируя существующее сообщение"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    selected_vehicles = filters.filters.get('vehicle_type', [])

    for display_text, key in VEHICLE_TYPE_MAPPING.items():
        is_selected = key in selected_vehicles or display_text in selected_vehicles

        if is_selected:
            text = f"✅ {display_text}"
            callback = f"vehicle_type_remove_{key}"
        else:
            text = f"🔘 {display_text}"
            callback = f"vehicle_type_add_{key}"

        keyboard.add(InlineKeyboardButton(text, callback_data=callback))

    keyboard.row(
        InlineKeyboardButton("✅ Выбрать все", callback_data="vehicle_type_select-all"),
        InlineKeyboardButton("🗑️ Очистить", callback_data="vehicle_type_clear")
    )
    keyboard.row(InlineKeyboardButton("🔙 Назад", callback_data="back_to_filters"))

    selected_display_texts = []
    for key in selected_vehicles:
        if key in VEHICLE_TYPE_REVERSE_MAPPING:
            selected_display_texts.append(VEHICLE_TYPE_REVERSE_MAPPING[key])
        else:
            selected_display_texts.append(key)

    selected_text = ", ".join(selected_display_texts[:3])
    if len(selected_display_texts) > 3:
        selected_text += f" и ещё {len(selected_display_texts) - 3}"

    message_text = f"🚛 **ВЫБОР ТИПА ТРАНСПОРТА**\n\n**Выбрано:** {selected_text if selected_display_texts else '❌ Не выбрано'}\n\nВыберите типы транспорта, которые у вас есть:"

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"❌ Ошибка редактирования сообщения типа транспорта: {e}")


def show_application_type_filter(bot, db, chat_id, filters, message_id):
    """Показывает выбор типа заявки, редактируя существующее сообщение"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    selected_types = filters.filters.get('application_type', [])

    types = [
        ('fixed', '📦 Фиксированная цена'),
        ('auction', '🏷️ Аукцион (запрос ставок)')
    ]

    for key, display in types:
        if key in selected_types:
            text = f"✅ {display}"
            callback = f"app_type_remove_{key}"
        else:
            text = f"🔘 {display}"
            callback = f"app_type_add_{key}"

        keyboard.add(InlineKeyboardButton(text, callback_data=callback))

    keyboard.row(
        InlineKeyboardButton("✅ Выбрать все", callback_data="app_type_select-all"),
        InlineKeyboardButton("🗑️ Очистить", callback_data="app_type_clear")
    )
    keyboard.row(InlineKeyboardButton("🔙 Назад", callback_data="back_to_filters"))

    selected_text = ", ".join(
        [display for key, display in types if key in selected_types]) if selected_types else "❌ Не выбрано"

    message_text = f"📝 **ВЫБОР ТИПА ЗАЯВКИ**\n\n**Выбрано:** {selected_text}\n\nВыберите типы заявок:"

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"❌ Ошибка редактирования сообщения типа заявки: {e}")


def ask_capacity_range(bot, chat_id, user_id):
    """Запрос диапазона грузоподъемности"""
    filter_states[user_id] = {
        'waiting_for': 'capacity_min',
        'step': 1
    }

    bot.send_message(
        chat_id,
        "⚖️ **НАСТРОЙКА ГРУЗОПОДЪЕМНОСТИ**\n\n"
        "Введите минимальную грузоподъемность в тоннах (например: 5):\n\n"
        "Или отправьте 0, если ограничения нет.",
        parse_mode='Markdown'
    )


def ask_volume_range(bot, chat_id, user_id):
    """Запрос диапазона объема"""
    filter_states[user_id] = {
        'waiting_for': 'volume_min',
        'step': 1
    }

    bot.send_message(
        chat_id,
        "📏 **НАСТРОЙКА ОБЪЕМА КУЗОВА**\n\n"
        "Введите минимальный объем в м³ (например: 20):\n\n"
        "Или отправьте 0, если ограничения нет.",
        parse_mode='Markdown'
    )


def ask_price_range(bot, chat_id, user_id):
    """Запрос диапазона цен"""
    filter_states[user_id] = {
        'waiting_for': 'price_min',
        'step': 1
    }

    bot.send_message(
        chat_id,
        "💰 **НАСТРОЙКА ДИАПАЗОНА ЦЕН**\n\n"
        "Введите минимальную цену в рублях (например: 10000):\n\n"
        "Или отправьте 0, если ограничения нет.",
        parse_mode='Markdown'
    )


def ask_loading_date(bot, chat_id, user_id):
    """Запрос даты погрузки"""
    filter_states[user_id] = {
        'waiting_for': 'loading_date_from',
        'step': 1
    }

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📅 Сегодня"),
        KeyboardButton("📅 Завтра"),
        KeyboardButton("📅 Неделя"),
        KeyboardButton("📅 Месяц"),
        KeyboardButton("❌ Без ограничений"),
        KeyboardButton("❌ Отмена")
    )

    bot.send_message(
        chat_id,
        "📅 **НАСТРОЙКА ДАТЫ ПОГРУЗКИ**\n\n"
        "Выберите период дат погрузки или введите дату в формате ДД.ММ.ГГГГ:",
        reply_markup=keyboard
    )


def ask_city(bot, chat_id, user_id, city_type):
    """Запрос городов"""
    filter_states[user_id] = {
        'waiting_for': city_type,
        'cities': []
    }

    city_name = "погрузки" if city_type == 'loading_city' else "выгрузки"

    bot.send_message(
        chat_id,
        f"🏙️ **НАСТРОЙКА ГОРОДА {city_name.upper()}**\n\n"
        f"Введите названия городов через запятую (например: Москва, Санкт-Петербург, Казань):\n\n"
        f"Или отправьте '❌ Без ограничений' для сброса.",
        parse_mode='Markdown'
    )


def toggle_boolean_filter(bot, db, chat_id, user_id, filter_key, message_id):
    """Переключает булевый фильтр и обновляет сообщение"""
    filters = ExecutorFilters(db, user_id)
    current_value = filters.filters.get(filter_key, False)
    filters.update_filter(filter_key, not current_value)

    filter_name = "Только активные" if filter_key == 'show_active_only' else "Без моего отклика"
    new_value = "✅ Включено" if not current_value else "❌ Выключено"

    # Показываем временное уведомление
    bot.answer_callback_query(
        f"{filter_name}: {new_value}",
        show_alert=False
    )

    # Возвращаемся к меню фильтров
    show_filter_menu(bot, db, user_id, chat_id, message_id)


def register_filter_text_handlers(bot, db):
    """Регистрирует обработчики текстовых сообщений для фильтров"""

    @bot.message_handler(func=lambda message: message.from_user.id in filter_states)
    def handle_filter_input(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if user_id not in filter_states:
            return

        state = filter_states[user_id]
        waiting_for = state.get('waiting_for')
        text = message.text.strip()

        if text == "❌ Отмена":
            del filter_states[user_id]
            bot.send_message(chat_id, "❌ Настройка фильтра отменена.")
            return

        filters = ExecutorFilters(db, user_id)

        try:
            if waiting_for in ['capacity_min', 'capacity_max', 'volume_min', 'volume_max', 'price_min',
                               'price_max']:
                handle_numeric_filter(bot, db, chat_id, user_id, waiting_for, text, state)

            elif waiting_for in ['loading_date_from', 'loading_date_to']:
                handle_date_filter(bot, db, chat_id, user_id, waiting_for, text, state)

            elif waiting_for in ['loading_city', 'unloading_city']:
                handle_city_filter(bot, db, chat_id, user_id, waiting_for, text, state)

        except Exception as e:
            print(f"❌ Ошибка обработки фильтра: {e}")
            bot.send_message(chat_id, "❌ Произошла ошибка. Попробуйте снова.")



def handle_numeric_filter(bot, db, chat_id, user_id, filter_key, text, state):
    """Обработка числовых фильтров"""
    try:
        value = float(text) if text != '0' else 0

        # Получаем тип фильтра (грузоподъемность, объем или цена)
        filter_type = None
        if 'capacity' in filter_key:
            filter_type = 'capacity'
        elif 'volume' in filter_key:
            filter_type = 'volume'
        elif 'price' in filter_key:
            filter_type = 'price'

        if state.get('step') == 1:
            # Первое значение (минимум)
            filters = ExecutorFilters(db, user_id)

            # Определяем ключи для минимального и максимального значений
            min_key = f"{filter_type}_min"
            max_key = f"{filter_type}_max"

            if filter_key.endswith('_min'):
                # Сохраняем минимальное значение
                filters.update_filter(min_key, value if value > 0 else None)

                # Переходим к запросу максимального значения
                state['waiting_for'] = max_key
                state['step'] = 2
                state['min_key'] = min_key
                state['max_key'] = max_key
                state['filter_type'] = filter_type

                bot.send_message(
                    chat_id,
                    "Введите максимальное значение:\n\n"
                    "Или отправьте 0, если ограничения нет."
                )
            else:
                # Если пользователь сразу ввел максимальное значение (без минимального)
                filters.update_filter(max_key, value if value > 0 else None)
                del filter_states[user_id]

                filter_name = {
                    'capacity': 'грузоподъемности',
                    'volume': 'объема',
                    'price': 'цены'
                }.get(filter_type, '')

                bot.send_message(
                    chat_id,
                    f"✅ Максимальное значение для фильтра {filter_name} сохранено.",
                    parse_mode='Markdown'
                )

        elif state.get('step') == 2:
            # Второе значение (максимум)
            filters = ExecutorFilters(db, user_id)

            # Получаем сохраненные ключи из состояния
            min_key = state.get('min_key')
            max_key = state.get('max_key')
            filter_type = state.get('filter_type')

            # Получаем ранее сохраненное минимальное значение
            min_value = filters.filters.get(min_key)

            # Проверяем, что максимальное значение больше минимального (если оба установлены)
            if min_value and min_value > 0 and value > 0 and value <= min_value:
                bot.send_message(chat_id, "❌ Максимальное значение должно быть больше минимального.")
                return

            # Сохраняем максимальное значение
            filters.update_filter(max_key, value if value > 0 else None)

            # Очищаем состояние
            del filter_states[user_id]

            # Получаем сохраненные значения для отображения
            saved_min = filters.filters.get(min_key)
            saved_max = filters.filters.get(max_key)

            filter_name = {
                'capacity': 'грузоподъемности',
                'volume': 'объема',
                'price': 'цены'
            }.get(filter_type, '')

            # Формируем сообщение
            if saved_min and saved_max:
                if saved_min == saved_max:
                    message = f"✅ Фильтр {filter_name} установлен: {saved_min}"
                else:
                    message = f"✅ Фильтр {filter_name} установлен: {saved_min} - {saved_max}"
            elif saved_min:
                message = f"✅ Фильтр {filter_name} установлен: от {saved_min}"
            elif saved_max:
                message = f"✅ Фильтр {filter_name} установлен: до {saved_max}"
            else:
                message = f"✅ Фильтр {filter_name} отключен"

            # Добавляем единицы измерения
            if filter_type == 'capacity' and saved_max != 0 and saved_min != 0:
                message += " т"
            elif filter_type == 'volume' and saved_max != 0 and saved_min != 0:
                message += " м³"
            elif filter_type == 'price' and saved_max != 0 and saved_min != 0:
                if saved_min or saved_max:
                    # Форматируем цены
                    if saved_min:
                        min_formatted = f"{int(saved_min):,}".replace(',', ' ')
                        message = message.replace(str(saved_min), min_formatted)
                    if saved_max:
                        max_formatted = f"{int(saved_max):,}".replace(',', ' ')
                        message = message.replace(str(saved_max), max_formatted)
                    message += " ₽"

            bot.send_message(chat_id, message, parse_mode='Markdown')

            # Возвращаем к меню фильтров
            show_filter_menu(bot, db, user_id, chat_id)

    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректное число.")


def handle_date_filter(bot, db, chat_id, user_id, filter_key, text, state):
    """Обработка фильтра даты"""
    try:
        today = datetime.now().date()

        # Обработка предустановленных периодов
        if text == "❌ Без ограничений":
            filters = ExecutorFilters(db, user_id)
            filters.update_filter('loading_date_from', None)
            filters.update_filter('loading_date_to', None)
            del filter_states[user_id]
            bot.send_message(chat_id, "✅ Фильтр даты отключен.", reply_markup=ReplyKeyboardRemove())
            show_filter_menu(bot, db, user_id, chat_id)
            return

        elif text == "📅 Сегодня":
            date_from = today.strftime('%Y-%m-%d')
            date_to = today.strftime('%Y-%m-%d')

        elif text == "📅 Завтра":
            tomorrow = today + timedelta(days=1)
            date_from = tomorrow.strftime('%Y-%m-%d')
            date_to = tomorrow.strftime('%Y-%m-%d')

        elif text == "📅 Неделя":
            date_from = today.strftime('%Y-%m-%d')
            date_to = (today + timedelta(days=7)).strftime('%Y-%m-%d')

        elif text == "📅 Месяц":
            date_from = today.strftime('%Y-%m-%d')
            date_to = (today + timedelta(days=30)).strftime('%Y-%m-%d')

        else:
            # Пытаемся распарсить дату
            try:
                # Формат ДД.ММ.ГГГГ
                if '.' in text:
                    date_obj = datetime.strptime(text, '%d.%m.%Y').date()
                # Формат ДД-ММ-ГГГГ
                elif '-' in text:
                    date_obj = datetime.strptime(text, '%d-%m-%Y').date()
                # Формат ГГГГ-ММ-ДД
                else:
                    date_obj = datetime.strptime(text, '%Y-%m-%d').date()

                date_from = date_obj.strftime('%Y-%m-%d')
                date_to = date_obj.strftime('%Y-%m-%d')

            except ValueError:
                bot.send_message(
                    chat_id,
                    "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или выберите из вариантов."
                )
                return

        filters = ExecutorFilters(db, user_id)

        if state.get('step') == 1:
            # Первая дата (начало периода)
            filters.update_filter('loading_date_from', date_from)

            state['waiting_for'] = 'loading_date_to'
            state['step'] = 2

            bot.send_message(
                chat_id,
                "Введите конечную дату периода (или ту же дату для одного дня):\n\n"
                "Формат: ДД.ММ.ГГГГ"
            )

        elif state.get('step') == 2:
            # Вторая дата (конец периода)
            filters.update_filter('loading_date_to', date_to)

            del filter_states[user_id]

            date_from_display = filters.filters.get('loading_date_from')
            date_to_display = date_to

            if date_from_display == date_to_display:
                date_str = datetime.strptime(date_from_display, '%Y-%m-%d').strftime('%d.%m.%Y')
                message = f"✅ Фильтр даты установлен на: {date_str}"
            else:
                date_from_str = datetime.strptime(date_from_display, '%Y-%m-%d').strftime('%d.%m.%Y')
                date_to_str = datetime.strptime(date_to_display, '%Y-%m-%d').strftime('%d.%m.%Y')
                message = f"✅ Фильтр даты установлен на период: {date_from_str} - {date_to_str}"

            bot.send_message(chat_id, message, reply_markup=ReplyKeyboardRemove(),  parse_mode='Markdown')
            show_filter_menu(bot, db, user_id, chat_id)

    except Exception as e:
        print(f"❌ Ошибка обработки даты: {e}")
        bot.send_message(chat_id, "❌ Ошибка обработки даты.")


def handle_city_filter(bot, db, chat_id, user_id, filter_key, text, state):
    """Обработка фильтра городов"""
    if text == "❌ Без ограничений":
        filters = ExecutorFilters(db, user_id)
        filters.update_filter(filter_key, [])
        del filter_states[user_id]

        # Показываем сообщение и возвращаем в меню фильтров
        bot.send_message(
            chat_id,
            "✅ Фильтр городов отключен.",
            parse_mode='Markdown'
        )

        # Ждем секунду и показываем меню
        import time
        time.sleep(1)
        show_filter_menu(bot, db, user_id, chat_id)
        return

    # Разделяем города по запятой
    cities = [city.strip() for city in text.split(',') if city.strip()]

    if not cities:
        bot.send_message(chat_id, "❌ Введите хотя бы один город.")
        return

    filters = ExecutorFilters(db, user_id)

    # Сохраняем города как есть (оригинальные названия)
    filters.update_filter(filter_key, cities)

    del filter_states[user_id]

    city_name = "погрузки" if filter_key == 'loading_city' else "выгрузки"

    # Показываем сообщение
    message = bot.send_message(
        chat_id,
        f"✅ Фильтр городов {city_name} сохранен.\n\n**Выбранные города:** {', '.join(cities)}",
        parse_mode='Markdown'
    )

    # Через 2 секунды возвращаемся к меню фильтров
    import threading
    def return_to_menu():
        import time
        time.sleep(2)
        try:
            bot.delete_message(chat_id, message.message_id)
        except:
            pass
        show_filter_menu(bot, db, user_id, chat_id)

    threading.Thread(target=return_to_menu).start()


def show_city_filter(bot, db, chat_id, filters, message_id, filter_key):
    """Показывает текущие настройки фильтра городов"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    selected_cities = filters.filters.get(filter_key, [])

    city_name = "погрузки" if filter_key == 'loading_city' else "выгрузки"

    # Кнопка для добавления новых городов
    keyboard.add(
        InlineKeyboardButton(
            "➕ Добавить города",
            callback_data=f"{filter_key}_add"
        )
    )

    # Показываем текущие города (если есть)
    if selected_cities:
        for city in selected_cities:
            keyboard.add(
                InlineKeyboardButton(
                    f"❌ {city}",
                    callback_data=f"{filter_key}_remove_{city}"
                )
            )

        keyboard.add(
            InlineKeyboardButton(
                "🗑️ Очистить все",
                callback_data=f"{filter_key}_clear"
            )
        )

    keyboard.row(InlineKeyboardButton("🔙 Назад", callback_data="back_to_filters"))

    message_text = f"🏙️ **ФИЛЬТР ГОРОДА {city_name.upper()}**\n\n"

    if selected_cities:
        message_text += f"**Выбрано городов:** {len(selected_cities)}\n"
        message_text += f"**Список:** {', '.join(selected_cities[:5])}"
        if len(selected_cities) > 5:
            message_text += f" и ещё {len(selected_cities) - 5}"
    else:
        message_text += "❌ Не установлен"

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"❌ Ошибка редактирования сообщения городов: {e}")

def check_filters_for_application(filters, application_data):
    """
    Проверяет, соответствует ли заявка фильтрам перевозчика.

    Args:
        filters (dict): Фильтры перевозчика из ExecutorFilters
        application_data (dict): Данные новой заявки

    Returns:
        tuple: (bool, str) - (проходит ли фильтры, причина отказа если не проходит)
    """

    # 1. Фильтр по типу груза
    if filters.get('cargo_type') and len(filters['cargo_type']) > 0:
        cargo_type = application_data.get('cargo_type')
        if cargo_type not in filters['cargo_type']:
            return False, f"Тип груза '{cargo_type}' не входит в выбранные типы"

    # 2. Фильтр по категории груза
    if filters.get('cargo_category') and len(filters['cargo_category']) > 0:
        cargo_category = application_data.get('cargo_category')
        if cargo_category not in filters['cargo_category']:
            return False, f"Категория груза '{cargo_category}' не входит в выбранные категории"

    # 3. Фильтр по типу транспорта
    if filters.get('vehicle_type') and len(filters['vehicle_type']) > 0:
        vehicle_type = application_data.get('vehicle_type')
        if vehicle_type not in filters['vehicle_type']:
            return False, f"Тип транспорта '{vehicle_type}' не входит в выбранные типы"

    # 4. Фильтр по грузоподъемности
    capacity_min_filter = filters.get('capacity_min')
    capacity_max_filter = filters.get('capacity_max')
    app_capacity_min = application_data.get('capacity_min')
    app_capacity_max = application_data.get('capacity_max')

    if capacity_min_filter is not None and app_capacity_max is not None:
        if float(capacity_min_filter) > float(app_capacity_max):
            return False, f"Минимальная грузоподъемность фильтра ({capacity_min_filter} т) > максимальной грузоподъемности заявки ({app_capacity_max} т)"

    if capacity_max_filter is not None and app_capacity_min is not None:
        if float(capacity_max_filter) < float(app_capacity_min):
            return False, f"Максимальная грузоподъемность фильтра ({capacity_max_filter} т) < минимальной грузоподъемности заявки ({app_capacity_min} т)"

    # 5. Фильтр по объему кузова
    volume_min_filter = filters.get('volume_min')
    volume_max_filter = filters.get('volume_max')
    app_volume_min = application_data.get('volume_min')
    app_volume_max = application_data.get('volume_max')

    if volume_min_filter is not None and app_volume_max is not None:
        if float(volume_min_filter) > float(app_volume_max):
            return False, f"Минимальный объем фильтра ({volume_min_filter} м³) > максимального объема заявки ({app_volume_max} м³)"

    if volume_max_filter is not None and app_volume_min is not None:
        if float(volume_max_filter) < float(app_volume_min):
            return False, f"Максимальный объем фильтра ({volume_max_filter} м³) < минимального объема заявки ({app_volume_min} м³)"

    # 6. Фильтр по цене
    price_min_filter = filters.get('price_min')
    price_max_filter = filters.get('price_max')

    # Определяем минимальную цену заявки
    app_price = application_data.get('min_price', 0)
    if app_price is None:
        app_price = 0

    if price_min_filter is not None:
        if float(price_min_filter) > float(app_price):
            return False, f"Минимальная цена фильтра ({price_min_filter} руб.) > цены заявки ({app_price} руб.)"

    if price_max_filter is not None:
        if float(price_max_filter) < float(app_price):
            return False, f"Максимальная цена фильтра ({price_max_filter} руб.) < цены заявки ({app_price} руб.)"

    # 7. Фильтр по дате погрузки
    loading_date_from = filters.get('loading_date_from')
    loading_date_to = filters.get('loading_date_to')
    app_loading_date = application_data.get('loading_date')

    if app_loading_date:
        if loading_date_from and app_loading_date < loading_date_from:
            return False, f"Дата погрузки заявки ({app_loading_date}) раньше начала периода фильтра ({loading_date_from})"

        if loading_date_to and app_loading_date > loading_date_to:
            return False, f"Дата погрузки заявки ({app_loading_date}) позже конца периода фильтра ({loading_date_to})"

    # 8. Фильтр по городам погрузки
    loading_cities_filter = filters.get('loading_city')
    app_loading_cities = application_data.get('loading_cities', [])

    if loading_cities_filter and len(loading_cities_filter) > 0 and app_loading_cities:
        city_match = False
        for city_filter in loading_cities_filter:
            for app_city in app_loading_cities:
                if city_filter.lower() in app_city.lower():
                    city_match = True
                    break
            if city_match:
                break

        if not city_match:
            return False, f"Города погрузки заявки ({', '.join(app_loading_cities)}) не соответствуют фильтру"

    # 9. Фильтр по городам выгрузки
    unloading_cities_filter = filters.get('unloading_city')
    app_unloading_cities = application_data.get('unloading_cities', [])

    if unloading_cities_filter and len(unloading_cities_filter) > 0 and app_unloading_cities:
        city_match = False
        for city_filter in unloading_cities_filter:
            for app_city in app_unloading_cities:
                if city_filter.lower() in app_city.lower():
                    city_match = True
                    break
            if city_match:
                break

        if not city_match:
            return False, f"Города выгрузки заявки ({', '.join(app_unloading_cities)}) не соответствуют фильтру"

    # 10. Фильтр по типу заявки
    app_type_filter = filters.get('application_type')
    app_application_type = application_data.get('application_type')

    if app_type_filter and len(app_type_filter) > 0:
        if app_application_type not in app_type_filter:
            return False, f"Тип заявки '{app_application_type}' не входит в выбранные типы"

    # 11. Фильтр "Только активные" - всегда true для новых заявок
    # 12. Фильтр "Без моего отклика" - не применим для новых заявок

    # Все фильтры пройдены
    return True, "Заявка соответствует всем фильтрам"


def prepare_application_data_for_filter_check(application, points):
    """
    Подготавливает данные заявки из БД для проверки фильтрами.

    Args:
        application (dict): Данные заявки из БД
        points (list): Точки маршрута из БД

    Returns:
        dict: Подготовленные данные для проверки фильтрами
    """
    data = {
        'cargo_type': application.get('cargo_type'),
        'cargo_category': application.get('cargo_category'),
        'vehicle_type': application.get('vehicle_type'),
        'application_type': application.get('application_type'),
        'loading_cities': [],
        'unloading_cities': [],
    }

    # Числовые значения
    for key in ['capacity_min', 'capacity_max', 'volume_min', 'volume_max', 'weight', 'volume']:
        if key in application and application[key] is not None:
            try:
                data[key] = float(application[key])
            except (ValueError, TypeError):
                data[key] = 0

    # Дата погрузки
    if 'loading_datetime' in application and application['loading_datetime']:
        data['loading_date'] = application['loading_datetime'].split(' ')[0]  # Берем только дату

    # Города погрузки и выгрузки
    loading_points = [p for p in points if p['point_type'] == 'loading']
    unloading_points = [p for p in points if p['point_type'] == 'unloading']

    for point in loading_points:
        if point.get('city'):
            data['loading_cities'].append(point['city'])

    for point in unloading_points:
        if point.get('city'):
            data['unloading_cities'].append(point['city'])

    # Цена/бюджет
    if application.get('application_type') == 'fixed':
        # Для фиксированных заявок берем минимальную цену из payment_options
        payment_options_str = application.get('payment_options', '{}')
        try:
            payment_options = json.loads(payment_options_str) if payment_options_str else {}
        except:
            payment_options = {}

        prices = []
        for key in ['nds', 'ip', 'self-employed', 'cash']:
            if key in payment_options and payment_options[key]:
                try:
                    prices.append(float(payment_options[key]))
                except (ValueError, TypeError):
                    pass

        if prices:
            data['min_price'] = min(prices)
        elif application.get('fixed_price'):
            try:
                data['min_price'] = float(application['fixed_price'])
            except (ValueError, TypeError):
                data['min_price'] = 0
        else:
            data['min_price'] = 0
    else:
        # Для аукциона берем desired_budget
        if application.get('desired_budget'):
            try:
                data['min_price'] = float(application['desired_budget'])
            except (ValueError, TypeError):
                data['min_price'] = 0
        else:
            data['min_price'] = 0

    return data

