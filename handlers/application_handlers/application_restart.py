from datetime import datetime

import pytz
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.application_handlers.display_application_handlers import format_application_for_executor
from handlers.main_handlers.executor_filter_handlers import check_filters_for_application, \
    prepare_application_data_for_filter_check
from utils.email_sender import send_email_notification
from utils.dicts import CARGO_TYPE_REVERSE_MAPPING, CARGO_CATEGORY_REVERSE_MAPPING
from utils.filters import ExecutorFilters


def restart_expired_applications(bot, db):
    """
    Перезапускает заявки, которые долго не принимаются (более 2 часов)
    Обновляет updated_at и уведомляет всех перевозчиков
    """
    print("🔄 Проверка заявок для перезапуска...")

    # Находим заявки, которые активны более 2 часов и не имеют принятых откликов
    expired_applications = db.fetch_all("""
        SELECT a.*, 
       COUNT(CASE WHEN ar.status IN ('accepted', 'accepted_budget', 'counter_offer', 'assigned') THEN 1 END) as accepted_responses
        FROM applications a
        LEFT JOIN application_responses ar ON a.id = ar.application_id
        WHERE a.status IN ('active', 'urgent')
          AND datetime(a.created_at) <= datetime('now', '-2 hours', '+3 hours')
          AND (datetime(a.updated_at) <= datetime('now', '-2 hours', '+3 hours') 
               OR datetime(a.updated_at) IS NULL)
        GROUP BY a.id
        HAVING accepted_responses = 0
        ORDER BY a.created_at ASC
    """)

    if not expired_applications:
        print("✅ Нет заявок для перезапуска")
        return

    print(f"📋 Найдено заявок для перезапуска: {len(expired_applications)}")

    for app in expired_applications:
        try:
            # Перезапускаем заявку (обновляем updated_at)
            restart_application(bot, db, app)
        except Exception as e:
            print(f"❌ Ошибка при перезапуске заявки #{app['id']}: {e}")


def restart_application(bot, db, application):
    """
    Перезапускает одну заявку - обновляет updated_at и уведомляет всех перевозчиков
    """
    app_id = application['id']
    print(f"🔄 Перезапуск заявки #{app_id}...")

    moscow_tz = pytz.timezone('Europe/Moscow')
    current_time_moscow = datetime.now(moscow_tz)
    formatted_time = current_time_moscow.strftime('%Y-%m-%d %H:%M:%S')

    # 1. Обновляем поле updated_at заявки
    db.execute_query(
        "UPDATE applications SET updated_at = ? WHERE id = ?",
        (formatted_time, app_id)
    )

    # 4. Уведомляем перевозчиков о заявке
    notify_all_executors_about_application(bot, db, app_id)

    print(f"✅ Заявка #{app_id} перезапущена (обновлен updated_at)")


def notify_about_restart(bot, db, application):
    """
    Уведомляет администратора и логиста о перезапуске заявки
    """
    try:
        app_id = application['id']
        logist_id = application['created_by']

        # Получаем информацию о логисте
        logist_info = db.fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?",
            (logist_id,)
        )

        if not logist_info:
            print(f"❌ Логист {logist_id} не найден")
            return

        # Получаем всех администраторов
        admins = db.fetch_all(
            "SELECT * FROM users WHERE role IN ('admin', 'external_admin') AND status = 'active'"
        )

        # Формируем сообщение
        cargo_type_display = CARGO_TYPE_REVERSE_MAPPING.get(
            application.get('cargo_custom_type') or application.get('cargo_type', 'Не указан'),
            'Не указан'
        )

        # Получаем точки маршрута для информации
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (app_id,)
        )

        # Формируем информацию о точках
        points_info = ""
        if points:
            for point in points:
                city_str = f"{point['city']} - " if point.get('city') else ""
                points_info += f"• {point['point_type'].capitalize()}: {city_str}{point['address']}\n"

        # Получаем информацию о количестве откликов
        responses_info = db.fetch_one("""
            SELECT 
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_count,
                COUNT(CASE WHEN status = 'accepted' THEN 1 END) as accepted_count,
                COUNT(CASE WHEN status = 'counter_offer' THEN 1 END) as counter_offer_count
            FROM application_responses 
            WHERE application_id = ?
        """, (app_id,))

        message = f"""
⚠️ **ЗАЯВКА ПЕРЕЗАПУЩЕНА**

📦 **Заявка:** #{app_id}

📋 **Причина:** Заявка не была принята в течение 2 часов

💼 **Информация о заявке:**
• Тип: {'СТАНДАРТНАЯ' if application['application_type'] == 'fixed' else 'ЗАПРОС СТАВОК'}
• Груз: {cargo_type_display}
• Вес: {float(application.get('weight', 0)):.2f} т
• Объем: {float(application.get('volume', 0)):.2f} м³

🗺️ **Маршрут:**
{points_info}

📊 **Статистика откликов:**
• Отклонено: {responses_info.get('rejected_count', 0)}
• Принято: {responses_info.get('accepted_count', 0)}
• Встречных предложений: {responses_info.get('counter_offer_count', 0)}

💰 **Условия оплаты:**
"""

        # Добавляем информацию об оплате
        if application['application_type'] == 'fixed' and application.get('fixed_price'):
            message += f"• Фиксированная ставка: {float(application['fixed_price']):,.0f} руб."
        elif application['application_type'] == 'auction' and application.get('desired_budget'):
            message += f"• Желаемый бюджет: {float(application['desired_budget']):,.0f} руб."
        else:
            message += "• Не указаны"

        message += f"""

🕒 **Время создания:** {application.get('created_at', 'Не указано')}
🕒 **Время перезапуска:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

✅ **Заявка обновлена и уведомление отправлено ВСЕМ перевозчикам**
        """.strip()

        # Отправляем уведомление администраторам
        for admin in admins:
            try:
                bot.send_message(admin['telegram_id'], message, parse_mode='Markdown')

                # Отправляем email администратору
                if admin.get('email'):
                    send_email_notification(
                        f"Перезапуск заявки #{app_id}",
                        message,
                        admin['email']
                    )

            except Exception as e:
                print(f"❌ Не удалось уведомить администратора {admin['telegram_id']}: {e}")

        # Отправляем уведомление логисту
        try:
            bot.send_message(logist_id, message, parse_mode='Markdown')

            # Отправляем email логисту
            if logist_info.get('email'):
                send_email_notification(
                    f"Ваша заявка #{app_id} перезапущена",
                    message,
                    logist_info['email']
                )

        except Exception as e:
            print(f"❌ Не удалось уведомить логиста {logist_id}: {e}")

    except Exception as e:
        print(f"❌ Ошибка при уведомлении о перезапуске: {e}")


def notify_all_executors_about_application(bot, db, application_id):
    """
    Уведомляет ВСЕХ перевозчиков о заявке в соответствии с их фильтрами,
    исключая тех, кто уже отказался от этой заявки (статус 'rejected')
    """
    try:
        # Получаем информацию о заявке
        application = db.fetch_one(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application:
            print(f"❌ Заявка #{application_id} не найдена")
            return

        # Получаем точки маршрута
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (application_id,)
        )

        # Получаем информацию о создателе заявки
        creator_info = db.fetch_one(
            'SELECT * FROM users WHERE telegram_id = ?',
            (application['created_by'],)
        )

        # Получаем информацию о компании
        company_info = None
        if creator_info and creator_info.get('company_id'):
            company_info = db.fetch_one(
                'SELECT * FROM companies WHERE id = ?',
                (creator_info['company_id'],)
            )

        # Форматируем заявку
        application_text = format_application_for_executor(application, points, creator_info, company_info)

        # Подготавливаем данные заявки для проверки фильтров
        app_data_for_check = prepare_application_data_for_filter_check(application, points)

        # Получаем ВСЕХ активных перевозчиков, КРОМЕ тех, кто уже отказался от этой заявки
        executors = db.fetch_all("""
            SELECT u.telegram_id 
            FROM users u
            WHERE u.role IN ('executor', 'external_executor') 
              AND u.status = 'active'
              AND NOT EXISTS (
                SELECT 1 
                FROM application_responses ar 
                WHERE ar.application_id = ? 
                  AND ar.executor_id = u.telegram_id 
                  AND ar.status IN ('rejected', 'rejected_by_executor') 
              )
        """, (application_id,))

        if not executors:
            print(f"✅ Нет активных перевозчиков для уведомления по заявке #{application_id} (или все уже отказались)")
            return

        print(f"📢 Проверяем фильтры для {len(executors)} перевозчиков по заявке #{application_id}")

        # Отправляем уведомление только тем перевозчикам, чьи фильтры совпадают
        sent_count = 0
        filtered_count = 0
        failed_count = 0

        for executor in executors:
            executor_id = executor['telegram_id']

            try:
                # Загружаем фильтры перевозчика
                filters_obj = ExecutorFilters(db, executor_id)
                filters = filters_obj.filters

                # Проверяем фильтры
                passes_filter, reason = check_filters_for_application(filters, app_data_for_check)

                if not passes_filter:
                    print(f"  ⏭️ Пропуск {executor_id}: {reason}")
                    filtered_count += 1
                    continue

                # Создаем клавиатуру для быстрого перехода
                keyboard = InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    InlineKeyboardButton(
                        "🔔 Посмотреть заявку",
                        callback_data=f"executor_view_application_{application_id}"
                    )
                )

                bot.send_message(
                    executor_id,
                    application_text,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )

                sent_count += 1
                print(f"  ✅ Уведомлен {executor_id}")

            except Exception as e:
                # Если перевозчик заблокировал бота, пропускаем
                if "bot was blocked by the user" in str(e):
                    print(f"⚠️ Перевозчик {executor_id} заблокировал бота")
                else:
                    print(f"❌ Не удалось уведомить перевозчика {executor_id}: {e}")

                failed_count += 1

        print(f"📊 Итоги рассылки:")
        print(f"  • Отправлено: {sent_count}")
        print(f"  • Отфильтровано: {filtered_count}")
        print(f"  • Ошибок: {failed_count}")

    except Exception as e:
        print(f"❌ Ошибка при уведомлении перевозчиков: {e}")
        import traceback
        traceback.print_exc()



def register_restart_handlers(bot, db):
    """Регистрирует обработчики для перезапущенных заявок"""

    @bot.callback_query_handler(func=lambda call: call.data.startswith('view_restarted_application_'))
    def handle_view_restarted_application(call):
        """Обработка нажатия на кнопку просмотра перезапущенной заявки"""
        try:
            application_id = int(call.data.split('_')[3])

            # Получаем информацию о заявке
            application = db.fetch_one(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,)
            )

            if not application:
                bot.answer_callback_query(call.id, "❌ Заявка не найдена")
                return

            # Получаем точки маршрута
            points = db.fetch_all(
                "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
                (application_id,)
            )

            # Формируем сообщение с заявкой
            from handlers.application_handlers.display_application_handlers import format_application_for_executor

            creator_info = db.fetch_one(
                'SELECT * FROM users WHERE telegram_id = ?',
                (application['created_by'],)
            )

            company_info = None
            if creator_info and creator_info.get('company_id'):
                company_info = db.fetch_one(
                    'SELECT * FROM companies WHERE id = ?',
                    (creator_info['company_id'],)
                )

            application_text = format_application_for_executor(application, points, creator_info, company_info)

            # Добавляем пометку о перезапуске
            additional_info = """

🔄 **ЗАЯВКА ОБНОВЛЕНА (ПЕРЕЗАПУЩЕНА)**
⚠️ Данная заявка была автоматически перезапущена для повторного поиска перевозчика.
🕒 **Последнее обновление:** {updated_at}
            """.format(updated_at=application.get('updated_at', 'Недавно')).strip()

            full_text = application_text + "\n\n" + additional_info

            # Отправляем сообщение
            bot.send_message(
                call.message.chat.id,
                full_text,
                parse_mode='Markdown'
            )

            bot.answer_callback_query(call.id, "📋 Информация о заявке")

        except Exception as e:
            print(f"❌ Ошибка в обработчике перезапущенной заявки: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки заявки")


# Дополнительные функции для ручного управления
def register_admin_restart_handlers(bot, db):
    """Регистрирует команды администратора для ручного перезапуска заявок"""
    application_temp_data = {}

    @bot.message_handler(func=lambda message: message.text == '🔄 Перезапустить заявку')
    def handle_restart_application_command(message):
        """Команда для перезапуска заявки администратором"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'external_admin']:
            bot.send_message(chat_id, "❌ Эта команда доступна только администраторам.")
            return

        bot.send_message(
            chat_id,
            "📝 Введите ID заявки для перезапуска:",
            reply_markup=get_cancel_keyboard()
        )

        # Устанавливаем состояние ожидания ID заявки
        if user_id not in application_temp_data:
            application_temp_data[user_id] = {}
        application_temp_data[user_id]['waiting_for_restart_id'] = True

    @bot.message_handler(func=lambda message:
    message.from_user.id in application_temp_data and
    application_temp_data[message.from_user.id].get('waiting_for_restart_id'))
    def handle_application_id_input(message):
        """Обработка ввода ID заявки для перезапуска"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        try:
            application_id = int(message.text.strip())

            # Получаем заявку
            application = db.fetch_one("""
                SELECT a.*, 
                       COUNT(CASE WHEN ar.status IN ('accepted', 'accepted_budget', 'counter_offer', 'assigned') THEN 1 END) as accepted_responses
                FROM applications a
                LEFT JOIN application_responses ar ON a.id = ar.application_id
                WHERE a.id = ? AND a.status IN ('active', 'urgent')
                GROUP BY a.id
            """, (application_id,))

            if not application:
                bot.send_message(chat_id, f"❌ Активная заявка #{application_id} не найдена.")
                return

            # Запрашиваем подтверждение
            bot.send_message(
                chat_id,
                f"⚠️ **Подтвердите перезапуск заявки #{application_id}**\n\n"
                f"После перезапуска:\n"
                f"1. Обновится поле updated_at\n"
                f"2. Заявка станет срочной (urgent)\n"
                f"3. Уведомление будет отправлено ВСЕМ перевозчикам\n\n"
                f"Вы уверены?",
                reply_markup=get_confirm_restart_keyboard(application_id),
                parse_mode='Markdown'
            )

            # Сбрасываем состояние
            application_temp_data[user_id]['waiting_for_restart_id'] = False

        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректный числовой ID заявки.")
        except Exception as e:
            print(f"❌ Ошибка при обработке ID заявки: {e}")
            bot.send_message(chat_id, "❌ Произошла ошибка. Попробуйте снова.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_restart_'))
    def handle_confirm_restart(call):
        """Подтверждение ручного перезапуска заявки"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        application_id = int(call.data.split('_')[2])

        # Получаем заявку
        application = db.fetch_one(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        try:
            # Перезапускаем заявку
            restart_application(bot, db, application)

            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"✅ Заявка #{application_id} успешно перезапущена!\n"
                     f"Уведомление отправлено всем перевозчикам.",
                parse_mode='Markdown'
            )

            bot.answer_callback_query(call.id, "✅ Заявка перезапущена")

        except Exception as e:
            print(f"❌ Ошибка при ручном перезапуске: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при перезапуске")


def get_cancel_keyboard():
    """Клавиатура для отмены действия"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_restart"))
    return keyboard


def get_confirm_restart_keyboard(application_id):
    """Клавиатура для подтверждения перезапуска"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Да, перезапустить", callback_data=f"confirm_restart_{application_id}"),
        InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_restart")
    )
    return keyboard


def manual_restart_application(bot, db, application_id, user_id):
    """
    Ручной перезапуск заявки администратором
    """
    try:
        # Получаем заявку
        application = db.fetch_one(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application:
            return False, "Заявка не найдена"

        # Обновляем заявку
        db.execute_query(
            "UPDATE applications SET updated_at = datetime('now'), status = 'urgent' WHERE id = ?",
            (application_id,)
        )

        # Уведомляем администратора и логиста
        notify_about_restart(bot, db, application)

        # Уведомляем ВСЕХ перевозчиков
        notify_all_executors_about_application(bot, db, application_id)

        return True, f"Заявка #{application_id} успешно перезапущена"

    except Exception as e:
        print(f"❌ Ошибка при ручном перезапуске: {e}")
        return False, f"Ошибка при перезапуске: {str(e)}"