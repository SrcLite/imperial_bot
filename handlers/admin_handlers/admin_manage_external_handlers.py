import re

from telebot.types import ReplyKeyboardRemove

from keyboards.admin_keyboards import *
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from datetime import datetime

from utils.helpers import init_user_rating

admin_temp_data = {}
role_names = {
    'admin': '👑 Администратор',
    'logist': '📊 Логист',
    'executor': '🚛 Перевозчик',
    'external_admin': '👑 Администратор',
    'external_logist': '📊 Логист',
    'external_executor': '🚛 Перевозчик'
}


def register_external_user_admin_handlers(bot, db):
    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_ext_management_action')
    def handle_external_user_management_action(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(admin_id)
        if not user and user['status'] != 'active':
            bot.send_message(
                admin_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        user_role = db.get_user_role(admin_id)
        user_role = user_role['role'] if user_role else None

        if message.text == "👤 Добавить пользователя":
            # Инициализируем временные данные для нового перевозчика
            admin_temp_data[admin_id] = {
                'new_external_user': {},
                'editing_external_user_id': None
            }

            bot.send_message(
                chat_id,
                "🆔 Введите Telegram ID пользователя:\n\n"
                "Чтобы вам было легче, воспользуйтесь ботом, чтобы узнать ID пользователя - @username_to_id_bot",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_external_user_telegram_id')

        elif message.text == "📋 Список пользователей":
            show_external_users_list(bot, db, admin_id, chat_id)

        elif message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Выберите группу пользователей:",
                reply_markup=get_user_management_keyboard(user_role)
            )
            set_user_state(admin_id, 'waiting_for_group_management')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_external_user_telegram_id')
    def handle_external_user_telegram_id(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🚛 Управление пользователями\n\n"
                "Выберите действие:",
                reply_markup=get_external_user_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_ext_management_action')
            return

        telegram_id = message.text.strip()
        admin_temp_data[admin_id]['new_external_user']['telegram_id'] = telegram_id

        # Получаем все компании кроме компании с ID=1
        companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' AND id != 1 ORDER BY name"
        )

        if not companies:
            bot.send_message(
                chat_id,
                "❌ В системе нет доступных компаний для выбора.",
                reply_markup=get_back_keyboard()
            )
            return

        bot.send_message(
            chat_id,
            '💼 Введите должность пользователя:',
            reply_markup=get_role_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_external_user_role')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_external_user_role')
    def handle_external_user_role(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🆔 Введите Telegram ID пользователя:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_external_user_telegram_id')
            return
        elif message.text == '👑 Администратор':
            admin_temp_data[admin_id]['new_external_user']['role'] = 'external_admin'
        elif message.text == '📊 Логист':
            admin_temp_data[admin_id]['new_external_user']['role'] = 'external_logist'
        elif message.text == '🚛 Перевозчик':
            admin_temp_data[admin_id]['new_external_user']['role'] = 'external_executor'

        companies = db.fetch_all(
            "SELECT id, name FROM companies WHERE status = 'approved' AND id != 1"
        )

        bot.send_message(
            chat_id,
            "🏢 Выберите компанию пользователя:",
            reply_markup=get_admin_company_selection_keyboard(companies)
        )
        set_user_state(admin_id, 'waiting_for_external_user_company_select')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_external_user_company_select')
    def handle_external_user_company_select(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🆔 Введите Telegram ID пользователя:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_external_user_telegram_id')
            return

        company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text
        company = db.fetch_one(
            "SELECT id, name FROM companies WHERE name = ? AND status = 'approved' AND id != 1",
            (company_name,)
        )

        companies = db.fetch_all(
            "SELECT id, name FROM companies WHERE AND status = 'approved' AND id != 1"
        )

        if not company:
            bot.send_message(chat_id,
                             "❌ Компания не найдена или не доступна для выбора. Пожалуйста, выберите компанию из списка.",
                             get_executor_company_selection_keyboard(companies))
            return

        company_id = company['id']
        name = company["name"]

        admin_temp_data[admin_id]['new_external_user']['company_id'] = company_id
        admin_temp_data[admin_id]['new_external_user']['company_name'] = name

        # Показываем сводку данных
        show_external_user_summary(bot, admin_id, chat_id)

    def show_external_user_summary(bot, admin_id, chat_id):
        """Показывает сводку данных нового пользователя"""
        data = admin_temp_data[admin_id]['new_external_user']

        summary_text = f"""
📋 **Проверьте данные нового пользователя:**

🆔 **Telegram ID:** {data['telegram_id']}
💼 **Роль:** {data['role']}
🏢 **Компания:** {data.get('company_name', 'Не указана')}

Если все верно, нажмите "✅ Подтвердить добавление".
Если нужно что-то изменить, выберите поле для редактирования.
        """

        bot.send_message(
            chat_id,
            summary_text,
            reply_markup=get_exteranl_confirmation_keyboard(data['role'])
        )
        set_user_state(admin_id, 'waiting_for_external_user_confirmation')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_external_user_confirmation')
    def handle_external_user_confirmation(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "✅ Подтвердить добавление":
            complete_external_user_creation(bot, db, admin_id, chat_id)
        elif message.text == "✏️ Редактировать Telegram ID":
            bot.send_message(
                chat_id,
                f"Текущий Telegram ID: {admin_temp_data[admin_id]['new_external_user']['telegram_id']}\nВведите новый Telegram ID:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_external_user_telegram_id')
        elif message.text == "✏️ Редактировать компанию":
            # Получаем все компании кроме компании с ID=1
            companies = db.fetch_all(
                "SELECT * FROM companies WHERE status = 'approved' AND id != 1 ORDER BY name"
            )
            bot.send_message(
                chat_id,
                f"Текущая компания: {admin_temp_data[admin_id]['new_external_user'].get('company_name', 'Не указана')}\nВыберите новую компанию:",
                reply_markup=get_admin_company_selection_keyboard(companies)
            )
            set_user_state(admin_id, 'editing_external_user_company')
        elif message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🚛 Управление пользователями\n\n"
                "Выберите действие:",
                reply_markup=get_external_user_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_ext_management_action')
            if admin_id in admin_temp_data:
                del admin_temp_data[admin_id]

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_external_user_telegram_id')
    def handle_editing_external_user_telegram_id(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_external_user_summary(bot, admin_id, chat_id)
            return

        telegram_id = message.text.strip()
        admin_temp_data[admin_id]['new_external_user']['telegram_id'] = telegram_id
        show_external_user_summary(bot, admin_id, chat_id)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_external_user_company')
    def handle_editing_external_user_company(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_external_user_summary(bot, admin_id, chat_id)
            return

        company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text
        company = db.fetch_one(
            "SELECT id, name FROM companies WHERE name = ? AND status = 'approved' AND id != 1",
            (company_name,)
        )

        if not company:
            bot.send_message(chat_id,
                             "❌ Компания не найдена или не доступна для выбора. Пожалуйста, выберите компанию из списка.")
            return

        company_id = company['id']
        name = company["name"]

        admin_temp_data[admin_id]['new_external_user']['company_id'] = company_id
        admin_temp_data[admin_id]['new_external_user']['company_name'] = name
        show_external_user_summary(bot, admin_id, chat_id)

    def complete_external_user_creation(bot, db, admin_id, chat_id):
        """Завершает создание пользователя"""
        try:
            data = admin_temp_data[admin_id]['new_external_user']

            # Создаем пользователя с ролью external_user
            user_id = db.execute_query(
                """INSERT INTO users 
                (telegram_id, company_id, role, status, created_by, created_at) 
                VALUES (?, ?, ?, 'pending', ?, datetime('now'))""",
                (data['telegram_id'], data['company_id'], data['role'], admin_id)
            )

            if user_id:
                bot.send_message(
                    chat_id,
                    f"✅ Пользователь с Telegram ID {data['telegram_id']} успешно добавлен и отправлен на модерацию!\n"
                    f"🏢 Компания: {data['company_name']}",
                    reply_markup=get_external_user_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_ext_management_action')

                if admin_id in admin_temp_data:
                    del admin_temp_data[admin_id]

            else:
                bot.send_message(
                    chat_id,
                    "❌ Ошибка при добавлении пользователя. Попробуйте позже.",
                    reply_markup=get_external_user_management_keyboard()
                )

        except Exception as e:
            print(f"Ошибка при создании пользователя: {e}")
            bot.send_message(
                chat_id,
                "❌ Произошла ошибка при добавлении пользователя. Попробуйте позже.",
                reply_markup=get_external_user_management_keyboard()
            )

    def show_external_users_list(bot, db, admin_id, chat_id):
        """Показывает список всех перевозчиков"""
        print("Вызывается список пользователей")
        external_users = db.fetch_all(
            "SELECT * FROM users WHERE (role = 'external_admin' or role = 'external_logist' or role = 'external_executor') AND status = 'active' ORDER BY first_name, last_name"
        )

        if not external_users:
            bot.send_message(
                chat_id,
                "📭 Список пользователей пуст.",
                reply_markup=get_external_user_management_keyboard()
            )
            return

        # Сохраняем список перевозчиков для последующего выбора
        if admin_id not in admin_temp_data:
            admin_temp_data[admin_id] = {}
        admin_temp_data[admin_id]['external_users_list'] = external_users

        # Формируем сообщение со списком
        message_text = "📋 Список пользователя:\n\n"
        for i, external_user in enumerate(external_users, 1):
            message_text += f"{i}. {external_user['first_name']} {external_user.get('last_name', '')} - {role_names.get(external_user['role'], 'Должность не указана')}\n"
            message_text += f"   📞 {external_user.get('phone', 'Телефон не указан')}\n\n"

        message_text += "Выберите пользователя для управления:"

        # Создаем клавиатуру с кнопками для каждого перевозчика (включая ID)
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        for external_user in external_users:
            button_text = f"👤 {external_user['first_name']} {external_user.get('last_name', '')} (ID: {external_user['telegram_id']})"
            keyboard.add(KeyboardButton(button_text))

        keyboard.add(KeyboardButton("⬅️ Назад"))

        bot.send_message(chat_id, message_text, reply_markup=keyboard)
        set_user_state(admin_id, 'waiting_for_external_user_selection')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_external_user_selection')
    def handle_external_user_selection(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🚛 Управление пользователями\n\n"
                "Выберите действие:",
                reply_markup=get_external_user_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_ext_management_action')
            return

        # Ищем выбранного перевозчика по ID (как в test1)
        try:
            # Извлекаем ID перевозчика из текста кнопки
            external_user_id = int(message.text.split('ID: ')[1].split(')')[0])
        except (IndexError, ValueError):
            bot.send_message(chat_id, "❌ Неверный формат выбора. Попробуйте еще раз.")
            return

        # Находим перевозчика
        selected_external_user = None
        for external_user in admin_temp_data[admin_id]['external_users_list']:
            if external_user[
                'telegram_id'] == external_user_id:
                selected_external_user = external_user
                break

        if not selected_external_user:
            bot.send_message(chat_id, "❌ Пользователь не найден. Попробуйте еще раз.")
            return

        # Сохраняем выбранного перевозчика для редактирования
        admin_temp_data[admin_id]['editing_external_user'] = selected_external_user

        # Показываем меню управления выбранным перевозчиком
        show_external_user_management_menu(bot, admin_id, chat_id, selected_external_user)

    def show_external_user_management_menu(bot, admin_id, chat_id, external_user):
        """Показывает меню управления конкретным перевозчиком"""

        company = db.get_company_by_id(external_user['company_id'])
        # Экранируем специальные символы Markdown
        def escape_markdown(text):
            if text is None:
                return "Не указано"
            escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            return ''.join(['\\' + char if char in escape_chars else char for char in str(text)])

        role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }

        status_names = {
            'active': '✅ Активный',
            'pending': '🕐 В обработке',
            'blocked': '❌ Заблокирован'
        }

        message_text = f"""
    👤 *Управление пользователем:*

    *Имя:* {external_user['first_name']}
    *Фамилия:* {external_user.get('last_name', 'Не указана')}
    *Отчество:* {external_user.get('patronymic', 'Не указано')}
    *Компания:* {company.get('name', 'Не указана')}
    *Должность:* {role_names.get(external_user['role'], 'Не указана')}
    *Телефон:* {external_user.get('phone', 'Не указан')}
    *Email:* {external_user.get('email', 'Не указан')}
    *Дата рождения:* {external_user.get('birth_date', 'Не указана')}
    *Паспорт:* {external_user.get('passport_series', '')} {external_user.get('passport_number', '')}
    *Дата выдачи паспорта:* {external_user.get('passport_issue_date', 'Не указана')}
    *Адрес регистрации:* {external_user.get('registration_address', 'Не указан')}
    *Код АТИ:* {external_user.get('ati_code', 'Не указан')}
    *Статус:* {status_names.get(external_user['status'], 'Не указан')}

    Выберите действие:
            """

        bot.send_message(
            chat_id,
            message_text,
            reply_markup=get_specific_external_user_management_keyboard(),
        )
        set_user_state(admin_id, 'waiting_for_specific_external_user_action')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_specific_external_user_action')
    def handle_specific_external_user_action(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "✏️ Редактировать данные":
            start_external_user_editing(bot, admin_id, chat_id)
        elif message.text == "🗑️ Удалить пользователя":
            bot.send_message(
                chat_id,
                "❌ Вы уверены, что хотите удалить этого пользователя?\n\n"
                "Это действие нельзя отменить.",
                reply_markup=get_confirmation_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_delete_external_user_confirmation')
        elif message.text == "⬅️ Назад к списку":
            show_external_users_list(bot, db, admin_id, chat_id)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_delete_external_user_confirmation')
    def handle_delete_confirmation(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "✅ Да, удалить":
            delete_external_user(bot, db, admin_id, chat_id)
        elif message.text == "❌ Нет, отменить":
            if admin_id in admin_temp_data and 'editing_external_user' in admin_temp_data[admin_id]:
                show_external_user_management_menu(bot, admin_id, chat_id,
                                                   admin_temp_data[admin_id]['editing_external_user'])
            else:
                bot.send_message(
                    chat_id,
                    "🚛 Управление пользователями\n\n"
                    "Выберите действие:",
                    reply_markup=get_external_user_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_ext_management_action')

    def delete_external_user(bot, db, admin_id, chat_id):
        try:
            if admin_id not in admin_temp_data or 'editing_external_user' not in admin_temp_data[admin_id]:
                bot.send_message(chat_id, "❌ Ошибка. пользователь не найден.")
                return

            external_user = admin_temp_data[admin_id]['editing_external_user']

            success = db.execute_query(
                "DELETE FROM users WHERE id = ?",
                (external_user['id'],)
            )
            if success:
                bot.send_message(
                    chat_id,
                    f"✅ Пользователь {external_user['first_name']} {external_user['last_name']} успешно удален.",
                    reply_markup=get_external_user_management_keyboard()
                )

                if admin_id in admin_temp_data:
                    if 'editing_external_user' in admin_temp_data[admin_id]:
                        del admin_temp_data[admin_id]['editing_external_user']
                    if 'external_users_list' in admin_temp_data[admin_id]:
                        del admin_temp_data[admin_id]['external_users_list']
                set_user_state(admin_id, 'waiting_for_ext_management_action')
            else:
                bot.send_message(chat_id, "❌ Ошибка при удалении пользователя.")

        except Exception as e:
            print(f"Ошибка при удалении пользователя: {e}")
            bot.send_message(chat_id, "❌ Произошла ошибка при удалении пользователя.")

    def start_external_user_editing(bot, admin_id, chat_id):
        if admin_id not in admin_temp_data or 'editing_external_user' not in admin_temp_data[admin_id]:
            bot.send_message(chat_id, "❌ Ошибка. Пользователь не найден.")
            return
        bot.send_message(
            chat_id,
            "✏️ Редактирование данных пользователя\n\n"
            "Выберите что хотите отредактировать:",
            reply_markup=get_extended_editing_external_user_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_editing_external_user_field_selection')

    @bot.message_handler(
        func=lambda message: get_user_state(
            message.from_user.id) == 'waiting_for_editing_external_user_field_selection')
    def handle_editing_external_user_field_selection(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            if admin_id in admin_temp_data and 'editing_external_user' in admin_temp_data[admin_id]:
                show_external_user_management_menu(bot, admin_id, chat_id,
                                                   admin_temp_data[admin_id]['editing_external_user'])
            return

        external_user = admin_temp_data[admin_id]['editing_external_user']

        if message.text == "👤 Редактировать имя":
            bot.send_message(
                chat_id,
                f"Текущее имя: {external_user['first_name']}\nВведите новое имя:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_name')

        elif message.text == "👤 Редактировать фамилию":
            bot.send_message(
                chat_id,
                f"Текущая фамилия: {external_user.get('last_name', 'Не указана')}\nВведите новую фамилию:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_last_name')

        elif message.text == "👤 Редактировать отчество":
            bot.send_message(
                chat_id,
                f"Текущее отчество: {external_user.get('patronymic', 'Не указано')}\nВведите новое отчество:",
                reply_markup=get_skip_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_patronymic')

        elif message.text == "💼 Редактировать должность":
            bot.send_message(
                chat_id,
                f"Текущая должность: {role_names.get(external_user.get('role', 'Не указана'))}\nВведите новую должность:",
                reply_markup=get_role_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_role')

        elif message.text == "📞 Редактировать телефон":
            bot.send_message(
                chat_id,
                f"Текущий телефон: {external_user.get('phone', 'Не указан')}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_phone')

        elif message.text == "📧 Редактировать email":
            bot.send_message(
                chat_id,
                f"Текущий email: {external_user.get('email', 'Не указан')}\nВведите новый email:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_email')

        elif message.text == "🎂 Редактировать дату рождения":
            bot.send_message(
                chat_id,
                f"Текущая дата рождения: {external_user.get('birth_date', 'Не указана')}\nВведите новую дату рождения (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_birth_date')

        elif message.text == "📘 Редактировать серию паспорта":
            bot.send_message(
                chat_id,
                f"Текущая серия паспорта: {external_user.get('passport_series', 'Не указана')}\nВведите новую серию паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_passport_series')

        elif message.text == "📘 Редактировать номер паспорта":
            bot.send_message(
                chat_id,
                f"Текущий номер паспорта: {external_user.get('passport_number', 'Не указан')}\nВведите новый номер паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_passport_number')

        elif message.text == "📅 Редактировать дату выдачи паспорта":
            bot.send_message(
                chat_id,
                f"Текущая дата выдачи паспорта: {external_user.get('passport_issue_date', 'Не указана')}\nВведите новую дату выдачи паспорта (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_passport_issue_date')

        elif message.text == "📍 Редактировать адрес регистрации":
            bot.send_message(
                chat_id,
                f"Текущий адрес регистрации: {external_user.get('registration_address', 'Не указан')}\nВведите новый адрес регистрации:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_registration_address')

        elif message.text == "🔢 Редактировать код АТИ":
            bot.send_message(
                chat_id,
                f"Текущий код АТИ: {external_user.get('ati_code', 'Не указан')}\nВведите новый код АТИ:",
                reply_markup=get_skip_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_external_user_ati_code')
        elif message.text == '🏢 Редактировать компанию':
            companies = db.get_approved_companies()
            bot.send_message(
                chat_id,
                f"Текущая компания: {external_user.get('company_name', 'Не указан')}\nВыберите новую компанию:",
                reply_markup=get_admin_company_selection_keyboard(companies)
            )
            set_user_state(admin_id, "editing_existing_external_user_company")

    # Обработчики редактирования существующих перевозчиков
    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_name')
    def handle_editing_existing_external_user_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Имя должно содержать минимум 2 символа. Введите имя:")
            return

        success = db.execute_query(
            "UPDATE users SET first_name = ? WHERE id = ?",
            (message.text.strip(), admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['first_name'] = message.text.strip()
            bot.send_message(chat_id, "✅ Имя успешно обновлено!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении имени.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_company')
    def handle_editing_existing_external_user_company(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text
        company = db.fetch_one(
            "SELECT id, name FROM companies WHERE name = ? AND status = 'approved'",
            (company_name,)
        )
        company_id = company['id']
        name = company['name']
        if not company:
            bot.send_message(chat_id, "❌ Компания не найдена. Пожалуйста, выберите компанию из списка.")
            return
        success = db.execute_query(
            "update users set company_id = ? where id = ?",
        )
        if success:
            admin_temp_data[admin_id]['new_external_user']['company_id'] = company_id
            admin_temp_data[admin_id]['new_external_user']['company_name'] = name
            bot.send(chat_id, "✅Компания успешно обновлена!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(
                chat_id,
                "❌ Ошибка при обновлении компании."
            )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_last_name')
    def handle_editing_existing_external_user_last_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Фамилия не может быть пустой. Введите фамилию:")
            return

        success = db.execute_query(
            "UPDATE users SET last_name = ? WHERE id = ?",
            (message.text.strip(), admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['last_name'] = message.text.strip()
            bot.send_message(chat_id, "✅ Фамилия успешно обновлена!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении фамилии.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_patronymic')
    def handle_editing_existing_external_user_patronymic(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        if message.text == "⏭️ Пропустить":
            patronymic = None
        else:
            patronymic = message.text.strip()
            if not patronymic:
                bot.send_message(chat_id, "❌ Отчество не может быть пустым. Введите отчество или пропустите:")
                return

        success = db.execute_query(
            "UPDATE users SET patronymic = ? WHERE id = ?",
            (patronymic, admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['patronymic'] = patronymic
            bot.send_message(chat_id, "✅ Отчество успешно обновлено!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении отчества.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_birth_date')
    def handle_editing_existing_external_user_birth_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        try:
            birth_date = datetime.strptime(message.text, '%d.%m.%Y')
            if birth_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата рождения не может быть в будущем. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        success = db.execute_query(
            "UPDATE users SET birth_date = ? WHERE id = ?",
            (message.text.strip(), admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['birth_date'] = message.text.strip()
            bot.send_message(chat_id, "✅ Дата рождения успешно обновлена!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении даты рождения.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_passport_series')
    def handle_editing_existing_external_user_passport_series(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 4:
            bot.send_message(chat_id, "❌ Серия паспорта должна состоять из 4 цифр. Попробуйте еще раз:")
            return

        success = db.execute_query(
            "UPDATE users SET passport_series = ? WHERE id = ?",
            (message.text.strip(), admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['passport_series'] = message.text.strip()
            bot.send_message(chat_id, "✅ Серия паспорта успешно обновлена!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении серии паспорта.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_passport_number')
    def handle_editing_existing_external_user_passport_number(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 6:
            bot.send_message(chat_id, "❌ Номер паспорта должен состоять из 6 цифр. Попробуйте еще раз:")
            return

        success = db.execute_query(
            "UPDATE users SET passport_number = ? WHERE id = ?",
            (message.text.strip(), admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['passport_number'] = message.text.strip()
            bot.send_message(chat_id, "✅ Номер паспорта успешно обновлен!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении номера паспорта.")

    @bot.message_handler(
        func=lambda message: get_user_state(
            message.from_user.id) == 'editing_existing_external_user_passport_issue_date')
    def handle_editing_existing_external_user_passport_issue_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        try:
            issue_date = datetime.strptime(message.text, '%d.%m.%Y')
            if issue_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        success = db.execute_query(
            "UPDATE users SET passport_issue_date = ? WHERE id = ?",
            (message.text.strip(), admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['passport_issue_date'] = message.text.strip()
            bot.send_message(chat_id, "✅ Дата выдачи паспорта успешно обновлена!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении даты выдачи паспорта.")

    @bot.message_handler(
        func=lambda message: get_user_state(
            message.from_user.id) == 'editing_existing_external_user_registration_address')
    def handle_editing_existing_external_user_registration_address(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Адрес регистрации не может быть пустым. Введите адрес:")
            return

        success = db.execute_query(
            "UPDATE users SET registration_address = ? WHERE id = ?",
            (message.text.strip(), admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['registration_address'] = message.text.strip()
            bot.send_message(chat_id, "✅ Адрес регистрации успешно обновлен!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении адреса регистрации.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_ati_code')
    def handle_editing_existing_external_user_ati_code(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        if message.text == "⏭️ Пропустить":
            ati_code = None
        else:
            ati_code = message.text.strip()
            if not ati_code.isdigit():
                bot.send_message(chat_id, "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз:")
                return

        success = db.execute_query(
            "UPDATE users SET ati_code = ? WHERE id = ?",
            (ati_code, admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['ati_code'] = ati_code
            bot.send_message(chat_id, "✅ Код АТИ успешно обновлен!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении кода АТИ.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_role')
    def handle_editing_existing_external_user_role(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        role = ''

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        elif message.text == '👑 Администратор':
            role = 'external_admin'
        elif message.text == '📊 Логист':
            role = 'external_logist'
        elif message.text == '🚛 Перевозчик':
            role = 'external_executor'

        success = db.execute_query(
            "UPDATE users SET role = ? WHERE id = ?",
            (role, admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['role'] = role
            bot.send_message(chat_id, "✅ Должность успешно обновлена!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении должности.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_phone')
    def handle_editing_existing_external_user_phone(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            bot.send_message(
                chat_id,
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:"
            )
            return

        success = db.execute_query(
            "UPDATE users SET phone = ? WHERE id = ?",
            (phone, admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['phone'] = phone
            bot.send_message(chat_id, "✅ Телефон успешно обновлен!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении телефона.")

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_external_user_email')
    def handle_editing_existing_external_user_email(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            start_external_user_editing(bot, admin_id, chat_id)
            return

        email = message.text.strip()

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
            return

        success = db.execute_query(
            "UPDATE users SET email = ? WHERE id = ?",
            (email, admin_temp_data[admin_id]['editing_external_user']['id'])
        )

        if success:
            admin_temp_data[admin_id]['editing_external_user']['email'] = email
            bot.send_message(chat_id, "✅ Email успешно обновлен!")
            start_external_user_editing(bot, admin_id, chat_id)
        else:
            bot.send_message(chat_id, "❌ Ошибка при обновлении email.")