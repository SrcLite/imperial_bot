from telebot.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

from keyboards.admin_rate_keyboard import get_admin_rate_keyboard, get_edit_rate_keyboard


def register_admin_rates_handlers(bot, db):
    # Хранение временных данных для пользователей
    user_temp_data = {}

    @bot.message_handler(func=lambda message: message.text == '💵 Управление подпиской')
    def admin_rates_handler(message):
        user_id = message.from_user.id
        user = db.get_user_by_telegram_id(user_id)

        # Проверка прав администратора
        if user['role'] not in ['admin', 'external_admin']:
            bot.send_message(
                user_id,
                '❌ Эта функция доступна только администраторам.',
                reply_markup=ReplyKeyboardRemove()
            )
            return

        if user['status'] != 'active':
            bot.send_message(
                user_id,
                '❌ Администратор не подтвердил вашу учетную запись.',
                reply_markup=ReplyKeyboardRemove()
            )
            return

        # Получаем текущие тарифы
        rates = get_current_rates(db)

        # Формируем сообщение с текущими тарифами
        rates_text = format_rates_message(rates)

        bot.send_message(
            user_id,
            f"⚙️ **Управление тарифами**\n\n{rates_text}\n\nВыберите действие:",
            reply_markup=get_admin_rate_keyboard(),
            parse_mode='Markdown'
        )

    @bot.message_handler(func=lambda message: message.text == '✏️ Изменить тарифы')
    def edit_rates_handler(message):
        user_id = message.from_user.id

        # Получаем текущие тарифы
        rates = get_current_rates(db)
        rates_text = format_rates_message(rates)

        bot.send_message(
            user_id,
            f'✏️ **Изменение тарифов**\n\n{rates_text}\n\nВыберите тариф, который хотите изменить:',
            reply_markup=get_edit_rate_keyboard(),
            parse_mode='Markdown'
        )

    @bot.message_handler(func=lambda message: message.text == '📋 Просмотреть тарифы')
    def view_rates_handler(message):
        user_id = message.from_user.id
        rates = get_current_rates(db)
        rates_text = format_rates_message(rates)

        # Формируем полный текст для пользователей
        user_rates_text = format_user_rates_message(rates)

        bot.send_message(
            user_id,
            f"📋 **Текущие тарифы**\n\n{rates_text}\n\n"
            f"**Текст для пользователей:**\n\n{user_rates_text}",
            parse_mode='Markdown'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_rate_'))
    def handle_edit_rate_callback(call):
        user_id = call.from_user.id
        rate_type = call.data.split('_')[2]  # vat, no_vat, card, trial

        # Сохраняем выбранный тип тарифа
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['editing_rate_type'] = rate_type

        # Определяем название тарифа для отображения
        rate_names = {
            'vat': '💰 С НДС 22%',
            'no_vat': '💰 Без НДС',
            'card': '💰 Оплата на карту',
            'trial': '🌟 Льготный период'
        }

        # Получаем текущее значение
        rates = get_current_rates(db)
        current_value = rates.get(rate_type, 0)

        # Формируем вопрос в зависимости от типа тарифа
        if rate_type == 'trial':
            question = f"Введите количество месяцев льготного периода (текущее значение: {current_value} мес.):"
        else:
            question = f"Введите новую стоимость для тарифа '{rate_names[rate_type]}' в рублях (текущее значение: {current_value} руб.):"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=question,
            reply_markup=get_cancel_keyboard()
        )

        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message:
    message.from_user.id in user_temp_data and
    user_temp_data[message.from_user.id].get('editing_rate_type'))
    def handle_rate_input(message):
        user_id = message.from_user.id
        rate_type = user_temp_data[user_id]['editing_rate_type']
        input_text = message.text.strip()

        try:
            # Проверяем ввод в зависимости от типа тарифа
            if rate_type == 'trial':
                # Для льготного периода проверяем, что это целое число
                new_value = int(input_text)
                if new_value < 0 or new_value > 12:
                    raise ValueError("Льготный период должен быть от 0 до 12 месяцев")
                rate_name = "льготный период"
                unit = "мес."
            else:
                # Для стоимостей проверяем, что это число
                new_value = float(input_text)
                if new_value <= 0:
                    raise ValueError("Стоимость должна быть положительным числом")
                rate_name = {
                    'vat': "С НДС 22%",
                    'no_vat': "Без НДС",
                    'card': "Оплата на карту"
                }[rate_type]
                unit = "руб."

            # Сохраняем в базу данных
            save_rate_to_db(db, rate_type, new_value)

            # Обновляем временные данные
            del user_temp_data[user_id]['editing_rate_type']

            # Получаем обновленные тарифы
            rates = get_current_rates(db)
            rates_text = format_rates_message(rates)

            bot.send_message(
                user_id,
                f"✅ Тариф '{rate_name}' успешно обновлен!\nНовое значение: **{new_value} {unit}**\n\n{rates_text}",
                reply_markup=get_admin_rate_keyboard(),
                parse_mode='Markdown'
            )

        except ValueError as e:
            error_msg = str(e)
            if "could not convert" in error_msg:
                error_msg = "Пожалуйста, введите корректное число"

            bot.send_message(
                user_id,
                f"❌ Ошибка: {error_msg}\n\nПопробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
        except Exception as e:
            print(f"❌ Ошибка при обновлении тарифа: {e}")
            bot.send_message(
                user_id,
                f"❌ Произошла ошибка при обновлении тарифа. Попробуйте еще раз.",
                reply_markup=get_admin_rate_keyboard()
            )

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel_edit_rate')
    def handle_cancel_edit(call):
        user_id = call.from_user.id

        # Очищаем временные данные
        if user_id in user_temp_data:
            if 'editing_rate_type' in user_temp_data[user_id]:
                del user_temp_data[user_id]['editing_rate_type']

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Изменение тарифа отменено.",
            reply_markup=None
        )

        bot.answer_callback_query(call.id, "Отменено")


def get_current_rates(db):
    """Получает текущие тарифы из базы данных"""
    # Инициализируем значения по умолчанию
    default_rates = {
        'vat': 1464.0,
        'no_vat': 1200.0,
        'card': 1200.0,
        'trial': 3
    }

    try:
        # Пытаемся получить тарифы из базы
        rates_data = db.fetch_all("SELECT * FROM rates")

        if rates_data:
            # Преобразуем в словарь
            rates = {}
            for rate in rates_data:
                rates[rate['rate_type']] = rate['value']

            # Проверяем наличие всех необходимых тарифов
            for rate_type, default_value in default_rates.items():
                if rate_type not in rates:
                    # Если тарифа нет в базе, создаем его с дефолтным значением
                    rates[rate_type] = default_value
                    save_rate_to_db(db, rate_type, default_value)

            return rates
        else:
            # Если таблица пуста, создаем дефолтные тарифы
            for rate_type, value in default_rates.items():
                save_rate_to_db(db, rate_type, value)
            return default_rates

    except Exception as e:
        print(f"❌ Ошибка при получении тарифов: {e}")
        # Возвращаем дефолтные значения в случае ошибки
        return default_rates


def save_rate_to_db(db, rate_type, value):
    """Сохраняет тариф в базу данных"""
    try:
        # Проверяем, существует ли уже запись
        existing_rate = db.fetch_one(
            "SELECT id FROM rates WHERE rate_type = ?",
            (rate_type,)
        )

        if existing_rate:
            # Обновляем существующий тариф
            db.execute_query(
                "UPDATE rates SET value = ? WHERE rate_type = ?",
                (value, rate_type)
            )
        else:
            # Создаем новый тариф
            db.execute_query(
                "INSERT INTO rates (rate_type, value) VALUES (?, ?)",
                (rate_type, value)
            )
    except Exception as e:
        print(f"❌ Ошибка при сохранении тарифа {rate_type}: {e}")
        raise e


def format_rates_message(rates):
    """Форматирует сообщение с тарифами"""
    return f"""🎯 **Текущие тарифы:**

💰 **С НДС 22%:** {rates['vat']:,.0f} рублей
💰 **Без НДС:** {rates['no_vat']:,.0f} рублей  
💰 **Оплата на карту:** {rates['card']:,.0f} рублей

🌟 **Льготный период:** {rates['trial']} месяца
"""


def format_user_rates_message(rates):
    """Форматирует полный текст для пользователей с текущими тарифами"""
    return f"""🎯 Прайс-лист для пользователей:

💰 С НДС 22%: {rates['vat']:,.0f} рублей
💰 Без НДС: {rates['no_vat']:,.0f} рублей
💰 Оплата на карту: {rates['card']:,.0f} рублей

🌟 Особые условия:
✨ Первые {rates['trial']} месяца — пробный период (бесплатно).
✨ С {rates['trial'] + 1}-го месяца услуги предоставляются по предоплате на основании выбранного тарифа.

📦 Что входит в стоимость:
✅ Неограниченное количество заявок и откликов
✅ Круглосуточная работа бота  
✅ Техническая поддержка и консультации
✅ Регулярные обновления функционала
✅ Доступ во всех популярных мессенджерах
✅ {rates['trial']} месяца бесплатного использования
✅ Выбор удобного тарифа с {rates['trial'] + 1}-го месяца
✅ Оплата по выбранному варианту (с НДС, без НДС или на карту)"""


def get_cancel_keyboard():
    """Клавиатура для отмены действия"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_edit_rate"))
    return keyboard


# Функция для создания таблицы rates в базе данных (вызовите один раз при инициализации)
def create_rates_table(db):
    """Создает таблицу для хранения тарифов"""
    db.execute_query("""
        CREATE TABLE IF NOT EXISTS rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rate_type TEXT UNIQUE NOT NULL,
            value DECIMAL(10, 2) NOT NULL,
           
        )
    """)