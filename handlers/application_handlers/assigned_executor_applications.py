import ast
import json
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from database.db import logger
from handlers.application_handlers.display_application_handlers import format_application_for_executor
from handlers.application_handlers.executor_application_handlers import get_cargo_info
from utils.dicts import CARGO_TYPE_REVERSE_MAPPING
from utils.email_sender import send_email_notification
from utils.helpers import notify_executor_about_completion_confirmation, \
    update_user_rating_on_rejection, update_user_rating_on_completion

user_application_data = {}


def register_assigned_executor_applications_handlers(bot, db):
    @bot.message_handler(func=lambda message: message.text == '✅ Мои принятые заявки')
    def show_my_accepted_applications(message):
        """Показывает заявки, которые перевозчик принял или на которые откликнулся"""
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

        # Получаем заявки, на которые пользователь откликнулся
        # Сортируем по дате первой погрузки
        applications = db.fetch_all("""
               SELECT DISTINCT a.*, u.first_name, u.last_name, u.phone as logist_phone, u.email, 
                      ar.status as response_status, ar.created_at as response_date,
                      ar.id as response_id,
                      ac.status as completion_status,
                      ac.completion_requested_at
               FROM applications a 
               JOIN users u ON a.created_by = u.telegram_id 
               JOIN application_responses ar ON a.id = ar.application_id 
               LEFT JOIN application_completions ac ON a.id = ac.application_id
               WHERE ar.executor_id = ? 
               AND ar.status IN ('accepted', 'accepted_budget', 'counter_offer', 'assigned')
               AND a.status NOT IN ('cancelled')
               ORDER BY 
                   CASE 
                       WHEN a.status = 'assigned' THEN 1
                       WHEN ac.status = 'pending' THEN 2
                       WHEN a.status = 'completed' THEN 3
                       ELSE 4
                   END
           """, (user_id,))

        if not applications:
            bot.send_message(chat_id, "📭 У вас пока нет принятых заявок.")
            return

        # Сохраняем заявки для этого пользователя
        if user_id not in user_application_data:
            user_application_data[user_id] = {}

        user_application_data[user_id]['applications'] = applications
        user_application_data[user_id]['current_index'] = 0
        user_application_data[user_id]['message_id'] = None
        user_application_data[user_id]['is_accepted'] = True

        # Показываем первую заявку
        show_accepted_application_page(user_id, chat_id, 0, is_new=True)

    def show_accepted_application_page(user_id, chat_id, index, is_new=False):
        """Показывает принятую заявку по указанному индексу"""
        if user_id not in user_application_data or not user_application_data[user_id].get('applications'):
            bot.send_message(chat_id, "❌ Данные о заявках устарели. Нажмите '✅ Мои принятые заявки' снова.")
            return

        applications = user_application_data[user_id]['applications']

        if index < 0 or index >= len(applications):
            return

        app = applications[index]

        # Получаем точки маршрута
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (app['id'],)
        )

        # Форматируем заявку с информацией о статусе отклика и выполнении
        application_text = format_accepted_application_for_executor(app, points)

        # Добавляем нумерацию страниц
        page_info = f"\n\n📄 Страница {index + 1} из {len(applications)}"
        full_text = application_text + page_info

        # Создаем клавиатуру с навигацией для принятых заявок
        keyboard = get_accepted_application_navigation_keyboard(
            app['id'],
            index,
            len(applications),
            app.get('assigned_to'),
            app.get('status'),
            app.get('completion_status'),
            app.get('response_id')
        )

        if is_new:
            msg = bot.send_message(
                chat_id,
                full_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            user_application_data[user_id]['message_id'] = msg.message_id
        else:
            message_id = user_application_data[user_id].get('message_id')
            if message_id:
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=full_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    msg = bot.send_message(
                        chat_id,
                        full_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                    user_application_data[user_id]['message_id'] = msg.message_id

        # Обновляем текущий индекс
        user_application_data[user_id]['current_index'] = index

    def format_accepted_application_for_executor(app, points):
        """Форматирует заявку для отображения перевозчику (для принятых заявок)"""
        # Базовое форматирование заявки
        creator_info = db.fetch_one('select * from users where telegram_id = ?', (app['created_by'],))
        company_info = db.fetch_one('select * from companies where id = ?', (creator_info['company_id'],))

        # Форматируем заявку
        application_text = format_application_for_executor(app, points, creator_info, company_info)

        # Получаем статус выполнения
        completion_status = get_completion_status_info(
            app.get('status'),
            app.get('completion_status'),
            app.get('assigned_to'),
            app['created_by']
        )

        # Добавляем информацию о статусе отклика
        status_info = get_response_status_info(app.get('response_status', ''), app.get('assigned_to'),
                                               app['created_by'])
        response_date = app.get('response_date')

        if response_date:
            try:
                if isinstance(response_date, str):
                    response_date = datetime.strptime(response_date, '%Y-%m-%d %H:%M:%S')
                formatted_date = response_date.strftime('%d.%m.%Y %H:%M')
                date_info = f"\n📅 **Дата отклика:** {formatted_date}"
            except:
                date_info = ""
        else:
            date_info = ""

        # Добавляем информацию о запросе подтверждения
        completion_request_info = ""
        if app.get('completion_status') == 'pending':
            completion_requested_at = app.get('completion_requested_at')
            if completion_requested_at:
                try:
                    if isinstance(completion_requested_at, str):
                        completion_requested_at = datetime.strptime(completion_requested_at, '%Y-%m-%d %H:%M:%S')
                    formatted_date = completion_requested_at.strftime('%d.%m.%Y %H:%M')
                    completion_request_info = f"\n⏳ **Запрос отправлен:** {formatted_date}"
                except:
                    pass

        # Добавляем статус в начало текста
        status_text = f"**Статус заявки:** {completion_status}\n"
        status_text += f"**Статус вашего отклика:** {status_info}{date_info}{completion_request_info}\n\n"

        return status_text + application_text

    def get_completion_status_info(status, completion_status, assigned_to, created_by):
        """Возвращает читаемое описание статуса выполнения"""
        if status == 'completed':
            if completion_status == 'confirmed':
                return "✅ **Выполнена и подтверждена**"
            elif completion_status == 'rejected':
                return "❌ **Выполнение отклонено логистом**"
            else:
                return "✅ **Выполнена**"
        elif status == 'assigned':
            if completion_status == 'pending':
                return "⏳ **Ожидает подтверждения логиста**"
            else:
                return "🚚 **Активная (в работе)**"
        else:
            status_map = {
                'active': "🔍 **Активная (ожидает назначения)**",
                'pending': "⏳ **В обработке**",
                'cancelled': "❌ **Отменена**"
            }
            return status_map.get(status, status)

    def get_response_status_info(status, assigned_to=None, created_by=None):
        """Возвращает читаемое описание статуса отклика"""
        if assigned_to:
            status_map = {
                'assigned': '✅ Заявка назначена вам',
                'accepted': '✅ Заявка назначена вам',
                'accepted_budget': '💰 Заявка назначена вам по бюджету'
            }
        else:
            status_map = {
                'accepted': '⏳ Ожидает решения логиста',
                'accepted_budget': '💰 Принято по бюджету (ожидает решения)',
                'counter_offer': '💵 Встречное предложение отправлено',
                'rejected': '❌ Отклонено'
            }
        return status_map.get(status, status)

    def get_accepted_application_navigation_keyboard(application_id, current_index, total_count, assigned_to, status,
                                                     completion_status, response_id):
        """Создает клавиатуру с навигацией по принятым заявкам"""
        keyboard = InlineKeyboardMarkup(row_width=3)

        # Кнопки навигации
        nav_buttons = []

        if current_index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"accepted_nav_prev_{current_index}"))

        nav_buttons.append(
            InlineKeyboardButton("📋 ДЕТАЛИ", callback_data=f"view_accepted_application_{application_id}"))

        if current_index < total_count - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"accepted_nav_next_{current_index}"))

        keyboard.add(*nav_buttons)

        # Кнопки действий в зависимости от статуса
        if status == 'assigned' and assigned_to:
            if completion_status == 'pending':
                # Ожидает подтверждения логиста
                keyboard.add(
                    InlineKeyboardButton(
                        "⏳ Ожидает подтверждения",
                        callback_data=f"#"
                    )
                )
            else:
                # Активная заявка - показываем кнопки отказа и завершения
                row_actions = [
                    InlineKeyboardButton("❌ Отказаться", callback_data=f"reject_accepted_application_{application_id}"),
                    InlineKeyboardButton("✅ Завершить",
                                         callback_data=f"complete_application_{application_id}_{response_id}")
                ]
                keyboard.add(*row_actions)
        elif status == 'completed':
            # Заявка выполнена
            if completion_status == 'confirmed':
                keyboard.add(
                    InlineKeyboardButton(
                        "✅ Подтверждена логистом",
                        callback_data=f"#"
                    )
                )
            elif completion_status == 'rejected':
                keyboard.add(
                    InlineKeyboardButton(
                        "❌ Отклонена логистом",
                        callback_data=f"#"
                    )
                )
            else:
                keyboard.add(
                    InlineKeyboardButton(
                        "✅ Выполнена",
                        callback_data=f"#"
                    )
                )

        # Кнопка закрыть
        keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_accepted_applications"))

        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data.startswith('accepted_nav_'))
    def handle_accepted_navigation(call):
        """Обработка навигации по принятым заявкам"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        direction = data_parts[2]  # prev или next
        current_index = int(data_parts[3])

        if user_id not in user_application_data:
            bot.answer_callback_query(call.id, "❌ Сессия просмотра истекла")
            return

        applications = user_application_data[user_id].get('applications', [])

        if not applications:
            bot.answer_callback_query(call.id, "❌ Нет доступных заявок")
            return

        # Определяем новый индекс
        if direction == 'prev':
            new_index = current_index - 1
        else:  # next
            new_index = current_index + 1

        # Проверяем границы
        if new_index < 0 or new_index >= len(applications):
            bot.answer_callback_query(call.id)
            return

        # Показываем новую страницу
        show_accepted_application_page(user_id, chat_id, new_index, is_new=False)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('complete_application_'))
    def handle_complete_application(call):
        """Обработка нажатия кнопки 'Завершить'"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        application_id = int(data_parts[2])
        response_id = int(data_parts[3]) if len(data_parts) > 3 else None

        # Проверяем, назначена ли заявка этому перевозчику
        application = db.fetch_one(
            "SELECT created_by, assigned_to, status FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        if application['assigned_to'] != user_id:
            bot.answer_callback_query(call.id, "❌ Заявка не назначена вам")
            return

        if application['status'] != 'assigned':
            bot.answer_callback_query(call.id, "❌ Заявка уже не активна")
            return

        # Проверяем, не отправлен ли уже запрос на подтверждение
        existing_completion = db.fetch_one(
            "SELECT * FROM application_completions WHERE application_id = ? AND status = 'pending'",
            (application_id,)
        )

        if existing_completion:
            bot.answer_callback_query(call.id, "❌ Запрос на подтверждение уже отправлен")
            return

        # Запрашиваем подтверждение завершения
        bot.send_message(
            chat_id,
            "✅ **Подтверждение выполнения заявки**\n\n"
            f"Вы собираетесь отметить заявку #{application_id} как выполненную.\n"
            "После подтверждения логист получит уведомление и должен будет подтвердить выполнение.\n\n"
            "Укажите комментарий к выполнению (опционально):",
            reply_markup=get_cancel_completion_keyboard(application_id, response_id)
        )

        # Сохраняем состояние
        if user_id not in user_application_data:
            user_application_data[user_id] = {}

        user_application_data[user_id]['waiting_for_completion_comment'] = True
        user_application_data[user_id]['completion_application_id'] = application_id
        user_application_data[user_id]['completion_response_id'] = response_id

        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message:
    message.from_user.id in user_application_data and
    user_application_data[message.from_user.id].get('waiting_for_completion_comment'))
    def handle_completion_comment(message):
        """Обработка комментария к выполнению заявки"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        if user_id not in user_application_data:
            return

        application_id = user_application_data[user_id].get('completion_application_id')
        response_id = user_application_data[user_id].get('completion_response_id')
        comment = message.text if message.text.strip() else "Комментарий не указан"

        # Получаем информацию о заявке
        application = db.fetch_one(
            "SELECT created_by, assigned_to, status FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application:
            bot.send_message(chat_id, "❌ Заявка не найдена")
            return

        # Проверяем, что заявка все еще назначена этому перевозчику
        if application['assigned_to'] != user_id:
            bot.send_message(chat_id, "❌ Заявка больше не назначена вам")
            return

        # Получаем текущую дату и время в правильном формате
        from datetime import datetime
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Создаем запись о запросе подтверждения выполнения
        db.execute_query(
            """INSERT INTO application_completions 
            (application_id, executor_id, logist_id, status, executor_comment, completion_requested_at) 
            VALUES (?, ?, ?, 'pending', ?, ?)""",
            (application_id, user_id, application['created_by'], comment, current_datetime)
        )

        # Обновляем статус заявки (добавляем поле completion_status)
        db.execute_query(
            "UPDATE applications SET completion_status = 'pending' WHERE id = ?",
            (application_id,)
        )

        # Уведомляем логиста
        notify_logist_about_completion_request(bot, db, application_id, user_id, comment)

        # Обновляем список заявок перевозчика
        update_executor_applications_list(user_id)

        # Сбрасываем состояние
        user_application_data[user_id]['waiting_for_completion_comment'] = False
        del user_application_data[user_id]['completion_application_id']
        del user_application_data[user_id]['completion_response_id']

        # Удаляем предыдущие сообщения
        try:
            bot.delete_message(chat_id, message.message_id - 1)
        except:
            pass

        bot.send_message(
            chat_id,
            "✅ **Запрос на подтверждение выполнения отправлен!**\n\n"
            f"Логист получил уведомление о выполнении заявки #{application_id}.\n"
            "Ожидайте подтверждения.\n\n"
            f"**Ваш комментарий:** {comment}",
            parse_mode='Markdown'
        )

        # Обновляем текущую страницу с заявкой
        if user_id in user_application_data and 'applications' in user_application_data[user_id]:
            current_index = user_application_data[user_id].get('current_index', 0)
            show_accepted_application_page(user_id, chat_id, current_index, is_new=True)

    def notify_logist_about_completion_request(bot, db, application_id, executor_id, comment):
        """Уведомляет логиста о запросе подтверждения выполнения"""
        # Получаем информацию о заявке и перевозчике
        application_info = db.fetch_one("""
                SELECT a.*, u.first_name as executor_first_name, u.last_name as executor_last_name,
                       u.phone as executor_phone, c.name as company_name
                FROM applications a
                JOIN users u ON a.assigned_to = u.telegram_id
                LEFT JOIN companies c ON u.company_id = c.id
                WHERE a.id = ?
            """, (application_id,))

        # Получаем точки маршрута для отображения первого и последнего города
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (application_id,)
        )
        loading_points = [p for p in points if p['point_type'] == 'loading']
        unloading_points = [p for p in points if p['point_type'] == 'unloading']

        first_loading_city = loading_points[0]['city'] if loading_points and 'city' in loading_points[
            0] else "Не указано"
        last_unloading_city = unloading_points[-1]['city'] if unloading_points and 'city' in unloading_points[
            -1] else "Не указано"

        if not application_info:
            return

        logist_id = application_info['created_by']
        executor_name = f"{application_info['executor_first_name']} {application_info['executor_last_name']}"
        executor_phone = application_info.get('executor_phone', 'Не указан')
        company_name = application_info.get('company_name', 'Не указана')

        # Формируем текст сообщения
        message_text = f"""
    ✅ **Запрос на подтверждение выполнения заявки**

    Перевозчик отметил заявку #{application_id} как выполненную.

    👤 **Перевозчик:** {executor_name}
    🏢 **Компания:** {company_name}
    📞 **Телефон:** {executor_phone}

    💬 **Комментарий перевозчика:**
    {comment}

    📋 **Детали заявки:**
    • Груз: {CARGO_TYPE_REVERSE_MAPPING.get(application_info.get('cargo_type', 'Не указан'), application_info.get('cargo_custom_type'))}
    • Вес: {float(application_info.get('weight', 0)):.2f} т
    • Объем: {float(application_info.get('volume', 0)):.2f} м³
    • Маршрут: {first_loading_city} → {last_unloading_city}

    Пожалуйста, проверьте выполнение заявки и подтвердите его.
    """

        # Создаем клавиатуру для логиста
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("✅ Подтвердить выполнение",
                                 callback_data=f"logist_confirm_completion_{application_id}"),
            InlineKeyboardButton("❌ Отклонить выполнение", callback_data=f"logist_reject_completion_{application_id}")
        )

        try:
            bot.send_message(logist_id, message_text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить логиста {logist_id}: {e}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('logist_confirm_completion_'))
    def handle_logist_confirm_completion(call):
        """Логист подтверждает выполнение заявки"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        application_id = int(call.data.split('_')[3])

        # Проверяем, что пользователь - логист этой заявки
        application = db.fetch_one(
            "SELECT created_by, assigned_to FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application or application['created_by'] != user_id:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для подтверждения этой заявки")
            return

        # Получаем информацию о запросе подтверждения
        completion_request = db.fetch_one(
            "SELECT * FROM application_completions WHERE application_id = ? AND status = 'pending'",
            (application_id,)
        )

        if not completion_request:
            bot.answer_callback_query(call.id, "❌ Запрос на подтверждение не найден")
            return

        from datetime import datetime
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Обновляем статус подтверждения
        db.execute_query(
            """UPDATE application_completions 
            SET status = 'confirmed', 
                completion_confirmed_at = ?,
                logist_id = ?
            WHERE application_id = ?""",
            (current_datetime, user_id, application_id)
        )

        # Обновляем статус заявки
        db.execute_query(
            """UPDATE applications 
            SET status = 'completed', 
                completion_status = 'confirmed',
                completion_confirmed_at = ?
            WHERE id = ?""",
            (current_datetime, application_id)
        )

        # Получаем информацию об перевозчике
        executor_id = completion_request['executor_id']

        # Обновляем рейтинг перевозчика (бонус за успешное выполнение)
        bonus_data = db.fetch_one("select value from rating_rules "
                                  "where rule_type = 'executor'"
                                  "and rule_name = 'Завершение заявки'"
                                  "and is_active = 1")
        bonus_amount = bonus_data['value'] if bonus_data else 5.0
        update_user_rating_on_completion(db, executor_id, application_id, bonus_amount, "Завершение заявки", 'executor')
        bonus_data = db.fetch_one("select value from rating_rules "
                                  "where rule_type = 'logist'"
                                  "and rule_name = 'Завершение заявки'"
                                  "and is_active = 1")
        bonus_amount = bonus_data['value'] if bonus_data else 5.0
        update_user_rating_on_completion(db, application['created_by'], application_id, bonus_amount,
                                         "Завершение заявки", 'logist')

        application = db.fetch_one('select * from applications where id = ?', (application_id,))
        payment_deadline = ''
        if application['payment_deadline']:
            payment_deadline = application['payment_deadline'].strftime('%d.%m.%Y') if not isinstance(
                application['payment_deadline'], str) else application['payment_deadline']

        # Уведомляем перевозчика
        notify_executor_about_completion_confirmation(bot, db, application_id, executor_id, payment_deadline)

        payment_data = db.fetch_one("""
                SELECT payment_options 
                FROM application_responses 
                WHERE application_id = ? AND executor_id = ?
            """, (application_id, executor_id))

        # Формируем информацию об оплате
        payment_info = "Не указана"

        if payment_data and payment_data.get('payment_options'):
            try:
                payment_options = payment_data['payment_options']
                if payment_options:
                    # Парсим JSON строку с выбранными способами оплаты
                    if isinstance(payment_options, str):
                        payments = json.loads(payment_options)
                    else:
                        payments = payment_options

                    if payments:
                        # Создаем читаемое представление способов оплаты
                        payment_methods = {
                            'cash': 'Наличные',
                            'nds': 'С НДС',
                            'ip': 'ИП'
                        }

                        payment_details = []
                        total_amount = 0

                        for method, amount in payments.items():
                            if method in payment_methods and amount:
                                amount_float = float(amount)
                                total_amount += amount_float
                                payment_details.append(f"  • {payment_methods[method]}: {amount_float:,.0f} руб.")

                        if payment_details:
                            if len(payment_details) == 1:
                                # Если выбран только один способ оплаты
                                payment_info = f"{payment_details[0].replace('  • ', '')}"
                            else:
                                # Если выбрано несколько способов оплаты
                                payment_info = "\n".join(payment_details)
                                payment_info += f"\n\n💰 **Итого:** {total_amount:,.0f} руб."
            except (json.JSONDecodeError, ValueError, AttributeError) as e:
                print(f"Ошибка при обработке payment_options: {e}")
                # В случае ошибки используем старый метод
                payment_info = f"{float(application.get('fixed_price') or application.get('desired_budget', 0)):,.0f} руб."

        # Редактируем сообщение логиста
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="✅ **Выполнение заявки подтверждено!**\n\n"
                 f"Заявка #{application_id} успешно подтверждена.\n"
                 f"Перевозчик получил уведомление.\n"
                 f"Необходимо произвести оплату в {payment_info}\n До 🗓 {payment_deadline}",
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "✅ Выполнение подтверждено")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('logist_reject_completion_'))
    def handle_logist_reject_completion(call):
        """Логист отклоняет выполнение заявки"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        application_id = int(call.data.split('_')[3])

        # Получаем информацию о заявке
        application = db.fetch_one(
            "SELECT created_by, assigned_to FROM applications WHERE id = ?",
            (application_id,)
        )

        # Получаем ID отклика
        response = db.fetch_one(
            "SELECT id FROM application_responses WHERE application_id = ? AND executor_id = ?",
            (application_id, application['assigned_to'])
        )

        # Запрашиваем причину отклонения
        bot.send_message(
            chat_id,
            "❌ **Укажите причину отклонения выполнения:**\n\n"
            "Пожалуйста, подробно опишите, почему вы не можете подтвердить выполнение заявки.",
            reply_markup=get_cancel_rejection_keyboard(application_id, response['id'])
        )

        # Сохраняем состояние
        if user_id not in user_application_data:
            user_application_data[user_id] = {}

        user_application_data[user_id]['waiting_for_rejection_reason'] = True
        user_application_data[user_id]['rejection_application_id'] = application_id

        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message:
    message.from_user.id in user_application_data and
    user_application_data[message.from_user.id].get('waiting_for_rejection_reason'))
    def handle_completion_rejection_reason(message):
        """Обработка причины отказа от заявки"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        if user_id not in user_application_data:
            return

        application_id = user_application_data[user_id].get('rejection_application_id')
        response_id = user_application_data[user_id].get('rejection_response_id')
        reason = message.text if message.text.strip() else "Причина не указана"

        # Получаем информацию о заявке
        application = db.fetch_one(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application:
            bot.send_message(chat_id, "❌ Заявка не найдена")
            return

        # Получаем информацию о перевозчике
        executor_id = application['assigned_to']

        # Обновляем статус заявки на urgent (срочная) вместо active
        db.execute_query(
            "UPDATE applications SET assigned_to = NULL, status = 'urgent' WHERE id = ?",
            (application_id,)
        )

        # Обновляем статус отклика
        db.execute_query(
            """UPDATE application_responses 
            SET status = 'rejected_by_executor',
                updated_at = datetime('now')
            WHERE id = ?""",
            (response_id,)
        )

        # Понижаем рейтинг перевозчика за отказ от назначенной заявки
        penalty_data = db.fetch_one("select value from rating_rules "
                                    "where rule_type = 'executor' "
                                    "and rule_name = 'Отклонение заявки' "
                                    "and is_active = 1")
        penalty_amount = penalty_data['value'] if penalty_data else -5.0
        update_user_rating_on_rejection(db, executor_id, application_id, penalty_amount, "Отклонение заявки", reason,
                                        'executor')

        executor_info = db.get_user_by_telegram_id(executor_id)
        admins = db.get_all_admins()

        email_subject = f"Заявка Номер:{application_id} отменена перевозчиком"
        email_message = f"""
        Заявка #{application_id} была отменена перевозчиком после принятия.

        Детали заявки:
            ID заявки: #{application_id}
            Тип заявки: {'СТАНДАРТНАЯ' if application['application_type'] == 'fixed' else 'ЗАПРОС СТАВОК'}
            Статус: Отменена перевозчиком

        Перевозчик:
            Имя: {executor_info['first_name']} {executor_info.get('last_name', '')}
            Телефон: {executor_info.get('phone', 'Не указан')}
            Telegram ID: {executor_id}

        Время отмены: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

        Заявка возвращена в активные и может быть переназначена другому перевозчику.
                    """

        for admin in admins:
            admin_email = admin.get('email')
            if not admin_email or not isinstance(admin_email, str) or not admin_email.strip():
                print(f"Пропускаем администратора с некорректным email: {admin}")
                continue

            try:
                send_email_notification(email_subject, email_message.strip(), admin_email)
                print(f"Email отправлен администратору: {admin_email}")
            except Exception as e:
                print(f"Ошибка при отправке email администратору {admin_email}: {e}")
                continue

        print(f"Отправка email администраторам завершена. Обработано: {len(admins)} записей")

        # Уведомляем логиста об отказе и изменении статуса
        try:
            bot.send_message(
                application['created_by'],
                f"⚠️ **Перевозчик отказался от заявки #{application_id}**\n\n"
                f"Перевозчик отказался от выполнения назначенной ему заявки.\n\n"
                f"**Причина отказа:** {reason}\n\n"
                f"✅ Заявка переведена в статус **СРОЧНАЯ** и будет отправлена всем активным перевозчикам.",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Не удалось уведомить логиста: {e}")

        # Отправляем уведомление всем перевозчикам кроме отказавшегося
        notify_all_executors_about_urgent_application(bot, db, application_id, executor_id)

        # Удаляем заявку из списка принятых заявок перевозчика
        if executor_id in user_application_data and 'applications' in user_application_data[executor_id]:
            user_application_data[executor_id]['applications'] = [
                app for app in user_application_data[executor_id]['applications']
                if app['id'] != application_id
            ]

        # Сбрасываем состояние
        user_application_data[user_id]['waiting_for_rejection_reason'] = False
        del user_application_data[user_id]['rejection_application_id']
        del user_application_data[user_id]['rejection_response_id']

        # Удаляем предыдущие сообщения
        try:
            bot.delete_message(chat_id, message.message_id - 1)
        except:
            pass

        bot.send_message(
            chat_id,
            f"❌ **Вы отклонили выполнение заявки #{application_id}!**\n\n"
            f"✅ Заявка переведена в статус **СРОЧНАЯ** и отправлена всем перевозчикам.\n\n"
            f"**Причина отказа:** {reason}",
            parse_mode='Markdown'
        )

    def notify_all_executors_about_urgent_application(bot, db, application_id, excluded_executor_id):
        """
        Уведомляет всех активных перевозчиков о срочной заявке
        (кроме перевозчика, который отказался от заявки)
        """
        # Получаем полную информацию о заявке
        application = db.fetch_one("""
                SELECT a.*, u.first_name, u.last_name, u.phone, c.name as company_name
                FROM applications a
                JOIN users u ON a.created_by = u.telegram_id
                LEFT JOIN companies c ON u.company_id = c.id
                WHERE a.id = ?
            """, (application_id,))

        if not application:
            print(f"Заявка #{application_id} не найдена")
            return

        # Получаем точки маршрута
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (application_id,)
        )

        # Форматируем заявку для уведомления
        creator_info = db.fetch_one('select * from users where telegram_id = ?', (application['created_by'],))
        company_info = db.fetch_one('select * from companies where id = ?', (creator_info['company_id'],))
        application_text = format_application_for_executor(application, points, creator_info, company_info)

        # Получаем всех активных перевозчиков (кроме исключенного)
        executors = db.fetch_all("""
                SELECT telegram_id FROM users 
                WHERE role = 'executor' 
                and status = 'active'
                AND telegram_id != ?
            """, (excluded_executor_id,))

        # Добавляем специальную пометку о срочности
        urgent_notification = "🚨 **СРОЧНАЯ ЗАЯВКА** 🚨\n\n"

        full_message = urgent_notification + application_text

        # Отправляем уведомление каждому перевозчику
        notified_count = 0
        for executor in executors:
            executor_id = executor['telegram_id']
            try:
                bot.send_message(
                    executor_id,
                    full_message,
                    parse_mode='Markdown'
                )
                notified_count += 1
            except Exception as e:
                print(f"Не удалось отправить уведомление перевозчику {executor_id}: {e}")

        print(
            f"Отправлено уведомлений о срочной заявке #{application_id}: {notified_count} из {len(executors)} перевозчиков")

    def notify_logist_about_completion_rejection(bot, db, application_id, logist_id, reason):
        """Уведомляет перевозчика об отклонении выполнения"""
        # Получаем информацию о логисте
        application = db.fetch_one("""
            SELECT a.*, u.first_name as executor_first_name, u.last_name as executor_last_name, u.ati_code
            FROM applications a
            JOIN users u ON a.assigned_to = u.telegram_id
            WHERE a.id = ?
        """, (application_id,))

        if not application:
            return

        logist_name = f"{application['executor_first_name']} {application['executor_last_name']}"

        message = f"""
⚠️ **Выполнение заявки отклонено**

Перевозчик отклонил выполнение заявки #{application_id}.

👤 **Логист:** {logist_name}
    **АТИ:** {application['ati_code']}

❌ **Причина отклонения:**
{reason}

"""

        try:
            bot.send_message(logist_id, message, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить перевозчика {logist_id}: {e}")

    def update_executor_applications_list(user_id):
        """Обновляет список заявок перевозчика"""
        if user_id in user_application_data:
            # Обновляем список заявок
            applications = db.fetch_all("""
                   SELECT DISTINCT a.*, u.first_name, u.last_name, u.phone as logist_phone, u.email, 
                          ar.status as response_status, ar.created_at as response_date,
                          ar.id as response_id,
                          ac.status as completion_status,
                          ac.completion_requested_at
                   FROM applications a 
                   JOIN users u ON a.created_by = u.telegram_id 
                   JOIN application_responses ar ON a.id = ar.application_id 
                   LEFT JOIN application_completions ac ON a.id = ac.application_id
                   WHERE ar.executor_id = ? 
                   AND ar.status IN ('accepted', 'accepted_budget', 'counter_offer', 'assigned')
                   AND a.status NOT IN ('cancelled')
                   ORDER BY 
                       CASE 
                           WHEN a.status = 'assigned' THEN 1
                           WHEN ac.status = 'pending' THEN 2
                           WHEN a.status = 'completed' THEN 3
                           ELSE 4
                       END
               """, (user_id,))

            user_application_data[user_id]['applications'] = applications

    def get_cancel_completion_keyboard(application_id, response_id):
        """Клавиатура для отмены запроса на завершение"""
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("❌ Отменить", callback_data=f"back_to_accepted_list")
        )
        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data == 'close_accepted_applications')
    def handle_close_accepted_applications(call):
        """Закрывает просмотр принятых заявок"""
        user_id = call.from_user.id

        # Удаляем сообщение с заявками
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Очищаем данные пользователя
        if user_id in user_application_data:
            del user_application_data[user_id]

        bot.answer_callback_query(call.id, "✅ Просмотр принятых заявок завершен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('view_accepted_application_'))
    def handle_view_accepted_application(call):
        """Обработка нажатия кнопки 'ДЕТАЛИ' для принятой заявки"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[3])

        # Получаем полную информацию о заявке
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        payment_options_response = db.fetch_one("""
               SELECT payment_options 
               FROM application_responses 
               WHERE application_id = ? AND executor_id = ?
               ORDER BY created_at DESC 
               LIMIT 1
           """, (application_id, user_id))

        payment_options_data = None
        if payment_options_response and payment_options_response.get('payment_options'):
            payment_options_data = payment_options_response['payment_options']

        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        application['payment_options'] = db.fetch_one('select payment_options from application_responses where id = ?', (application_id,))

        # Получаем статус отклика перевозчика
        response = db.fetch_one(
            "SELECT status, created_at, id as response_id FROM application_responses WHERE application_id = ? AND executor_id = ?",
            (application_id, user_id)
        )

        # Получаем точки маршрута
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (application_id,)
        )

        # Разделяем точки на погрузку и выгрузку
        loading_points = [p for p in points if p['point_type'] == 'loading']
        unloading_points = [p for p in points if p['point_type'] == 'unloading']

        # Формируем ссылку для Яндекс.Карт
        map_url = None
        if loading_points and unloading_points:
            # Берем координаты первой точки погрузки и последней точки выгрузки
            loading_coords = None
            unloading_coords = None

            for point in loading_points:
                if point.get('coordinates'):
                    try:
                        coords = json.loads(point['coordinates'])
                        loading_coords = coords
                        break
                    except:
                        continue

            for point in reversed(unloading_points):  # Берем последнюю точку выгрузки
                if point.get('coordinates'):
                    try:
                        coords = json.loads(point['coordinates'])
                        unloading_coords = coords
                        break
                    except:
                        continue

            if loading_coords and unloading_coords:
                rtext = f"{loading_coords['lat']},{loading_coords['lon']}~{unloading_coords['lat']},{unloading_coords['lon']}"
                map_url = f"https://yandex.ru/maps/?rtext={rtext}&rtt=auto"
            elif loading_coords:
                map_url = f"https://yandex.ru/maps/?ll={loading_coords['lon']},{loading_coords['lat']}&z=12"

        # Получаем информацию о грузе
        cargo_info = get_cargo_info(application)

        # Получаем контактные данные логиста
        logist_info = db.fetch_one(
            "SELECT phone, email FROM users WHERE telegram_id = ?",
            (application['created_by'],)
        )

        # Форматируем детальную информацию о заявке
        detailed_text = format_detailed_application(
            application, loading_points, unloading_points, cargo_info, logist_info, payment_options_data
        )

        # Добавляем информацию о статусе отклика
        if response:
            status_info = get_response_status_info(response['status'], application.get('assigned_to'),
                                                   application['created_by'])
            response_date = response.get('created_at')

            if response_date:
                try:
                    if isinstance(response_date, str):
                        response_date = datetime.strptime(response_date, '%Y-%m-%d %H:%M:%S')
                    formatted_date = response_date.strftime('%d.%m.%Y %H:%M')
                    status_text = f"\n\n📊 **Статус вашего отклика:** {status_info}\n📅 **Дата отклика:** {formatted_date}"
                except:
                    status_text = f"\n\n📊 **Статус вашего отклика:** {status_info}"
            else:
                status_text = f"\n\n📊 **Статус вашего отклика:** {status_info}"
        else:
            status_text = "\n\n📊 **Статус вашего отклика:** Неизвестен"

        detailed_text = detailed_text + status_text

        # Создаем клавиатуру для просмотра деталей принятой заявки
        keyboard = get_accepted_application_details_keyboard(
            application_id,
            map_url,
            logist_info.get('phone') if logist_info else None,
            application.get('assigned_to'),
            response.get('response_id') if response else None
        )

        # Редактируем сообщение с заявкой
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=detailed_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "📋 Подробная информация о заявке")

    def get_accepted_application_details_keyboard(application_id, map_url=None, logist_phone=None, assigned_to=None,
                                                  response_id=None):
        """Создает клавиатуру для детального просмотра принятой заявки"""
        keyboard = InlineKeyboardMarkup(row_width=2)

        # Первый ряд: основные действия
        row1 = []
        if map_url:
            row1.append(InlineKeyboardButton("🗺️ Построить маршрут", url=map_url))
        if logist_phone:
            row1.append(InlineKeyboardButton("📞 ПОЗВОНИТЬ", callback_data=f"call_logist_{application_id}"))

        if row1:
            keyboard.add(*row1)

        # Кнопка отказа от заявки (если заявка назначена)
        if assigned_to:
            keyboard.add(InlineKeyboardButton(
                "❌ Отказаться от заявки",
                callback_data=f"reject_accepted_details_{application_id}_{response_id}"
            ))

        # Кнопка назад к списку
        keyboard.add(InlineKeyboardButton("↩️ Назад к списку", callback_data="back_to_accepted_list"))

        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reject_accepted_application_'))
    def handle_reject_accepted_application(call):
        """Обработка нажатия кнопки 'Отказаться от заявки' из списка"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[3])

        # Проверяем, назначена ли заявка этому перевозчику
        application = db.fetch_one(
            "SELECT assigned_to FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application or application['assigned_to'] != user_id:
            bot.answer_callback_query(call.id, "❌ Заявка не назначена вам")
            return

        # Получаем ID отклика
        response = db.fetch_one(
            "SELECT id FROM application_responses WHERE application_id = ? AND executor_id = ?",
            (application_id, user_id)
        )

        if not response:
            bot.answer_callback_query(call.id, "❌ Отклик не найден")
            return

        # Запрашиваем подтверждение с предупреждением о штрафе
        bot.send_message(
            call.message.chat.id,
            "⚠️ **ВНИМАНИЕ: Отказ от принятой заявки!**\n\n"
            f"Вы собираетесь отказаться от заявки #{application_id}.\n"
            "Укажите причину отказа:",
            reply_markup=get_cancel_rejection_keyboard(application_id, response['id'])
        )

        # Сохраняем состояние
        if user_id not in user_application_data:
            user_application_data[user_id] = {}

        user_application_data[user_id]['waiting_for_rejection_reason'] = True
        user_application_data[user_id]['rejection_application_id'] = application_id
        user_application_data[user_id]['rejection_response_id'] = response['id']

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reject_accepted_details_'))
    def handle_reject_accepted_details(call):
        """Обработка нажатия кнопки 'Отказаться от заявки' из деталей"""
        user_id = call.from_user.id
        data_parts = call.data.split('_')
        application_id = int(data_parts[3])
        response_id = int(data_parts[4]) if len(data_parts) > 4 else None

        # Проверяем, назначена ли заявка этому перевозчику
        application = db.fetch_one(
            "SELECT assigned_to FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application or application['assigned_to'] != user_id:
            bot.answer_callback_query(call.id, "❌ Заявка не назначена вам")
            return

        # Если response_id не передан, получаем его
        if not response_id:
            response = db.fetch_one(
                "SELECT id FROM application_responses WHERE application_id = ? AND executor_id = ?",
                (application_id, user_id)
            )
            if response:
                response_id = response['id']

        # Запрашиваем подтверждение с предупреждением о штрафе
        bot.send_message(
            call.message.chat.id,
            "⚠️ **ВНИМАНИЕ: Отказ от принятой заявки!**\n\n"
            f"Вы собираетесь отказаться от заявки #{application_id}.\n"
            "Укажите причину отказа:",
            reply_markup=get_cancel_rejection_keyboard(application_id, response_id)
        )

        # Сохраняем состояние
        if user_id not in user_application_data:
            user_application_data[user_id] = {}

        user_application_data[user_id]['waiting_for_rejection_reason'] = True
        user_application_data[user_id]['rejection_application_id'] = application_id
        user_application_data[user_id]['rejection_response_id'] = response_id

        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message:
    message.from_user.id in user_application_data and
    user_application_data[message.from_user.id].get('waiting_for_rejection_reason'))
    def handle_rejection_reason(message):
        """Обработка причины отказа от заявки"""
        user_id = message.from_user.id

        if user_id not in user_application_data:
            return

        application_id = user_application_data[user_id].get('rejection_application_id')
        response_id = user_application_data[user_id].get('rejection_response_id')
        reason = message.text if message.text.strip() else "Причина не указана"

        # Получаем информацию о заявке
        application = db.fetch_one(
            "SELECT created_by, assigned_to FROM applications WHERE id = ?",
            (application_id,)
        )

        if not application:
            bot.send_message(message.chat.id, "❌ Заявка не найдена")
            return

        # Проверяем, что заявка все еще назначена этому перевозчику
        if application['assigned_to'] != user_id:
            bot.send_message(message.chat.id, "❌ Заявка больше не назначена вам")
            return

        # Обновляем статус заявки
        db.execute_query(
            "UPDATE applications SET assigned_to = NULL, status = 'active' WHERE id = ?",
            (application_id,)
        )

        # Обновляем статус отклика
        db.execute_query(
            """UPDATE application_responses 
            SET status = 'rejected_by_executor' 
            WHERE id = ?""",
            (response_id,)
        )

        # Понижаем рейтинг перевозчика за отказ от назначенной заявки
        penalty_data = db.fetch_one("select value from rating_rules "
                                    "where rule_type = 'executor'"
                                    "and rule_name = 'Отклонение заявки'"
                                    "and is_active = 1")
        penalty_amount = penalty_data['value'] if penalty_data else -5.0
        update_user_rating_on_rejection(db, user_id, application_id, penalty_amount, "Отклонение заявки", reason,
                                        'executor')

        # Получаем текущий рейтинг
        current_rating = db.fetch_one(
            "SELECT current_rating FROM user_ratings WHERE user_id = ? AND rating_type = 'executor'",
            (user_id,)
        )

        if current_rating:
            new_rating = max(0, current_rating['current_rating'] + penalty_amount)

            # Обновляем рейтинг
            db.execute_query(
                """UPDATE user_ratings 
                SET current_rating = ?, 
                    updated_at = datetime('now') 
                WHERE user_id = ? AND rating_type = 'executor'""",
                (new_rating, user_id)
            )

            # Записываем в историю
            db.execute_query(
                """INSERT INTO rating_history 
                (user_id, rating_type, old_rating, new_rating, change_reason, change_source, application_id, response_id) 
                VALUES (?, 'executor', ?, ?, ?, ?, ?, ?)""",
                (user_id, current_rating['current_rating'], new_rating,
                 f'Отказ от назначенной заявки: {reason}', 'application_rejection', application_id, response_id)
            )

        # Уведомляем логиста
        try:
            bot.send_message(
                application['created_by'],
                f"⚠️ **Перевозчик отказался от заявки #{application_id}**\n\n"
                f"Перевозчик отказался от выполнения назначенной ему заявки.\n\n"
                f"**Причина отказа:** {reason}\n\n"
                f"Заявка возвращена в активные и доступна для других перевозчиков.",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Не удалось уведомить логиста: {e}")

        # Удаляем заявку из списка принятых заявок перевозчика
        if user_id in user_application_data and 'applications' in user_application_data[user_id]:
            user_application_data[user_id]['applications'] = [
                app for app in user_application_data[user_id]['applications']
                if app['id'] != application_id
            ]

        # Сбрасываем состояние
        user_application_data[user_id]['waiting_for_rejection_reason'] = False
        del user_application_data[user_id]['rejection_application_id']
        del user_application_data[user_id]['rejection_response_id']

        # Удаляем предыдущие сообщения
        try:
            bot.delete_message(message.chat.id, message.message_id - 1)
        except:
            pass

        bot.send_message(
            message.chat.id,
            f"❌ **Вы отказались от заявки #{application_id}!**\n\n"
            f"Заявка возвращена в активные и доступна другим перевозчикам.\n\n"
            f"**Причина отказа:** {reason}",
            parse_mode='Markdown'
        )

        # Если у пользователя еще есть заявки, показываем список
        if user_id in user_application_data and 'applications' in user_application_data[user_id] and \
                user_application_data[user_id]['applications']:
            # Показываем первую страницу обновленного списка
            show_accepted_application_page(user_id, message.chat.id, 0, is_new=True)
        else:
            # Показываем сообщение, что заявок нет
            bot.send_message(
                message.chat.id,
                "📭 У вас больше нет принятых заявок.",
                parse_mode='Markdown'
            )

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_accepted_list')
    def handle_back_to_accepted_list(call):
        """Возвращает к списку принятых заявок"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Проверяем, есть ли сохраненные заявки
        if user_id not in user_application_data or 'applications' not in user_application_data[user_id]:
            bot.answer_callback_query(call.id, "❌ Нет сохраненных заявок")
            return

        applications = user_application_data[user_id]['applications']
        current_index = user_application_data[user_id].get('current_index', 0)

        # Показываем страницу с сохраненным индексом
        show_accepted_application_page(user_id, chat_id, current_index, is_new=False)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('call_logist_'))
    def handle_call_logist(call):
        """Обработка нажатия кнопки 'ПОЗВОНИТЬ'"""
        application_id = int(call.data.split('_')[2])

        # Получаем телефон логиста
        application = db.fetch_one("""
            SELECT u.phone 
            FROM applications a 
            JOIN users u ON a.created_by = u.telegram_id 
            WHERE a.id = ?
        """, (application_id,))

        if application and application.get('phone'):
            phone_number = application['phone']
            bot.send_message(
                call.message.chat.id,
                f"📞 **Телефон логиста:** {phone_number}\n\n"
                f"Вы можете скопировать номер и позвонить.\n"
                f"Или используйте ссылку для звонка: [tel:{phone_number}](tel:{phone_number})",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(call.message.chat.id, "❌ Телефон логиста не указан.")

        bot.answer_callback_query(call.id)

    def get_cancel_rejection_keyboard(application_id, response_id):
        """Клавиатура для отмены отказа от заявки"""
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("❌ Отменить отказ", callback_data=f"back_to_accepted_list")
        )
        return keyboard

    def format_detailed_application(application, loading_points, unloading_points, cargo_info, logist_info,
                                    payment_options_responses=None):
        """Форматирует детальную информацию о заявке с несколькими точками"""

        app_id = application['id']
        app_type = "СТАНДАРТНАЯ" if application['application_type'] == 'fixed' else "ЗАПРОС СТАВОК"

        # Цена/бюджет
        price_info = ""
        if application['application_type'] == 'auction':
            price_info = f"🎯 **Желаемый бюджет:** {float(application.get('desired_budget', 0)):,.0f} руб."
        elif application['application_type'] == 'fixed':
            fixed_price = application.get('fixed_price', 0)
            if fixed_price:
                price_info = f"💰 **Фиксированная ставка:** {float(fixed_price):,.0f} руб."

        # Точки погрузки с датами
        loading_text = f"**📍 Точки погрузки ({len(loading_points)}):**\n"
        if loading_points:
            for i, point in enumerate(loading_points, 1):
                city = point.get('city', '')
                address = point.get('address', '')

                # Формируем местоположение
                location_parts = []
                if city:
                    location_parts.append(f"**{city}**")
                if address:
                    location_parts.append(address)

                location_str = ", ".join(location_parts) if location_parts else "Не указано"

                loading_text += f"   {i}. {location_str}\n"

                # Добавляем дату/время для каждой точки
                if point.get('point_datetime'):
                    try:
                        dt = point['point_datetime']
                        if isinstance(dt, str):
                            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                        loading_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                    except:
                        loading_text += f"      📅 {point['point_datetime']}\n"

                if point.get('coordinates'):
                    try:
                        coords = json.loads(point['coordinates'])
                        loading_text += f"      📍 Координаты: {coords['lat']:.6f}, {coords['lon']:.6f}\n"
                    except:
                        pass
        else:
            loading_text += "   Нет точек погрузки\n"
        loading_text += "\n"

        # Точки выгрузки с датами
        unloading_text = f"**🏁 Точки выгрузки ({len(unloading_points)}):**\n"
        if unloading_points:
            for i, point in enumerate(unloading_points, 1):
                city = point.get('city', '')
                address = point.get('address', '')

                # Формируем местоположение
                location_parts = []
                if city:
                    location_parts.append(f"**{city}**")
                if address:
                    location_parts.append(address)

                location_str = ", ".join(location_parts) if location_parts else "Не указано"

                unloading_text += f"   {i}. {location_str}\n"

                # Добавляем дату/время для каждой точки
                if point.get('point_datetime'):
                    try:
                        dt = point['point_datetime']
                        if isinstance(dt, str):
                            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                        unloading_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                    except:
                        unloading_text += f"      📅 {point['point_datetime']}\n"

                if point.get('coordinates'):
                    try:
                        coords = json.loads(point['coordinates'])
                        unloading_text += f"      📍 Координаты: {coords['lat']:.6f}, {coords['lon']:.6f}\n"
                    except:
                        pass
        else:
            unloading_text += "   Нет точек выгрузки\n"
        unloading_text += "\n"

        # Груз
        cargo_type_display = CARGO_TYPE_REVERSE_MAPPING.get(cargo_info['type'], cargo_info['type'])

        cargo_text = f"""
    📦 **Характер груза:** {cargo_type_display}
    ⚖️ **Вес:** {float(cargo_info['weight']):.2f} т
    📏 **Объем:** {float(cargo_info['volume']):.2f} м³
        """.strip()

        # Транспорт
        from utils.dicts import VEHICLE_TYPE_REVERSE_MAPPING
        vehicle_type_display = VEHICLE_TYPE_REVERSE_MAPPING.get(application.get('vehicle_type'),
                                                                application.get('vehicle_type', 'Не указан'))

        transport_text = f"""
    🚛 **Тип кузова:** {vehicle_type_display}
        """.strip()

        # ОПЛАТА - ТЕПЕРЬ БЕРЕМ ИЗ application_responses
        payment_text = "💰 **Варианты оплаты:**\n"

        # Используем payment_options_responses, который должен содержать данные из application_responses
        if payment_options_responses:
            try:
                # Проверяем, что пришло - словарь или строка
                if isinstance(payment_options_responses, dict):
                    parsed_options = payment_options_responses
                elif isinstance(payment_options_responses, str):
                    # Пробуем распарсить как JSON
                    try:
                        parsed_options = json.loads(payment_options_responses)
                    except json.JSONDecodeError:
                        try:
                            parsed_options = ast.literal_eval(payment_options_responses)
                        except:
                            parsed_options = {}
                else:
                    parsed_options = {}

                payments = []

                # Проверяем наличие каждого ключа
                if parsed_options.get('nds'):
                    try:
                        amount = float(parsed_options['nds'])
                        payments.append(f"• С НДС: {amount:,.0f} ₽")
                    except (ValueError, TypeError):
                        pass

                if parsed_options.get('ip'):
                    try:
                        amount = float(parsed_options['ip'])
                        payments.append(f"• ИП без НДС: {amount:,.0f} ₽")
                    except (ValueError, TypeError):
                        pass

                if parsed_options.get('self-employed'):
                    try:
                        amount = float(parsed_options['self-employed'])
                        payments.append(f"• Самозанятый: {amount:,.0f} ₽")
                    except (ValueError, TypeError):
                        pass

                if parsed_options.get('cash'):
                    try:
                        amount = float(parsed_options['cash'])
                        payments.append(f"• Наличные: {amount:,.0f} ₽")
                    except (ValueError, TypeError):
                        pass

                payment_text += "\n".join(payments) if payments else "Не указаны"

            except Exception as e:
                print(f"Ошибка парсинга payment_options: {e}")
                import traceback
                traceback.print_exc()
                payment_text += "Ошибка формата данных"
        else:
            payment_text += "Не указаны"

        # Контакты
        contacts_text = ""
        if logist_info:
            phone = logist_info.get('phone', 'Не указан')
            email = logist_info.get('email', 'Не указан')
            contacts_text = f"""
    👤 **Контакты логиста:**
    📞 Телефон: {phone}
    📧 Email: {email}
            """.strip()

        # Сборка полного текста
        detailed_text = f"""
    📋 **ПОДРОБНАЯ ИНФОРМАЦИЯ О ЗАЯВКЕ #{app_id}**

    🎯 **Тип заявки:** {app_type}
    {price_info}

    🗺️ **Маршрут:**
    {loading_text}
    {unloading_text}

    {cargo_text}

    {transport_text}

    {payment_text}

    {contacts_text}

    💬 **Примечания:** {application.get('notes', 'Не указаны')}
        """.strip()

        return detailed_text