import re

from telebot.types import ReplyKeyboardRemove

from handlers.admin_handlers.pending_moderations_handlers import add_pending_moderation
from keyboards.admin_keyboards import *
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from datetime import datetime

from keyboards.main_menus import get_main_menu
from keyboards.registration_user_keyboards import get_company_selection_keyboard
from utils.dicts import user_fields_display
from utils.email_sender import send_email_notification
from utils.helpers import init_user_rating

admin_temp_data = {}
status_names = {
    'active': '✅ Активный',
    'pending': '🕐 В обработке',
    'blocked': '❌ Заблокирован'
}
role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }


def register_logists_admin_handlers(bot, db):
    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_logist_management_action')
    def handle_logist_management_action(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(admin_id)
        role = user_role['role'] if user_role else None

        if message.text == "👤 Добавить логиста":
            # Инициализируем временные данные для нового логиста
            admin_temp_data[admin_id] = {
                'new_logist': {},
                'editing_logist_id': None
            }

            bot.send_message(
                chat_id,
                "👤 Добавление нового логиста\n\n"
                "Введите имя логиста:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_logist_name')

        elif message.text == "📋 Список логистов":
            show_logists_list(bot, db, admin_id, chat_id, role)

        elif message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Выберите группу пользователей:",
                reply_markup=get_user_management_keyboard(role)
            )
            set_user_state(admin_id, 'waiting_for_group_management')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_logist_name')
    def handle_logist_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "👥 Управление логистами\n\n"
                "Выберите действие:",
                reply_markup=get_logist_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_logist_management_action')
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Имя должно содержать минимум 2 символа. Введите имя:")
            return

        admin_temp_data[admin_id]['new_logist']['first_name'] = message.text.strip()
        bot.send_message(
            chat_id,
            "📞 Введите номер телефона логиста (в формате +7XXXXXXXXXX или 8XXXXXXXXXX):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_logist_phone')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_logist_phone')
    def handle_logist_phone(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Введите имя логиста",
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(admin_id, 'waiting_for_logist_name')
            return

        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            bot.send_message(
                chat_id,
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:"
            )
            return

        admin_temp_data[admin_id]['new_logist']['phone'] = phone

        bot.send_message(
            chat_id,
            "🆔 Введите Telegram ID логиста:\n\n"
            "Чтобы вам было легче, воспользуйтесь ботом, чтобы узнать ID пользователя - @username_to_id_bot",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_logist_telegram_id')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_logist_telegram_id')
    def handle_telegram_id(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '📞 Введите номер телефона логиста:',
                reply_markup=get_back_keyboard()
            )
        set_user_state(admin_id, 'waiting_for_logist_phone')
        telegram_id = message.text.strip()

        admin_temp_data[admin_id]['new_logist']['telegram_id'] = telegram_id
        bot.send_message(
            chat_id,
            '📧 Введите email логиста (по умолчанию logist@impe-rial.ru):',
            reply_markup=get_email_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_logist_email')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_logist_email')
    def handle_logist_email(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🆔 Введите Telegram ID логиста:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_logist_telegram_id')
            return

        email = message.text.strip()

        # Если нажата кнопка стандартного email
        if message.text == "📧 logist@impe-rial.ru":
            email = "logist@impe-rial.ru"
        else:
            # Валидация email
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
                return

        admin_temp_data[admin_id]['new_logist']['email'] = email

        show_logist_summary(bot, admin_id, chat_id)

    def show_logist_summary(bot, admin_id, chat_id):
        """Показывает сводку данных нового логиста"""
        admin_role = db.get_user_by_telegram_id(admin_id)['role']
        if admin_role in ['external_admin', 'external_logist']:
            admin_temp_data[admin_id]['new_logist']['role'] = 'external_logist'
        else:
            admin_temp_data[admin_id]['new_logist']['role'] = 'logist'

        data = admin_temp_data[admin_id]['new_logist']
        role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }
        summary_text = f"""
            📋 **Проверьте данные нового логиста:**

            👤 **Имя:** {data['first_name']}
            💼 **Должность:** {role_names.get(data['role'])}
            📞 **Телефон:** {data['phone']}
            🆔 Telegram ID:** {data['telegram_id']}
            📧 **Email:** {data['email']}

            Если все верно, нажмите "✅ Подтвердить добавление".
            Если нужно что-то изменить, выберите поле для редактирования.
                    """

        bot.send_message(
            chat_id,
            summary_text,
            reply_markup=get_logist_confirmation_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_logist_confirmation')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_logist_confirmation')
    def handle_logist_confirmation(message):
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
        role = user_role['role'] if user_role else None

        if message.text == "✅ Подтвердить добавление":
            complete_logist_creation(bot, db, admin_id, chat_id, role)
        elif message.text == "✏️ Редактировать имя":
            bot.send_message(
                chat_id,
                f"Текущее имя: {admin_temp_data[admin_id]['new_logist']['first_name']}\nВведите новое имя:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_logist_name')

        elif message.text == "✏️ Редактировать должность":
            bot.send_message(
                chat_id,
                f"Текущая должность: {role_names.get(admin_temp_data[admin_id]['new_logist']['role'])}\nВведите новую должность:",
                reply_markup=get_role_keyboard()
            )
            set_user_state(admin_id, 'editing_logist_role')

        elif message.text == "✏️ Редактировать телефон":
            bot.send_message(
                chat_id,
                f"Текущий телефон: {admin_temp_data[admin_id]['new_logist']['phone']}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_logist_phone')

        elif message.text == "✏️ Редактировать email":
            bot.send_message(
                chat_id,
                f"Текущий email: {admin_temp_data[admin_id]['new_logist']['email']}\nВведите новый email:",
                reply_markup=get_email_keyboard()
            )
            set_user_state(admin_id, 'editing_logist_email')
        elif message.text == "✏️ Редактировать Telegram ID":
            bot.send_message(
                chat_id,
                f"Текущий email: {admin_temp_data[admin_id]['new_logist']['telegram_id']}\nВведите новый Telegram ID:",
                reply_markup=get_email_keyboard()
            )
            set_user_state(admin_id, 'editing_logist_telegram_id')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_logist_name')
    def handle_editing_logist_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_logist_summary(bot, admin_id, chat_id)
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Имя должно содержать минимум 2 символа. Введите имя:")
            return

        admin_temp_data[admin_id]['new_logist']['first_name'] = message.text.strip()
        show_logist_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_logist_role')
    def handle_editing_logist_role(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(admin_id)
        role = user_role['role'] if user_role else None

        if message.text == "⬅️ Назад":
            show_logist_summary(bot, admin_id, chat_id)
            return

        if role == 'external_admin':
            if message.text == '👑 Администратор':
                admin_temp_data[admin_id]['new_logist']['role'] = 'external_admin'
            elif message.text == '📊 Логист':
                admin_temp_data[admin_id]['new_logist']['role'] = 'external_logist'
            elif message.text == '🚛 Перевозчик':
                admin_temp_data[admin_id]['new_logist']['role'] = 'external_executor'
        else:
            if message.text == '👑 Администратор':
                admin_temp_data[admin_id]['new_logist']['role'] = 'admin'
            elif message.text == '📊 Логист':
                admin_temp_data[admin_id]['new_logist']['role'] = 'logist'
            elif message.text == '🚛 Перевозчик':
                admin_temp_data[admin_id]['new_logist']['role'] = 'executor'

        show_logist_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_logist_phone')
    def handle_editing_logist_phone(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_logist_summary(bot, admin_id, chat_id)
            return

        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            bot.send_message(
                chat_id,
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:"
            )
            return

        admin_temp_data[admin_id]['new_logist']['phone'] = phone
        show_logist_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_logist_email')
    def handle_editing_logist_email(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_logist_summary(bot, admin_id, chat_id)
            return

        email = message.text.strip()

        if message.text == "📧 logist@impe-rial.ru":
            email = "logist@impe-rial.ru"
        else:
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
                return

        admin_temp_data[admin_id]['new_logist']['email'] = email
        show_logist_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_logist_telegram_id')
    def handle_editing_telegram_id(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_logist_summary(bot, admin_id, chat_id)
            return

        telegram_id = message.text.strip()

        admin_temp_data[admin_id]['new_logist']['telegram_id'] = telegram_id
        show_logist_summary(bot, admin_id, chat_id)

    def format_logist_moderation_message(data, company_name):
        role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }
        return f"""
            🆕 **НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ ПОЛЬЗОВАТЕЛЯ**
            
            👤 **Данные пользователя:**
            👤 **Имя:** {data['first_name']}
            💼 **Должность:** {role_names.get(data['role'])}
            📞 **Телефон:** {data['phone']}
            🆔 Telegram ID:** {data['telegram_id']}
            📧 **Email:** {data['email']}
            🏢 **Компания** {company_name}
            
            Выберите действие:
            """

    def complete_logist_creation(bot, db, admin_id, chat_id, admin_role):
        try:
            data = admin_temp_data[admin_id]['new_logist']
            user = db.get_user_by_telegram_id(admin_id)
            company_result = db.get_company_by_id(user['company_id'])
            company_id = company_result['id']
            company_name = company_result[
                'name'] if company_result and 'name' in company_result else None
            user_role = db.get_user_role(admin_id)
            role = user_role['role'] if user_role else None


            # Проверяем, существует ли пользователь с таким telegram_id
            existing_user = db.get_user_by_telegram_id(data['telegram_id'])

            if existing_user:
                print('Пользователь существует - обновляем данные')
                update_fields = []
                update_values = []

                # Поля для обновления
                fields_to_update = [
                    ('company_id', company_id),
                    ('first_name', data.get('first_name')),
                    ('role', data.get('role')),
                    ('phone', data.get('phone')),
                    ('email', data.get('email')),
                    ('created_by', admin_id),
                    ('updated_by', admin_id)
                ]

                # Определяем статус в зависимости от роли администратора
                if admin_role == 'admin':
                    target_status = 'added'
                else:
                    target_status = 'added_pending'

                fields_to_update.append(('status', target_status))

                # Собираем поля для обновления
                for field, value in fields_to_update:
                    if value is not None:
                        update_fields.append(f"{field} = ?")
                        update_values.append(value)

                update_fields.append("updated_at = datetime('now')")

                # Добавляем условие WHERE
                update_values.append(data['telegram_id'])

                if update_fields:
                    query = f"""
                        UPDATE users 
                        SET {', '.join(update_fields)}
                        WHERE telegram_id = ?
                    """
                    success = db.execute_query(query, tuple(update_values))

                    if success:
                        if admin_role == 'external_admin':
                            # Для external_admin отправляем на модерацию
                            admins = db.get_all_admins()
                            if not admins:
                                print("Не найдены администраторы для отправки заявки")
                                return

                            bot.send_message(
                                admin_id,
                                '🕐 **Данные отправлены главному администратору на проверку**\n'
                                'Вам придет уведомление о результате проверки',
                                reply_markup=get_main_menu(role)
                            )
                            add_pending_moderation('user_update', data['telegram_id'])
                            set_user_state(admin_id, '')

                            message_text = format_logist_moderation_message(data, company_name)

                            for admin in admins:
                                try:
                                    bot.send_message(
                                        admin['telegram_id'],
                                        message_text,
                                        reply_markup=get_approve_reject_user_keyboard(data['telegram_id']),
                                        parse_mode='Markdown'
                                    )
                                except Exception as e:
                                    print(f"Ошибка при отправке сообщения администратору {admin['telegram_id']}: {e}")
                        else:
                            # Для админа - сразу активируем
                            bot.send_message(
                                chat_id,
                                f"✅ Данные логиста {data['first_name']} успешно обновлены!\n\n"
                                f"Логист должен завершить регистрацию, введя остальные данные.",
                                reply_markup=get_logist_management_keyboard()
                            )

                            # Уведомляем пользователя об обновлении
                            try:
                                bot.send_message(
                                    data['telegram_id'],
                                    f"✅ Ваши данные были обновлены администратором.\n\n"
                                    f"Теперь вы можете продолжить регистрацию в роли логиста.\n"
                                    f"Нажмите /start для начала работы.",
                                    reply_markup=ReplyKeyboardRemove()
                                )
                            except Exception as e:
                                print(f"Не удалось уведомить пользователя {data['telegram_id']}: {e}")

                        if admin_id in admin_temp_data:
                            del admin_temp_data[admin_id]

                        set_user_state(admin_id, 'waiting_for_logist_management_action')
                    else:
                        bot.send_message(chat_id, "❌ Ошибка при обновлении данных логиста.")
                        return
                else:
                    bot.send_message(chat_id, "❌ Нет данных для обновления.")
                    return

            else:
                print('Пользователь не существует - создаем нового')
                if admin_role == 'external_admin':
                    success = db.execute_query(
                        """INSERT INTO users 
                            (first_name, role, phone, telegram_id, email, company_id, created_by, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 'added_pending')""",
                        (data['first_name'], data['role'], data['phone'], data['telegram_id'],
                         data['email'], company_id, admin_id)
                    )

                    if success:
                        # Инициализируем рейтинг для нового пользователя
                        init_user_rating(db, data['telegram_id'], data['role'])

                        admins = db.get_all_admins()
                        if not admins:
                            print("Не найдены администраторы для отправки заявки")
                            return

                        bot.send_message(
                            admin_id,
                            '🕐 **Данные отправлены главному администратору на проверку**\n'
                            'Вам придет уведомление о результате проверки',
                            reply_markup=get_main_menu(role)
                        )
                        add_pending_moderation('user_registration', data['telegram_id'])
                        set_user_state(admin_id, '')

                        message_text = format_logist_moderation_message(data, company_name)

                        for admin in admins:
                            try:
                                bot.send_message(
                                    admin['telegram_id'],
                                    message_text,
                                    reply_markup=get_approve_reject_user_keyboard(data['telegram_id']),
                                    parse_mode='Markdown'
                                )
                            except Exception as e:
                                print(f"Ошибка при отправке сообщения администратору {admin['telegram_id']}: {e}")
                    else:
                        bot.send_message(chat_id, '❌ Ошибка при сохранении данных.')
                        return
                else:
                    # Админ создает нового логиста
                    success = db.execute_query(
                        """INSERT INTO users 
                        (company_id, first_name, role, phone, telegram_id, email, status, created_by, approved_by, created_at) 
                        VALUES (?, ?, ?, ?, ?, ?, 'added', ?, ?, datetime('now'))""",
                        (company_id, data['first_name'], data['role'], data['phone'],
                         data['telegram_id'], data['email'], admin_id, admin_id)
                    )

                    if success:
                        # Инициализируем рейтинг для нового пользователя
                        init_user_rating(db, data['telegram_id'], data['role'])

                        bot.send_message(
                            chat_id,
                            f"✅ Логист {data['first_name']} успешно добавлен!\n\n"
                            f"Логист должен завершить регистрацию, введя остальные данные.",
                            reply_markup=get_logist_management_keyboard()
                        )

                        # Отправляем приветственное сообщение новому пользователю
                        try:
                            bot.send_message(
                                data['telegram_id'],
                                f"✅ Вас добавили в систему как логиста.\n\n"
                                f"Нажмите /start для продолжения регистрации.",
                                reply_markup=get_main_menu(data['role'])
                            )
                        except Exception as e:
                            print(f"Не удалось отправить приветственное сообщение: {e}")

                        if admin_id in admin_temp_data:
                            del admin_temp_data[admin_id]

                        set_user_state(admin_id, 'waiting_for_logist_management_action')
                    else:
                        bot.send_message(
                            chat_id,
                            "❌ Ошибка при добавлении логиста. Попробуйте позже.",
                            reply_markup=get_logist_management_keyboard()
                        )

        except Exception as e:
            print(f"Ошибка при создании/обновлении логиста: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(
                chat_id,
                "❌ Произошла ошибка при добавлении логиста. Попробуйте позже.",
                reply_markup=get_logist_management_keyboard()
            )

    def show_logists_list(bot, db, admin_id, chat_id, role):
        if role == 'external_admin':
            company_result = db.get_company_id_by_user_id(admin_id)
            company_id = company_result['company_id'] if company_result and 'company_id' in company_result else None
            logists = db.fetch_all("select * from users where role='external_logist' and status = 'active' and company_id = ?", (company_id,))
            if not logists:
                bot.send_message(
                    chat_id,
                    "📭 Список логистов пуст.",
                    reply_markup=get_logist_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_logist_management_action')
                return
            if admin_id not in admin_temp_data:
                admin_temp_data[admin_id] = {}
            admin_temp_data[admin_id]['logists_list'] = logists

        else:
            logists = db.fetch_all(
                "SELECT * FROM users WHERE role = 'logist' AND status = 'active' ORDER BY first_name"
            )

            if not logists:
                bot.send_message(
                    chat_id,
                    "📭 Список логистов пуст.",
                    reply_markup=get_logist_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_logist_management_action')
                return

            # Сохраняем список логистов для последующего выбора
            if admin_id not in admin_temp_data:
                admin_temp_data[admin_id] = {}
            admin_temp_data[admin_id]['logists_list'] = logists

        role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }
        # Формируем сообщение со списком
        message_text = "📋 Список логистов:\n\n"
        for i, logist in enumerate(logists, 1):
            message_text += f"{i}. {logist['first_name']} - {role_names.get(logist['role'], 'Должность не указана')}\n"
            message_text += f"   📞 {logist.get('phone', 'Телефон не указан')}\n"
            message_text += f"   📧 {logist.get('email', 'Email не указан')}\n\n"

        message_text += "Выберите логиста для управления:"

        # Создаем клавиатуру с кнопками для каждого логиста
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        for i, logist in enumerate(logists, 1):
            keyboard.add(
                KeyboardButton(f"👤 {logist['first_name']} {logist['last_name']} (ID: {logist['telegram_id']})"))

        keyboard.add(KeyboardButton("⬅️ Назад"))

        bot.send_message(chat_id, message_text, reply_markup=keyboard)
        set_user_state(admin_id, 'waiting_for_logist_selection')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_logist_selection')
    def handle_logist_selection(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "👥 Управление логистами\n\n"
                "Выберите действие:",
                reply_markup=get_logist_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_logist_management_action')
            return

        # Ищем выбранного логиста
        if admin_id not in admin_temp_data or 'logists_list' not in admin_temp_data[admin_id]:
            bot.send_message(chat_id, "❌ Ошибка. Попробуйте еще раз.")
            return

        # Извлекаем ID логиста из текста кнопки
        try:
            logist_id = int(message.text.split('ID: ')[1].split(')')[0])
        except (IndexError, ValueError):
            bot.send_message(chat_id, "❌ Неверный формат выбора. Попробуйте еще раз.")
            return

        # Находим логиста
        selected_logist = None
        for logist in admin_temp_data[admin_id]['logists_list']:
            if logist['telegram_id'] == logist_id:
                selected_logist = logist
                break

        if not selected_logist:
            bot.send_message(chat_id, "❌ Логист не найден. Попробуйте еще раз.")
            return

        # Сохраняем выбранного логиста для редактирования
        admin_temp_data[admin_id]['editing_logist'] = selected_logist

        # Показываем меню управления выбранным логистом
        print("Запускается функция show_logist_management_menu")
        show_logist_management_menu(bot, admin_id, chat_id, selected_logist)

    def show_logist_management_menu(bot, admin_id, chat_id, logist):
        """Показывает меню управления конкретным логистом"""
        company = db.get_company_by_id(logist.get('company_id'))
        role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }

        message_text = f"""
            👤 **Управление логистом:**

            **Имя:** {logist['first_name']}
            **Фамилия:** {logist.get('last_name', 'Не указана')}
            **Отчество:** {logist.get('patronymic', 'Не указано')}
            **Компания:** {company.get('name', 'Не указана')}
            **Должность:** {role_names.get(logist['role'], 'Не указана')}
            **Телефон:** {logist.get('phone', 'Не указан')}
            **Email:** {logist.get('email', 'Не указан')}
            **Дата рождения:** {logist.get('birth_date', 'Не указана')}
            **Паспорт:** {logist.get('passport_series', '')} {logist.get('passport_number', '')}
            **Дата выдачи паспорта:** {logist.get('passport_issue_date', 'Не указана')}
            **Адрес регистрации:** {logist.get('registration_address', 'Не указан')}
            **Код АТИ:** {logist.get('ati_code', 'Не указан')}
            **Статус:** {status_names.get(logist['status'], 'Не указан')}

            Выберите действие:
                    """

        bot.send_message(
            chat_id,
            message_text,
            reply_markup=get_specific_logist_management_keyboard(),
            parse_mode='Markdown'
        )
        set_user_state(admin_id, 'waiting_for_specific_logist_action')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_specific_logist_action')
    def handle_specific_logist_action(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(admin_id)
        role = user_role['role'] if user_role else None

        if message.text == "✏️ Редактировать данные":
            # Начинаем процесс редактирования
            start_logist_editing(bot, admin_id)

        elif message.text == "🗑️ Удалить логиста":
            # Запрос подтверждения удаления
            bot.send_message(
                chat_id,
                "❌ Вы уверены, что хотите удалить этого логиста?\n\n"
                "Это действие нельзя отменить.",
                reply_markup=get_confirmation_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_delete_logist_confirmation')

        elif message.text == "⬅️ Назад к списку":
            show_logists_list(bot, db, admin_id, chat_id, role)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_delete_logist_confirmation')
    def handle_delete_confirmation(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(admin_id)
        role = user_role['role'] if user_role else None

        if message.text == "✅ Да, удалить":
            delete_logist(bot, db, admin_id, chat_id, role)
        elif message.text == "❌ Нет, отменить":
            if admin_id in admin_temp_data and 'editing_logist' in admin_temp_data[admin_id]:
                show_logist_management_menu(bot, admin_id, chat_id, admin_temp_data[admin_id]['editing_logist'])
            else:
                bot.send_message(
                    chat_id,
                    "👥 Управление логистами\n\n"
                    "Выберите действие:",
                    reply_markup=get_logist_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_logist_management_action')

    def delete_logist(bot, db, admin_id, chat_id, user_role):
        """Удаляет логиста"""
        admin_username = db.get_username(admin_id)
        username = admin_username['username'] if admin_username and "username" in admin_username else None
        if user_role == 'external_admin':
            if admin_id not in admin_temp_data or 'editing_logist' not in admin_temp_data[admin_id]:
                bot.send_message(chat_id, "❌ Ошибка. Логист не найден.")
                return

            logist = admin_temp_data[admin_id]['editing_logist']
            admins = db.get_all_admins()
            if not admins:
                print("Не найдены администраторы для отправки заявки")
                return
            bot.send_message(
                chat_id,
                "🕐**Ваша заявка на удаление пользователя отправлена администратору!**\n\n"
                "**Вы получите уведомление о результате модерации заявки.**",
                reply_markup=get_logist_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_logist_management_action')
            for admin in admins:
                bot.send_message(
                    admin['telegram_id'],
                    f"❗️ Запрос на удаление пользователя {logist['first_name']}, Telegram ID:{logist['telegram_id']}!!!\n\n"
                    f"Запросил @{username}",
                    reply_markup=get_approve_reject_delete_keyboard(logist['telegram_id'], admin_id),
                )
                add_pending_moderation('user_delete', logist['telegram_id'])
        else:
            try:
                if admin_id not in admin_temp_data or 'editing_logist' not in admin_temp_data[admin_id]:
                    bot.send_message(chat_id, "❌ Ошибка. Логист не найден.")
                    return

                logist = admin_temp_data[admin_id]['editing_logist']

                success = db.execute_query(
                    "delete from users WHERE telegram_id = ?",
                    (logist.get('id'),)
                )

                if success:
                    bot.send_message(
                        chat_id,
                        f"✅ Логист {logist['first_name']} успешно удален.",
                        reply_markup=get_logist_management_keyboard()
                    )

                    # Очищаем временные данные
                    if admin_id in admin_temp_data:
                        if 'editing_logist' in admin_temp_data[admin_id]:
                            del admin_temp_data[admin_id]['editing_logist']
                        if 'logists_list' in admin_temp_data[admin_id]:
                            del admin_temp_data[admin_id]['logists_list']

                    set_user_state(admin_id, 'waiting_for_logist_management_action')
                else:
                    bot.send_message(chat_id, "❌ Ошибка при удалении логиста.")

            except Exception as e:
                print(f"Ошибка при удалении логиста: {e}")
                bot.send_message(chat_id, "❌ Произошла ошибка при удалении логиста.")

    def start_logist_editing(bot, admin_id):
        """Начинает процесс редактирования логиста"""
        if admin_id not in admin_temp_data or 'editing_logist' not in admin_temp_data[admin_id]:
            bot.send_message(admin_id, "❌ Ошибка. Логист не найден.")
            return

        bot.send_message(
            admin_id,
            "✏️ Редактирование данных логиста\n\n"
            "Выберите что хотите отредактировать:",
            reply_markup=get_extended_editing_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_editing_logist_field_selection')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_editing_logist_field_selection')
    def handle_editing_logist_field_selection(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )

        if message.text == "⬅️ Назад":
            if admin_id in admin_temp_data and 'editing_logist' in admin_temp_data[admin_id]:
                show_logist_management_menu(bot, admin_id, chat_id, admin_temp_data[admin_id]['editing_logist'])
            return

        logist = admin_temp_data[admin_id]['editing_logist']

        if message.text == "👤 Редактировать имя":
            bot.send_message(
                chat_id,
                f"Текущее имя: {logist['first_name']}\nВведите новое имя:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_name')

        elif message.text == "👤 Редактировать фамилию":
            bot.send_message(
                chat_id,
                f"Текущая фамилия: {logist.get('last_name', 'Не указана')}\nВведите новую фамилию:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_last_name')

        elif message.text == "👤 Редактировать отчество":
            bot.send_message(
                chat_id,
                f"Текущее отчество: {logist.get('patronymic', 'Не указано')}\nВведите новое отчество:",
                reply_markup=get_skip_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_patronymic')

        elif message.text == "💼 Редактировать должность":
            bot.send_message(
                chat_id,
                f"Текущая должность: {role_names.get(logist.get('role', 'Не указана'))}\nВыберите новую должность:",
                reply_markup=get_role_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_role')

        elif message.text == "📞 Редактировать телефон":
            bot.send_message(
                chat_id,
                f"Текущий телефон: {logist.get('phone', 'Не указан')}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_phone')

        elif message.text == "📧 Редактировать email":
            bot.send_message(
                chat_id,
                f"Текущий email: {logist.get('email', 'Не указан')}\nВведите новый email:",
                reply_markup=get_email_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_email')

        elif message.text == "🎂 Редактировать дату рождения":
            bot.send_message(
                chat_id,
                f"Текущая дата рождения: {logist.get('birth_date', 'Не указана')}\nВведите новую дату рождения (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_birth_date')

        elif message.text == "📘 Редактировать серию паспорта":
            bot.send_message(
                chat_id,
                f"Текущая серия паспорта: {logist.get('passport_series', 'Не указана')}\nВведите новую серию паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_passport_series')

        elif message.text == "📘 Редактировать номер паспорта":
            bot.send_message(
                chat_id,
                f"Текущий номер паспорта: {logist.get('passport_number', 'Не указан')}\nВведите новый номер паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_passport_number')

        elif message.text == "📅 Редактировать дату выдачи паспорта":
            bot.send_message(
                chat_id,
                f"Текущая дата выдачи паспорта: {logist.get('passport_issue_date', 'Не указана')}\nВведите новую дату выдачи паспорта (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_passport_issue_date')

        elif message.text == "📍 Редактировать адрес регистрации":
            bot.send_message(
                chat_id,
                f"Текущий адрес регистрации: {logist.get('registration_address', 'Не указан')}\nВведите новый адрес регистрации:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_registration_address')

        elif message.text == "🔢 Редактировать код АТИ":
            bot.send_message(
                chat_id,
                f"Текущий код АТИ: {logist.get('ati_code', 'Не указан')}\nВведите новый код АТИ:",
                reply_markup=get_skip_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_logist_ati_code')
        elif message.text == "🏢 Редактировать компанию":
            bot.send_message(
                chat_id,
                f"Текущая компания: {logist.get('company', 'Не указана')}\n Выберите новую компанию:",
                reply_markup=get_company_selection_keyboard(companies)
            )
            set_user_state(admin_id, 'waiting_for_existing_logist_company')

    def edit_user(admin_id, user_id, old_value, new_value, parameter, query):
        user_info = db.get_user_role(admin_id)
        role = user_info['role'] if user_info else None
        user = db.get_user_by_telegram_id(user_id)
        if role == 'admin':
            success = db.execute_query(query, (new_value,user_id))
            print(f"DEBUG - execute_query result: {success}")
            if success:
                admin_temp_data[admin_id]['editing_logist'][parameter] = new_value
                bot.send_message(admin_id, "✅ Данные успешно обновлены!")
                if parameter == 'role':
                    bot.send_message(
                        admin_id,
                        "👥 Управление логистами\n\n"
                        "Выберите действие:",
                        reply_markup=get_logist_management_keyboard()
                    )
                    set_user_state(admin_id, 'waiting_for_logist_management_action')
                else:
                    start_logist_editing(bot, admin_id)
            else:
                bot.send_message(admin_id, "❌ Ошибка при обновлении данных.")
        else:
            email_subject = f"📝 Заявка на изменение данных"
            email_message =  f"""
                     **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
                     **Telegram ID:** {user_id}
                     **Роль:** {role_names.get(user['role'])}

                     **Изменяемое поле:** {user_fields_display.get(parameter, parameter)}
                     **Старое значение:** {role_names.get(old_value, old_value)}
                     **Новое значение:** {role_names.get(new_value, new_value)}

                     **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

                     Откройте чат с Телеграм-ботом, примите или отклоните регистрацию.
                """,
            admins = db.get_all_admins()
            for admin in admins:
                bot.send_message(
                    admin['telegram_id'],
                    f"""
                📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ ДАННЫХ**

                👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
                🆔 **Telegram ID:** {user_id}
                🏢 **Роль:** {role_names.get(user['role'])}

                📋 **Изменяемое поле:** {user_fields_display.get(parameter, parameter)}
                📄 **Старое значение:** {role_names.get(old_value, old_value)}
                🔄 **Новое значение:** {role_names.get(new_value, new_value)}

                ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

                Для подтверждения или отклонения изменения используйте панель администратора.
                    """,
                reply_markup = get_approve_reject_edit_keyboard(user_id, new_value, parameter, admin_id)
                )
                if not admin['email'] or not isinstance(admin['email'], str) or not admin['email'].strip():
                    print(f"Пропускаем администратора с некорректным email: {admin}")
                    continue

                    # Убираем пробелы
                if not admin['email'] or not isinstance(admin['email'], str) or not admin['email'].strip():
                    print(f"Пропускаем администратора с некорректным email: {admin}")
                    continue

                try:
                    # Отправляем email
                    send_email_notification(email_subject, email_message, admin['email'])
                    print(f"Email отправлен администратору: {admin['email']}")
                except Exception as e:
                    print(f"Ошибка при отправке email администратору {admin['email']}: {e}")
                    # Продолжаем отправку остальным администраторам
                    continue

            add_pending_moderation('user_edit', user_id)
            bot.send_message(
                admin_id,
                '🕐**Данные отправлены главному администратору на проверку**\n'
                '  **Вам придет уведомление о результате проверки**',
                reply_markup = get_main_menu(role)
            )
            set_user_state(admin_id, '')

    # Обработчики редактирования существующего логиста
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_name')
    def handle_editing_existing_logist_first_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'first_name'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Имя должно содержать минимум 2 символа. Введите имя:")
            return

        query = 'UPDATE users SET first_name = ? WHERE telegram_id = ?'

        new_first_name = message.text.strip()
        old_first_name = user['first_name']

        edit_user(admin_id, logist_id, old_first_name, new_first_name, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_last_name')
    def handle_editing_existing_logist_last_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'last_name'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Фамилия не может быть пустой. Введите фамилию:")
            return

        query = 'UPDATE users SET last_name = ? WHERE telegram_id = ?'

        new_last_name = message.text.strip()
        old_last_name = user['last_name']

        edit_user(admin_id, logist_id, old_last_name, new_last_name, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_patronymic')
    def handle_editing_existing_logist_patronymic(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'patronymic'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        if message.text == "⏭️ Пропустить":
            patronymic = None
        else:
            patronymic = message.text.strip()
            if not patronymic:
                bot.send_message(chat_id, "❌ Отчество не может быть пустым. Введите отчество или пропустите:")
                return

        query = 'UPDATE users SET patronymic = ? WHERE telegram_id = ?'

        new_patronymic = message.text.strip()
        old_patronymic = user['patronymic']

        edit_user(admin_id, logist_id, old_patronymic, new_patronymic, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_existing_logist_company')
    def handle_editing_existing_executor_company(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'company'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return
        if message.text == '🔍Поиск по ИНН':
            bot.send_message(
                chat_id,
                'Введите ИНН компании, которую хотите выбрать:',
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(admin_id, 'waiting_for_company_inn_existing')
            return
        else:
            # Убираем эмодзи из названия компании
            company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text

            query = 'UPDATE users SET company = ? WHERE telegram_id = ?'

            new_company = company_name
            old_company = user['company']

            edit_user(admin_id, logist_id, old_company, new_company, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_inn_existing')
    def handle_company_inn(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        company_data = db.get_approved_company_by_inn(message.text)
        if not company_data:
            bot.send_message(chat_id, '❌ Компания с таким ИНН не найдена.')
            return

        bot.send_message(
            chat_id,
            'Выберите компанию:',
            reply_markup=get_company_selection_keyboard(company_data)
        )
        set_user_state(admin_id, 'waiting_for_existing_logist_company')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_birth_date')
    def handle_editing_existing_logist_birth_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'birth_date'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        # Валидация даты рождения
        try:
            birth_date = datetime.strptime(message.text, '%d.%m.%Y')
            if birth_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата рождения не может быть в будущем. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET birth_date = ? WHERE telegram_id = ?'

        new_birth_date = message.text.strip()
        old_birth_date = user['birth_date']

        edit_user(admin_id, logist_id, old_birth_date, new_birth_date, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_passport_series')
    def handle_editing_existing_logist_passport_series(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'passport_series'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 4:
            bot.send_message(chat_id, "❌ Серия паспорта должна состоять из 4 цифр. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET passport_series = ? WHERE telegram_id = ?'

        new_passport_series = message.text.strip()
        old_passport_series = user['passport_series']

        edit_user(admin_id, logist_id, old_passport_series, new_passport_series, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_passport_number')
    def handle_editing_existing_logist_passport_number(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'passport_number'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 6:
            bot.send_message(chat_id, "❌ Номер паспорта должен состоять из 6 цифр. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET passport_number = ? WHERE telegram_id = ?'

        new_passport_number = message.text.strip()
        old_passport_number = user['passport_number']

        edit_user(admin_id, logist_id, old_passport_number, new_passport_number, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_passport_issue_date')
    def handle_editing_existing_logist_passport_issue_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'passport_issue_date'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        # Валидация даты выдачи паспорта
        try:
            issue_date = datetime.strptime(message.text, '%d.%m.%Y')
            if issue_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET first_name = ? WHERE telegram_id = ?'

        new_passport_issue_date = message.text.strip()
        old_passport_issue_date = user['passport_issue_date']

        edit_user(admin_id, logist_id, old_passport_issue_date, new_passport_issue_date, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_registration_address')
    def handle_editing_existing_logist_registration_address(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'registration_address'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Адрес регистрации не может быть пустым. Введите адрес:")
            return

        query = 'UPDATE users SET registration_address = ? WHERE telegram_id = ?'

        new_registration_address = message.text.strip()
        old_registration_address = user['registration_address']

        edit_user(admin_id, logist_id, old_registration_address, new_registration_address, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_ati_code')
    def handle_editing_existing_logist_ati_code(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'ati_code'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        if message.text == "⏭️ Пропустить":
            ati_code = None
        else:
            ati_code = message.text.strip()
            if not ati_code.isdigit():
                bot.send_message(chat_id, "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз:")
                return

        query = 'UPDATE users SET ati_code = ? WHERE telegram_id = ?'

        new_ati_code = message.text.strip()
        old_ati_code = user['ati_code']

        edit_user(admin_id, logist_id, old_ati_code, new_ati_code, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_role')
    def handle_editing_existing_logist_role(message):
        admin_id = message.from_user.id
        admin = db.get_user_by_telegram_id(admin_id)
        admin_role = admin['role']
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'role'
        user = db.get_user_by_telegram_id(logist_id)
        role = ''

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return
        if admin_role in ['admin', 'logist', 'executor']:
            if message.text == '👑 Администратор':
                role = 'admin'
            elif message.text == '📊 Логист':
                role = 'logist'
            elif message.text == '🚛 Перевозчик':
                role = 'executor'
        else:
            if message.text == '👑 Администратор':
                role = 'external_admin'
            elif message.text == '📊 Логист':
                role = 'external_logist'
            elif message.text == '🚛 Перевозчик':
                role = 'external_executor'
        admin_temp_data[admin_id]['editing_logist']['role'] = role

        query = 'UPDATE users SET role = ? WHERE telegram_id = ?'

        new_role = role
        old_role = user['role']


        edit_user(admin_id, logist_id, old_role, new_role, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_phone')
    def handle_editing_existing_logist_phone(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'phone'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            bot.send_message(
                chat_id,
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:"
            )
            return

        query = 'UPDATE users SET phone = ? WHERE telegram_id = ?'

        new_phone = message.text.strip()
        old_phone = user['phone']

        edit_user(admin_id, logist_id, old_phone, new_phone, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_logist_email')
    def handle_editing_existing_logist_email(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        logist_id = admin_temp_data[admin_id]['editing_logist']['telegram_id']
        parameter = 'email'
        user = db.get_user_by_telegram_id(logist_id)

        if message.text == "⬅️ Назад":
            start_logist_editing(bot, admin_id)
            return

        email = message.text.strip()

        if message.text == "📧 logist@impe-rial.ru":
            email = "logist@impe-rial.ru"
        else:
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
                return

        query = 'UPDATE users SET email = ? WHERE telegram_id = ?'

        new_email = message.text.strip()
        old_email = user['email']

        edit_user(admin_id, logist_id, old_email, new_email, parameter, query)

