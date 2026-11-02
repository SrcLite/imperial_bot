from handlers.admin_handlers.admin_rates_handlers import get_current_rates, format_user_rates_message
from utils.dicts import role_names
from utils.subscription_manager import SubscriptionManager
from telebot.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from keyboards.main_menus import get_main_menu, get_start_menu, get_subscription_keyboard
from keyboards.registration_user_keyboards import get_terms_keyboard, get_registration_agreement_keyboard, \
    get_company_selection_keyboard, get_reg_company_keyboard
from handlers.registration_handlers.registration_user_handlers import set_user_state


def handle_start(bot, message, db):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    first_name = message.from_user.first_name

    # Проверяем, зарегистрирован ли пользователь
    user = db.get_user_by_telegram_id(user_id)

    # Создаем менеджер подписок
    subscription_manager = SubscriptionManager(db)

    if user and user.get('status') == 'active' and user.get('accepted_terms') == 'true':
        # ПРОВЕРКА ПОДПИСКИ ДЛЯ ВНЕШНИХ ПОЛЬЗОВАТЕЛЕЙ
        if user['role'] in ['any']:
            subscription_status = subscription_manager.check_subscription_status(user_id)

            if not subscription_status['has_active_subscription']:
                # У пользователя нет активной подписки
                subscription_info = subscription_manager.get_subscription_info(user_id)

                if subscription_info and subscription_info['subscription_type'] == 'trial':
                    # Пробный период закончился
                    welcome_text = f"""
                    ⏰ Ваш пробный период закончился!

                    Для продолжения использования бота необходимо оплатить подписку:
                    • Стоимость: {subscription_status.get('price', 0)} ₽/месяц
                    • Пробный период: 3 месяца бесплатно

                    Выберите действие:
                    """

                    keyboard = get_subscription_keyboard()
                    bot.send_message(
                        message.chat.id,
                        welcome_text,
                        reply_markup=keyboard
                    )
                    return
                else:
                    # Нет подписки вообще
                    welcome_text = f"""
                        🔒 Требуется подписка!

                        Для использования бота необходимо активировать подписку.
                        Пробный период: 3 месяца бесплатно.

                        Выберите действие:
                    """

                    keyboard = get_subscription_keyboard()
                    bot.send_message(
                        message.chat.id,
                        welcome_text,
                        reply_markup=keyboard
                    )
                    return

        role = user['role']
        welcome_text = f"""
            Добро пожаловать назад, {first_name}! 🎉

            Ваша роль: {role_names.get(role)}
            Используйте меню ниже для работы с системой.
                    """

        # Показываем информацию о подписке, если она есть
        if user['role'] in ['external_admin', 'external_logist', 'external_executor']:
            subscription_info = subscription_manager.get_subscription_info(user_id)
            if subscription_info:
                subscription_text = f"""
                📅 Подписка активна до: {subscription_info['end_date']}
                ⏱️ Осталось дней: {subscription_info['days_left']}
                💳 Стоимость: {subscription_info['price']} ₽/месяц
                """
                welcome_text += subscription_text

        bot.send_message(user_id,
                         welcome_text,
                         reply_markup=get_main_menu(role))
    elif user and user.get('status') == 'added_pending':
        bot.send_message(
            user_id,
            "⏳ Вас уже частично зарегистрировали, ваши данные находятся на проверке у главного администратора.\n Попробуйте зарегистрироваться позже...",
            reply_markup = ReplyKeyboardRemove()
        )
    elif user and user.get('status') == 'pending':
        # Пользователь есть, но не подтвержден
        bot.send_message(
            message.chat.id,
            "⏳ Ваша регистрация находится на рассмотрении администратора.\nОжидайте подтверждения.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    elif user and user.get('status') is None and user.get('accepted_terms') == 'true' and user.get('role') is not None and user.get('company_id') is None:
        bot.send_message(user_id, "✅ Вы уже частично зарегистрированы, продолжим регистрацию")
        approved_companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )
        set_user_state(user_id, 'waiting_for_company_selection')
        if approved_companies:
            companies_text = "🏢 **Выберите вашу компанию из списка:**\n\n"
            for company in approved_companies:
                companies_text += f"• {company['name']}\n"

            companies_text += "\nИли зарегистрируйте новую компанию:"

            bot.send_message(
                user_id,
                companies_text,
                reply_markup=get_company_selection_keyboard(approved_companies),
                parse_mode="Markdown"
            )
        else:
            bot.send_message(
                user_id,
                "📋 **Регистрация компании**\n\n"
                "В системе пока нет зарегистрированных компаний. "
                "Необходимо зарегистрировать компанию для продолжения.",
                reply_markup=get_reg_company_keyboard(),
                parse_mode="Markdown"
            )
            set_user_state(user_id, 'waiting_for_company_reg')
    elif user and user.get('status') is None and user.get('accepted_terms') == 'true' and user.get('role') is not None and user.get('company_id') is not None:
        bot.send_message(user_id, "✅ Вы уже частично зарегистрированы, продолжим регистрацию")
        bot.send_message(user_id, "Введите ваше имя:", reply_markup=ReplyKeyboardRemove())
        set_user_state(user_id, 'waiting_for_first_name')

    elif user and user.get('status') == 'added' and user.get('accepted_terms') != 'true':
        welcome_text = f"""
        Приветствуем, {first_name}! 👋

        Добро пожаловать в бот ООО «ИМПЕРИАЛ» для автоматизации грузоперевозок.

        ОГРН 1251600018119

        Перед началом работы необходимо ознакомиться с условиями платформы.
                """
        # Удаляем reply-клавиатуру перед отправкой inline-кнопок
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=ReplyKeyboardRemove()  # Убираем reply-клавиатуру
        )

        # Отправляем условия с inline-кнопками
        bot.send_message(
            message.chat.id,
            "Пожалуйста, ознакомьтесь с условиями:",
            reply_markup=get_terms_keyboard()
        )
        return
    elif user and user.get('status') == 'added' and user.get('accepted_terms') == 'true' and user.get('role') in [
        'executor', 'external_executor']:
        set_user_state(user_id, 'waiting_for_end_passport_main_photo')
        bot.send_message(
            message.chat.id,
            f"Вас уже зарегистрировали, для работы в системе вам необходимо добавить фото паспорта\n"
            "Сначала отправьте фото 1 страницы паспорта (с фото и данными):",
            reply_markup=ReplyKeyboardRemove()
        )
    elif user and user.get('status') == 'added' and user.get('accepted_terms') == 'true' and user.get('role') in [
        'logist', 'external_logist']:
        set_user_state(user_id, 'waiting_for_log_last_name')
        bot.send_message(
            user_id,
            f"{user.get('first_name')}, вас уже частично зарегистрировали, продолжите регистрацию для начла работы в системе.\n"
            "📝 Введите вашу фамилию:",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        # Новый пользователь - показываем стартовое меню
        rate = get_current_rates(db)
        rate_text = format_user_rates_message(rate)
        welcome_text = f"""
    Приветствуем, {first_name}! 👋

    Добро пожаловать в логистическую платформу!

    ОГРН 1251600018119

    {rate_text}

    Возможна индивидуальная настройка тарифов для корпоративных клиентов.

    • Нажмите «🤖 Посмотреть, как работает бот» — увидите реальные заявки
    • Нажмите «🖊 Начать регистрацию» — получите полный доступ к системе
        """

        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=get_start_menu(),
            parse_mode='Markdown'
        )


# Обработчик для кнопки "Начать регистрацию"
def handle_start_registration(bot, message, db):
    """Обработчик кнопки начала регистрации"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Проверяем, не зарегистрирован ли уже пользователь
    user = db.get_user_by_telegram_id(user_id)

    if user and user.get('status') == 'active':
        # Проверяем подписку для внешних пользователей
        subscription_manager = SubscriptionManager(db)

        if user['role'] in ['external_admin', 'external_logist', 'external_executor']:
            subscription_status = subscription_manager.check_subscription_status(user_id)

            if not subscription_status['has_active_subscription']:
                # У пользователя нет активной подписки
                welcome_text = f"""
🔒 Требуется подписка!

Для продолжения работы с ботом необходимо оплатить подписку.

Выберите действие:
                """

                keyboard = get_subscription_keyboard()
                bot.send_message(
                    chat_id,
                    welcome_text,
                    reply_markup=keyboard
                )
                return

        # Пользователь уже зарегистрирован и имеет активную подписку
        bot.send_message(
            chat_id,
            "✅ Вы уже зарегистрированы в системе!",
            reply_markup=get_main_menu(user['role'])
        )
        return

    if user and user.get('status') == 'pending':
        # Регистрация на рассмотрении
        bot.send_message(
            chat_id,
            "⏳ Ваша заявка на регистрацию уже находится на рассмотрении.\nОжидайте подтверждения администратора.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Начинаем процесс регистрации
    welcome_text = f"""
Приветствуем, {message.from_user.first_name}! 👋

Добро пожаловать в бот ООО «ИМПЕРИАЛ» для автоматизации грузоперевозок.

📝 **Регистрация состоит из 3 этапов:**

1. **Личные данные** - ФИО, телефон, email
2. **Данные компании** - название, ИНН, форма налогообложения
3. **Согласие с условиями** - ознакомление с правилами платформы

⚠️ **Важно:** Все данные должны быть заполнены корректно и соответствовать действительности.

Начнем регистрацию?
    """

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("✅ Да, начать регистрацию"))
    keyboard.add(KeyboardButton("❌ Отмена"))

    bot.send_message(
        chat_id,
        welcome_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    # Устанавливаем состояние для ожидания подтверждения начала регистрации
    set_user_state(user_id, 'waiting_for_registration_confirmation')


# Обработчик подтверждения начала регистрации
def handle_registration_confirmation(bot, message, db):
    """Обработчик подтверждения начала регистрации"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    first_name = message.from_user.first_name
    user = db.get_user_by_telegram_id(user_id)

    if message.text == "✅ Да, начать регистрацию":
        welcome_text = f"""
Приветствуем, {first_name}! 👋

Добро пожаловать в бот ООО «ИМПЕРИАЛ» для автоматизации грузоперевозок.

Перед началом работы необходимо ознакомиться с условиями платформы.
        """

        # Удаляем reply-клавиатуру перед отправкой inline-кнопок
        bot.send_message(
            chat_id,
            welcome_text,
            reply_markup=ReplyKeyboardRemove()  # Убираем reply-клавиатуру
        )

        # Отправляем условия с inline-кнопками
        bot.send_message(
            chat_id,
            "Пожалуйста, ознакомьтесь с условиями:",
            reply_markup=get_terms_keyboard()
        )


# Обработчик для кнопки "Моя подписка" в главном меню
def handle_my_subscription(bot, message, db):
    """Обработчик кнопки 'Моя подписка'"""
    user_id = message.from_user.id
    user = db.get_user_by_telegram_id(user_id)

    if not user:
        bot.send_message(user_id, "❌ Пользователь не найден.")
        return

    subscription_manager = SubscriptionManager(db)

    # Проверяем, требуется ли подписка для этой роли
    if user['role'] not in ['external_admin', 'external_logist', 'external_executor']:
        bot.send_message(
            user_id,
            f"✅ Для вашей роли ({role_names.get(user['role'])}) подписка не требуется."
        )
        return

    subscription_status = subscription_manager.check_subscription_status(user_id)
    subscription_info = subscription_manager.get_subscription_info(user_id)

    if subscription_info:
        # Есть информация о подписке
        if subscription_status['has_active_subscription']:
            message_text = f"""
📋 **Информация о вашей подписке:**

✅ **Статус:** Активна
📅 **Действует до:** {subscription_info['end_date']}
⏱️ **Осталось дней:** {subscription_info['days_left']}
💳 **Стоимость:** {subscription_info['price']} ₽/месяц
🎁 **Тип:** {subscription_info['subscription_type']}
            """

            if subscription_info['days_left'] <= 7:
                message_text += f"\n⚠️ **Внимание!** Подписка истекает через {subscription_info['days_left']} дней."

        else:
            message_text = f"""
❌ **Подписка истекла!**

Для продолжения работы необходимо оплатить подписку:
• Стоимость: {subscription_info['price']} ₽/месяц
• Пробный период: 3 месяца бесплатно
            """
    else:
        # Нет информации о подписке
        price = subscription_manager.calculate_subscription_price(user['id'], user['role'])
        message_text = f"""
🔒 **Подписка не активирована**

Для использования бота необходимо активировать подписку:
• Стоимость: {price} ₽/месяц
• Пробный период: 3 месяца бесплатно
        """

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    if subscription_status['has_active_subscription']:
        if subscription_info['days_left'] <= 30:
            keyboard.add(KeyboardButton("💳 Продлить подписку"))
    else:
        keyboard.add(KeyboardButton("💳 Оплатить подписку"))

    keyboard.add(KeyboardButton("📞 Связаться с поддержкой"))
    keyboard.add(KeyboardButton("⬅️ На главную"))

    bot.send_message(
        user_id,
        message_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


# Обработчик для кнопки "Оплатить подписку"
def handle_pay_subscription(bot, message, db):
    """Обработчик кнопки оплаты подписки"""
    user_id = message.from_user.id
    user = db.get_user_by_telegram_id(user_id)

    if not user:
        bot.send_message(user_id, "❌ Пользователь не найден.")
        return

    if user['role'] not in ['external_admin', 'external_logist', 'external_executor']:
        bot.send_message(
            user_id,
            f"❌ Оплата подписки доступна только внешним пользователям.\nВаша роль: {role_names.get(user['role'])}"
        )
        return

    subscription_manager = SubscriptionManager(db)
    price = subscription_manager.calculate_subscription_price(user['id'], user['role'])

    # Формируем текст с деталями оплаты
    payment_text = f"""
💳 **Оплата подписки**

📊 **Детали подписки:**
• Роль: {role_names.get(user['role'])}
• Стоимость: {price} ₽/месяц
"""

    # Если это external_admin, показываем дополнительную информацию
    if user['role'] == 'external_admin':
        # Получаем количество внешних логистов в компании
        external_users = db.fetch_one(
            """
            SELECT COUNT(*) as count FROM users 
            WHERE company_id = ? AND role IN ('external_logist', 'external_admin')
            """,
            (user['company_id'],)
        )

        if external_users['count'] > 1:
            additional_price = (external_users['count'] - 1) * 100
            payment_text += f"""
• Количество пользователей: {external_users['count']} чел.
• Доплата за пользователей: +{additional_price} ₽/месяц
"""

    payment_text += f"""

📋 **Инструкция по оплате:**

1. **Переведите {price} ₽ на карту:**
   💳 `2202 2001 2345 6789` (Сбербанк)

2. **В назначении платежа укажите:**
   `Подписка бот {user_id}`

3. **После оплаты:**
   • Отправьте скриншот чека
   • Или нажмите "📋 Проверить оплату"

⏱️ **После проверки оплаты** подписка будет активирована в течение 24 часов.

📞 **Для получения счета или помощи:**
• Напишите администратору @admin_username
• Или нажмите "📞 Связаться с администратором"
"""

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📋 Проверить оплату"))
    keyboard.add(KeyboardButton("📞 Связаться с администратором"))
    keyboard.add(KeyboardButton("⬅️ Назад"))

    bot.send_message(
        user_id,
        payment_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )