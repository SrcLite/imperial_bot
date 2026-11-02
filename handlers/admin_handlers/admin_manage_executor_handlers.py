import re
from telebot.types import ReplyKeyboardRemove

from handlers.admin_handlers.pending_moderations_handlers import add_pending_moderation
from keyboards.admin_keyboards import *
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from datetime import datetime
from keyboards.main_menus import get_main_menu, get_start_menu
from keyboards.registration_user_keyboards import get_company_selection_keyboard
from utils.dicts import user_fields_display
from utils.email_sender import send_email_notification
from utils.helpers import check_user_exists, init_user_rating

admin_temp_data = {}
role_names = {
            'admin': '👑 Администратор',
            'logist': '📊 Логист',
            'executor': '🚛 Перевозчик',
            'external_admin': '👑 Администратор',
            'external_logist': '📊 Логист',
            'external_executor': '🚛 Перевозчик'
        }
def register_executor_admin_handlers(bot, db):

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_management_action')
    def handle_executor_management_action(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(admin_id)
        user = db.get_user_by_telegram_id(admin_id)
        if not user and user['status'] != 'active':
            bot.send_message(
                admin_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        role = user_role['role'] if user_role else None
        if message.text == "👤 Добавить перевозчика":
            admin_temp_data[admin_id] = {
                'new_executor': {},
                'editing_executor_id': None
            }

            bot.send_message(
                chat_id,
                "👤 Добавление нового перевозчика\n\n"
                "Введите имя перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_first_name')
        elif message.text == "📋 Список перевозчиков":
            show_executors_list(bot, db, admin_id, chat_id, role)

        elif message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Выберите группу пользователей:",
                reply_markup=get_user_management_keyboard(role)
            )
            set_user_state(admin_id, 'waiting_for_group_management')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_first_name')
    def handle_executor_first_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🚛 Управление перевозчиками\n\n"
                "Выберите действие:",
                reply_markup=get_executor_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_management_action')
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Имя должно содержать минимум 2 символа. Введите имя:")
            return

        admin_temp_data[admin_id]['new_executor']['first_name'] = message.text.strip()

        bot.send_message(
            chat_id,
            "👤 Введите фамилию перевозчика:",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_last_name')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_last_name')
    def handle_executor_last_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "Введите имя перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_first_name')
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Фамилия должна содержать минимум 2 символа. Введите фамилию:")
            return

        admin_temp_data[admin_id]['new_executor']['last_name'] = message.text.strip()

        bot.send_message(
            chat_id,
            "👤 Введите отчество перевозчика (если есть):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_patronymic')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_patronymic')
    def handle_executor_patronymic(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(admin_id)
        role = user_info['role'] if user_info else None

        companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "👤 Введите фамилию перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_last_name')
            return

        if message.text == "⏭️ Пропустить":
            admin_temp_data[admin_id]['new_executor']['patronymic'] = None
        else:
            if not message.text.strip():
                bot.send_message(chat_id, "❌ Отчество не может быть пустым. Введите отчество или пропустите:")
                return
            admin_temp_data[admin_id]['new_executor']['patronymic'] = message.text.strip()


        bot.send_message(
            chat_id,
            "🆔 Введите Telegram ID логиста:\n\n"
            "Чтобы вам было легче, воспользуйтесь ботом, чтобы узнать ID пользователя - @username_to_id_bot",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_telegram_id')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_company')
    def handle_executor_company(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '👤 Введите отчество перевозчика (если есть):',
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_patronymic')
            return
        if message.text == '🔍Поиск по ИНН':
            bot.send_message(
                chat_id,
                'Введите ИНН компании, которую хотите выбрать:',
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(admin_id, 'waiting_for_company_inn')
            return
        else:
            # Убираем эмодзи из названия компании
            company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text

            company = db.fetch_one(
                "SELECT id, name FROM companies WHERE name = ? AND status = 'approved'",
                (company_name,)
            )

            if not company:
                bot.send_message(chat_id, "❌ Компания не найдена. Пожалуйста, выберите компанию из списка.")
                return

            company_id = company['id']
            admin_temp_data[admin_id]['new_executor']['company'] = company_id
            bot.send_message(
                chat_id,
                "🆔 Введите Telegram ID логиста:\n\n"
                "Чтобы вам было легче, воспользуйтесь ботом, чтобы узнать ID пользователя - @username_to_id_bot",
                reply_markup = get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_telegram_id')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_telegram_id')
    def handle_executor_telegram_id(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '👤 Введите отчество перевозчика (если есть):',
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_patronymic')
            return

        telegram_id = message.text.strip()
        admin_temp_data[admin_id]['new_executor']['telegram_id'] = telegram_id
        bot.send_message(
            chat_id,
            '📞 Введите номер телефона перевозчика (в формате +7XXXXXXXXXX или 8XXXXXXXXXX):',
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_phone')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_phone')
    def handle_executor_phone(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🆔 Введите Telegram ID логиста:\n\n"
                "Чтобы вам было легче, воспользуйтесь ботом, чтобы узнать ID пользователя - @username_to_id_bot",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_telegram_id')
            return

        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            bot.send_message(
                chat_id,
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:"
            )
            return

        admin_temp_data[admin_id]['new_executor']['phone'] = phone

        bot.send_message(
            chat_id,
            "📧 Введите email перевозчика:",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_email')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_email')
    def handle_executor_email(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "📞 Введите номер телефона перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_phone')
            return

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', message.text):
            bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['email'] = message.text.strip()

        bot.send_message(
            chat_id,
            "🎂 Введите дату рождения перевозчика (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_birth_date')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_birth_date')
    def handle_executor_birth_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "📧 Введите email перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_email')
            return

        try:
            birth_date = datetime.strptime(message.text, '%d.%m.%Y')
            if birth_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата рождения не может быть в будущем. Попробуйте еще раз:")
                return
            if birth_date.year < 1900:
                bot.send_message(chat_id, "❌ Дата рождения не может быть раньше 1900 года. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['birth_date'] = message.text.strip()

        bot.send_message(
            chat_id,
            "📘 Введите серию паспорта перевозчика (4 цифры):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_passport_series')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_passport_series')
    def handle_executor_passport_series(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🎂 Введите дату рождения перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_birth_date')
            return

        if not (message.text.isdigit() and len(message.text) == 4):
            bot.send_message(chat_id, "❌ Серия паспорта должна состоять из 4 цифр. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['passport_series'] = message.text

        bot.send_message(
            chat_id,
            "📘 Введите номер паспорта перевозчика (6 цифр):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_passport_number')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_passport_number')
    def handle_executor_passport_number(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "📘 Введите серию паспорта перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_passport_series')
            return

        if not (message.text.isdigit() and len(message.text) == 6):
            bot.send_message(chat_id, "❌ Номер паспорта должен состоять из 6 цифр. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['passport_number'] = message.text

        bot.send_message(
            chat_id,
            "📅 Введите дату выдачи паспорта перевозчика (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_passport_issue_date')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_passport_issue_date')
    def handle_executor_passport_issue_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "📘 Введите номер паспорта перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_passport_number')
            return

        try:
            issue_date = datetime.strptime(message.text, '%d.%m.%Y')
            if issue_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
            if issue_date.year < 1990:
                bot.send_message(chat_id, "❌ Дата выдачи не может быть раньше 1990 года. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['passport_issue_date'] = message.text

        bot.send_message(
            chat_id,
            "📍 Введите адрес регистрации перевозчика:",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_registration_address')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_registration_address')
    def handle_executor_registration_address(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "📅 Введите дату выдачи паспорта перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_passport_issue_date')
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Адрес регистрации не может быть пустым. Введите адрес:")
            return

        admin_temp_data[admin_id]['new_executor']['registration_address'] = message.text.strip()

        bot.send_message(
            chat_id,
            "🔢 Введите код АТИ перевозчика (если есть):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_executor_ati_code')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_ati_code')
    def handle_executor_ati_code(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "📍 Введите адрес регистрации перевозчика:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_registration_address')
            return

        if message.text == "⏭️ Пропустить":
            admin_temp_data[admin_id]['new_executor']['ati_code'] = None
        else:
            if not message.text.isdigit():
                bot.send_message(chat_id,
                                 "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз или пропустите:")
                return
            admin_temp_data[admin_id]['new_executor']['ati_code'] = message.text.strip()

        # Показываем сводку данных
        show_executor_summary(bot, admin_id, chat_id)

    def show_executor_summary(bot, admin_id, chat_id):
        """Показывает сводку данных нового перевозчика"""
        user_info = db.get_user_role(admin_id)
        role = user_info['role'] if user_info else None
        company_result = db.get_company_by_id(admin_id['company_id'])
        company_id = company_result['id'] if company_result and 'id' in company_result else None
        print(company_result)


        admin_temp_data[admin_id]['new_executor']['company'] = company_id

        data = admin_temp_data[admin_id]['new_executor']

        summary_text = f"""
        📋 **Проверьте данные нового перевозчика:**
        
        👤 **Личные данные:**
        **ФИО:** {data['last_name']} {data['first_name']} {data.get('patronymic', '')}
        **Компания:** 🏢 {company_result['name']}
        **Должность:** 🚛 Перевозчик
        **Телефон:** {data['phone']}
        **Email:** {data['email']}
        **Дата рождения:** {data.get('birth_date', 'Не указана')}
        
        📘 **Паспортные данные:**
        **Серия:** {data.get('passport_series', 'Не указана')}
        **Номер:** {data.get('passport_number', 'Не указана')}
        **Дата выдачи:** {data.get('passport_issue_date', 'Не указана')}
        **Адрес регистрации:** {data.get('registration_address', 'Не указан')}
        
        🔢 **Код АТИ:** {data.get('ati_code', 'Не указан')}
        
        Если все верно, нажмите "✅ Подтвердить добавление".
        Если нужно что-то изменить, выберите поле для редактирования.
        """

        bot.send_message(
            chat_id,
            summary_text,
            reply_markup=get_executor_confirmation_keyboard(role)
        )
        set_user_state(admin_id, 'waiting_for_executor_confirmation')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_confirmation')
    def handle_executor_confirmation(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(admin_id)
        role = user_info['role'] if user_info else None
        print(f'Роль админа: {role}')
        companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )

        if message.text == "✅ Подтвердить добавление":
            complete_executor_creation(bot, db, admin_id, chat_id, role)
        elif message.text == "✏️ Редактировать ФИО":
            bot.send_message(
                chat_id,
                "Выберите что редактировать:",
                reply_markup=get_edit_executor_name_keyboard()
            )
            set_user_state(admin_id, 'editing_executor_name')
        elif message.text == "✏️ Редактировать контакты":
            bot.send_message(
                chat_id,
                "Выберите что редактировать:",
                reply_markup=get_edit_executor_contacts_keyboard()
            )
            set_user_state(admin_id, 'editing_executor_contacts')
        elif message.text == "✏️ Редактировать паспорт":
            bot.send_message(
                chat_id,
                "Выберите что редактировать:",
                reply_markup=get_edit_executor_passport_keyboard()
            )
            set_user_state(admin_id, 'editing_executor_passport')
        elif message.text == "✏️ Редактировать код АТИ":
            bot.send_message(
                chat_id,
                f"Текущий код АТИ: {admin_temp_data[admin_id]['new_executor'].get('ati_code', 'Не указан')}\nВведите новый код АТИ:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_executor_ati')
        elif message.text == "✏️ Редактировать Telegram ID":
            bot.send_message(
                chat_id,
                f"Текущий Telegram ID {admin_temp_data[admin_id]['new_executor'].get('telegram_id', 'Не указан')}\nВведите новый Telegram ID:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_executor_telegram_id')
        elif message.text == "✏️ Редактировать компанию":
            bot.send_message(
                chat_id,
                f"Текущая компания {admin_temp_data[admin_id]['new_executor'].get('company', 'Не указан')}\nВыберите новую компанию:",
                reply_markup=get_company_selection_keyboard(companies)
            )
            set_user_state(admin_id, 'editing_executor_company')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_name')
    def handle_editing_executor_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        elif message.text == "👤 Редактировать имя":
            set_user_state(admin_id, 'editing_executor_first_name')
            bot.send_message(
                chat_id,
                f"Текущее имя: {admin_temp_data[admin_id]['new_executor']['first_name']}\nВведите новое имя:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "👤 Редактировать фамилию":
            set_user_state(admin_id, 'editing_executor_last_name')
            bot.send_message(
                chat_id,
                f"Текущая фамилия: {admin_temp_data[admin_id]['new_executor']['last_name']}\nВведите новую фамилию:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "👤 Редактировать отчество":
            set_user_state(admin_id, 'editing_executor_patronymic')
            bot.send_message(
                chat_id,
                f"Текущее отчество: {admin_temp_data[admin_id]['new_executor'].get('patronymic', 'Не указано')}\nВведите новое отчество:",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_first_name')
    def handle_editing_executor_first_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return

        if not message.text.isalpha() or len(message.text) < 2:
            bot.send_message(chat_id,
                             "❌ Имя должно содержать только буквы и быть не короче 2 символов. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['first_name'] = message.text.strip()
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_last_name')
    def handle_editing_executor_last_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return

        if not message.text.isalpha() or len(message.text) < 2:
            bot.send_message(chat_id,
                             "❌ Фамилия должна содержать только буквы и быть не короче 2 символов. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['last_name'] = message.text.strip()
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_patronymic')
    def handle_editing_executor_patronymic(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return

        if message.text == "⏭️ Пропустить":
            admin_temp_data[admin_id]['new_executor']['patronymic'] = None
        else:
            if not message.text.isalpha() or len(message.text) < 2:
                bot.send_message(chat_id,
                                 "❌ Отчество должно содержать только буквы и быть не короче 2 символов. Попробуйте еще раз или пропустите:")
                return
            admin_temp_data[admin_id]['new_executor']['patronymic'] = message.text.strip()

        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_editing_executor_company')
    def handle_editing_executor_company(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        if message.text == '🔍Поиск по ИНН':
            bot.send_message(
                chat_id,
                'Введите ИНН компании, которую хотите выбрать:',
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(admin_id, 'waiting_for_company_inn_editing')
            return
        else:
            # Убираем эмодзи из названия компании
            company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text

            company = db.fetch_one(
                "SELECT id, name FROM companies WHERE name = ? AND status = 'approved'",
                (company_name,)
            )

            if not company:
                bot.send_message(chat_id, "❌ Компания не найдена. Пожалуйста, выберите компанию из списка.")
                return

            company_id = company['id']
            admin_temp_data[admin_id]['new_executor']['company'] = company_id
            show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_inn' or
                                              get_user_state(message.from_user.id) == 'waiting_for_company_inn_editing' or
                                              get_user_state(message.from_user.id) == 'waiting_for_company_inn_existing')
    def handle_company_inn(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        company_data = db.get_approved_company_by_inn(message.text)
        current_state = get_user_state(admin_id)
        if not company_data:
            bot.send_message(chat_id, '❌ Компания с таким ИНН не найдена.')
            return

        bot.send_message(
            chat_id,
            'Выберите компанию:',
            reply_markup=get_company_selection_keyboard(company_data)
        )
        if current_state == 'waiting_for_company_inn':
            set_user_state(admin_id, 'waiting_for_executor_company')
        elif current_state == 'waiting_for_company_inn_editing':
            set_user_state(admin_id, 'waiting_for_editing_executor_company')
        elif current_state == 'waiting_for_existing_executor_company':
            set_user_state(admin_id, 'waiting_for_existing_executor_company')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_telegram_id')
    def handle_editing_executor_telegram_id(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        telegram_id = message.text.strip()
        admin_temp_data[admin_id]['new_executor']['telegram_id'] = telegram_id
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_contacts')
    def handle_editing_executor_contacts(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        elif message.text == "📞 Редактировать телефон":
            set_user_state(admin_id, 'editing_executor_phone')
            bot.send_message(
                chat_id,
                f"Текущий телефон: {admin_temp_data[admin_id]['new_executor']['phone']}\nВведите новый номер телефона:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📧 Редактировать email":
            set_user_state(admin_id, 'editing_executor_email')
            bot.send_message(
                chat_id,
                f"Текущий email: {admin_temp_data[admin_id]['new_executor']['email']}\nВведите новый email:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "🎂 Редактировать дату рождения":
            set_user_state(admin_id, 'editing_executor_birth_date')
            bot.send_message(
                chat_id,
                f"Текущая дата рождения: {admin_temp_data[admin_id]['new_executor'].get('birth_date', 'Не указана')}\nВведите новую дату рождения:",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_phone')
    def handle_editing_executor_phone(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            bot.send_message(
                chat_id,
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:"
            )
            return

        admin_temp_data[admin_id]['new_executor']['phone'] = phone
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_email')
    def handle_editing_executor_email(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return

        email = message.text.strip()

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['email'] = email
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_birth_date')
    def handle_editing_executor_birth_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return

        try:
            birth_date = datetime.strptime(message.text, '%d.%m.%Y')
            if birth_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата рождения не может быть в будущем. Попробуйте еще раз:")
                return
            if birth_date.year < 1900:
                bot.send_message(chat_id, "❌ Дата рождения не может быть раньше 1900 года. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        admin_temp_data[admin_id]['new_executor']['birth_date'] = message.text.strip()
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_passport')
    def handle_editing_executor_passport(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        elif message.text == "📘 Редактировать серию паспорта":
            set_user_state(admin_id, 'editing_executor_passport_series')
            bot.send_message(
                chat_id,
                f"Текущая серия паспорта: {admin_temp_data[admin_id]['new_executor']['passport_series']}\nВведите новую серию:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📘 Редактировать номер паспорта":
            set_user_state(admin_id, 'editing_executor_passport_number')
            bot.send_message(
                chat_id,
                f"Текущий номер паспорта: {admin_temp_data[admin_id]['new_executor']['passport_number']}\nВведите новый номер:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📍 Редактировать адрес регистрации":
            set_user_state(admin_id, 'editing_executor_registration_address')
            bot.send_message(
                chat_id,
                f"Текущий адрес регистрации: {admin_temp_data[admin_id]['new_executor']['registration_address']}\nВведите новый адрес:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📅 Редактировать дату выдачи паспорта":
            set_user_state(admin_id, 'editing_executor_passport_issue_date')
            bot.send_message(
                chat_id,
                f"Текущая дата выдачи паспорта: {admin_temp_data[admin_id]['new_executor']['passport_issue_date']}\nВведите новую дату выдачи:",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_passport_series')
    def handle_editing_executor_passport_series(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        passport_series = message.text.strip()
        if len(passport_series) != 4 or not passport_series.isdigit():
            bot.send_message(chat_id, '❌ Серия паспорта должна содержать 4 цифры.')
            return
        admin_temp_data[admin_id]['new_executor']['passport_series'] = passport_series
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_passport_number')
    def handle_editing_executor_passport_number(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        passport_number = message.text.strip()
        if len(passport_number) != 6 or not passport_number.isdigit():
            bot.send_message(chat_id, '❌ Номер паспорта должен содержать 6 цифр.')
            return
        admin_temp_data[admin_id]['new_executor']['passport_number'] = passport_number
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_registration_address')
    def handle_editing_executor_registration_address(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        registration_address = message.text.strip()
        admin_temp_data[admin_id]['new_executor']['registration_address'] = registration_address
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_passport_issue_date')
    def handle_editing_executor_passport_issue_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return
        passport_issue_date = message.text.strip()
        try:
            issue_date = datetime.strptime(passport_issue_date, '%d.%m.%Y')
            if issue_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
            if issue_date.year < 1990:
                bot.send_message(chat_id, "❌ Дата выдачи не может быть раньше 1990 года. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return
        admin_temp_data[admin_id]['new_executor']['passport_issue_date'] = passport_issue_date
        show_executor_summary(bot, admin_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_executor_ati')
    def handle_editing_executor_ati(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == "⬅️ Назад":
            show_executor_summary(bot, admin_id, chat_id)
            return

        if message.text == "⏭️ Пропустить":
            admin_temp_data[admin_id]['new_executor']['ati_code'] = None
        else:
            ati_code = message.text.strip()
            if not ati_code.isdigit():
                bot.send_message(chat_id, "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз:")
                return
            admin_temp_data[admin_id]['new_executor']['ati_code'] = ati_code

        show_executor_summary(bot, admin_id, chat_id)

    def format_logist_moderation_message(data):
        return  f"""📋 **Проверьте данные нового перевозчика:**
        
        👤 **Личные данные:**
        **ФИО:** {data['last_name']} {data['first_name']} {data.get('patronymic', '')}
        **Компания:** 🏢 {data['company_name']}
        **Должность:** {role_names.get(data['role'])}
        **Телефон:** {data['phone']}
        **Email:** {data['email']}
        **Дата рождения:** {data.get('birth_date', 'Не указана')}
        
        📘 **Паспортные данные:**
        **Серия:** {data.get('passport_series', 'Не указана')}
        **Номер:** {data.get('passport_number', 'Не указана')}
        **Дата выдачи:** {data.get('passport_issue_date', 'Не указана')}
        **Адрес регистрации:** {data.get('registration_address', 'Не указан')}
        
        🔢 **Код АТИ:** {data.get('ati_code', 'Не указан')}
        
        Если все верно, нажмите "✅ Подтвердить добавление".
        """

    def complete_executor_creation(bot, db, admin_id, chat_id, admin_role):
        """Завершает создание перевозчика с поддержкой обновления существующих пользователей"""
        try:
            # Получаем данные нового перевозчика
            data = admin_temp_data[admin_id]['new_executor']
            company_name = db.get_company_by_id(data['company'])['name']
            data['company_name'] = company_name

            # Проверяем, существует ли пользователь с таким telegram_id
            existing_user = db.get_user_by_telegram_id(data['telegram_id'])

            if existing_user:
                # Пользователь существует - обновляем данные
                # Формируем запрос на обновление только переданных полей
                update_fields = []
                update_values = []

                # Список полей для обновления
                fields_to_update = [
                    ('company_id', data.get('company')),
                    ('first_name', data.get('first_name')),
                    ('last_name', data.get('last_name')),
                    ('patronymic', data.get('patronymic')),
                    ('phone', data.get('phone')),
                    ('email', data.get('email')),
                    ('birth_date', data.get('birth_date')),
                    ('passport_series', data.get('passport_series')),
                    ('passport_number', data.get('passport_number')),
                    ('passport_issue_date', data.get('passport_issue_date')),
                    ('registration_address', data.get('registration_address')),
                    ('ati_code', data.get('ati_code')),
                    ('created_by', admin_id),
                    ('updated_by', admin_id)
                ]

                # Определяем роль и статус в зависимости от роли администратора
                if admin_role == 'admin':
                    target_role = 'executor'
                    data['role'] = 'executor'
                    target_status = 'added'
                else:
                    target_role = 'external_executor'
                    data['role'] = 'external_executor'
                    target_status = 'added_pending'

                fields_to_update.extend([
                    ('role', target_role),
                    ('status', target_status)
                ])

                # Собираем поля для обновления
                for field, value in fields_to_update:
                    if value is not None:  # Обновляем только если значение передано
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
                        # Проверяем, нужно ли отправлять на модерацию
                        if admin_role == 'admin':
                            bot.send_message(
                                chat_id,
                                f"✅ Данные перевозчика {data['first_name']} {data['last_name']} успешно обновлены!",
                                reply_markup=get_executor_management_keyboard()
                            )
                            set_user_state(admin_id, 'waiting_for_executor_management_action')
                        else:
                            # Для не-админов отправляем на модерацию
                            admins = db.get_all_admins()
                            if not admins:
                                print('Не найдены админы для отправки')
                                bot.send_message(chat_id, '❌ Не найдены администраторы для модерации.')
                                return

                            bot.send_message(
                                admin_id,
                                '🕐 **Данные отправлены главному администратору на проверку**\n'
                                'Вам придет уведомление о результате проверки',
                                reply_markup=get_main_menu(admin_role)
                            )
                            set_user_state(admin_id, '')

                            # Отправляем данные на модерацию
                            print(f"Роль добавленного пользователя{data.get('role')}")
                            message_text = format_logist_moderation_message(data)
                            for admin in admins:
                                try:
                                    bot.send_message(
                                        admin['telegram_id'],
                                        message_text,
                                        reply_markup=get_approve_reject_user_keyboard(data['telegram_id']),
                                        parse_mode='Markdown'
                                    )
                                    add_pending_moderation('user_update', data['telegram_id'])
                                except Exception as e:
                                    print(f"Ошибка при отправке сообщения администратору {admin['telegram_id']}: {e}")
                    else:
                        bot.send_message(chat_id, "❌ Ошибка при обновлении данных перевозчика.")
                        return
                else:
                    bot.send_message(chat_id, "❌ Нет данных для обновления.")
                    return

            else:
                # Пользователь не существует - создаем нового
                # Определяем роль и статус в зависимости от роли администратора
                if admin_role in ['external_admin', 'external_logist', 'logist']:
                    if admin_role in ["external_admin", "external_logist"]:
                        data['role'] = 'external_executor'
                        data['status'] = 'added_pending'
                    elif admin_role == "logist":
                        data['role'] = 'executor'
                        data['status'] = 'added_pending'

                    success = db.execute_query(
                        """INSERT INTO users 
                        (telegram_id, company_id, first_name, last_name, patronymic, role, phone, email, 
                        birth_date, passport_series, passport_number, passport_issue_date, 
                        registration_address, ati_code, status, created_by) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            data['telegram_id'], data['company'], data['first_name'], data['last_name'],
                            data.get('patronymic'), data['role'], data['phone'], data['email'],
                            data.get('birth_date'), data.get('passport_series'), data.get('passport_number'),
                            data.get('passport_issue_date'), data.get('registration_address'),
                            data.get('ati_code'), data['status'], admin_id
                        )
                    )
                    if success:
                        admins = db.get_all_admins()
                        if not admins:
                            print('Не найдены админы для отправки')
                            return

                        bot.send_message(
                            admin_id,
                            '🕐 **Данные отправлены главному администратору на проверку**\n'
                            'Вам придет уведомление о результате проверки',
                            reply_markup=get_main_menu(admin_role)
                        )
                        set_user_state(admin_id, '')
                        print(f"Роль добавленного пользователя{data.get('role')}")
                        message_text = format_logist_moderation_message(data)
                        for admin in admins:
                            try:
                                bot.send_message(
                                    admin['telegram_id'],
                                    message_text,
                                    reply_markup=get_approve_reject_user_keyboard(data['telegram_id']),
                                    parse_mode='Markdown'
                                )
                                add_pending_moderation('user_registration', data['telegram_id'])
                            except Exception as e:
                                print(f"Ошибка при отправке сообщения администратору {admin['telegram_id']}: {e}")
                    else:
                        bot.send_message(chat_id, '❌ Ошибка при сохранении данных.')
                        return
                else:
                    # Админ создает нового перевозчика
                    data['role'] = 'executor'

                    success = db.execute_query(
                        """INSERT INTO users 
                        (telegram_id, company_id, first_name, last_name, patronymic, role, phone, email, 
                        birth_date, passport_series, passport_number, passport_issue_date, 
                        registration_address, ati_code, status, created_by, approved_by) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'added', ?, ?)""",
                        (
                            data['telegram_id'], data['company'], data['first_name'], data['last_name'],
                            data.get('patronymic'), data['role'], data['phone'], data['email'],
                            data.get('birth_date'), data.get('passport_series'), data.get('passport_number'),
                            data.get('passport_issue_date'), data.get('registration_address'),
                            data.get('ati_code'), admin_id, admin_id
                        )
                    )

                    if success:
                        # Инициализируем рейтинг только для новых пользователей
                        init_user_rating(db, data['telegram_id'], data['role'])

                        bot.send_message(
                            chat_id,
                            f"✅ Перевозчик {data['first_name']} {data['last_name']} успешно добавлен!",
                            reply_markup=get_executor_management_keyboard()
                        )

                        # Отправляем приветственное сообщение новому пользователю
                        try:
                            from handlers.main_handlers.common import handle_start
                            # Имитируем команду /start для нового пользователя
                            class MockMessage:
                                def __init__(self, user_id, first_name):
                                    self.from_user = type('User', (), {'id': user_id, 'first_name': first_name})()
                                    self.chat = type('Chat', (), {'id': user_id})()
                                    self.text = '/start'

                            mock_message = MockMessage(data['telegram_id'], data['first_name'])
                            handle_start(bot, mock_message, db)
                        except Exception as e:
                            print(f"Не удалось отправить приветственное сообщение: {e}")

                        if admin_id in admin_temp_data:
                            del admin_temp_data[admin_id]

                        set_user_state(admin_id, 'waiting_for_executor_management_action')
                    else:
                        bot.send_message(
                            chat_id,
                            "❌ Ошибка при добавлении перевозчика. Попробуйте позже.",
                            reply_markup=get_executor_management_keyboard()
                        )

        except Exception as e:
            print(f"Ошибка при создании/обновлении перевозчика: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(
                chat_id,
                "❌ Произошла ошибка при обработке данных перевозчика. Попробуйте позже.",
                reply_markup=get_executor_management_keyboard()
            )

    def show_executors_list(bot, db, admin_id, chat_id, role):
        """Показывает список всех перевозчиков"""

        company_result = db.get_company_id_by_user_id(admin_id)
        company_id = company_result['company_id'] if company_result and 'company_id' in company_result else None
        if role == "external_admin" or role == 'external_logist':
            executors = db.fetch_all(
                "select * from users where role='external_executor' and status = 'active' and company_id = ?",
                (company_id,))

            if not executors:
                bot.send_message(
                    chat_id,
                    "📭 Список перевозчиков пуст.",
                    reply_markup=get_executor_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_logist_management_action')
                return
            if admin_id not in admin_temp_data:
                admin_temp_data[admin_id] = {}
            admin_temp_data[admin_id]['executors_list'] = executors
            message_text = "📋 Список перевозчиков:\n\n"
            for i, executor in enumerate(executors, 1):
                message_text += f"{i}. {executor['first_name']} {executor.get('last_name', '')} - {role_names.get(executor['role'], 'Должность не указана')}\n"
                message_text += f"   📞 {executor.get('phone', 'Телефон не указан')}\n\n"

            message_text += "Выберите перевозчика для управления:"

            # Создаем клавиатуру с кнопками для каждого перевозчика (включая ID)
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            for executor in executors:
                button_text = f"👤 {executor['first_name']} {executor.get('last_name', '')} (ID: {executor['telegram_id']})"
                keyboard.add(KeyboardButton(button_text))

            keyboard.add(KeyboardButton("⬅️ Назад"))

            bot.send_message(chat_id, message_text, reply_markup=keyboard)
            set_user_state(admin_id, 'waiting_for_executor_selection')
        elif role == 'logist':
            executors = db.fetch_all(
                "select * from users where role='executor' and status = 'active' and company_id = ?",
                (company_id,))
            if not executors:
                bot.send_message(
                    chat_id,
                    "📭 Список перевозчиков пуст.",
                    reply_markup=get_executor_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_logist_management_action')
            if admin_id not in admin_temp_data:
                admin_temp_data[admin_id] = {}
            admin_temp_data[admin_id]['executors_list'] = executors
            message_text = "📋 Список перевозчиков:\n\n"
            for i, executor in enumerate(executors, 1):
                message_text += f"{i}. {executor['first_name']} {executor.get('last_name', '')} - {role_names.get(executor['role'], 'Должность не указана')}\n"
                message_text += f"   📞 {executor.get('phone', 'Телефон не указан')}\n\n"

            message_text += "Выберите перевозчика для управления:"

            # Создаем клавиатуру с кнопками для каждого перевозчика (включая ID)
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            for executor in executors:
                button_text = f"👤 {executor['first_name']} {executor.get('last_name', '')} (ID: {executor['telegram_id']})"
                keyboard.add(KeyboardButton(button_text))

            keyboard.add(KeyboardButton("⬅️ Назад"))

            bot.send_message(chat_id, message_text, reply_markup=keyboard)
            set_user_state(admin_id, 'waiting_for_executor_selection')
        else:
            executors = db.fetch_all(
                "SELECT * FROM users WHERE role = 'executor' AND status = 'active' ORDER BY first_name, last_name"
            )

            if not executors:
                bot.send_message(
                    chat_id,
                    "📭 Список перевозчиков пуст.",
                    reply_markup=get_executor_management_keyboard()
                )
                return

            # Сохраняем список перевозчиков для последующего выбора
            if admin_id not in admin_temp_data:
                admin_temp_data[admin_id] = {}
            admin_temp_data[admin_id]['executors_list'] = executors

            # Формируем сообщение со списком
            message_text = "📋 Список перевозчиков:\n\n"
            for i, executor in enumerate(executors, 1):
                message_text += f"{i}. {executor['first_name']} {executor.get('last_name', '')} - {role_names.get(executor['role'], 'Должность не указана')}\n"
                message_text += f"   📞 {executor.get('phone', 'Телефон не указан')}\n\n"

            message_text += "Выберите перевозчика для управления:"

            # Создаем клавиатуру с кнопками для каждого перевозчика (включая ID)
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            for executor in executors:
                button_text = f"👤 {executor['first_name']} {executor.get('last_name', '')} (ID: {executor['telegram_id']})"
                keyboard.add(KeyboardButton(button_text))

            keyboard.add(KeyboardButton("⬅️ Назад"))

            bot.send_message(chat_id, message_text, reply_markup=keyboard)
            set_user_state(admin_id, 'waiting_for_executor_selection')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_executor_selection')
    def handle_executor_selection(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                "🚛 Управление перевозчиками\n\n"
                "Выберите действие:",
                reply_markup=get_executor_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_management_action')
            return

        # Ищем выбранного перевозчика по ID (как в test1)
        try:
            # Извлекаем ID перевозчика из текста кнопки
            executor_id = int(message.text.split('ID: ')[1].split(')')[0])
        except (IndexError, ValueError):
            bot.send_message(chat_id, "❌ Неверный формат выбора. Попробуйте еще раз.")
            return

        # Находим перевозчика
        selected_executor = None
        for executor in admin_temp_data[admin_id]['executors_list']:
            if executor['telegram_id'] == executor_id:  # или executor['telegram_id'] в зависимости от того, что вы используете
                selected_executor = executor
                break

        if not selected_executor:
            bot.send_message(chat_id, "❌ Перевозчик не найден. Попробуйте еще раз.")
            return

        # Сохраняем выбранного перевозчика для редактирования
        admin_temp_data[admin_id]['editing_executor'] = selected_executor

        # Показываем меню управления выбранным перевозчиком
        show_executor_management_menu(bot, admin_id, chat_id, selected_executor)

    def show_executor_management_menu(bot, admin_id, chat_id, executor):
        """Показывает меню управления конкретным перевозчиком"""

        company = db.get_company_by_id(executor.get('company_id'))

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
        👤 **Управление перевозчиком:**
        
        **Имя:** {executor['first_name']}
        **Фамилия:** {executor.get('last_name', 'Не указана')}
        **Отчество:** {executor.get('patronymic', 'Не указано')}
        **Компания:** {company.get('name', 'Не указана')}
        **Должность:** {role_names.get(executor['role'], 'Не указана')}
        **Телефон:** {executor.get('phone', 'Не указан')}
        **Email:** {executor.get('email', 'Не указан')}
        **Дата рождения:** {executor.get('birth_date', 'Не указана')}
        **Паспорт:** {executor.get('passport_series', '')} {executor.get('passport_number', '')}
        **Дата выдачи паспорта:** {executor.get('passport_issue_date', 'Не указана')}
        **Адрес регистрации:** {executor.get('registration_address', 'Не указан')}
        **Код АТИ:** {executor.get('ati_code', 'Не указан')}
        **Статус:** {status_names.get(executor['status'], 'Не указан')}
        
        Выберите действие:
                """

        bot.send_message(
            chat_id,
            message_text,
            reply_markup=get_specific_executor_management_keyboard(),
            parse_mode='Markdown'
        )
        set_user_state(admin_id, 'waiting_for_specific_executor_action')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_specific_executor_action')
    def handle_specific_executor_action(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(admin_id)
        role = user_info['role'] if user_info else None

        if message.text == "✏️ Редактировать данные":
            start_executor_editing(bot, admin_id)
        elif message.text == "🗑️ Удалить перевозчика":
            bot.send_message(
                chat_id,
                "❌ Вы уверены, что хотите удалить этого перевозчика?\n\n"
                "Это действие нельзя отменить.",
                reply_markup=get_confirmation_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_delete_executor_confirmation')
        elif message.text == "⬅️ Назад к списку":
            show_executors_list(bot, db, admin_id, chat_id, role)
            set_user_state(admin_id, 'waiting_for_executor_selection')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_delete_executor_confirmation')
    def handle_delete_confirmation(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(admin_id)
        role = user_role['role'] if user_role else None

        if message.text == "✅ Да, удалить":
            delete_executor(bot, db, admin_id, chat_id, role)
        elif message.text == "❌ Нет, отменить":
            if admin_id in admin_temp_data and 'editing_executor' in admin_temp_data[admin_id]:
                show_executor_management_menu(bot, admin_id, chat_id, admin_temp_data[admin_id]['editing_executor'])
            else:
                bot.send_message(
                    chat_id,
                    "🚛 Управление перевозчиками\n\n"
                    "Выберите действие:",
                    reply_markup=get_executor_management_keyboard()
                )
                set_user_state(admin_id, 'waiting_for_executor_management_action')

    def delete_executor(bot, db, admin_id, chat_id, user_role):
        try:
            admin_username = db.get_username(admin_id)
            username = admin_username['username'] if admin_username and "username" in admin_username else None
            if user_role == 'admin':
                if admin_id not in admin_temp_data or 'editing_executor' not in admin_temp_data[admin_id]:
                    bot.send_message(chat_id, "❌ Ошибка. Перевозчик не найден.")
                    return

                executor = admin_temp_data[admin_id]['editing_executor']

                success = db.execute_query(
                    "DELETE FROM users WHERE telegram_id = ?",
                    (executor['id'],)
                )
                if success:
                    bot.send_message(
                        chat_id,
                        f"✅ Перевозчик {executor['first_name']} {executor['last_name']} успешно удален.",
                        reply_markup=get_executor_management_keyboard()
                    )

                    if admin_id in admin_temp_data:
                        if 'editing_executor' in admin_temp_data[admin_id]:
                            del admin_temp_data[admin_id]['editing_executor']
                        if 'executors_list' in admin_temp_data[admin_id]:
                            del admin_temp_data[admin_id]['executors_list']
                    set_user_state(admin_id, 'waiting_for_executor_management_action')
                else:
                    bot.send_message(chat_id, "❌ Ошибка при удалении перевозчика.")

            else:
                if admin_id not in admin_temp_data or 'editing_executor' not in admin_temp_data[admin_id]:
                    bot.send_message(chat_id, "❌ Ошибка. Перевозчик не найден.")
                    return

                executor = admin_temp_data[admin_id]['editing_executor']
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
                set_user_state(admin_id, 'waiting_for_executor_management_action')
                for admin in admins:
                    bot.send_message(
                        admin['telegram_id'],
                        f"❗️ Запрос на удаление пользователя {executor['first_name']}, Telegram ID:{executor['telegram_id']}!!!\n"
                        f"Username: @{executor['username']}, 💼 Должность: {role_names.get(executor['role'])}\n\n"
                        f"Запросил @{username}",
                        reply_markup=get_approve_reject_delete_keyboard(executor['telegram_id'], admin_id),
                    )
                    add_pending_moderation('user_delete', executor['telegram_id'], admin_id)
        except Exception as e:
            print(f"Ошибка при удалении перевозчика: {e}")
            bot.send_message(chat_id, "❌ Произошла ошибка при удалении перевозчика.")


    def start_executor_editing(bot, admin_id):
        if admin_id not in admin_temp_data or 'editing_executor' not in admin_temp_data[admin_id]:
            bot.send_message(admin_id, "❌ Ошибка. Перевозчик не найден.")
            return
        bot.send_message(
            admin_id,
            "✏️ Редактирование данных перевозчика\n\n"
            "Выберите что хотите отредактировать:",
            reply_markup=get_extended_editing_keyboard()
        )
        set_user_state(admin_id, 'waiting_for_editing_executor_field_selection')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_editing_executor_field_selection')
    def handle_editing_executor_field_selection(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id

        companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )

        if message.text == "⬅️ Назад":
            if admin_id in admin_temp_data and 'editing_executor' in admin_temp_data[admin_id]:
                show_executor_management_menu(bot, admin_id, chat_id, admin_temp_data[admin_id]['editing_executor'])
                set_user_state(admin_id, 'waiting_for_executor_management_action')
            return

        executor = admin_temp_data[admin_id]['editing_executor']

        if message.text == "👤 Редактировать имя":
            bot.send_message(
                chat_id,
                f"Текущее имя: {executor['first_name']}\nВведите новое имя:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_name')

        elif message.text == "👤 Редактировать фамилию":
            bot.send_message(
                chat_id,
                f"Текущая фамилия: {executor.get('last_name', 'Не указана')}\nВведите новую фамилию:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_last_name')

        elif message.text == "👤 Редактировать отчество":
            bot.send_message(
                chat_id,
                f"Текущее отчество: {executor.get('patronymic', 'Не указано')}\nВведите новое отчество:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_patronymic')

        elif message.text == "🏢 Редактировать компанию":
            bot.send_message(
                chat_id,
                f"Текущая компания: {executor.get('company', 'Не указана')}\n Выберите новую компанию:",
                reply_markup = get_company_selection_keyboard(companies)
            )
            set_user_state(admin_id, 'waiting_for_existing_executor_company')

        elif message.text == "💼 Редактировать должность":
            bot.send_message(
                chat_id,
                f"Текущая должность: {role_names.get(executor.get('role', 'Не указана'))}\nВведите новую должность:",
                reply_markup=get_role_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_role')

        elif message.text == "📞 Редактировать телефон":
            bot.send_message(
                chat_id,
                f"Текущий телефон: {executor.get('phone', 'Не указан')}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_phone')

        elif message.text == "📧 Редактировать email":
            bot.send_message(
                chat_id,
                f"Текущий email: {executor.get('email', 'Не указан')}\nВведите новый email:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_email')

        elif message.text == "🎂 Редактировать дату рождения":
            bot.send_message(
                chat_id,
                f"Текущая дата рождения: {executor.get('birth_date', 'Не указана')}\nВведите новую дату рождения (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_birth_date')

        elif message.text == "📘 Редактировать серию паспорта":
            bot.send_message(
                chat_id,
                f"Текущая серия паспорта: {executor.get('passport_series', 'Не указана')}\nВведите новую серию паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_passport_series')

        elif message.text == "📘 Редактировать номер паспорта":
            bot.send_message(
                chat_id,
                f"Текущий номер паспорта: {executor.get('passport_number', 'Не указан')}\nВведите новый номер паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_passport_number')

        elif message.text == "📅 Редактировать дату выдачи паспорта":
            bot.send_message(
                chat_id,
                f"Текущая дата выдачи паспорта: {executor.get('passport_issue_date', 'Не указана')}\nВведите новую дату выдачи паспорта (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_passport_issue_date')

        elif message.text == "📍 Редактировать адрес регистрации":
            bot.send_message(
                chat_id,
                f"Текущий адрес регистрации: {executor.get('registration_address', 'Не указан')}\nВведите новый адрес регистрации:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_registration_address')

        elif message.text == "🔢 Редактировать код АТИ":
            bot.send_message(
                chat_id,
                f"Текущий код АТИ: {executor.get('ati_code', 'Не указан')}\nВведите новый код АТИ:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(admin_id, 'editing_existing_executor_ati_code')

    def edit_user(admin_id, user_id, old_value, new_value, parameter, query):
        user_info = db.get_user_role(admin_id)
        role = user_info['role'] if user_info else None
        user = db.get_user_by_telegram_id(user_id)
        values = []
        values.append(new_value)
        values.append(user_id)
        if role == 'admin':
            success = db.execute_query(query, (new_value, user_id))

            if success:
                admin_temp_data[admin_id]['editing_executor'][parameter] = new_value
                bot.send_message(admin_id, "✅ Данные успешно обновлены!")
                if parameter == 'role':
                    bot.send_message(
                        admin_id,
                        "🚛 Управление перевозчиками\n\n"
                        "Выберите действие:",
                        reply_markup=get_executor_management_keyboard()
                    )
                    set_user_state(admin_id, 'waiting_for_executor_management_action')
                else:
                    start_executor_editing(bot, admin_id)
            else:
                bot.send_message(admin_id, "❌ Ошибка при обновлении имени.")
        else:
            email_subject = f'📝 Заявка на изменение данных'
            email_message = f"""
                **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
                **Telegram ID:** {user_id}
                **Роль:** {role_names.get(user['role'])}

                **Изменяемое поле:** {user_fields_display.get(parameter, parameter)}
                **Старое значение:** {role_names.get(old_value, old_value)}
                **Новое значение:** {role_names.get(new_value, new_value)}

                **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

                Откройте чат с Телеграм-ботом, чтобы принять или отклонить регистрацию
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
            add_pending_moderation('edit_user', user_id)
            bot.send_message(
                admin_id,
                '🕐**Данные отправлены главному администратору на проверку**\n'
                '  **Вам придет уведомление о результате проверки**',
                reply_markup = get_main_menu(role)
            )
            set_user_state(admin_id, '')

    # Обработчики редактирования существующих перевозчиков
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_name')
    def handle_editing_existing_executor_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'first_name'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Имя должно содержать минимум 2 символа. Введите имя:")
            return

        query = 'UPDATE users SET first_name = ? WHERE telegram_id = ?'

        new_first_name = message.text.strip()
        old_first_name = user['first_name']


        edit_user(admin_id, executor_id, old_first_name, new_first_name, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_last_name')
    def handle_editing_existing_executor_last_name(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'last_name'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Фамилия не может быть пустой. Введите фамилию:")
            return

        query = 'UPDATE users SET last_name = ? WHERE telegram_id = ?'

        new_last_name = message.text.strip()
        old_last_name = user['last_name']

        edit_user(admin_id, executor_id, old_last_name, new_last_name, parameter, query)


    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_patronymic')
    def handle_editing_existing_executor_patronymic(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'patronymic'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        patronymic = message.text.strip()
        if not patronymic:
            bot.send_message(chat_id, "❌ Отчество не может быть пустым. Введите отчество или пропустите:")
            return

        query = 'UPDATE users SET patronymic = ? WHERE telegram_id = ?'

        new_patronymic = message.text.strip()
        old_patronymic = user['patronymic']

        edit_user(admin_id, executor_id, old_patronymic, new_patronymic, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_existing_executor_company')
    def handle_editing_existing_executor_company(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'company'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
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

            edit_user(admin_id, executor_id, old_company, new_company, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_birth_date')
    def handle_editing_existing_executor_birth_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'birth_date'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

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

        edit_user(admin_id, executor_id, old_birth_date, new_birth_date, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_passport_series')
    def handle_editing_existing_executor_passport_series(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'passport_series'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 4:
            bot.send_message(chat_id, "❌ Серия паспорта должна состоять из 4 цифр. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET passport_series = ? WHERE telegram_id = ?'

        new_passport_series = message.text.strip()
        old_passport_series = user['passport_series']

        edit_user(admin_id, executor_id, old_passport_series, new_passport_series, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_passport_number')
    def handle_editing_existing_executor_passport_number(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'passport_number'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 6:
            bot.send_message(chat_id, "❌ Номер паспорта должен состоять из 6 цифр. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET passport_number = ? WHERE telegram_id = ?'

        new_passport_number = message.text.strip()
        old_passport_number = user['passport_number']

        edit_user(admin_id, executor_id, old_passport_number, new_passport_number, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_passport_issue_date')
    def handle_editing_existing_executor_passport_issue_date(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'passport_issue_date'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        try:
            issue_date = datetime.strptime(message.text, '%d.%m.%Y')
            if issue_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET passport_issue_date = ? WHERE telegram_id = ?'

        new_passport_issue_date = message.text.strip()
        old_passport_issue_date = user['passport_issue_date']

        edit_user(admin_id, executor_id, old_passport_issue_date, new_passport_issue_date, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_registration_address')
    def handle_editing_existing_executor_registration_address(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'registration_address'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Адрес регистрации не может быть пустым. Введите адрес:")
            return

        query = 'UPDATE users SET registration_address = ? WHERE telegram_id = ?'

        new_registration_address = message.text.strip()
        old_registration_address = user['registration_address']

        edit_user(admin_id, executor_id, old_registration_address, new_registration_address, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_ati_code')
    def handle_editing_existing_executor_ati_code(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'ati_code'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        if message.text == "⏭️ Пропустить":
            ati_code = None
        else:
            ati_code = message.text.strip()
            if not ati_code.isdigit():
                bot.send_message(chat_id, "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз:")
                return

        query = 'UPDATE users SET ati_code = ? WHERE telegram_id = ?'

        new_ati_code = ati_code
        old_ati_code = user['ati_code']

        edit_user(admin_id, executor_id, old_ati_code, new_ati_code, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_role')
    def handle_editing_existing_executor_role(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        admin = db.get_user_by_telegram_id(admin_id)
        admin_role = admin['role']
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'role'
        user = db.get_user_by_telegram_id(executor_id)
        user_role = db.get_user_role(user["role"])
        role = user_role['role'] if user_role else None
        role = ''

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
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
        admin_temp_data[admin_id]['editing_executor']['role'] = role
        query = 'UPDATE users SET role = ? WHERE telegram_id = ?'

        new_role = role
        old_role = user['role']

        edit_user(admin_id, executor_id, old_role, new_role, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_phone')
    def handle_editing_existing_executor_phone(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'phone'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
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

        edit_user(admin_id, executor_id, old_phone, new_phone, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_existing_executor_email')
    def handle_editing_existing_executor_email(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        executor_id = admin_temp_data[admin_id]['editing_executor']['telegram_id']
        parameter = 'email'
        user = db.get_user_by_telegram_id(executor_id)

        if message.text == "⬅️ Назад":
            start_executor_editing(bot, admin_id)
            return

        email = message.text.strip()

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
            return

        query = 'UPDATE users SET email = ? WHERE telegram_id = ?'

        new_email = email
        old_email = user['email']

        edit_user(admin_id, executor_id, old_email, new_email, parameter, query)