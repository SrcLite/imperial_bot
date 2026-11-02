import json
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from handlers.application_handlers.google_sheets_export import export_application_responses_to_google_sheets
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from config.google_sheets_config import is_google_sheets_enabled


def register_admin_anomaly_handlers(bot, db):
    """Регистрация обработчиков для системы аномалий"""

    @bot.message_handler(func=lambda message: message.text == '📈 Настройка аномалий')
    def handle_anomaly_settings(message):
        """Показывает текущие настройки аномалий"""
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
        set_user_state(user_id, '')
        # Проверяем, что пользователь - администратор
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.send_message(chat_id, "❌ Эта функция доступна только администраторам.")
            return

        # Получаем текущие настройки
        settings = db.get_anomaly_settings()
        if not settings:
            bot.send_message(chat_id, "❌ Настройки аномалий не найдены.")
            return

        percentage = settings.get('anomaly_percentage', 30.0)

        # Создаем клавиатуру с двумя кнопками
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📊 Изменить процент", callback_data="change_anomaly_percentage"),
            InlineKeyboardButton("📋 Список всех заявок", callback_data="list_all_applications")
        )

        bot.send_message(
            chat_id,
            f"⚙️ **Настройки системы аномалий**\n\n"
            f"📊 **Текущий порог отклонения:** {percentage:.1f}%\n\n"
            f"Система будет помечать как аномальные ставки, которые:\n"
            f"• Ниже бюджета более чем на {percentage:.1f}%\n"
            f"• Выше бюджета более чем на {percentage:.1f}%\n\n"
            f"Выберите действие:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    @bot.callback_query_handler(func=lambda call: call.data == 'change_anomaly_percentage')
    def handle_change_percentage(call):
        """Запрашивает новый процент отклонения"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📊 **Введите новый процент отклонения для аномалий:**\n\n"
                 "Введите число от 1 до 100 (например, 30 для 30%).\n"
                 "Система будет помечать ставки, отклоняющиеся от бюджета более чем на указанный процент.",
            parse_mode='Markdown'
        )

        set_user_state(user_id, 'waiting_anomaly_percentage')
        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_anomaly_percentage')
    def handle_anomaly_percentage_input(message):
        """Обрабатывает ввод нового процента отклонения"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        try:
            percentage = float(message.text.replace(',', '.'))

            if percentage <= 0 or percentage > 100:
                bot.send_message(chat_id, "❌ Процент должен быть от 0.1 до 100. Введите корректное значение:")
                return

            # Обновляем настройки
            db.update_anomaly_percentage(percentage)

            # Очищаем состояние
            set_user_state(user_id, '')

            # Получаем текущие настройки для обновления сообщения
            settings = db.get_anomaly_settings()
            percentage = settings.get('anomaly_percentage', 30.0)

            # Создаем клавиатуру с двумя кнопками
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("📊 Изменить процент", callback_data="change_anomaly_percentage"),
                InlineKeyboardButton("📋 Список всех заявок", callback_data="list_all_applications")
            )

            # Отправляем новое сообщение с обновленными данными
            bot.send_message(
                chat_id,
                f"✅ **Процент отклонения обновлен!**\n\n"
                f"Новое значение: **{percentage:.1f}%**\n\n"
                f"Система будет помечать как аномальные ставки, которые:\n"
                f"• Ниже бюджета более чем на {percentage:.1f}%\n"
                f"• Выше бюджета более чем на {percentage:.1f}%\n\n"
                f"Выберите действие:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )

        except ValueError:
            bot.send_message(chat_id, "❌ Пожалуйста, введите корректное число (например: 30 для 30%):")

    @bot.callback_query_handler(func=lambda call: call.data == 'list_all_applications')
    def handle_list_all_applications(call):
        """Показывает список всех аукционных заявок с отметками об аномалиях"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Получаем все аукционные заявки с откликами
        applications = db.fetch_all("""
            SELECT a.*, COUNT(ar.id) as responses_count
            FROM applications a
            LEFT JOIN application_responses ar ON a.id = ar.application_id 
                AND ar.status IN ('counter_offer', 'accepted_budget')
            WHERE a.application_type = 'auction'
            GROUP BY a.id
            HAVING COUNT(ar.id) > 0
            ORDER BY a.created_at DESC
        """)

        if not applications:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="📭 **Нет аукционных заявок с откликами**\n\n"
                     "На данный момент нет заявок для проверки.",
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return

        # Формируем инлайн-клавиатуру с заявками
        keyboard = InlineKeyboardMarkup(row_width=1)

        for app in applications:
            # Проверяем аномалии для заявки
            anomalies = db.check_response_anomalies(app['id'])
            has_anomalies = len(anomalies) > 0

            # Получаем точки маршрута
            loading_point = db.fetch_one(
                "SELECT address FROM application_points WHERE application_id = ? AND point_type = 'loading' ORDER BY point_order LIMIT 1",
                (app['id'],)
            )
            unloading_point = db.fetch_one(
                "SELECT address FROM application_points WHERE application_id = ? AND point_type = 'unloading' ORDER BY point_order LIMIT 1",
                (app['id'],)
            )

            loading_city = loading_point['address'].split(',')[0] if loading_point else 'Не указано'
            unloading_city = unloading_point['address'].split(',')[0] if unloading_point else 'Не указано'

            # Формируем текст кнопки с отметкой об аномалиях
            if has_anomalies:
                button_text = f"⚠️ Заявка #{app['id']} | {loading_city} → {unloading_city} | ⚠️ {len(anomalies)} аном."
            else:
                button_text = f"✅ Заявка #{app['id']} | {loading_city} → {unloading_city}"

            keyboard.add(InlineKeyboardButton(button_text, callback_data=f"view_anomaly_application_details_{app['id']}"))

        # Добавляем кнопку "Назад"
        keyboard.add(InlineKeyboardButton("↩️ Назад", callback_data="back_to_anomaly_settings"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📋 **Список всех аукционных заявок**\n\n"
                 "Заявки с аномальными ставками помечены ⚠️\n"
                 "Выберите заявку для просмотра деталей и ставок:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('view_anomaly_application_details_'))
    def handle_view_application_details(call):
        """Показывает детали заявки и все ставки с выделением аномальных"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        application_id = int(call.data.split('_')[4])

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Получаем информацию о заявке
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        # Получаем точки маршрута
        loading_points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? AND point_type = 'loading' ORDER BY point_order",
            (application_id,)
        )
        unloading_points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? AND point_type = 'unloading' ORDER BY point_order",
            (application_id,)
        )

        # Получаем все ответы на заявку
        responses = db.fetch_all("""
            SELECT ar.*, u.first_name, u.last_name, u.phone as executor_phone, 
                   c.name as company_name, c.inn as company_inn
            FROM application_responses ar
            JOIN users u ON ar.executor_id = u.telegram_id
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE ar.application_id = ? 
                AND ar.status IN ('counter_offer', 'accepted_budget', 'selected')
            ORDER BY ar.created_at DESC
        """, (application_id,))

        # Получаем настройки аномалий
        settings = db.get_anomaly_settings()
        percentage = settings.get('anomaly_percentage', 30.0)

        # Получаем аномалии для заявки
        anomalies = db.check_response_anomalies(application_id)

        # Формируем текст заявки
        loading_addresses = "\n".join(
            [f"  • {p['address']}" for p in loading_points]) if loading_points else "Не указано"
        unloading_addresses = "\n".join(
            [f"  • {p['address']}" for p in unloading_points]) if unloading_points else "Не указано"

        text = f"📋 **Заявка #{application_id}**\n\n"
        text += f"📅 **Дата создания:** {application['created_at'][:16] if application.get('created_at') else 'Не указана'}\n"
        text += f"💰 **Бюджет:** {float(application.get('desired_budget', 0)):,.0f} руб.\n"
        text += f"⚠️ **Порог аномалий:** {percentage:.1f}%\n\n"

        text += f"📍 **Погрузка:**\n{loading_addresses}\n\n"
        text += f"🏁 **Выгрузка:**\n{unloading_addresses}\n\n"

        if application.get('loading_datetime'):
            text += f"📅 **Дата погрузки:** {application['loading_datetime'][:16]}\n"
        if application.get('unloading_datetime'):
            text += f"📅 **Дата выгрузки:** {application['unloading_datetime'][:16]}\n\n"

        # Информация о грузе
        if application.get('cargo_type'):
            text += f"📦 **Характер груза:** {application['cargo_type']}\n"
        if application.get('weight'):
            text += f"⚖️ **Вес:** {float(application['weight']):.2f} т\n"
        if application.get('volume'):
            text += f"📏 **Объем:** {float(application['volume']):.2f} м³\n"
            text += "\n---\n"
            text += "📊 **Все ставки перевозчиков:**\n\n"

            if not responses:
                text += "📭 На эту заявку еще нет откликов.\n"
            else:
                for i, response in enumerate(responses, 1):
                    # Определяем, есть ли у этого ответа аномалии
                    has_response_anomalies = any(a['response_id'] == response['id'] for a in anomalies)

                    if has_response_anomalies:
                        text += f"⚠️ **{i}. {response['first_name']} {response['last_name']}** (АНОМАЛЬНЫЕ СТАВКИ)\n"
                    else:
                        text += f"✅ **{i}. {response['first_name']} {response['last_name']}**\n"

                    if response.get('company_name'):
                        text += f"🏢 Компания: {response['company_name']}\n"

                    text += f"📞 Телефон: {response.get('executor_phone', 'Не указан')}\n"
                    text += f"📅 Дата отклика: {response['created_at'][:16] if response.get('created_at') else 'Не указана'}\n"

                    # Парсим варианты оплаты
                    payment_options = {}
                    if response['payment_options']:
                        try:
                            payment_options = json.loads(response['payment_options'])
                        except:
                            pass

                    if payment_options:
                        text += "💰 **Ставки:**\n"
                        for payment_type, amount in payment_options.items():
                            try:
                                amount_float = float(amount)
                                desired_budget = float(application.get('desired_budget', 0))

                                # Проверяем, является ли эта ставка аномальной
                                is_anomaly = False
                                anomaly_info = ""
                                if desired_budget > 0:
                                    deviation = abs(amount_float - desired_budget) / desired_budget * 100
                                    if deviation > percentage:
                                        is_anomaly = True
                                        if amount_float < desired_budget:
                                            anomaly_info = f" ⚠️🔽 НИЖЕ НА {deviation:.1f}%"
                                        else:
                                            anomaly_info = f" ⚠️🔼 ВЫШЕ НА {deviation:.1f}%"

                                if is_anomaly:
                                    text += f"  • **{get_payment_type_name(payment_type)}:** {amount_float:,.0f} руб.{anomaly_info}\n"
                                else:
                                    text += f"  • {get_payment_type_name(payment_type)}: {amount_float:,.0f} руб.\n"

                            except (ValueError, TypeError):
                                text += f"  • {get_payment_type_name(payment_type)}: {amount}\n"
                    else:
                        text += "💰 Ставки не указаны\n"

                    text += "\n"

            text += "\n---\n"
            if anomalies:
                text += "ℹ️ *Ставки, помеченные как аномальные, требуют дополнительного внимания при выборе перевозчика.*"
            else:
                text += "ℹ️ *Все ставки находятся в пределах нормы.*"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)

        if responses:
            keyboard.add(
                InlineKeyboardButton("📊 Статистика аномалий", callback_data=f"anomaly_stats_{application_id}"),
            )

        keyboard.add(
            InlineKeyboardButton("📈 Экспорт в Google Таблицу", callback_data=f"export_anomalies_{application_id}"),
            InlineKeyboardButton("↩️ Назад к списку", callback_data="list_all_applications")
        )

        # Отправляем сообщение
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except Exception as e:
            # Если сообщение слишком длинное, разбиваем на части
            if "message is too long" in str(e):
                # Первая часть: информация о заявке
                part1 = text[:4000]
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=part1 + "\n\n[Продолжение следует...]",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )

                # Вторая часть: ставки перевозчиков
                part2 = text[4000:]
                if part2:
                    bot.send_message(
                        chat_id,
                        part2,
                        parse_mode='Markdown'
                    )
            else:
                raise e

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('anomaly_stats_'))
    def handle_anomaly_statistics(call):
        """Показывает статистику аномалий для заявки"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        application_id = int(call.data.split('_')[2])

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Получаем все ответы на заявку
        responses = db.fetch_all("""
            SELECT ar.*, u.first_name, u.last_name, c.name as company_name
            FROM application_responses ar
            JOIN users u ON ar.executor_id = u.telegram_id
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE ar.application_id = ? 
                AND ar.status IN ('counter_offer', 'accepted_budget')
        """, (application_id,))

        # Получаем настройки аномалий
        settings = db.get_anomaly_settings()
        percentage = settings.get('anomaly_percentage', 30.0)

        # Получаем информацию о заявке
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        desired_budget = float(application.get('desired_budget', 0))

        # Анализируем данные
        total_responses = len(responses)
        total_anomalies = 0
        anomalies_by_type = {'below': 0, 'above': 0}
        avg_deviations = []

        for response in responses:
            try:
                payment_options = json.loads(response['payment_options']) if response['payment_options'] else {}
                for amount in payment_options.values():
                    try:
                        amount_float = float(amount)
                        if desired_budget > 0:
                            deviation = abs(amount_float - desired_budget) / desired_budget * 100
                            avg_deviations.append(deviation)
                            if deviation > percentage:
                                total_anomalies += 1
                                if amount_float < desired_budget:
                                    anomalies_by_type['below'] += 1
                                else:
                                    anomalies_by_type['above'] += 1
                    except (ValueError, TypeError):
                        continue
            except (json.JSONDecodeError, TypeError):
                continue

        # Рассчитываем среднее отклонение
        avg_deviation = sum(avg_deviations) / len(avg_deviations) if avg_deviations else 0

        # Формируем текст
        text = f"📊 **Статистика аномалий - Заявка #{application_id}**\n\n"
        text += f"**Общая статистика:**\n"
        text += f"• Всего предложений: {total_responses}\n"
        text += f"• Аномальных ставок: {total_anomalies}\n"
        if total_responses > 0:
            text += f"• Процент аномалий: {total_anomalies / total_responses * 100:.1f}%\n"
        text += f"• Среднее отклонение: {avg_deviation:.1f}%\n\n"

        if total_anomalies > 0:
            text += f"**Распределение аномалий:**\n"
            text += f"• Ниже бюджета: {anomalies_by_type['below']} ({anomalies_by_type['below'] / total_anomalies * 100:.1f}% от аномалий)\n"
            text += f"• Выше бюджета: {anomalies_by_type['above']} ({anomalies_by_type['above'] / total_anomalies * 100:.1f}% от аномалий)\n\n"

        text += f"**Параметры проверки:**\n"
        text += f"• Бюджет заявки: {desired_budget:,.0f} руб.\n"
        text += f"• Порог аномалий: {percentage:.1f}%\n"
        text += f"• Диапазон нормы: {desired_budget * (1 - percentage / 100):,.0f} - {desired_budget * (1 + percentage / 100):,.0f} руб.\n\n"

        text += "ℹ️ *Анализ помогает выявить подозрительные предложения и принять взвешенное решение.*"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📋 Детали заявки", callback_data=f"view_anomaly_application_details_{application_id}"),
            InlineKeyboardButton("↩️ Назад", callback_data=f"view_anomaly_application_details_{application_id}")
        )

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('export_anomalies_'))
    def handle_export_anomalies(call):
        """Экспортирует аномалии в Google Таблицу"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        application_id = int(call.data.split('_')[2])

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Проверяем, включен ли Google Sheets
        if not is_google_sheets_enabled():
            bot.answer_callback_query(call.id, "❌ Google Sheets отключен. Включите его в настройках.")
            return

        try:
            # Экспортируем все ответы по заявке
            export_application_responses_to_google_sheets(db, application_id)

            bot.answer_callback_query(call.id, "✅ Данные экспортированы в Google Таблицу")

            # Обновляем сообщение
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"✅ **Данные заявки #{application_id} успешно экспортированы в Google Таблицу!**\n\n"
                     "Ставки перевозчиков теперь доступны для анализа в Google Sheets.",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка экспорта: {str(e)}")

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_anomaly_settings')
    def handle_back_to_anomaly_settings(call):
        """Возвращает к настройкам аномалий"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Получаем текущие настройки
        settings = db.get_anomaly_settings()
        percentage = settings.get('anomaly_percentage', 30.0)

        # Создаем клавиатуру с двумя кнопками
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📊 Изменить процент", callback_data="change_anomaly_percentage"),
            InlineKeyboardButton("📋 Список всех заявок", callback_data="list_all_applications")
        )

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"⚙️ **Настройки системы аномалий**\n\n"
                 f"📊 **Текущий порог отклонения:** {percentage:.1f}%\n\n"
                 f"Система будет помечать как аномальные ставки, которые:\n"
                 f"• Ниже бюджета более чем на {percentage:.1f}%\n"
                 f"• Выше бюджета более чем на {percentage:.1f}%\n\n"
                 f"Выберите действие:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    # Удаляем дублирующиеся функции, которые были в старом коде
    @bot.callback_query_handler(func=lambda call: call.data == 'check_anomalies_menu')
    def handle_check_anomalies_menu(call):
        """Перенаправляем на список всех заявок"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Перенаправляем на список всех заявок
        handle_list_all_applications(call)

    @bot.callback_query_handler(
        func=lambda call: call.data in ['view_all_anomalies', 'check_specific_application', 'anomaly_statistics'])
    def handle_deprecated_buttons(call):
        """Обработка устаревших кнопок - перенаправляем на список всех заявок"""
        bot.answer_callback_query(call.id, "ℹ️ Эта функция теперь доступна в списке всех заявок")
        handle_list_all_applications(call)

    def get_payment_type_name(payment_type):
        """Возвращает читаемое название типа оплаты"""
        names = {
            'nds': 'С НДС',
            'ip': 'Без НДС',
            'self-employed': 'Самозанятый',
            'cash': 'Наличные'
        }
        return names.get(payment_type, payment_type)