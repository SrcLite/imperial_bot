from datetime import datetime
import json
import ast
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from handlers.application_handlers.executor_application_handlers import get_payment_type_name, \
    notify_executor_about_selection, notify_other_executors_about_rejection
from utils.dicts import CARGO_TYPE_REVERSE_MAPPING
from utils.helpers import update_user_rating_on_completion

logist_responses_data = {}


def register_logist_application_bid_handlers(bot, db):
    @bot.message_handler(func=lambda message: message.text == '📊 Предложения по заявкам')
    def show_application_responses(message):
        """Показывает логисту все заявки с предложениями перевозчиков"""
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
        # Проверяем, что пользователь - логист
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'external_logist', 'admin', 'external_logist', 'external_admin']:
            bot.send_message(chat_id, "❌ Эта функция доступна только логистам.")
            return

        # Получаем заявки логиста с предложениями
        applications = db.fetch_all("""
            SELECT a.*, COUNT(ar.id) as responses_count
            FROM applications a
            LEFT JOIN application_responses ar ON a.id = ar.application_id 
                AND ar.status IN ('counter_offer', 'accepted_budget')
            WHERE a.created_by = ? 
                AND a.status = 'active' 
                AND a.application_type = 'auction'
            GROUP BY a.id
            HAVING COUNT(ar.id) > 0
            ORDER BY a.created_at DESC
        """, (user_id,))

        if not applications:
            bot.send_message(chat_id, "📭 На данный момент предложений по вашим заявкам нет.")
            return

        # Сохраняем заявки для этого логиста
        if user_id not in logist_responses_data:
            logist_responses_data[user_id] = {}

        logist_responses_data[user_id]['applications'] = applications
        logist_responses_data[user_id]['current_index'] = 0
        logist_responses_data[user_id]['message_id'] = None

        # Показываем первую заявку с предложениями
        show_responses_page(user_id, chat_id, 0, is_new=True)

    def show_responses_page(user_id, chat_id, index, is_new=False):
        """Показывает заявку с предложениями по указанному индексу"""
        if user_id not in logist_responses_data or not logist_responses_data[user_id].get('applications'):
            bot.send_message(chat_id, "❌ Данные о предложениях устарели. Нажмите '📊 Предложения по заявкам' снова.")
            return

        applications = logist_responses_data[user_id]['applications']

        if index < 0 or index >= len(applications):
            return

        app = applications[index]
        points = db.fetch_all(
            'select * from application_points where application_id = ? order by point_order', (app['id'],)
        )

        loading_points = [p for p in points if p['point_type'] == 'loading']
        unloading_points = [p for p in points if p['point_type'] == 'unloading']
        first_loading_city = loading_points[0]['city'] if loading_points and 'city' in loading_points[
            0] else "Не указано"
        first_unloading_city = unloading_points[0]['city'] if unloading_points and 'city' in unloading_points[
            0] else "Не указано"
        loading_city = first_loading_city
        unloading_city = first_unloading_city

        # Получаем количество предложений
        responses_count = db.fetch_one("""
            SELECT COUNT(*) as count 
            FROM application_responses 
            WHERE application_id = ? 
                AND status IN ('counter_offer', 'accepted_budget')
        """, (app['id'],))['count']

        # Форматируем текст заявки
        text = f"""
📋 **Заявка #{app['id']}**
🎯 **Тип:** Запрос ставок
💰 **Бюджет:** {float(app.get('desired_budget', 0)):,.0f} руб.
📦 **Груз:** {CARGO_TYPE_REVERSE_MAPPING.get(app.get('cargo_type', 'Не указан'))}
📍 **Маршрут:** {loading_city} → {unloading_city}

📊 **Получено предложений:** {responses_count}

Выберите заявку, чтобы посмотреть все предложения и выбрать перевозчика.
        """.strip()

        # Добавляем нумерацию страниц
        page_info = f"\n\n📄 Страница {index + 1} из {len(applications)}"
        full_text = text + page_info

        # Создаем клавиатуру с навигацией
        keyboard = InlineKeyboardMarkup(row_width=2)

        # Кнопки навигации
        nav_buttons = []
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"resp_nav_prev_{index}"))

        nav_buttons.append(InlineKeyboardButton("👁️ Посмотреть", callback_data=f"view_responses_{app['id']}"))

        if index < len(applications) - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"resp_nav_next_{index}"))

        keyboard.add(*nav_buttons)
        keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_responses"))

        if is_new:
            # Отправляем новое сообщение
            msg = bot.send_message(
                chat_id,
                full_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            logist_responses_data[user_id]['message_id'] = msg.message_id
        else:
            # Редактируем существующее сообщение
            message_id = logist_responses_data[user_id].get('message_id')
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
                    logist_responses_data[user_id]['message_id'] = msg.message_id

        # Обновляем текущий индекс
        logist_responses_data[user_id]['current_index'] = index

    @bot.callback_query_handler(func=lambda call: call.data.startswith('resp_detail_'))
    def handle_response_detail_navigation(call):
        """Обработка навигации по предложениям"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        direction = data_parts[2]  # prev или next
        current_index = int(data_parts[3])

        if user_id not in logist_responses_data:
            bot.answer_callback_query(call.id, "❌ Сессия просмотра истекла")
            return

        responses = logist_responses_data[user_id].get('responses', [])

        if not responses:
            bot.answer_callback_query(call.id, "❌ Нет доступных предложений")
            return

        # Определяем новый индекс
        if direction == 'prev':
            new_index = current_index - 1
        else:  # next
            new_index = current_index + 1

        # Проверяем границы
        if new_index < 0 or new_index >= len(responses):
            bot.answer_callback_query(call.id)
            return

        # Показываем новое предложение
        show_response_detail(user_id, chat_id, new_index)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('view_responses_'))
    def handle_view_responses(call):
        """Показывает все предложения по заявке"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[2])

        # Очищаем данные о просмотре списка
        if user_id in logist_responses_data:
            del logist_responses_data[user_id]

        # Получаем все предложения по заявке
        responses = db.fetch_all("""
            SELECT ar.*, u.first_name, u.last_name, u.phone, c.name as company_name, c.inn as company_inn
            FROM application_responses ar
            JOIN users u ON ar.executor_id = u.telegram_id
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE ar.application_id = ? 
                AND ar.status IN ('counter_offer', 'accepted_budget')
            ORDER BY ar.created_at DESC
        """, (application_id,))

        if not responses:
            bot.answer_callback_query(call.id, "❌ Предложений не найдено")
            return

        # Сохраняем предложения для этого логиста
        if user_id not in logist_responses_data:
            logist_responses_data[user_id] = {}

        logist_responses_data[user_id]['responses'] = responses
        logist_responses_data[user_id]['current_response_index'] = 0
        logist_responses_data[user_id]['message_id'] = call.message.message_id
        logist_responses_data[user_id]['application_id'] = application_id

        # Показываем первое предложение
        show_response_detail(user_id, call.message.chat.id, 0)

        bot.answer_callback_query(call.id)

    def show_response_detail(user_id, chat_id, index):
        """Показывает детали предложения по индексу"""
        if user_id not in logist_responses_data or not logist_responses_data[user_id].get('responses'):
            bot.send_message(chat_id, "❌ Данные о предложениях устарели.")
            return

        responses = logist_responses_data[user_id]['responses']
        application_id = logist_responses_data[user_id]['application_id']

        if index < 0 or index >= len(responses):
            return

        response = responses[index]

        # Парсим данные о компании и платежах
        try:
            company_info = {
                'name': response.get('company_name', 'Не указана'),
                'inn': response.get('company_inn', 'Не указан')
            }
            print(company_info.get('inn'))

            # Парсим payment_options из response
            payment_options = {}
            if response.get('payment_options'):
                try:
                    # Сначала пробуем JSON
                    payment_options = json.loads(response['payment_options'])
                except json.JSONDecodeError:
                    try:
                        # Пробуем ast.literal_eval как запасной вариант
                        payment_options = ast.literal_eval(response['payment_options'])
                    except:
                        payment_options = {}
                except Exception as e:
                    print(f"Error parsing payment options: {e}")
                    payment_options = {}
        except Exception as e:
            print(f"Error getting company info: {e}")
            company_info = {}
            payment_options = {}

        # Получаем информацию о заявке
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))

        # Форматируем текст предложения
        payments_text = ""
        if payment_options:
            for payment_type, amount in payment_options.items():
                payments_text += f"• {get_payment_type_name(payment_type)}: {amount:,.0f} руб.\n"
        else:
            payments_text = "• Варианты оплаты не указаны\n"

        # Определяем тип предложения
        if response['status'] == 'accepted_budget':
            offer_type = "✅ Принял по бюджету"
        else:
            offer_type = "💰 Встречное предложение"

        text = f"""
        📋 **Предложение по заявке #{application_id}**
        
        {offer_type}
        
        👤 **Перевозчик:** {response['first_name']} {response.get('last_name', '')}
        📞 **Телефон:** {response.get('phone', 'Не указан')}
        🏢 **Компания:** {company_info.get('name', 'Не указана')}
        🔢 **ИНН:** {company_info.get('inn', 'Не указан')}
        
        💰 **Предложенные ставки:**
        {payments_text}
        
        📅 **Дата предложения:** {response['created_at'][:16] if response.get('created_at') else 'Не указана'}
        
        📄 **Страница {index + 1} из {len(responses)}**
                """.strip()

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)

        # Кнопки навигации
        nav_buttons = []

        nav_buttons.append(InlineKeyboardButton("✅ ВЫБРАТЬ", callback_data=f"select_response_{response['id']}"))
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"resp_detail_prev_{index}"))

        if index < len(responses) - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"resp_detail_next_{index}"))

        keyboard.add(*nav_buttons)
        keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_response_detail"))

        # Редактируем сообщение
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=logist_responses_data[user_id]['message_id'],
                text=text,
                reply_markup=keyboard,
            )
        except Exception as e:
            print(f"Ошибка при редактировании сообщения: {e}")

        # Обновляем текущий индекс
        logist_responses_data[user_id]['current_response_index'] = index

    @bot.callback_query_handler(func=lambda call: call.data == 'close_response_detail')
    def handle_close_response_detail(call):
        """Закрывает просмотр деталей предложения"""
        user_id = call.from_user.id

        # Удаляем сообщение
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Очищаем данные пользователя
        if user_id in logist_responses_data:
            del logist_responses_data[user_id]

        bot.answer_callback_query(call.id, "✅ Просмотр завершен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('resp_detail_'))
    def handle_response_detail_navigation(call):
        """Обработка навигации по предложениям"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        direction = data_parts[2]  # prev или next
        current_index = int(data_parts[3])

        if user_id not in logist_responses_data:
            bot.answer_callback_query(call.id, "❌ Сессия просмотра истекла")
            return

        responses = logist_responses_data[user_id].get('responses', [])

        if not responses:
            bot.answer_callback_query(call.id, "❌ Нет доступных предложений")
            return

        # Определяем новый индекс
        if direction == 'prev':
            new_index = current_index - 1
        else:  # next
            new_index = current_index + 1

        # Проверяем границы
        if new_index < 0 or new_index >= len(responses):
            bot.answer_callback_query(call.id)
            return

        # Показываем новое предложение
        show_response_detail(user_id, chat_id, new_index)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('select_response_'))
    def handle_select_response(call):
        """Обработка выбора предложения логистом"""
        user_id = call.from_user.id
        response_id = int(call.data.split('_')[2])

        # Получаем полную информацию о предложении
        response = db.fetch_one("""
            SELECT ar.*, a.created_by as logist_id, a.id as application_id,
                   a.desired_budget, a.application_type
            FROM application_responses ar
            JOIN applications a ON ar.application_id = a.id
            WHERE ar.id = ?
        """, (response_id,))

        if not response:
            bot.answer_callback_query(call.id, "❌ Предложение не найдено")
            return

        # Проверяем, что пользователь - создатель заявки
        if response['logist_id'] != user_id:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для выбора этого предложения")
            return

        # Получаем информацию об перевозчике
        executor_info = db.fetch_one("""
            SELECT u.*, c.name as company_name, c.inn as company_inn
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE u.telegram_id = ?
        """, (response['executor_id'],))

        # Парсим payment_options из предложения
        payment_options = {}
        if response.get('payment_options'):
            try:
                payment_options = json.loads(response['payment_options'])
            except json.JSONDecodeError:
                try:
                    payment_options = ast.literal_eval(response['payment_options'])
                except:
                    payment_options = {}

        # Определяем итоговую цену
        final_price = None
        if payment_options:
            # Берем первый доступный вариант оплаты
            for price in payment_options.values():
                if price:
                    final_price = float(price)
                    break

        # Если цена не определена, используем бюджет заявки
        if not final_price and response['desired_budget']:
            final_price = float(response['desired_budget'])

        # СОХРАНЯЕМ ВСЕ ДАННЫЕ В БАЗУ ДАННЫХ

        # 1. Обновляем статус заявки и назначаем перевозчика
        # Убираем fixed_price из запроса, так как его нет в таблице
        db.execute_query(
            """UPDATE applications 
            SET status = 'assigned', 
                assigned_to = ?,
                updated_at = datetime('now')
            WHERE id = ?""",
            (response['executor_id'], response['application_id'])
        )

        # 2. Обновляем статус выбранного предложения на 'accepted'
        db.execute_query(
            """UPDATE application_responses 
            SET status = 'accepted',
                updated_at = datetime('now')
            WHERE id = ?""",
            (response_id,)
        )

        # 3. Обновляем статус остальных предложений на 'rejected'
        db.execute_query(
            """UPDATE application_responses 
            SET status = 'rejected',
                updated_at = datetime('now')
            WHERE application_id = ? 
                AND id != ? 
                AND status IN ('counter_offer', 'accepted_budget')""",
            (response['application_id'], response_id)
        )

        try:
            bonus_data = db.fetch_one("select value from rating_rules "
                                      "where rule_type = 'executor'"
                                      "and rule_name = 'Принятие заявки'"
                                      "and is_active = 1")
            bonus_amount = bonus_data['value'] if bonus_data else 2.0
            update_user_rating_on_completion(db, response['executor_id'], response_id, bonus_amount, "Принятие заявки",
                                             'executor')

        except Exception as e:
            print(f"Не удалось обновить рейтинг перевозчика: {e}")

        # 6. Экспортируем в Google Sheets
        try:
            from handlers.application_handlers.google_sheets_export import update_application_status_in_sheets
            update_application_status_in_sheets(
                db,
                response['application_id'],
                'assigned',
                response['executor_id']
            )
        except Exception as e:
            print(f"Не удалось обновить Google Sheets: {e}")

        # 7. Уведомляем выбранного перевозчика
        notify_executor_about_selection(bot, db, response['application_id'], response['executor_id'])

        # 8. Уведомляем остальных перевозчиков об отказе
        notify_other_executors_about_rejection(bot, db, response['application_id'], response['executor_id'])

        # Формируем текст подтверждения с деталями
        confirmation_text = f"""
    ✅ **Предложение выбрано!**

    📋 **Заявка #{response['application_id']}**
    👤 **Перевозчик:** {executor_info.get('first_name', '')} {executor_info.get('last_name', '')}
    🏢 **Компания:** {executor_info.get('company_name', 'Не указана')}
    🔢 **ИНН:** {executor_info.get('company_inn', 'Не указан')}

    💰 **Итоговая цена:** {final_price:,.0f} руб. {'(за бюджет)' if response['status'] == 'accepted_budget' else '(встречное предложение)'}

    📞 **Телефон перевозчика:** {executor_info.get('phone', 'Не указан')}

    ✅ Перевозчик уведомлен о вашем выборе.
    ❌ Остальные участники аукциона получили уведомления об отказе.
        """

        # Показываем сообщение об успехе
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=confirmation_text,
        )

        # 9. Отправляем логисту дополнительную информацию
        try:
            # Получаем все точки погрузки для заявки
            loading_points = db.fetch_all("""
                SELECT city, address, point_datetime, point_order 
                FROM application_points 
                WHERE application_id = ? AND point_type = 'loading' 
                ORDER BY point_order
            """, (response['application_id'],))

            # Получаем все точки выгрузки для заявки
            unloading_points = db.fetch_all("""
                SELECT city, address, point_datetime, point_order 
                FROM application_points 
                WHERE application_id = ? AND point_type = 'unloading' 
                ORDER BY point_order
            """, (response['application_id'],))

            # Формируем строку с точками погрузки
            loading_text = ""
            if loading_points:
                for i, point in enumerate(loading_points, 1):
                    city = point.get('city', '')
                    address = point.get('address', '')

                    # Формируем местоположение
                    location_parts = []
                    if city:
                        location_parts.append(city)
                    if address:
                        location_parts.append(address)

                    location_str = ", ".join(location_parts) if location_parts else "Не указано"

                    # Добавляем номер точки, если их несколько
                    if len(loading_points) > 1:
                        loading_text += f"      {i}. {location_str}\n"
                    else:
                        loading_text += f"      {location_str}\n"

                    # Добавляем дату, если есть
                    point_datetime = point.get('point_datetime')
                    if point_datetime:
                        try:
                            if isinstance(point_datetime, str):
                                # Пробуем разные форматы
                                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                                    try:
                                        dt = datetime.strptime(point_datetime, fmt)
                                        loading_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                                        break
                                    except:
                                        continue
                                else:
                                    loading_text += f"      📅 {point_datetime}\n"
                            else:
                                loading_text += f"      📅 {point_datetime.strftime('%d.%m.%Y %H:%M')}\n"
                        except:
                            loading_text += f"      📅 {point_datetime}\n"

                    if i < len(loading_points):
                        loading_text += "\n"
            else:
                loading_text = "      Не указано\n"

            # Формируем строку с точками выгрузки
            unloading_text = ""
            if unloading_points:
                for i, point in enumerate(unloading_points, 1):
                    city = point.get('city', '')
                    address = point.get('address', '')

                    # Формируем местоположение
                    location_parts = []
                    if city:
                        location_parts.append(city)
                    if address:
                        location_parts.append(address)

                    location_str = ", ".join(location_parts) if location_parts else "Не указано"

                    # Добавляем номер точки, если их несколько
                    if len(unloading_points) > 1:
                        unloading_text += f"      {i}. {location_str}\n"
                    else:
                        unloading_text += f"      {location_str}\n"

                    # Добавляем дату, если есть
                    point_datetime = point.get('point_datetime')
                    if point_datetime:
                        try:
                            if isinstance(point_datetime, str):
                                # Пробуем разные форматы
                                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                                    try:
                                        dt = datetime.strptime(point_datetime, fmt)
                                        unloading_text += f"      📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
                                        break
                                    except:
                                        continue
                                else:
                                    unloading_text += f"      📅 {point_datetime}\n"
                            else:
                                unloading_text += f"      📅 {point_datetime.strftime('%d.%m.%Y %H:%M')}\n"
                        except:
                            unloading_text += f"      📅 {point_datetime}\n"

                    if i < len(unloading_points):
                        unloading_text += "\n"
            else:
                unloading_text = "      Не указано\n"

            application_details = db.fetch_one('select * from applications where id =?', (response['application_id'],))

            if application_details:
                details_text = f"""
        📋 **Детали назначенной заявки:**

        🆔 **Номер заявки:** #{response['application_id']}
        🎯 **Тип:** {'Запрос ставок (аукцион)' if response['application_type'] == 'auction' else 'Стандартная'}
        📦 **Груз:** {CARGO_TYPE_REVERSE_MAPPING.get(application_details.get('cargo_type', 'Не указан'))}
        ⚖️ **Вес:** {float(application_details.get('weight', 0)):.2f} т
        📏 **Объем:** {float(application_details.get('volume', 0)):.2f} м³

        📍 **Точки погрузки ({len(loading_points)}):**
        {loading_text}
        🏁 **Точки выгрузки ({len(unloading_points)}):**
        {unloading_text}
        👤 **Контакты перевозчика:**
        • Имя: {executor_info.get('first_name', '')} {executor_info.get('last_name', '')}
        • Телефон: {executor_info.get('phone', 'Не указан')}
        • Компания: {executor_info.get('company_name', 'Не указана')}
        • ИНН: {executor_info.get('company_inn', 'Не указан')}

        💼 **Договоренности:**
        • Цена: {final_price:,.0f} руб.
        • Варианты оплаты: {', '.join([get_payment_type_name(k) for k in payment_options.keys()]) if payment_options else 'Не указаны'}

        ⚠️ **Рекомендации:**
        1. Свяжитесь с перевозчиком для уточнения деталей
        2. Подготовьте все необходимые документы
        3. Отслеживайте выполнение заявки в разделе "✅ Принятые заявки"
                """

                bot.send_message(
                    user_id,
                    details_text,
                    parse_mode='Markdown'
                )
        except Exception as e:
            print(f"Не удалось отправить детали логисту: {e}")

        # Очищаем данные
        if user_id in logist_responses_data:
            del logist_responses_data[user_id]

        bot.answer_callback_query(call.id, "✅ Предложение выбрано")

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_responses_list')
    def handle_back_to_responses_list(call):
        """Возврат к списку заявок с предложениями"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Очищаем данные о детальном просмотре
        if user_id in logist_responses_data:
            if 'responses' in logist_responses_data[user_id]:
                del logist_responses_data[user_id]['responses']
                del logist_responses_data[user_id]['current_response_index']
                del logist_responses_data[user_id]['application_id']

        # Показываем список заявок
        show_responses_page(user_id, chat_id, 0, is_new=False)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'close_responses')
    def handle_close_responses(call):
        """Закрывает просмотр предложений"""
        user_id = call.from_user.id

        # Удаляем сообщение
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Очищаем данные пользователя
        if user_id in logist_responses_data:
            del logist_responses_data[user_id]

        bot.answer_callback_query(call.id, "✅ Просмотр предложений завершен")