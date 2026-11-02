import json
from datetime import datetime, timezone, timedelta
from telebot.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, \
    InlineKeyboardButton
from config.config import config
from handlers.main_handlers.executor_filter_handlers import check_filters_for_application
from keyboards.application_keyboards import *
from keyboards.main_menus import get_main_menu
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from utils.dicts import CARGO_TYPE_MAPPING, VEHICLE_TYPE_MAPPING, \
    CARGO_TYPE_REVERSE_MAPPING, VEHICLE_TYPE_REVERSE_MAPPING
from utils.filters import ExecutorFilters

application_temp_data = {}
MSK = timezone(timedelta(hours=3))


def register_application_handlers(bot, db):
    @bot.message_handler(func=lambda message: message.text == '📥 Создать заявку')
    def start_application_creation(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)

        if (user['phone'] is None) or (user['email'] is None) or (user['ati_code'] is None) or (
                user['first_name'] is None) or (user['last_name'] is None) or (user['company_id'] is None):
            bot.send_message(
                chat_id,
                "❌ **Недостаточно данных для принятия заявок**\n\n"
                "📋 **Для работы с заявками необходимо заполнить:**\n"
                "• 👤 Имя\n"
                "• 👤 Фамилия\n"
                "• 🏢 Компания\n"
                "• 📞 Телефон\n"
                "• 📧 Email\n\n"
                "⚙️ **Как исправить:**\n"
                "1. Откройте меню ⚙️**Настройки**\n"
                "2. Выберите 👤**Мой профиль**\n"
                "3. Добавьте недостающие данные\n\n"
                "✅ После заполнения всех полей вы сможете создавать заявки!",
            )
            return

        if user['status'] != 'active':
            bot.send_message(chat_id, "❌ Администратор не подтвердил вашу учетную запись.")
            return

        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'admin', 'external_logist', 'external_admin']:
            bot.send_message(
                chat_id,
                "❌ Создавать заявки могут только логисты.",
                reply_markup=get_main_menu(user_role)
            )
            return

        application_temp_data[user_id] = {
            'step': 1,
            'application_type': None,
            'desired_budget': None,
            'loading_points': [],  # Массив точек погрузки с датами
            'unloading_points': [],  # Массив точек выгрузки с датами
            'current_point_type': None,  # 'loading' или 'unloading'
            'current_point_city': None,
            'cargo_type': None,
            'cargo_custom_type': None,
            'cargo_category': None,
            'cargo_custom_category': None,
            'weight': None,
            'volume': None,
            'loading_method': None,
            'vehicle_type': None,
            'payment_options': {},
            'payment_deadline': None,
            'contact_phone': None,
            'contact_email': None,
            'notes': None,
        }

        bot.send_message(
            chat_id,
            "📋 **Создание новой заявки**\n\n"
            "🎯 **Шаг 1: Выберите тип заявки:**\n\n"
            "• 📦 **СТАНДАРТНАЯ** - с фиксированной ставкой\n"
            "• 🏷️ **ЗАПРОС СТАВОК** - аукцион с вашим бюджетом\n",
            reply_markup=get_application_type_keyboard(),
            parse_mode='Markdown'
        )
        set_user_state(user_id, 'waiting_for_application_type')

    # Шаг 1: Тип заявки
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_application_type')
    def handle_application_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🕹 Выберите действие из меню:",
                reply_markup=get_main_menu(db.get_user_role(user_id)['role'])
            )
            set_user_state(user_id, 'main_menu')
            return

        if message.text == "📦 СТАНДАРТНАЯ (с фиксированной ставкой)":
            application_temp_data[user_id]['application_type'] = 'fixed'
            # Для фиксированной заявки переходим сразу к шагу 2 (маршрут)
            # Ставки будут вводиться на шаге 5
            go_to_step_2(bot, user_id, chat_id)

        elif message.text == "🏷️ ЗАПРОС СТАВОК (Аукцион)":
            application_temp_data[user_id]['application_type'] = 'auction'
            bot.send_message(
                chat_id,
                "🎯 Введите ваш желаемый бюджет (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_desired_budget')
        else:
            bot.send_message(chat_id, "❌ Пожалуйста, выберите тип заявки из предложенных вариантов.")

    # Удален обработчик handle_fixed_price

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_desired_budget')
    def handle_desired_budget(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        try:
            budget = float(message.text.replace(',', '.').replace(' ', ''))
            if budget <= 0:
                bot.send_message(chat_id, "❌ Бюджет должен быть больше 0. Введите корректную сумму:")
                return

            application_temp_data[user_id]['desired_budget'] = budget
            go_to_step_2(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректную сумму (только цифры):")

    def go_to_step_2(bot, user_id, chat_id):
        application_temp_data[user_id]['step'] = 2
        show_route_status(bot, user_id, chat_id)

    def show_route_status(bot, user_id, chat_id):
        """Показывает текущее состояние маршрута и меню управления"""
        data = application_temp_data[user_id]

        status_text = "🗺️ **Управление маршрутом**\n\n"

        # Показываем добавленные точки погрузки
        if data['loading_points']:
            status_text += "**📍 Точки погрузки:**\n"
            for i, point in enumerate(data['loading_points'], 1):
                status_text += f"{i}. **{point['city']}**, {point['address']}\n"
                if point.get('datetime'):
                    status_text += f"   📅 {point['datetime'].strftime('%d.%m.%Y %H:%M')}\n"
            status_text += "\n"
        else:
            status_text += "📍 **Точки погрузки:** не добавлены\n\n"

        # Показываем добавленные точки выгрузки
        if data['unloading_points']:
            status_text += "**🏁 Точки выгрузки:**\n"
            for i, point in enumerate(data['unloading_points'], 1):
                status_text += f"{i}. **{point['city']}**, {point['address']}\n"
                if point.get('datetime'):
                    status_text += f"   📅 {point['datetime'].strftime('%d.%m.%Y %H:%M')}\n"
            status_text += "\n"
        else:
            status_text += "🏁 **Точки выгрузки:** не добавлены\n\n"

        status_text += "Выберите действие:"

        bot.send_message(
            chat_id,
            status_text,
            reply_markup=get_route_management_keyboard(
                has_loading=len(data['loading_points']) > 0,
                has_unloading=len(data['unloading_points']) > 0
            ),
            parse_mode='Markdown'
        )

        # Проверяем, в каком мы режиме - создание или редактирование
        if get_user_state(user_id) in ['waiting_for_edit_route', 'waiting_for_point_deletion_edit', 'waiting_for_point_time_edit']:
            set_user_state(user_id, 'waiting_for_edit_route_management')
        else:
            set_user_state(user_id, 'waiting_for_route_management')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_route_management')
    def handle_route_management(message):
        """Обработка управления маршрутом в режиме создания заявки"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        data = application_temp_data[user_id]

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🎯 Выберите тип заявки:",
                reply_markup=get_application_type_keyboard()
            )
            set_user_state(user_id, 'waiting_for_application_type')
            return

        elif message.text == "[➕] Добавить точку погрузки":
            application_temp_data[user_id]['current_point_type'] = 'loading'
            bot.send_message(
                chat_id,
                "📍 **Добавление точки погрузки**\n\n"
                "Введите название города погрузки:\n"
                "Пример: Москва",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_city_input_create')

        elif message.text == "[➕] Добавить точку выгрузки":
            application_temp_data[user_id]['current_point_type'] = 'unloading'
            bot.send_message(
                chat_id,
                "📍 **Добавление точки выгрузки**\n\n"
                "Введите название города выгрузки:\n"
                "Пример: Санкт-Петербург",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_city_input_create')

        elif message.text == "❌ Удалить точку":
            show_points_for_deletion(bot, user_id, chat_id, mode='create')

        elif message.text == "✅ Завершить маршрут":
            if len(data['loading_points']) == 0:
                bot.send_message(
                    chat_id,
                    "❌ Необходимо добавить хотя бы одну точку погрузки."
                )
                show_route_status(bot, user_id, chat_id)
                return

            if len(data['unloading_points']) == 0:
                bot.send_message(
                    chat_id,
                    "❌ Необходимо добавить хотя бы одну точку выгрузки."
                )
                show_route_status(bot, user_id, chat_id)
                return

            go_to_step_3(bot, user_id, chat_id)

    def show_points_for_deletion(bot, user_id, chat_id, mode='create'):
        """Показывает список точек для удаления с учетом режима"""
        data = application_temp_data[user_id]

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)

        # Добавляем точки погрузки для удаления
        if data['loading_points']:
            for i, point in enumerate(data['loading_points'], 1):
                keyboard.add(KeyboardButton(f"❌ Погрузка {i}: {point['city']}"))

        # Добавляем точки выгрузки для удаления
        if data['unloading_points']:
            for i, point in enumerate(data['unloading_points'], 1):
                keyboard.add(KeyboardButton(f"❌ Выгрузка {i}: {point['city']}"))

        keyboard.add(KeyboardButton("⬅️ Назад"))

        bot.send_message(
            chat_id,
            "🗑️ **Выберите точку для удаления:**",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        # Устанавливаем состояние в зависимости от режима
        if mode == 'edit':
            set_user_state(user_id, 'waiting_for_point_deletion_edit')
        else:
            set_user_state(user_id, 'waiting_for_point_deletion_create')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_point_deletion_create')
    def handle_point_deletion_create(message):
        """Обработка удаления точки в режиме создания заявки"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        data = application_temp_data[user_id]

        if message.text == "⬅️ Назад":
            show_route_status(bot, user_id, chat_id)
            return

        # Парсим выбор пользователя
        text = message.text
        if text.startswith("❌ Погрузка"):
            try:
                # Извлекаем номер точки
                index_part = text.split(":")[0].replace("❌ Погрузка", "").strip()
                index = int(index_part) - 1
                if 0 <= index < len(data['loading_points']):
                    removed = data['loading_points'].pop(index)
                    bot.send_message(chat_id, f"✅ Точка погрузки '{removed['city']}' удалена.")
            except (ValueError, IndexError):
                bot.send_message(chat_id, "❌ Не удалось удалить точку.")

        elif text.startswith("❌ Выгрузка"):
            try:
                # Извлекаем номер точки
                index_part = text.split(":")[0].replace("❌ Выгрузка", "").strip()
                index = int(index_part) - 1
                if 0 <= index < len(data['unloading_points']):
                    removed = data['unloading_points'].pop(index)
                    bot.send_message(chat_id, f"✅ Точка выгрузки '{removed['city']}' удалена.")
            except (ValueError, IndexError):
                bot.send_message(chat_id, "❌ Не удалось удалить точку.")

        # Возвращаемся к управлению маршрутом
        show_route_status(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_point_deletion_edit')
    def handle_point_deletion_edit(message):
        """Обработка удаления точки в режиме редактирования заявки"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        data = application_temp_data[user_id]

        if message.text == "⬅️ Назад":
            show_route_status(bot, user_id, chat_id)
            return

        # Парсим выбор пользователя
        text = message.text
        if text.startswith("❌ Погрузка"):
            try:
                # Извлекаем номер точки
                index_part = text.split(":")[0].replace("❌ Погрузка", "").strip()
                index = int(index_part) - 1
                if 0 <= index < len(data['loading_points']):
                    removed = data['loading_points'].pop(index)
                    bot.send_message(chat_id, f"✅ Точка погрузки '{removed['city']}' удалена.")
            except (ValueError, IndexError):
                bot.send_message(chat_id, "❌ Не удалось удалить точку.")

        elif text.startswith("❌ Выгрузка"):
            try:
                # Извлекаем номер точки
                index_part = text.split(":")[0].replace("❌ Выгрузка", "").strip()
                index = int(index_part) - 1
                if 0 <= index < len(data['unloading_points']):
                    removed = data['unloading_points'].pop(index)
                    bot.send_message(chat_id, f"✅ Точка выгрузки '{removed['city']}' удалена.")
            except (ValueError, IndexError):
                bot.send_message(chat_id, "❌ Не удалось удалить точку.")

        # Возвращаемся к управлению маршрутом в режиме редактирования
        show_route_status(bot, user_id, chat_id)

    # Обработчик ввода города для режима создания
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_city_input_create')
    def handle_city_input_create(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_route_status(bot, user_id, chat_id)
            return

        city = message.text.strip()
        application_temp_data[user_id]['current_point_city'] = city

        point_type = application_temp_data[user_id]['current_point_type']
        point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

        bot.send_message(
            chat_id,
            f"✅ Город {point_type_text} сохранен: {city}\n\n"
            f"Теперь введите полный адрес {point_type_text} (улица, дом, помещение):\n"
            f"Пример: ул. Тверская, д. 12, офис 34",
        )
        set_user_state(user_id, 'waiting_for_address_input_create')

    # Обработчик ввода города для режима редактирования
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_city_input_edit')
    def handle_city_input_edit(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_route_status(bot, user_id, chat_id)
            return

        city = message.text.strip()
        application_temp_data[user_id]['current_point_city'] = city

        point_type = application_temp_data[user_id]['current_point_type']
        point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

        bot.send_message(
            chat_id,
            f"✅ Город {point_type_text} сохранен: {city}\n\n"
            f"Теперь введите полный адрес {point_type_text} (улица, дом, помещение):\n"
            f"Пример: ул. Тверская, д. 12, офис 34",
        )
        set_user_state(user_id, 'waiting_for_address_input_edit')

    # Обработчик ввода адреса для режима создания
    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_address_input_create')
    def handle_address_input_create(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        point_type = application_temp_data[user_id]['current_point_type']
        point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                f"📍 **Добавление точки {point_type_text}**\n\n"
                f"Введите название города {point_type_text}:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_city_input_create')
            return

        address = message.text.strip()
        city = application_temp_data[user_id]['current_point_city']

        application_temp_data[user_id]['temp_point_address'] = address
        application_temp_data[user_id]['temp_point_city'] = city

        bot.send_message(
            chat_id,
            f"📅 Введите дату {point_type_text} в формате ДД.ММ.ГГГГ:\n"
            f"Пример: 15.01.2024",
            reply_markup=ReplyKeyboardRemove()
        )
        set_user_state(user_id, 'waiting_for_point_date_create')

    # Обработчик ввода адреса для режима редактирования
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_address_input_edit')
    def handle_address_input_edit(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        point_type = application_temp_data[user_id]['current_point_type']
        point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                f"📍 **Добавление точки {point_type_text}**\n\n"
                f"Введите название города {point_type_text}:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_city_input_edit')
            return

        address = message.text.strip()
        city = application_temp_data[user_id]['current_point_city']

        application_temp_data[user_id]['temp_point_address'] = address
        application_temp_data[user_id]['temp_point_city'] = city

        bot.send_message(
            chat_id,
            f"📅 Введите дату {point_type_text} в формате ДД.ММ.ГГГГ:\n"
            f"Пример: 15.01.2024",
            reply_markup=ReplyKeyboardRemove()
        )
        set_user_state(user_id, 'waiting_for_point_date_edit')

    # Обработчик ввода даты для режима создания
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_point_date_create')
    def handle_point_date_create(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Введите полный адрес:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_address_input_create')
            return

        try:
            date = datetime.strptime(message.text, '%d.%m.%Y')
            if date.date() < datetime.now().date():
                bot.send_message(chat_id, "❌ Дата не может быть в прошлом. Введите корректную дату:")
                return

            application_temp_data[user_id]['temp_point_date'] = date

            point_type = application_temp_data[user_id]['current_point_type']
            point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

            bot.send_message(
                chat_id,
                f"⏰ Введите время {point_type_text} в формате ЧЧ:ММ:\n"
                f"Пример: 14:30",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_point_time_create')

        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГЧ:")

    # Обработчик ввода даты для режима редактирования
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_point_date_edit')
    def handle_point_date_edit(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Введите полный адрес:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_address_input_edit')
            return

        try:
            date = datetime.strptime(message.text, '%d.%m.%Y')
            if date.date() < datetime.now().date():
                bot.send_message(chat_id, "❌ Дата не может быть в прошлом. Введите корректную дату:")
                return

            application_temp_data[user_id]['temp_point_date'] = date

            point_type = application_temp_data[user_id]['current_point_type']
            point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

            bot.send_message(
                chat_id,
                f"⏰ Введите время {point_type_text} в формате ЧЧ:ММ:\n"
                f"Пример: 14:30",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_point_time_edit')

        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГЧ:")

    # Обработчик ввода времени для режима создания
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_point_time_create')
    def handle_point_time_create(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Введите дату в формате ДД.ММ.ГГГГ:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_point_date_create')
            return

        try:
            time_obj = datetime.strptime(message.text, '%H:%M').time()
            date = application_temp_data[user_id]['temp_point_date']
            point_datetime = datetime.combine(date.date(), time_obj)

            city = application_temp_data[user_id]['temp_point_city']
            address = application_temp_data[user_id]['temp_point_address']
            point_type = application_temp_data[user_id]['current_point_type']
            point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

            # Создаем точку с данными
            point_data = {
                'city': city,
                'address': address,
                'full_address': f"{city}, {address}",
                'datetime': point_datetime
            }

            # Сохраняем в соответствующий массив
            if point_type == 'loading':
                application_temp_data[user_id]['loading_points'].append(point_data)
            else:
                application_temp_data[user_id]['unloading_points'].append(point_data)

            # Очищаем временные данные
            temp_fields = ['temp_point_date', 'temp_point_city', 'temp_point_address']
            for field in temp_fields:
                if field in application_temp_data[user_id]:
                    del application_temp_data[user_id][field]

            bot.send_message(
                chat_id,
                f"✅ Точка {point_type_text} сохранена:\n"
                f"🏙️ Город: {city}\n"
                f"📍 Адрес: {address}\n"
                f"📅 Дата/время: {point_datetime.strftime('%d.%m.%Y %H:%M')}\n",
                reply_markup=ReplyKeyboardRemove()
            )

            show_route_status(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат времени. Используйте ЧЧ:ММ:")

    # Обработчик ввода времени для режима редактирования
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_point_time_edit')
    def handle_point_time_edit(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Введите дату в формате ДД.ММ.ГГГГ:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_point_date_edit')
            return

        try:
            time_obj = datetime.strptime(message.text, '%H:%M').time()
            date = application_temp_data[user_id]['temp_point_date']
            point_datetime = datetime.combine(date.date(), time_obj)

            city = application_temp_data[user_id]['temp_point_city']
            address = application_temp_data[user_id]['temp_point_address']
            point_type = application_temp_data[user_id]['current_point_type']
            point_type_text = "погрузки" if point_type == 'loading' else "выгрузки"

            # Создаем точку с данными
            point_data = {
                'city': city,
                'address': address,
                'full_address': f"{city}, {address}",
                'datetime': point_datetime
            }

            # Сохраняем в соответствующий массив
            if point_type == 'loading':
                application_temp_data[user_id]['loading_points'].append(point_data)
            else:
                application_temp_data[user_id]['unloading_points'].append(point_data)

            # Очищаем временные данные
            temp_fields = ['temp_point_date', 'temp_point_city', 'temp_point_address']
            for field in temp_fields:
                if field in application_temp_data[user_id]:
                    del application_temp_data[user_id][field]

            bot.send_message(
                chat_id,
                f"✅ Точка {point_type_text} сохранена:\n"
                f"🏙️ Город: {city}\n"
                f"📍 Адрес: {address}\n"
                f"📅 Дата/время: {point_datetime.strftime('%d.%m.%Y %H:%M')}\n",
                reply_markup=ReplyKeyboardRemove()
            )

            show_route_status(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат времени. Используйте ЧЧ:ММ:")

    def go_to_step_3(bot, user_id, chat_id):
        application_temp_data[user_id]['step'] = 3

        bot.send_message(
            chat_id,
            "📦 **Шаг 3: Характер груза, вес, объем, требуемый транспорт**\n\n"
            "Сначала выберите характер груза:",
            reply_markup=get_cargo_type_keyboard()
        )
        set_user_state(user_id, 'waiting_for_cargo_type')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_cargo_type')
    def handle_cargo_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            if application_temp_data[user_id]['step'] == 3:
                show_route_status(bot, user_id, chat_id)
            else:
                show_application_summary(bot, user_id, chat_id)
            return

        if message.text == "📝 ПРОЧЕЕ":
            bot.send_message(
                chat_id,
                "✏️ Введите характер груза:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_custom_cargo_type')
            return

        valid_types = ["✅ Обычный", "🥪 Скоропортящийся", "⚠️ Опасный", "🔔 Хрупкий",
                       "📱 ТНП", "🔌 Бытовая техника", "🧪 Бытовая химия"]

        if message.text in valid_types:
            cargo_type = CARGO_TYPE_MAPPING.get(message.text)
            application_temp_data[user_id]['cargo_type'] = cargo_type
            application_temp_data[user_id]['cargo_custom_type'] = 'Не указан'

            bot.send_message(
                chat_id,
                "⚖️ Введите вес груза (в тоннах):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_cargo_weight')
        else:
            bot.send_message(chat_id, "❌ Пожалуйста, выберите характер груза из предложенных вариантов.")

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_custom_cargo_type')
    def handle_custom_cargo_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        custom_type = message.text
        application_temp_data[user_id]['cargo_custom_type'] = custom_type
        application_temp_data[user_id]['cargo_type'] = "ПРОЧЕЕ"

        bot.send_message(
            chat_id,
            "⚖️ Введите вес груза (в тоннах):",
            reply_markup=ReplyKeyboardRemove()
        )
        set_user_state(user_id, 'waiting_for_cargo_weight')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_cargo_weight')
    def handle_cargo_weight(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "📦 Выберите характер груза:",
                reply_markup=get_cargo_type_keyboard()
            )
            set_user_state(user_id, 'waiting_for_cargo_type')
            return

        try:
            weight = float(message.text.replace(',', '.'))
            if weight <= 0:
                bot.send_message(chat_id, "❌ Вес должен быть больше 0. Введите корректное значение:")
                return

            application_temp_data[user_id]['weight'] = weight

            bot.send_message(
                chat_id,
                "📏 Введите объем груза (в м³):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_cargo_volume')

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректное число:")

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_cargo_volume')
    def handle_cargo_volume(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(chat_id, "Введите вес груза (в тоннах):")
            set_user_state(user_id, 'waiting_for_cargo_weight')
            return

        try:
            volume = float(message.text.replace(',', '.'))
            if volume <= 0:
                bot.send_message(chat_id, "❌ Объем должен быть больше 0. Введите корректное значение:")
                return

            application_temp_data[user_id]['volume'] = volume

            bot.send_message(
                chat_id,
                "🚛 **Требуемый транспорт**\n\n"
                "Выберите тип кузова:",
                reply_markup=get_vehicle_type_keyboard()
            )
            set_user_state(user_id, 'waiting_for_vehicle_type')

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректное число:")

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_vehicle_type')
    def handle_vehicle_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(chat_id, "Введите объем груза (в м³):")
            set_user_state(user_id, 'waiting_for_cargo_volume')
            return

        valid_types = ["📦 Тент", "🧊 Рефрижератор", "🌡️ Изотермический",
                       "🚚 Любой закрытый", "🚛 Открытая платформа", "📄 Промтоварный"]

        if message.text in valid_types:
            application_temp_data[user_id]['vehicle_type'] = VEHICLE_TYPE_MAPPING.get(message.text)

            bot.send_message(
                chat_id,
                "📝 **Шаг 4: Дополнительная информация**\n\n"
                "Введите примечания к заявке (необязательно):\n"
                "Пример: Срочная заявка, требуется срочная доставка",
                reply_markup=get_notes_keyboard()
            )
            set_user_state(user_id, 'waiting_for_notes')
        else:
            bot.send_message(chat_id, "❌ Пожалуйста, выберите тип кузова из предложенных вариантов.")

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_notes')
    def handle_notes(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🚛 Выберите тип кузова:",
                reply_markup=get_vehicle_type_keyboard()
            )
            set_user_state(user_id, 'waiting_for_vehicle_type')
            return

        if message.text == "⏭️ Пропустить":
            application_temp_data[user_id]['notes'] = 'Не указаны'
        else:
            application_temp_data[user_id]['notes'] = message.text.strip()

        go_to_step_5(bot, user_id, chat_id)

    def go_to_step_5(bot, user_id, chat_id):
        application_temp_data[user_id]['step'] = 5
        data = application_temp_data[user_id]

        if data['application_type'] == 'fixed':
            bot.send_message(
                chat_id,
                "💰 **Шаг 5: Способ оплаты**\n\n"
                "Введите ставку для **С НДС (22%)** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_nds_price')
        else:
            go_to_step_6(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_nds_price')
    def handle_nds_price(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if application_temp_data[user_id]['application_type'] != 'fixed':
            go_to_step_6(bot, user_id, chat_id)
            return

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(chat_id, "❌ Сумма должна быть больше 0. Введите корректную сумму:")
                return

            application_temp_data[user_id]['payment_options']['nds'] = price

            bot.send_message(
                chat_id,
                "Введите ставку **Без НДС** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_ip_price')

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректную сумму (только цифры):")

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_ip_price')
    def handle_ip_price(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if application_temp_data[user_id]['application_type'] != 'fixed':
            go_to_step_6(bot, user_id, chat_id)
            return

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(chat_id, "❌ Сумма должна быть больше 0. Введите корректную сумму:")
                return

            application_temp_data[user_id]['payment_options']['ip'] = price

            bot.send_message(
                chat_id,
                "Введите ставку для **Наличные** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_cash_price')

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректную сумму (только цифры):")

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_cash_price')
    def handle_cash_price(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if application_temp_data[user_id]['application_type'] != 'fixed':
            go_to_step_6(bot, user_id, chat_id)
            return

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(chat_id, "❌ Сумма должна быть больше 0. Введите корректную сумму:")
                return

            application_temp_data[user_id]['payment_options']['cash'] = price
            go_to_step_6(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректную сумму (только цифры):")

    def go_to_step_6(bot, user_id, chat_id):
        application_temp_data[user_id]['step'] = 6

        bot.send_message(
            chat_id,
            "📅 **Шаг 6: Сроки оплаты**\n\n"
            "Введите дату, до которой нужно оплатить заявку (в формате ДД.ММ.ГГГГ):\n"
            "Пример: 25.01.2024",
            reply_markup=get_payment_terms_keyboard()
        )
        set_user_state(user_id, 'waiting_for_payment_deadline')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_payment_deadline')
    def handle_payment_terms(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            data = application_temp_data[user_id]
            if data['application_type'] == 'fixed':
                bot.send_message(
                    chat_id,
                    "💰 Введите ставку для **Наличные** (в рублях):",
                    reply_markup=ReplyKeyboardRemove()
                )
                set_user_state(user_id, 'waiting_for_cash_price')
            else:
                go_to_step_5(bot, user_id, chat_id)
            return
        if message.text == "⏭️ Пропустить":
            application_temp_data[user_id]['payment_deadline'] = None
        else:
            try:
                deadline = datetime.strptime(message.text, '%d.%m.%Y')
                application_temp_data[user_id]['payment_deadline'] = deadline
            except ValueError:
                bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:")
                return

        user_info = db.get_user_by_telegram_id(user_id)
        application_temp_data[user_id]['contact_phone'] = user_info.get('phone', 'Не указан')
        application_temp_data[user_id]['contact_email'] = user_info.get('email', 'Не указан')

        go_to_summary(bot, user_id, chat_id)

    def go_to_summary(bot, user_id, chat_id):
        application_temp_data[user_id]['step'] = 7
        show_application_summary(bot, user_id, chat_id)

    def show_application_summary(bot, user_id, chat_id):
        data = application_temp_data[user_id]
        summary = format_application_summary(data)

        bot.send_message(
            chat_id,
            summary,
            reply_markup=get_application_preview_keyboard(),
            parse_mode='Markdown'
        )
        set_user_state(user_id, 'waiting_for_application_confirmation')

    def format_application_summary(data):
        """Форматирует сводку заявки с множественными точками"""

        if data['application_type'] == 'fixed':
            app_type_text = f"📦 СТАНДАРТНАЯ\n"
        else:
            app_type_text = f"🏷️ ЗАПРОС СТАВОК\n🎯 Желаемый бюджет: {data['desired_budget']:,.0f} руб.\n"

        route_text = ""

        if data['loading_points']:
            route_text += "**📍 Точки погрузки:**\n"
            for i, point in enumerate(data['loading_points'], 1):
                route_text += f"{i}. 🏙️ **{point['city']}**\n"
                route_text += f"   📍 Адрес: {point['address']}\n"
                if point.get('datetime'):
                    route_text += f"   📅 Дата/время: {point['datetime'].strftime('%d.%m.%Y %H:%M')}\n"
            route_text += "\n"

        if data['unloading_points']:
            route_text += "**🏁 Точки выгрузки:**\n"
            for i, point in enumerate(data['unloading_points'], 1):
                route_text += f"{i}. 🏙️ **{point['city']}**\n"
                route_text += f"   📍 Адрес: {point['address']}\n"
                if point.get('datetime'):
                    route_text += f"   📅 Дата/время: {point['datetime'].strftime('%d.%m.%Y %H:%M')}\n"
            route_text += "\n"

        if data['cargo_type'] == "ПРОЧЕЕ":
            cargo_type = data['cargo_custom_type']
        else:
            cargo_type = CARGO_TYPE_REVERSE_MAPPING.get(data['cargo_type'])

        cargo_text = f"📦 **Характер груза:** {cargo_type}\n"
        cargo_text += f"⚖️ **Вес:** {data['weight']} т\n"
        cargo_text += f"📏 **Объем:** {data['volume']} м³\n"
        cargo_text += f"🚛 **Тип кузова:** {VEHICLE_TYPE_REVERSE_MAPPING.get(data['vehicle_type'])}\n"

        payment_text = ""
        if data['application_type'] == 'fixed':
            payment_text = "💰 **Способ оплаты:**\n"
            if data['payment_options'].get('nds'):
                payment_text += f"   • С НДС (22%): {data['payment_options'].get('nds', 0):,.0f} руб.\n"
            if data['payment_options'].get('ip'):
                payment_text += f"   • Без НДС: {data['payment_options'].get('ip', 0):,.0f} руб.\n"
            if data['payment_options'].get('cash'):
                payment_text += f"   • Наличные: {data['payment_options'].get('cash', 0):,.0f} руб.\n"
            payment_text += "\n"

        payment_deadline_text = ""
        if data.get('payment_deadline'):
            # Проверяем тип данных
            if isinstance(data['payment_deadline'], datetime):
                payment_deadline_text = f"📅 **Срок оплаты:** до {data['payment_deadline'].strftime('%d.%m.%Y')}"
            else:
                # Если это строка, пробуем преобразовать или используем как есть
                try:
                    # Пробуем распарсить строку в дату
                    deadline_date = datetime.strptime(data['payment_deadline'], '%Y-%m-%d')
                    payment_deadline_text = f"📅 **Срок оплаты:** до {deadline_date.strftime('%d.%m.%Y')}"
                except:
                    # Если не получается, выводим как есть
                    payment_deadline_text = f"📅 **Срок оплаты:** до {data['payment_deadline']}"
        else:
            payment_deadline_text = "📅 **Срок оплаты:** Не указан"

        notes_text = ""
        if data.get('notes'):
            notes_text = f"📝 **Примечания:** {data['notes']}\n\n"

        contacts_text = f"👤 **Контакты:**\n"
        contacts_text += f"   📞 Телефон: {data['contact_phone']}\n"
        contacts_text += f"   📧 Email: {data['contact_email']}\n"

        summary = f"""
📋 **СВОДКА ЗАЯВКИ**

🎯 **Тип заявки:**
{app_type_text}
🗺️ **Маршрут:**
{route_text}
📦 **Груз и транспорт:**
{cargo_text}

{payment_text}
{payment_deadline_text}
{notes_text}
{contacts_text}

Проверьте данные и подтвердите создание заявки.
"""
        return summary

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_application_confirmation')
    def handle_application_confirmation(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "🟦 ✅ СОЗДАТЬ ЗАЯВКУ":
            create_application(bot, db, user_id, chat_id)

        elif message.text == "⚪ ✏️ Редактировать":
            bot.send_message(
                chat_id,
                "✏️ **Редактирование заявки**\n\n"
                "Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')

        elif message.text == "⚪ 🗑️ Отменить":
            if user_id in application_temp_data:
                del application_temp_data[user_id]
            bot.send_message(
                chat_id,
                "❌ Создание заявки отменено.",
                reply_markup=get_main_menu(db.get_user_role(user_id)['role'])
            )
            set_user_state(user_id, 'main_menu')

    def create_application(bot, db, user_id, chat_id):
        """Создает заявку в базе данных с множественными точками"""

        try:
            data = application_temp_data[user_id]

            payment_data = data['payment_options'].copy()
            payment_options_str = json.dumps(payment_data, ensure_ascii=False)

            payment_deadline = None
            if data.get('payment_deadline'):
                payment_deadline = data['payment_deadline'].strftime('%Y-%m-%d')

            # Сохраняем заявку в базу данных (без полей loading/unloading_datetime)
            cursor = db.execute_query(
                """INSERT INTO applications 
                (created_by, application_type, desired_budget,
                 cargo_type, cargo_custom_type, weight, volume, vehicle_type, 
                 payment_options, notes, contact_phone, contact_email, 
                 status, created_at, payment_deadline)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (user_id,
                 data['application_type'],
                 data.get('desired_budget'),
                 data['cargo_type'],
                 data.get('cargo_custom_type'),
                 data['weight'],
                 data['volume'],
                 data['vehicle_type'],
                 payment_options_str,
                 data.get('notes'),
                 data['contact_phone'],
                 data['contact_email'],
                 datetime.now(MSK).strftime('%Y-%m-%d %H:%M:%S'),
                 payment_deadline)
            )

            if cursor is None:
                raise Exception("Не удалось создать заявку в базе данных")

            application_id = cursor.lastrowid

            if not application_id:
                cursor = db.execute_query("SELECT last_insert_rowid()")
                if cursor:
                    result = cursor.fetchone()
                    if result:
                        application_id = result[0]

            if not application_id:
                raise Exception("Не удалось получить ID созданной заявки")

            # Сохраняем все точки погрузки с их датами и временем
            for i, point in enumerate(data['loading_points']):
                db.execute_query(
                    """INSERT INTO application_points 
                    (application_id, point_type, city, address, point_order, point_datetime)
                    VALUES (?, 'loading', ?, ?, ?, ?)""",
                    (application_id,
                     point['city'],
                     point.get('address', ''),
                     i,
                     point['datetime'].strftime('%Y-%m-%d %H:%M:%S'))
                )

            # Сохраняем все точки выгрузки с их датами и временем
            for i, point in enumerate(data['unloading_points']):
                db.execute_query(
                    """INSERT INTO application_points 
                    (application_id, point_type, city, address, point_order, point_datetime)
                    VALUES (?, 'unloading', ?, ?, ?, ?)""",
                    (application_id,
                     point['city'],
                     point.get('address', ''),
                     i,
                     point['datetime'].strftime('%Y-%m-%d %H:%M:%S'))
                )

            if user_id in application_temp_data:
                del application_temp_data[user_id]

            bot.send_message(
                chat_id,
                "✅ Заявка успешно создана и отправлена перевозчикам!",
                reply_markup=get_main_menu(db.get_user_role(user_id)['role'])
            )
            set_user_state(user_id, '')

            send_notifications_to_executors(bot, db, application_id, data)

        except Exception as e:
            print(f"Ошибка при создании заявки: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(
                chat_id,
                "❌ Произошла ошибка при создании заявки. Попробуйте позже.",
                reply_markup=get_main_menu(db.get_user_role(user_id)['role'])
            )

    def send_notifications_to_executors(bot, db, application_id, data):
        """Отправляет уведомления перевозчикам о новой заявке"""
        app_data_for_check = {
            'cargo_type': data['cargo_type'],
            'vehicle_type': data['vehicle_type'],
            'application_type': data['application_type'],
            'loading_cities': [point['city'] for point in data['loading_points']],
            'unloading_cities': [point['city'] for point in data['unloading_points']],
        }

        if data['application_type'] == 'fixed':
            payment_options = data['payment_options']
            prices = []
            if payment_options.get('nds'):
                prices.append(float(payment_options['nds']))
            if payment_options.get('ip'):
                prices.append(float(payment_options['ip']))
            if payment_options.get('cash'):
                prices.append(float(payment_options['cash']))
            if prices:
                app_data_for_check['min_price'] = min(prices)
        else:
            app_data_for_check['min_price'] = float(data.get('desired_budget', 0))

        loading_cities = [point['city'] for point in data['loading_points']]
        unloading_cities = [point['city'] for point in data['unloading_points']]

        if len(loading_cities) > 1:
            loading_city_display = f"{loading_cities[0]} и ещё {len(loading_cities) - 1}"
        else:
            loading_city_display = loading_cities[0] if loading_cities else "Не указан"

        if len(unloading_cities) > 1:
            unloading_city_display = f"{unloading_cities[0]} и ещё {len(unloading_cities) - 1}"
        else:
            unloading_city_display = unloading_cities[0] if unloading_cities else "Не указан"

        cargo_weight = float(data['weight'])
        cargo_volume = float(data['volume'])
        vehicle_type_display = VEHICLE_TYPE_REVERSE_MAPPING.get(data['vehicle_type'], data['vehicle_type'])

        if data['application_type'] == 'fixed':
            type_icon = "📦"
            type_text = "СТАНДАРТНАЯ"
            payment_options = data['payment_options']

            payments_text = ""
            if payment_options.get('nds'):
                payments_text += f"• С НДС: {float(payment_options['nds']):,.0f} руб.\n"
            if payment_options.get('ip'):
                payments_text += f"• Без НДС: {float(payment_options['ip']):,.0f} руб.\n"
            if payment_options.get('cash'):
                payments_text += f"• Наличные: {float(payment_options['cash']):,.0f} руб.\n"

            if payments_text:
                price_display = f"💰 **ВАРИАНТЫ ОПЛАТЫ:**\n{payments_text}"
            else:
                # Если нет payment_options, показываем просто фиксированную ставку (хотя она больше не используется)
                price_display = "💰 **Оплата:** Будет указана позже"
        else:
            type_icon = "🏷️"
            type_text = "ЗАПРОС СТАВОК"
            price_display = f"💰 **Бюджет:** {float(data['desired_budget']):,.0f} руб."

        executors = db.fetch_all("""
            SELECT telegram_id 
            FROM users 
            WHERE (role = 'executor' OR role = 'external_executor') 
            AND status = 'active'
        """)

        print(f"📢 Найдено {len(executors)} перевозчиков для уведомлений")

        sent_count = 0
        skipped_count = 0

        for executor in executors:
            executor_id = executor['telegram_id']

            try:
                filters_obj = ExecutorFilters(db, executor_id)
                filters = filters_obj.filters

                passes_filter, reason = check_filters_for_application(filters, app_data_for_check)

                if not passes_filter:
                    print(f"  ⏭️ Пропуск {executor_id}: {reason}")
                    skipped_count += 1
                    continue

                print(f"  ✅ Отправка уведомления перевозчику {executor_id}")

                message_text = f"""
❗️ РАЗМЕЩЕНА НОВАЯ ЗАЯВКА!
📦 ЗАЯВКА #{application_id}
📍 {loading_city_display} → {unloading_city_display} ({cargo_weight:.0f} т / {cargo_volume:.0f} м³)
🚛 Требуемый транспорт: {vehicle_type_display}

{price_display}

{type_icon} {type_text}
                """.strip()

                if data.get('payment_deadline'):
                    message_text += f"\n📅 **Срок оплаты:** до {data['payment_deadline'].strftime('%d.%m.%Y')}"

                keyboard = InlineKeyboardMarkup()
                keyboard.add(
                    InlineKeyboardButton("📋 Посмотреть заявку",
                                         callback_data=f"executor_view_application_{application_id}")
                )

                bot.send_message(
                    executor_id,
                    message_text,
                    reply_markup=keyboard
                )

                sent_count += 1

            except Exception as e:
                print(f"❌ Ошибка при проверке фильтров для перевозчика {executor_id}: {e}")
                import traceback
                traceback.print_exc()

        print(f"📊 Итог: отправлено {sent_count} уведомлений, пропущено {skipped_count} перевозчиков по фильтрам")

    # Обработчики редактирования
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_selection')
    def handle_edit_selection(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_application_summary(bot, user_id, chat_id)
            return

        edit_actions = {
            "✏️ Тип заявки": ('waiting_for_edit_application_type', 'type'),
            "✏️ Маршрут": ('waiting_for_edit_route', 'route'),
            "✏️ Характер груза": ('waiting_for_edit_cargo_type', 'cargo_type'),
            "✏️ Вес и объем": ('waiting_for_edit_weight_volume', 'weight_volume'),
            "✏️ Транспорт": ('waiting_for_edit_vehicle_type', 'vehicle_type'),
            "✏️ Примечания": ('waiting_for_edit_notes', 'notes'),
            "✏️ Оплата": ('waiting_for_edit_payment', 'payment'),
            "✏️ Срок оплаты": ('waiting_for_edit_payment_deadline', 'payment_deadline'),
            "📋 Просмотр заявки": (None, 'summary')
        }

        if message.text in edit_actions:
            state, field = edit_actions[message.text]
            if state:
                application_temp_data[user_id]['editing_field'] = field
                set_user_state(user_id, state)

                if field == 'type':
                    bot.send_message(
                        chat_id,
                        "🎯 Выберите тип заявки:",
                        reply_markup=get_application_type_keyboard()
                    )
                elif field == 'route':
                    show_route_status(bot, user_id, chat_id)
                elif field == 'cargo_type':
                    bot.send_message(
                        chat_id,
                        "Выберите характер груза:",
                        reply_markup=get_cargo_type_keyboard()
                    )
                elif field == 'weight_volume':
                    bot.send_message(
                        chat_id,
                        "⚖️ Введите новый вес груза (в тоннах):\n"
                        "Пример: 5.5 или 10",
                        reply_markup=ReplyKeyboardRemove()
                    )
                elif field == 'vehicle_type':
                    bot.send_message(
                        chat_id,
                        "🚛 Выберите тип кузова:",
                        reply_markup=get_vehicle_type_keyboard()
                    )
                elif field == 'notes':
                    current_notes = application_temp_data[user_id].get('notes', 'Не указаны')
                    bot.send_message(
                        chat_id,
                        f"📝 Текущие примечания: {current_notes}\n\n"
                        f"Введите новые примечания к заявке или нажмите '⏭️ Пропустить':",
                        reply_markup=get_notes_keyboard()
                    )
                elif field == 'payment':
                    data = application_temp_data[user_id]
                    if data['application_type'] == 'fixed':
                        bot.send_message(
                            chat_id,
                            "💰 Введите ставку для **С НДС (22%)** (в рублях):\n"
                            "Пример: 50000",
                            reply_markup=ReplyKeyboardRemove()
                        )
                    else:
                        current_budget = data.get('desired_budget', 0)
                        bot.send_message(
                            chat_id,
                            f"🎯 Текущий бюджет: {current_budget:,.0f} руб.\n\n"
                            f"Введите новый желаемый бюджет (в рублях):",
                            reply_markup=ReplyKeyboardRemove()
                        )
                elif field == 'payment_deadline':
                    current_deadline = application_temp_data[user_id].get('payment_deadline')
                    if current_deadline:
                        if isinstance(current_deadline, datetime):
                            deadline_text = current_deadline.strftime('%d.%m.%Y')
                        else:
                            deadline_text = str(current_deadline)
                    else:
                        deadline_text = "Не указан"

                    bot.send_message(
                        chat_id,
                        f"📅 Текущий срок оплаты: {deadline_text}\n\n"
                        f"Введите новую дату оплаты в формате ДД.ММ.ГГГГ\n"
                        f"или нажмите '⏭️ Пропустить' чтобы оставить без изменений:",
                        reply_markup=get_payment_terms_keyboard()
                    )
            else:
                show_application_summary(bot, user_id, chat_id)
        else:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, выберите действие из меню",
                reply_markup=get_edit_application_keyboard()
            )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_application_type')
    def handle_edit_application_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        if message.text == "📦 СТАНДАРТНАЯ (с фиксированной ставкой)":
            old_type = application_temp_data[user_id]['application_type']
            application_temp_data[user_id]['application_type'] = 'fixed'
            application_temp_data[user_id]['desired_budget'] = None  # Очищаем бюджет аукциона

            bot.send_message(
                chat_id,
                "✅ Тип заявки изменен на СТАНДАРТНАЯ\n\n"
                "💰 Теперь введите ставку для **С НДС (22%)** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_nds_price')

        elif message.text == "🏷️ ЗАПРОС СТАВОК (Аукцион)":
            old_type = application_temp_data[user_id]['application_type']
            application_temp_data[user_id]['application_type'] = 'auction'
            application_temp_data[user_id]['payment_options'] = {}  # Очищаем payment_options для фиксированной заявки

            bot.send_message(
                chat_id,
                "✅ Тип заявки изменен на ЗАПРОС СТАВОК\n\n"
                "🎯 Введите ваш желаемый бюджет (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_desired_budget')
        else:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, выберите тип заявки из предложенных вариантов.",
                reply_markup=get_application_type_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_desired_budget')
    def handle_edit_desired_budget(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🎯 Выберите тип заявки:",
                reply_markup=get_application_type_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_application_type')
            return

        try:
            budget = float(message.text.replace(',', '.').replace(' ', ''))
            if budget <= 0:
                bot.send_message(
                    chat_id,
                    "❌ Бюджет должен быть больше 0. Введите корректную сумму:"
                )
                return

            application_temp_data[user_id]['desired_budget'] = budget
            bot.send_message(chat_id, "✅ Бюджет заявки обновлен!")
            show_application_summary(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, введите корректную сумму (только цифры):"
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_weight_volume')
    def handle_edit_weight_volume(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        try:
            weight = float(message.text.replace(',', '.'))
            if weight <= 0:
                bot.send_message(
                    chat_id,
                    "❌ Вес должен быть больше 0. Введите корректное значение:"
                )
                return

            application_temp_data[user_id]['weight'] = weight
            bot.send_message(
                chat_id,
                "✅ Вес груза обновлен! Теперь введите объем (в м³):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_volume')

        except ValueError:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, введите корректное число (например: 5.5 или 10):"
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_nds_price')
    def handle_edit_nds_price(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🎯 Выберите тип заявки:",
                reply_markup=get_application_type_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_application_type')
            return

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(
                    chat_id,
                    "❌ Сумма должна быть больше 0. Введите корректную сумму:"
                )
                return

            application_temp_data[user_id]['payment_options'] = {'nds': price}
            bot.send_message(
                chat_id,
                "Введите ставку **Без НДС** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_ip_price')

        except ValueError:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, введите корректную сумму (только цифры):"
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_ip_price')
    def handle_edit_ip_price(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "💰 Введите ставку для **С НДС (22%)** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_nds_price')
            return

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(
                    chat_id,
                    "❌ Сумма должна быть больше 0. Введите корректную сумму:"
                )
                return

            application_temp_data[user_id]['payment_options']['ip'] = price
            bot.send_message(
                chat_id,
                "Введите ставку для **Наличные** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_cash_price')

        except ValueError:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, введите корректную сумму (только цифры):"
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_cash_price')
    def handle_edit_cash_price(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Введите ставку **Без НДС** (в рублях):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_ip_price')
            return

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(
                    chat_id,
                    "❌ Сумма должна быть больше 0. Введите корректную сумму:"
                )
                return

            application_temp_data[user_id]['payment_options']['cash'] = price
            bot.send_message(chat_id, "✅ Способ оплаты обновлен!")
            show_application_summary(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, введите корректную сумму (только цифры):"
            )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_payment_deadline')
    def handle_edit_payment_deadline(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        if message.text == "⏭️ Пропустить":
            # Оставляем текущий срок оплаты без изменений
            bot.send_message(chat_id, "✅ Срок оплаты оставлен без изменений")
            show_application_summary(bot, user_id, chat_id)
            return

        try:
            deadline = datetime.strptime(message.text, '%d.%m.%Y')
            if deadline.date() < datetime.now().date():
                bot.send_message(
                    chat_id,
                    "❌ Дата не может быть в прошлом. Введите корректную дату:"
                )
                return

            application_temp_data[user_id]['payment_deadline'] = deadline
            bot.send_message(chat_id, "✅ Срок оплаты обновлен!")
            show_application_summary(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(
                chat_id,
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:"
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_cargo_type')
    def handle_edit_cargo_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        if message.text == "📝 ПРОЧЕЕ":
            bot.send_message(
                chat_id,
                "✏️ Введите характер груза:",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_custom_cargo_type')
            return

        valid_types = ["✅ Обычный", "🥪 Скоропортящийся", "⚠️ Опасный", "🔔 Хрупкий",
                       "📱 ТНП", "🔌 Бытовая техника", "🧪 Бытовая химия"]

        if message.text in valid_types:
            cargo_type = CARGO_TYPE_MAPPING.get(message.text)
            application_temp_data[user_id]['cargo_type'] = cargo_type
            application_temp_data[user_id]['cargo_custom_type'] = 'Не указан'

            bot.send_message(chat_id, "✅ Характер груза обновлен!")
            show_application_summary(bot, user_id, chat_id)
        else:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, выберите характер груза из предложенных вариантов.",
                reply_markup=get_cargo_type_keyboard()
            )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_custom_cargo_type')
    def handle_edit_custom_cargo_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        custom_type = message.text
        application_temp_data[user_id]['cargo_custom_type'] = custom_type
        application_temp_data[user_id]['cargo_type'] = "ПРОЧЕЕ"

        bot.send_message(chat_id, "✅ Характер груза обновлен!")
        show_application_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_volume')
    def handle_edit_volume(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "⚖️ Введите новый вес груза (в тоннах):",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_edit_weight_volume')
            return

        try:
            volume = float(message.text.replace(',', '.'))
            if volume <= 0:
                bot.send_message(
                    chat_id,
                    "❌ Объем должен быть больше 0. Введите корректное значение:"
                )
                return

            application_temp_data[user_id]['volume'] = volume
            bot.send_message(chat_id, "✅ Вес и объем груза обновлены!")
            show_application_summary(bot, user_id, chat_id)

        except ValueError:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, введите корректное число (например: 20.5 или 30):"
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_vehicle_type')
    def handle_edit_vehicle_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        valid_types = ["📦 Тент", "🧊 Рефрижератор", "🌡️ Изотермический",
                       "🚚 Любой закрытый", "🚛 Открытая платформа", "📄 Промтоварный"]

        if message.text in valid_types:
            vehicle_type = VEHICLE_TYPE_MAPPING.get(message.text)
            application_temp_data[user_id]['vehicle_type'] = vehicle_type
            bot.send_message(chat_id, "✅ Тип кузова обновлен!")
            show_application_summary(bot, user_id, chat_id)
        else:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, выберите тип кузова из предложенных вариантов.",
                reply_markup=get_vehicle_type_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_notes')
    def handle_edit_notes(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        if message.text == "⏭️ Пропустить":
            application_temp_data[user_id]['notes'] = None
            bot.send_message(chat_id, "✅ Примечания удалены")
        else:
            application_temp_data[user_id]['notes'] = message.text.strip()
            bot.send_message(chat_id, "✅ Примечания обновлены!")

        show_application_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_payment')
    def handle_edit_payment(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(chat_id, "✏️ Выберите что хотите отредактировать:",
                             reply_markup=get_edit_application_keyboard())
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        data = application_temp_data[user_id]

        if data['application_type'] == 'fixed':
            try:
                price = float(message.text.replace(',', '.').replace(' ', ''))
                if price <= 0:
                    bot.send_message(chat_id, "❌ Сумма должна быть больше 0. Введите корректную сумму:")
                    return

                application_temp_data[user_id]['payment_options'] = {'nds': price}
                bot.send_message(chat_id, "Введите ставку **Без НДС** (в рублях):",
                                 reply_markup=ReplyKeyboardRemove())
                set_user_state(user_id, 'waiting_for_edit_ip_price')

            except ValueError:
                bot.send_message(chat_id, "❌ Пожалуйста, введите корректную сумму (только цифры):")
        else:
            try:
                budget = float(message.text.replace(',', '.').replace(' ', ''))
                if budget <= 0:
                    bot.send_message(chat_id, "❌ Бюджет должен быть больше 0. Введите корректную сумму:")
                    return

                application_temp_data[user_id]['desired_budget'] = budget
                bot.send_message(chat_id, "✅ Способ оплаты обновлен!")
                show_application_summary(bot, user_id, chat_id)

            except ValueError:
                bot.send_message(chat_id, "❌ Пожалуйста, введите корректную сумму (только цифры):")

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_route')
    def handle_edit_route(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        # Очищаем существующие точки маршрута для пересоздания
        application_temp_data[user_id]['loading_points'] = []
        application_temp_data[user_id]['unloading_points'] = []

        bot.send_message(
            chat_id,
            "🗺️ **Редактирование маршрута**\n\n"
            "Сейчас вы можете создать новый маршрут.\n"
            "Старые точки маршрута будут удалены.",
            reply_markup=get_route_management_keyboard(has_loading=False, has_unloading=False)
        )
        set_user_state(user_id, 'waiting_for_edit_route_management')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_route_management')
    def handle_edit_route_management(message):
        """Обработка управления маршрутом в режиме редактирования"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        data = application_temp_data[user_id]

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "✏️ Выберите что хотите отредактировать:",
                reply_markup=get_edit_application_keyboard()
            )
            set_user_state(user_id, 'waiting_for_edit_selection')
            return

        elif message.text == "[➕] Добавить точку погрузки":
            application_temp_data[user_id]['current_point_type'] = 'loading'
            bot.send_message(
                chat_id,
                "📍 **Добавление точки погрузки**\n\n"
                "Введите название города погрузки:\n"
                "Пример: Москва",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_city_input_edit')

        elif message.text == "[➕] Добавить точку выгрузки":
            application_temp_data[user_id]['current_point_type'] = 'unloading'
            bot.send_message(
                chat_id,
                "📍 **Добавление точки выгрузки**\n\n"
                "Введите название города выгрузки:\n"
                "Пример: Санкт-Петербург",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_city_input_edit')

        elif message.text == "❌ Удалить точку":
            show_points_for_deletion(bot, user_id, chat_id, mode='edit')

        elif message.text == "✅ Завершить маршрут":
            if len(data['loading_points']) == 0:
                bot.send_message(
                    chat_id,
                    "❌ Необходимо добавить хотя бы одну точку погрузки."
                )
                show_route_status(bot, user_id, chat_id)
                return

            if len(data['unloading_points']) == 0:
                bot.send_message(
                    chat_id,
                    "❌ Необходимо добавить хотя бы одну точку выгрузки."
                )
                show_route_status(bot, user_id, chat_id)
                return

            show_application_summary(bot, user_id, chat_id)



