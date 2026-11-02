import json
import ast
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from keyboards.main_menus import get_main_menu
from utils.dicts import CARGO_TYPE_REVERSE_MAPPING, VEHICLE_TYPE_REVERSE_MAPPING
from utils.helpers import update_user_rating_on_rejection


def register_logist_accepted_applications_handlers(bot, db):
    """Регистрация обработчиков для принятых заявок логиста"""

    # Словарь для хранения временных данных
    temp_data = {}

    @bot.message_handler(func=lambda message: message.text == '✅ Принятые заявки')
    def show_logist_accepted_applications(message):
        """Показывает заявки, которые приняли перевозчики"""
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

        # Проверяем роль пользователя
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'external_logist', 'admin', 'external_admin']:
            bot.send_message(chat_id, "❌ Эта функция доступна только логистам.")
            return

        # Получаем заявки, которые имеют отклики с положительным статусом
        applications = db.fetch_all("""
            SELECT DISTINCT 
                a.*,
                ar.executor_id,
                ar.status as response_status,
                ar.payment_options as response_payment_options,
                ar.created_at as response_created_at,
                u.first_name as executor_first_name,
                u.last_name as executor_last_name,
                u.phone as executor_phone,
                c.name as company_name,
                c.inn as company_inn
            FROM applications a
            JOIN application_responses ar ON a.id = ar.application_id
            JOIN users u ON ar.executor_id = u.telegram_id
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE a.created_by = ?
            AND ar.status IN ('accepted', 'accepted_budget', 'counter_offer')
            AND a.status = 'assigned'
            AND a.assigned_to = ar.executor_id  -- Не назначенные или назначенные этому перевозчику
            ORDER BY ar.created_at DESC
        """, (user_id,))

        if not applications:
            bot.send_message(chat_id, "📭 У вас нет заявок с принятыми откликами.")
            return

        # Группируем заявки по application_id
        apps_by_id = {}
        for app in applications:
            app_id = app['id']
            if app_id not in apps_by_id:
                apps_by_id[app_id] = {
                    'application': app,
                    'responses': []
                }

            # Получаем точки маршрута для отображения
            points = db.fetch_all(
                "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
                (app_id,)
            )

            loading_points = [p for p in points if p['point_type'] == 'loading']
            unloading_points = [p for p in points if p['point_type'] == 'unloading']

            # Создаем информацию об отклике
            response_info = {
                'executor_id': app['executor_id'],
                'executor_name': f"{app['executor_first_name']} {app['executor_last_name']}",
                'executor_phone': app['executor_phone'],
                'company_name': app['company_name'],
                'company_inn': app['company_inn'],
                'status': app['response_status'],
                'payment_options': app['response_payment_options'],
                'created_at': app['response_created_at'],
                'loading_points': loading_points,
                'unloading_points': unloading_points
            }

            apps_by_id[app_id]['responses'].append(response_info)

        # Сохраняем данные
        if user_id not in temp_data:
            temp_data[user_id] = {}

        temp_data[user_id]['applications_by_id'] = apps_by_id
        temp_data[user_id]['application_ids'] = list(apps_by_id.keys())
        temp_data[user_id]['current_index'] = 0

        # Показываем первую заявку
        show_logist_accepted_application_page(user_id, chat_id, 0, is_new=True)

    def show_logist_accepted_application_page(user_id, chat_id, index, is_new=False):
        """Показывает заявку с откликами логисту"""
        if user_id not in temp_data or 'applications_by_id' not in temp_data[user_id]:
            bot.send_message(chat_id, "❌ Данные устарели. Нажмите '✅ Принятые заявки' снова.")
            return

        app_ids = temp_data[user_id]['application_ids']

        if index < 0 or index >= len(app_ids):
            return

        app_id = app_ids[index]
        app_data = temp_data[user_id]['applications_by_id'][app_id]
        application = app_data['application']
        responses = app_data['responses']

        # Форматируем текст заявки
        print(application['cargo_type'])
        text = format_logist_accepted_application(application, responses)

        # Создаем клавиатуру
        keyboard = get_logist_accepted_application_keyboard(app_id, index, len(app_ids), responses)

        if is_new:
            msg = bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode='Markdown')
            temp_data[user_id]['message_id'] = msg.message_id
        else:
            message_id = temp_data[user_id].get('message_id')
            if message_id:
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                except:
                    msg = bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode='Markdown')
                    temp_data[user_id]['message_id'] = msg.message_id

        temp_data[user_id]['current_index'] = index

    @bot.callback_query_handler(func=lambda call: call.data.startswith('logist_accepted_nav_'))
    def handle_logist_accepted_navigation(call):
        """Обработка навигации по принятым заявкам"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        direction = data_parts[3]  # prev или next
        current_index = int(data_parts[4])

        if user_id not in temp_data or 'application_ids' not in temp_data[user_id]:
            bot.answer_callback_query(call.id, "❌ Сессия истекла")
            return

        app_ids = temp_data[user_id]['application_ids']

        if direction == 'prev':
            new_index = current_index - 1
        else:
            new_index = current_index + 1

        if new_index < 0 or new_index >= len(app_ids):
            bot.answer_callback_query(call.id)
            return

        show_logist_accepted_application_page(user_id, chat_id, new_index, is_new=False)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('select_executor_'))
    def handle_select_executor(call):
        """Обработка выбора перевозчика для заявки"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        application_id = int(data_parts[2])
        executor_id = int(data_parts[3])

        # Получаем информацию об перевозчике
        executor_info = db.fetch_one("""
            SELECT u.*, c.name as company_name, c.inn as company_inn
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE u.telegram_id = ?
        """, (executor_id,))

        if not executor_info:
            bot.answer_callback_query(call.id, "❌ Перевозчик не найден")
            return

        # Получаем информацию о заявке
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))

        # Получаем точки маршрута для отображения
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE applicationbgn_id = ? ORDER BY point_order",
            (application_id,)
        )

        loading_points = [p for p in points if p['point_type'] == 'loading']
        unloading_points = [p for p in points if p['point_type'] == 'unloading']

        # Получаем отклик этого перевозчика
        response = db.fetch_one("""
            SELECT * FROM application_responses 
            WHERE application_id = ? AND executor_id = ?
        """, (application_id, executor_id))

        if not response:
            bot.answer_callback_query(call.id, "❌ Отклик не найден")
            return

        # Парсим варианты оплаты
        payment_options = {}
        if response['payment_options']:
            try:
                payment_options = ast.literal_eval(response['payment_options'])
            except:
                try:
                    payment_options = json.loads(response['payment_options'])
                except:
                    pass

        # Формируем текст с деталями перевозчика
        executor_name = f"{executor_info['first_name']} {executor_info['last_name']}"
        company_name = executor_info.get('company_name', 'Не указана')
        company_inn = executor_info.get('company_inn', 'Не указан')
        executor_phone = executor_info.get('phone', 'Не указан')

        # Статус отклика
        status_text = {
            'accepted': '✅ Принята',
            'accepted_budget': '✅ Принята по бюджету',
            'counter_offer': '💰 Встречное предложение'
        }.get(response['status'], response['status'])

        # Форматируем варианты оплаты
        payments_text = ""
        if payment_options:
            for payment_type, amount in payment_options.items():
                payment_name = get_payment_type_name(payment_type)
                payments_text += f"• {payment_name}: {float(amount):,.0f} руб.\n"
        else:
            payments_text = "Не указаны"

        # Форматируем маршрут
        route_text = ""
        if loading_points:
            route_text += "**📍 Точки погрузки:**\n"
            for i, point in enumerate(loading_points, 1):
                route_text += f"   {i}. **{point['city']}**, {point['address']}\n"
                if point.get('point_datetime'):
                    try:
                        dt = point['point_datetime']
                        if isinstance(dt, str):
                            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                        route_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                    except:
                        pass

        if unloading_points:
            route_text += "**🏁 Точки выгрузки:**\n"
            for i, point in enumerate(unloading_points, 1):
                route_text += f"   {i}. **{point['city']}**, {point['address']}\n"
                if point.get('point_datetime'):
                    try:
                        dt = point['point_datetime']
                        if isinstance(dt, str):
                            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                        route_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                    except:
                        pass

        text = f"""
👤 **Перевозчик:** {executor_name}
🏢 **Компания:** {company_name}
🔢 **ИНН:** {company_inn}
📞 **Телефон:** {executor_phone}

📋 **Статус отклика:** {status_text}
💰 **Предложенные условия оплаты:**
{payments_text}

📅 **Отклик отправлен:** {response['created_at']}

📦 **Заявка #{application_id}**
🎯 **Тип:** {'СТАНДАРТНАЯ' if application['application_type'] == 'fixed' else 'ЗАПРОС СТАВОК'}

{route_text}

💼 **Груз:** {CARGO_TYPE_REVERSE_MAPPING.get(application.get('cargo_type', 'Не указан'), application.get('cargo_custom_type'))}
⚖️ **Вес:** {float(application.get('weight', 0)):.2f} т
📏 **Объем:** {float(application.get('volume', 0)):.2f} м³
🚛 **Транспорт:** {VEHICLE_TYPE_REVERSE_MAPPING.get(application.get('vehicle_type', 'Не указан'), application.get('vehicle_type', 'Не указан'))}

Выберите действие для этого перевозчика:
"""

        # Создаем клавиатуру с действиями
        keyboard = InlineKeyboardMarkup(row_width=2)

        # Основные действия
        row1 = [
            InlineKeyboardButton("✅ Назначить", callback_data=f"assign_executor_{application_id}_{executor_id}"),
            InlineKeyboardButton("📞 Позвонить", callback_data=f"call_executor_{executor_id}")
        ]
        keyboard.add(*row1)

        # Дополнительные действия
        row2 = [
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_executor_{application_id}_{executor_id}"),
            InlineKeyboardButton("↩️ Назад", callback_data=f"back_to_accepted_{application_id}")
        ]
        keyboard.add(*row2)

        # Редактируем сообщение
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('assign_executor_'))
    def handle_assign_executor(call):
        """Назначение перевозчика на заявку"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        application_id = int(data_parts[2])
        executor_id = int(data_parts[3])

        # Проверяем, что заявка принадлежит этому логисту
        application = db.fetch_one(
            "SELECT created_by, assigned_to FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application or application['created_by'] != user_id:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для назначения этой заявки")
            return

        # Проверяем, не назначена ли уже заявка другому перевозчику
        if application['assigned_to'] and application['assigned_to'] != executor_id:
            bot.answer_callback_query(call.id, "❌ Заявка уже назначена другому перевозчику")
            return

        # Обновляем заявку
        db.execute_query(
            "UPDATE applications SET assigned_to = ?, status = 'assigned' WHERE id = ?",
            (executor_id, application_id)
        )

        # Обновляем статус отклика
        db.execute_query(
            "UPDATE application_responses SET status = 'assigned' WHERE application_id = ? AND executor_id = ?",
            (application_id, executor_id)
        )

        # Отклоняем остальные отклики на эту заявку
        db.execute_query(
            """UPDATE application_responses 
            SET status = 'rejected_by_logist' 
            WHERE application_id = ? AND executor_id != ? AND status IN ('accepted', 'accepted_budget', 'counter_offer')""",
            (application_id, executor_id)
        )

        # Уведомляем перевозчика о назначении
        notify_executor_about_assignment(bot, db, application_id, executor_id)

        # Уведомляем других перевозчиков об отказе
        notify_other_executors_about_rejection(bot, db, application_id, executor_id)

        # Показываем сообщение об успехе
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="✅ **Перевозчик назначен на заявку!**\n\n"
                 f"Перевозчик успешно назначен на заявку #{application_id}.\n"
                 "Перевозчик получил уведомление о назначении.",
            parse_mode='Markdown'
        )

        # Обновляем рейтинг перевозчика (бонус за получение заявки)
        update_executor_rating_on_assignment(db, executor_id, application_id)

        # Удаляем заявку из списка принятых (теперь она назначена)
        if user_id in temp_data and 'application_ids' in temp_data[user_id]:
            if application_id in temp_data[user_id]['application_ids']:
                temp_data[user_id]['application_ids'].remove(application_id)
                if temp_data[user_id]['applications_by_id'] and application_id in temp_data[user_id][
                    'applications_by_id']:
                    del temp_data[user_id]['applications_by_id'][application_id]

        bot.answer_callback_query(call.id, "✅ Перевозчик назначен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reject_executor_'))
    def handle_reject_executor(call):
        """Отклонение отклика перевозчика"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        application_id = int(data_parts[2])
        executor_id = int(data_parts[3])

        # Проверяем, что заявка принадлежит этому логисту
        application = db.fetch_one(
            "SELECT created_by FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application or application['created_by'] != user_id:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для отклонения этого отклика")
            return

        # Обновляем статус отклика
        db.execute_query(
            "UPDATE application_responses SET status = 'rejected_by_logist' WHERE application_id = ? AND executor_id = ?",
            (application_id, executor_id)
        )

        # Уведомляем перевозчика об отклонении
        notify_executor_about_rejection(bot, db, application_id, executor_id)

        # Обновляем список заявок в temp_data
        if user_id in temp_data and 'applications_by_id' in temp_data[user_id]:
            if application_id in temp_data[user_id]['applications_by_id']:
                # Удаляем этого перевозчика из списка откликов
                app_data = temp_data[user_id]['applications_by_id'][application_id]
                app_data['responses'] = [
                    resp for resp in app_data['responses']
                    if resp['executor_id'] != executor_id
                ]

                # Если не осталось откликов, удаляем заявку из списка
                if not app_data['responses']:
                    temp_data[user_id]['application_ids'] = [
                        app_id for app_id in temp_data[user_id]['application_ids']
                        if app_id != application_id
                    ]
                    del temp_data[user_id]['applications_by_id'][application_id]

        # Показываем сообщение об успехе
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="❌ **Отклик перевозчика отклонен!**\n\n"
                 f"Отклик перевозчика на заявку #{application_id} отклонен.\n"
                 "Перевозчик получил уведомление об отклонении.",
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "✅ Отклик отклонен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('call_executor_'))
    def handle_call_executor(call):
        """Позвонить перевозчику"""
        executor_id = int(call.data.split('_')[2])

        # Получаем телефон перевозчика
        executor_info = db.fetch_one(
            "SELECT phone FROM users WHERE telegram_id = ?",
            (executor_id,)
        )

        if executor_info and executor_info.get('phone'):
            phone_number = executor_info['phone']
            bot.send_message(
                call.message.chat.id,
                f"📞 **Телефон перевозчика:** {phone_number}\n\n"
                f"Вы можете скопировать номер и позвонить.\n"
                f"Или используйте ссылку для звонка: [tel:{phone_number}](tel:{phone_number})",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(call.message.chat.id, "❌ Телефон перевозчика не указан.")

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_accepted_'))
    def handle_back_to_accepted(call):
        """Возврат к списку заявок"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        application_id = int(call.data.split('_')[3])

        # Находим индекс заявки
        if user_id in temp_data and 'application_ids' in temp_data[user_id]:
            app_ids = temp_data[user_id]['application_ids']
            if application_id in app_ids:
                index = app_ids.index(application_id)
                show_logist_accepted_application_page(user_id, chat_id, index, is_new=False)

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'close_logist_accepted')
    def handle_close_logist_accepted(call):
        """Закрытие просмотра принятых заявок"""
        user_id = call.from_user.id

        bot.delete_message(call.message.chat.id, call.message.message_id)

        if user_id in temp_data:
            if 'applications_by_id' in temp_data[user_id]:
                del temp_data[user_id]['applications_by_id']
            if 'application_ids' in temp_data[user_id]:
                del temp_data[user_id]['application_ids']

        bot.answer_callback_query(call.id, "✅ Просмотр завершен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('unassign_application_'))
    def handle_unassign_application(call):
        """Отзыв заявки у перевозчика"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        application_id = int(call.data.split('_')[2])

        # Проверяем, что заявка принадлежит этому логисту и назначена
        application = db.fetch_one(
            "SELECT created_by, assigned_to, status FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application or application['created_by'] != user_id:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для отзыва этой заявки")
            return

        if not application['assigned_to']:
            bot.answer_callback_query(call.id, "❌ Заявка не назначена перевозчику")
            return

        executor_id = application['assigned_to']

        # Запрашиваем подтверждение
        bot.send_message(
            chat_id,
            "⚠️ **ВНИМАНИЕ: Отзыв заявки у перевозчика!**\n\n"
            f"Вы собираетесь отозвать заявку #{application_id} у перевозчика.\n"
            "Перевозчик получит уведомление об отзыве.\n\n"
            "Укажите причину отзыва (опционально):",
            reply_markup=get_cancel_unassign_keyboard(application_id)
        )

        # Сохраняем состояние
        if user_id not in temp_data:
            temp_data[user_id] = {}

        temp_data[user_id]['waiting_for_unassign_reason'] = True
        temp_data[user_id]['unassign_application_id'] = application_id
        temp_data[user_id]['unassign_executor_id'] = executor_id

        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message:
    message.from_user.id in temp_data and
    temp_data[message.from_user.id].get('waiting_for_unassign_reason'))
    def handle_unassign_reason(message):
        """Обработка причины отзыва заявки"""
        user_id = message.from_user.id
        role = db.get_user_role(user_id)

        if user_id not in temp_data:
            return

        application_id = temp_data[user_id].get('unassign_application_id')
        executor_id = temp_data[user_id].get('unassign_executor_id')
        reason = message.text if message.text.strip() else "Причина не указана"

        # Обновляем статус заявки на 'urgent' (срочная)
        db.execute_query(
            "UPDATE applications SET assigned_to = NULL, status = 'urgent' WHERE id = ?",
            (application_id,)
        )

        # Обновляем статус отклика перевозчика
        db.execute_query(
            """UPDATE application_responses 
            SET status = 'rejected' 
            WHERE application_id = ? AND executor_id = ?""",
            (application_id, executor_id)
        )

        # Уведомляем перевозчика об отзыве
        notify_executor_about_unassignment(bot, db, application_id, executor_id, reason)

        # ПОНИЖАЕМ РЕЙТИНГ ЛОГИСТА ЗА ОТЗЫВ ЗАЯВКИ
        penalty_data = db.fetch_one("select value from rating_rules "
                                    "where rule_type = 'logist' "
                                    "and rule_name = 'Отзыв заявки' "
                                    "and is_active = 1")
        penalty_amount = penalty_data['value'] if penalty_data else -5.0
        update_user_rating_on_rejection(db, user_id, application_id, penalty_amount, "Отзыв заявки", reason, 'logist')

        # Уведомляем других перевозчиков о срочной заявке (кроме отозванного)
        notify_other_executors_about_urgent_application(bot, db, application_id, executor_id)

        # Удаляем предыдущие сообщения
        try:
            bot.delete_message(message.chat.id, message.message_id - 1)
        except:
            pass

        bot.send_message(
            message.chat.id,
            "✅ **Заявка отозвана у перевозчика и помечена как СРОЧНАЯ!**\n\n"
            f"Заявка #{application_id} отозвана у перевозчика и теперь отображается как срочная для всех перевозчиков.\n"
            f"Остальные перевозчики получили уведомление о срочной заявке.",
            parse_mode='Markdown'
        )

        # Сбрасываем состояние
        temp_data[user_id]['waiting_for_unassign_reason'] = False
        del temp_data[user_id]['unassign_application_id']
        del temp_data[user_id]['unassign_executor_id']

        # Обновляем меню логиста
        bot.send_message(
            message.chat.id,
            "Выберите действие:",
            reply_markup=get_main_menu(role['role'])
        )

    def format_logist_accepted_application(application, responses):
        """Форматирует заявку с откликами для логиста"""
        app_id = application['id']

        # Информация о заявке
        app_type = "СТАНДАРТНАЯ" if application['application_type'] == 'fixed' else "ЗАПРОС СТАВОК"

        # Цена/бюджет
        price_info = ""
        if application['application_type'] == 'auction':
            budget = application.get('desired_budget', 0)
            price_info = f"🎯 **Желаемый бюджет:** {float(budget):,.0f} руб."

        # Получаем точки маршрута для отображения
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (app_id,)
        )

        loading_points = [p for p in points if p['point_type'] == 'loading']
        unloading_points = [p for p in points if p['point_type'] == 'unloading']

        # Форматируем маршрут с датами для каждой точки
        route_text = ""
        if loading_points:
            route_text += "**📍 Точки погрузки:**\n"
            for i, point in enumerate(loading_points, 1):
                route_text += f"   {i}. **{point['city']}**, {point['address']}\n"
                if point.get('point_datetime'):
                    try:
                        dt = point['point_datetime']
                        if isinstance(dt, str):
                            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                        route_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                    except:
                        pass

        if unloading_points:
            route_text += "**🏁 Точки выгрузки:**\n"
            for i, point in enumerate(unloading_points, 1):
                route_text += f"   {i}. **{point['city']}**, {point['address']}\n"
                if point.get('point_datetime'):
                    try:
                        dt = point['point_datetime']
                        if isinstance(dt, str):
                            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                        route_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                    except:
                        pass

        # Груз
        cargo_type = application.get('cargo_type', 'Не указан') or application.get('cargo_custom_type')
        weight = float(application.get('weight', 0))
        volume = float(application.get('volume', 0))

        # Статус назначения
        assigned_status = ""
        if application.get('assigned_to'):
            assigned_status = "\n⚠️ **ЗАЯВКА УЖЕ НАЗНАЧЕНА ПЕРЕВОЗЧИКУ**\n"

        # Информация об откликах
        responses_text = "\n👥 **ОТКЛИКИ перевозчиков:**\n\n"

        if not responses:
            responses_text += "Нет откликов\n"
        else:
            for i, resp in enumerate(responses, 1):
                status_text = {
                    'accepted': '✅ Принята',
                    'accepted_budget': '✅ Принята по бюджету',
                    'counter_offer': '💰 Встречное предложение'
                }.get(resp['status'], resp['status'])

                # Парсим варианты оплаты
                payment_options = {}
                if resp['payment_options']:
                    try:
                        payment_options = ast.literal_eval(resp['payment_options'])
                    except:
                        try:
                            payment_options = json.loads(resp['payment_options'])
                        except:
                            pass

                # Форматируем варианты оплаты
                payments_display = ""
                if payment_options:
                    for payment_type, amount in payment_options.items():
                        payment_name = get_payment_type_name(payment_type)
                        payments_display += f"      - {payment_name}: {float(amount):,.0f} руб.\n"
                else:
                    payments_display = "      - Не указаны\n"

                responses_text += f"{i}. **{resp['executor_name']}**\n"
                responses_text += f"   📱 Телефон: {resp['executor_phone']}\n"
                responses_text += f"   🏢 Компания: {resp.get('company_name', 'Не указана')}\n"
                responses_text += f"   🔢 ИНН: {resp.get('company_inn', 'Не указан')}\n"
                responses_text += f"   📋 Статус: {status_text}\n"
                responses_text += f"   💰 Условия оплаты:\n{payments_display}"
                responses_text += f"   📅 Отклик: {resp['created_at']}\n\n"

        text = f"""
📋 **ЗАЯВКА #{app_id} С ОТКЛИКАМИ**

{assigned_status}
🎯 **Тип заявки:** {app_type}
{price_info}

🗺️ **Маршрут:**
{route_text}
💼 **Груз:**
📦 Тип: {CARGO_TYPE_REVERSE_MAPPING.get(cargo_type, cargo_type)}
⚖️ Вес: {weight:.2f} т
📏 Объем: {volume:.2f} м³
🚛 Транспорт: {VEHICLE_TYPE_REVERSE_MAPPING.get(application.get('vehicle_type', 'Не указан'), application.get('vehicle_type', 'Не указан'))}

{responses_text}
💬 **Примечания:** {application.get('notes', 'Нет')}
"""

        return text.strip()


def get_logist_accepted_application_keyboard(application_id, current_index, total_count, responses):
    """Создает клавиатуру для заявки с откликами"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Навигация
    nav_buttons = []

    if current_index > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"logist_accepted_nav_prev_{current_index}"))

    nav_buttons.append(InlineKeyboardButton(f"{current_index + 1}/{total_count}", callback_data="#"))

    if current_index < total_count - 1:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"logist_accepted_nav_next_{current_index}"))

    keyboard.add(*nav_buttons)

    # Кнопки для каждого перевозчика
    if responses:
        for resp in responses:
            executor_id = resp['executor_id']
            executor_name = resp['executor_name'].split()[0] if resp['executor_name'] else "Перевозчик"
            status_icon = {
                'accepted': '✅',
                'accepted_budget': '✅',
                'counter_offer': '💰'
            }.get(resp['status'], '❓')

            keyboard.add(
                InlineKeyboardButton(
                    f"{status_icon} {executor_name}",
                    callback_data=f"select_executor_{application_id}_{executor_id}"
                )
            )

    # Кнопка отзыва заявки (если уже назначена)
    keyboard.add(
        InlineKeyboardButton(
            "🔄 Отозвать заявку у перевозчика",
            callback_data=f"unassign_application_{application_id}"
        )
    )

    # Кнопка закрыть
    keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_logist_accepted"))

    return keyboard


def get_cancel_unassign_keyboard(application_id):
    """Клавиатура для отмены отзыва заявки"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("❌ Отменить отзыв", callback_data=f"back_to_accepted_{application_id}")
    )
    return keyboard


def get_payment_type_name(payment_type):
    """Возвращает читаемое название типа оплаты"""
    names = {
        'nds': 'С НДС',
        'ip': 'Без НДС',
        'self-employed': 'Самозанятый',
        'cash': 'Наличные'
    }
    return names.get(payment_type, payment_type)


def notify_executor_about_assignment(bot, db, application_id, executor_id):
    """Уведомляет перевозчика о назначении на заявку"""
    # Получаем информацию о заявке
    application = db.fetch_one("""
        SELECT a.*, u.first_name as logist_first_name, u.last_name as logist_last_name, u.phone as logist_phone
        FROM applications a
        JOIN users u ON a.created_by = u.telegram_id
        WHERE a.id = ?
    """, (application_id,))

    if not application:
        return

    # Получаем точки маршрута
    points = db.fetch_all(
        "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
        (application_id,)
    )

    loading_points = [p for p in points if p['point_type'] == 'loading']
    unloading_points = [p for p in points if p['point_type'] == 'unloading']

    first_loading_city = loading_points[0]['city'] if loading_points else "Не указано"
    last_unloading_city = unloading_points[-1]['city'] if unloading_points else "Не указано"

    logist_name = f"{application['logist_first_name']} {application['logist_last_name']}"
    logist_phone = application.get('logist_phone', 'Не указан')

    # Форматируем даты погрузки/выгрузки из точек
    loading_dates = []
    for point in loading_points[:2]:  # Показываем первые 2 точки для краткости
        if point.get('point_datetime'):
            try:
                dt = point['point_datetime']
                if isinstance(dt, str):
                    dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                loading_dates.append(dt.strftime('%d.%m.%Y %H:%M'))
            except:
                pass

    unloading_dates = []
    for point in unloading_points[:2]:
        if point.get('point_datetime'):
            try:
                dt = point['point_datetime']
                if isinstance(dt, str):
                    dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                unloading_dates.append(dt.strftime('%d.%m.%Y %H:%M'))
            except:
                pass

    loading_date_str = ", ".join(loading_dates) if loading_dates else "Не указана"
    unloading_date_str = ", ".join(unloading_dates) if unloading_dates else "Не указана"

    message = f"""
🎉 **Поздравляем! Вас назначили на заявку!**

📦 **Заявка #{application_id}**
👤 **Логист:** {logist_name}
📞 **Телефон логиста:** {logist_phone}

💼 **Детали заявки:**
• Тип: {'СТАНДАРТНАЯ' if application['application_type'] == 'fixed' else 'ЗАПРОС СТАВОК'}
• Груз: {application.get('cargo_custom_type') or application.get('cargo_type', 'Не указан')}
• Вес: {float(application.get('weight', 0)):.2f} т
• Объем: {float(application.get('volume', 0)):.2f} м³
• Транспорт: {VEHICLE_TYPE_REVERSE_MAPPING.get(application.get('vehicle_type', 'Не указан'), application.get('vehicle_type', 'Не указан'))}

🗺️ **Маршрут:**
📍 Погрузка: {first_loading_city} ({loading_date_str})
🏁 Выгрузка: {last_unloading_city} ({unloading_date_str})

💰 **Оплата:** {float(application.get('fixed_price') or application.get('desired_budget', 0)):,.0f} руб.

Свяжитесь с логистом для уточнения деталей выполнения заявки.
"""

    try:
        bot.send_message(executor_id, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Не удалось уведомить перевозчика {executor_id}: {e}")


def notify_executor_about_rejection(bot, db, application_id, executor_id):
    """Уведомляет перевозчика об отклонении его отклика"""
    message = f"""
ℹ️ **Ваш отклик отклонен**

Ваш отклик на заявку #{application_id} был отклонен логистом.

Вы можете продолжить поиск других заявок в разделе "🔔 Новые заявки".
"""

    try:
        bot.send_message(executor_id, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Не удалось уведомить перевозчика {executor_id}: {e}")


def notify_other_executors_about_rejection(bot, db, application_id, selected_executor_id):
    """Уведомляет остальных перевозчиков об отклонении их откликов"""
    # Получаем всех перевозчиков, кроме выбранного
    other_executors = db.fetch_all("""
        SELECT DISTINCT executor_id 
        FROM application_responses 
        WHERE application_id = ? 
            AND executor_id != ? 
            AND status IN ('accepted', 'accepted_budget', 'counter_offer')
    """, (application_id, selected_executor_id))

    for executor in other_executors:
        executor_id = executor['executor_id']
        message = f"""
ℹ️ **По заявке #{application_id} выбран другой перевозчик.**

К сожалению, ваш отклик не был выбран для выполнения заявки.

Спасибо за участие! Вы можете продолжить поиск других заявок в разделе "🔔 Новые заявки".
"""

        try:
            bot.send_message(executor_id, message, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить перевозчика {executor_id}: {e}")


def notify_executor_about_unassignment(bot, db, application_id, executor_id, reason):
    """Уведомляет перевозчика об отзыве заявки"""
    message = f"""
⚠️ **Заявка отозвана логистом**

Логист отозвал заявку #{application_id} у вас.

**Причина отзыва:** {reason}

Заявка будет доступна другим перевозчикам.
"""

    try:
        bot.send_message(executor_id, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Не удалось уведомить перевозчика {executor_id}: {e}")


def notify_other_executors_about_urgent_application(bot, db, application_id, excluded_executor_id):
    """Уведомляет других перевозчиков о срочной заявке (кроме отозванного)"""
    # Получаем всех активных перевозчиков, которые подходят для этой заявки
    other_executors = db.fetch_all("""
        SELECT DISTINCT u.telegram_id as executor_id
        FROM users u
        WHERE u.telegram_id != ?
        AND u.status = 'active'
        AND u.role IN ('executor', 'external_executor')
    """, (excluded_executor_id,))

    if not other_executors:
        return

    # Получаем информацию о заявке
    application = db.fetch_one("""
        SELECT a.*, u.first_name as logist_first_name, u.last_name as logist_last_name
        FROM applications a
        JOIN users u ON a.created_by = u.telegram_id
        WHERE a.id = ?
    """, (application_id,))

    if not application:
        return

    # Получаем точки маршрута
    points = db.fetch_all(
        "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
        (application_id,)
    )

    loading_points = [p for p in points if p['point_type'] == 'loading']
    unloading_points = [p for p in points if p['point_type'] == 'unloading']

    first_loading_city = loading_points[0]['city'] if loading_points else "Не указано"
    last_unloading_city = unloading_points[-1]['city'] if unloading_points else "Не указано"

    logist_name = f"{application['logist_first_name']} {application['logist_last_name']}"

    # Форматируем сообщение о срочной заявке
    cargo_type = application.get('cargo_custom_type') or application.get('cargo_type', 'Не указан')
    weight = float(application.get('weight', 0))
    volume = float(application.get('volume', 0))

    # Форматируем даты погрузки/выгрузки из точек
    loading_dates = []
    for point in loading_points[:2]:
        if point.get('point_datetime'):
            try:
                dt = point['point_datetime']
                if isinstance(dt, str):
                    dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                loading_dates.append(dt.strftime('%d.%m.%Y %H:%M'))
            except:
                pass

    unloading_dates = []
    for point in unloading_points[:2]:
        if point.get('point_datetime'):
            try:
                dt = point['point_datetime']
                if isinstance(dt, str):
                    dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                unloading_dates.append(dt.strftime('%d.%m.%Y %H:%M'))
            except:
                pass

    loading_date_str = ", ".join(loading_dates) if loading_dates else "Не указана"
    unloading_date_str = ", ".join(unloading_dates) if unloading_dates else "Не указана"

    message = f"""
🚨 **СРОЧНАЯ ЗАЯВКА!**

📦 **Заявка #{application_id} СТАЛА СРОЧНОЙ!**

👤 **Логист:** {logist_name}

💼 **Детали заявки:**
• Тип: {'СТАНДАРТНАЯ' if application['application_type'] == 'fixed' else 'ЗАПРОС СТАВОК'}
• Груз: {cargo_type}
• Вес: {weight:.2f} т
• Объем: {volume:.2f} м³
• Транспорт: {VEHICLE_TYPE_REVERSE_MAPPING.get(application.get('vehicle_type', 'Не указан'), application.get('vehicle_type', 'Не указан'))}

🗺️ **Маршрут:**
📍 Погрузка: {first_loading_city} ({loading_date_str})
🏁 Выгрузка: {last_unloading_city} ({unloading_date_str})

💰 **Оплата:** {float(application.get('fixed_price') or application.get('desired_budget', 0)):,.0f} руб.

💬 **Примечания:** {application.get('notes', 'Нет')}

⚠️ **Заявка помечена как СРОЧНАЯ и требует быстрого реагирования!**

Перейдите в раздел "🔔 Новые заявки" для просмотра деталей и подачи отклика.
"""

    # Отправляем уведомление всем другим перевозчикам
    for executor in other_executors:
        executor_id = executor['executor_id']
        try:
            bot.send_message(executor_id, message, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить перевозчика {executor_id} о срочной заявке: {e}")


def update_executor_rating_on_assignment(db, executor_id, application_id):
    """Обновляет рейтинг перевозчика при назначении заявки"""
    # Бонус за получение заявки
    reward_data = db.fetch_one("select value from rating_rules "
                               "where rule_type = 'executor' "
                               "and rule_name = 'Назначение на заявку' "
                               "and is_active = 1")
    reward_amount = reward_data['value'] if reward_data else 5.0

    # Получаем текущий рейтинг
    current_rating = db.fetch_one(
        "SELECT current_rating FROM user_ratings WHERE user_id = ? AND rating_type = 'executor'",
        (executor_id,)
    )

    if current_rating:
        new_rating = min(100.0, current_rating['current_rating'] + reward_amount)

        # Обновляем рейтинг
        db.execute_query(
            """UPDATE user_ratings 
            SET current_rating = ?, 
                total_applications = total_applications + 1,
                updated_at = datetime('now') 
            WHERE user_id = ? AND rating_type = 'executor'""",
            (new_rating, executor_id)
        )

        # Записываем в историю
        db.execute_query(
            """INSERT INTO rating_history 
            (user_id, rating_type, old_rating, new_rating, change_amount, change_reason, change_source, application_id) 
            VALUES (?, 'executor', ?, ?, ?, ?, ?, ?)""",
            (executor_id, current_rating['current_rating'], new_rating, reward_amount,
             'Назначение на заявку', 'application_assignment', application_id)
        )