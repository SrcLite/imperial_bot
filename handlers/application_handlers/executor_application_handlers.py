import json
import ast
import pytz
from datetime import datetime, timedelta

from telebot.types import ReplyKeyboardRemove

from handlers.application_handlers.display_application_handlers import format_application_for_executor
from handlers.application_handlers.google_sheets_export import export_response_to_google_sheets
from keyboards.application_keyboards import *
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from utils.dicts import CARGO_TYPE_REVERSE_MAPPING, VEHICLE_TYPE_REVERSE_MAPPING
from utils.filters import get_filtered_applications
from utils.google_sheets import init_google_sheets
from config.google_sheets_config import is_google_sheets_enabled
from utils.helpers import update_user_rating_on_completion

application_temp_data = {}


def is_loading_date_valid(db, application_id):
    """
    Проверяет, что дата первой погрузки не просрочена.
    Использует московское время (MSK, UTC+3).
    """
    import pytz
    from datetime import datetime, timedelta

    msk_tz = pytz.timezone('Europe/Moscow')
    current_msk = datetime.now(msk_tz)

    # Получаем дату первой точки погрузки из application_points
    first_loading = db.fetch_one("""
        SELECT point_datetime 
        FROM application_points 
        WHERE application_id = ? AND point_type = 'loading' 
        ORDER BY point_order LIMIT 1
    """, (application_id,))

    if not first_loading or not first_loading.get('point_datetime'):
        # Если нет точек погрузки, считаем заявку валидной (или невалидной - по вашему усмотрению)
        return True

    loading_datetime_str = first_loading['point_datetime']

    try:
        # Преобразуем строку в datetime объект
        if isinstance(loading_datetime_str, str):
            # Учитываем возможные форматы даты
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    loading_dt = datetime.strptime(loading_datetime_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                return False
        else:
            return False

        # Применяем московский часовой пояс, если дата без таймзоны
        if loading_dt.tzinfo is None:
            loading_dt_msk = msk_tz.localize(loading_dt)
        else:
            loading_dt_msk = loading_dt.astimezone(msk_tz)

        # Сравниваем с текущим московским временем
        # Добавляем небольшой запас в 1 час на случай опозданий
        one_hour = timedelta(hours=1)
        return loading_dt_msk >= (current_msk - one_hour)

    except Exception as e:
        print(f"Ошибка при проверке даты погрузки для заявки {application_id}: {e}")
        return False


def register_executor_application_handlers(bot, db):
    user_application_data = {}

    @bot.message_handler(func=lambda message: message.text == '🔔 Новые заявки')
    def show_active_applications(message):
        """Показывает активные заявки перевозчику с постраничной навигацией"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        user = db.get_user_by_telegram_id(user_id)
        if user['status'] != 'active':
            bot.send_message(chat_id, "❌ Администратор не подтвердил вашу учетную запись.",
                             reply_markup=ReplyKeyboardRemove())
            return
        if user_role['role'] not in ['executor', 'external_executor']:
            bot.send_message(chat_id, "❌ Эта функция доступна только перевозчикам.")
            return

        # Получаем активные заявки, исключая те, которые пользователь уже отклонил
        from utils.filters import ExecutorFilters
        filters = ExecutorFilters(db, user_id)

        applications = get_filtered_applications(db, user_id, filters.filters)
        if not applications:
            bot.send_message(chat_id, "📭 На данный момент активных заявок нет.")
            return

        # Фильтруем заявки, оставляя только те, у которых дата погрузки не просрочена
        valid_applications = []
        expired_applications = []

        for app in applications:
            # Проверяем дату первой погрузки через новую функцию с передачей application_id
            if is_loading_date_valid(db, app['id']):
                valid_applications.append(app)
            else:
                # Если заявка просрочена, добавляем в список для обновления статуса
                expired_applications.append(app['id'])

        # Обновляем статус просроченных заявок (но только тех, которые еще active)
        if expired_applications:
            placeholders = ','.join(['?' for _ in expired_applications])
            db.execute_query(f"""
                UPDATE applications 
                SET status = 'expired' 
                WHERE id IN ({placeholders}) AND status = 'active'
            """, expired_applications)
            print(f"✅ Обновлен статус для {len(expired_applications)} просроченных заявок: {expired_applications}")

        if not valid_applications:
            bot.send_message(chat_id, "📭 На данный момент нет заявок с актуальными датами погрузки.")
            return

        # Сохраняем заявки для этого пользователя
        if user_id not in user_application_data:
            user_application_data[user_id] = {}

        user_application_data[user_id]['applications'] = valid_applications
        user_application_data[user_id]['current_index'] = 0
        user_application_data[user_id]['message_id'] = None

        # Показываем первую заявку
        show_application_page(user_id, chat_id, 0, is_new=True)

    def show_application_page(user_id, chat_id, index, is_new=False):
        """Показывает заявку по указанному индексу"""
        if user_id not in user_application_data or not user_application_data[user_id].get('applications'):
            bot.send_message(chat_id, "❌ Данные о заявках устарели. Нажмите '🔔 Новые заявки' снова.")
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

        creator_info = db.fetch_one('select * from users where telegram_id = ?', (app['created_by'],))
        company_info = db.fetch_one('select * from companies where id = ?', (creator_info['company_id'],))

        # Форматируем заявку
        application_text = format_application_for_executor(app, points, creator_info, company_info)
        # Добавляем нумерацию страниц
        page_info = f"\n\n📄 Страница {index + 1} из {len(applications)}"
        full_text = application_text + page_info

        # Создаем клавиатуру с навигацией
        keyboard = get_application_navigation_keyboard(app['id'], index, len(applications))

        if is_new:
            # Отправляем новое сообщение
            msg = bot.send_message(
                chat_id,
                full_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            user_application_data[user_id]['message_id'] = msg.message_id
        else:
            # Редактируем существующее сообщение
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
                    # Если сообщение не найдено, отправляем новое
                    msg = bot.send_message(
                        chat_id,
                        full_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                    user_application_data[user_id]['message_id'] = msg.message_id

        # Обновляем текущий индекс
        user_application_data[user_id]['current_index'] = index

    def get_application_navigation_keyboard(application_id, current_index, total_count):
        """Создает клавиатуру с навигацией по заявкам"""
        keyboard = InlineKeyboardMarkup(row_width=3)

        # Кнопки навигации
        nav_buttons = []

        if current_index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"nav_prev_{current_index}"))

        nav_buttons.append(
            InlineKeyboardButton("📋 ОЗНАКОМИТЬСЯ", callback_data=f"executor_view_application_{application_id}"))

        if current_index < total_count - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"nav_next_{current_index}"))

        keyboard.add(*nav_buttons)

        # Кнопка закрыть
        keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_applications"))

        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data.startswith('nav_'))
    def handle_navigation(call):
        """Обработка навигации по заявкам"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        direction = data_parts[1]  # prev или next
        current_index = int(data_parts[2])

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
        show_application_page(user_id, chat_id, new_index, is_new=False)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'close_applications')
    def handle_close_applications(call):
        """Закрывает просмотр заявок"""
        user_id = call.from_user.id

        # Удаляем сообщение с заявками
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Очищаем данные пользователя
        if user_id in user_application_data:
            del user_application_data[user_id]

        bot.answer_callback_query(call.id, "✅ Просмотр заявок завершен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('executor_view_application_'))
    def handle_view_application(call):
        """Обработка нажатия кнопки 'ОЗНАКОМИТЬСЯ'"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[3])

        # Очищаем данные о просмотре заявок
        if user_id in user_application_data:
            del user_application_data[user_id]

        # Получаем полную информацию о заявке
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        # Получаем точки маршрута
        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (application_id,)
        )

        # Разделяем точки на погрузку и выгрузку
        loading_points = [p for p in points if p['point_type'] == 'loading']
        unloading_points = [p for p in points if p['point_type'] == 'unloading']

        # Формируем ссылку для Яндекс.Карт с поддержкой нескольких точек
        map_url = generate_yandex_maps_url(loading_points, unloading_points)

        # Получаем информацию о грузе
        cargo_info = get_cargo_info(application)

        # Получаем контактные данные логиста
        logist_info = db.fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?",
            (application['created_by'],)
        )

        # Извлекаем срок оплаты из payment_options
        payment_deadline = None
        if application.get('payment_deadline'):
            payment_deadline = application.get('payment_deadline')

        # Форматируем детальную информацию о заявке
        detailed_text = format_detailed_application(
            db, application, loading_points, unloading_points, cargo_info, logist_info, payment_deadline
        )

        # Создаем клавиатуру в зависимости от типа заявки
        if application['application_type'] == 'fixed':
            keyboard = get_fixed_application_keyboard(application_id, map_url,
                                                      logist_info.get('phone') if logist_info else None)
        else:
            keyboard = get_auction_application_keyboard(application_id, map_url,
                                                        logist_info.get('phone') if logist_info else None)

        # Редактируем сообщение с заявкой
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=detailed_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "📋 Подробная информация о заявке")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reject_application_'))
    def handle_reject_application(call):
        """Обработка нажатия кнопки 'ОТКЛОНИТЬ'"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[2])

        # Проверяем, не отклонил ли уже пользователь эту заявку ранее
        existing_response = db.fetch_one(
            "SELECT * FROM application_responses WHERE application_id = ? AND executor_id = ? AND status = 'rejected'",
            (application_id, user_id)
        )

        if existing_response:
            bot.answer_callback_query(call.id, "❌ Вы уже отклонили эту заявку")
            return

        # Получаем информацию о заявке
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        # Проверяем, была ли заявка уже назначена этому перевозчику
        was_assigned = False
        if application['status'] == 'assigned' and application.get('assigned_to') == user_id:
            was_assigned = True

            # Применяем штраф за отклонение принятой заявки (10 баллов из 100)
            user_info = db.get_user_by_telegram_id(user_id)
            rating_type = ''
            if user_info['role'] == ['executor', 'external_executor']:
                rating_type = 'executor'
            # Получаем текущий рейтинг из базы данных
            rating_data = db.fetch_one("""
                SELECT current_rating FROM user_ratings 
                WHERE user_id = ? AND rating_type = ?
            """, (user_id, rating_type))

            if rating_data:
                old_rating = rating_data['current_rating']
                new_rating = max(0, old_rating - 5)  # Штраф 10 баллов

                # Обновляем рейтинг в базе данных
                db.execute_query("""
                    UPDATE user_ratings 
                    SET current_rating = ?, 
                        updated_at = datetime('now')
                    WHERE user_id = ? AND rating_type = ?
                """, (new_rating, user_id, rating_type))

                # Добавляем запись в историю рейтинга
                db.execute_query("""
                    INSERT INTO rating_history 
                    (user_id, rating_type, old_rating, new_rating, change_amount, 
                     change_type, change_reason, application_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (user_id, rating_type, old_rating, new_rating, -5,
                      'penalty', f'Отклонение принятой заявки #{application_id}', application_id))

        # Записываем отказ перевозчика
        db.execute_query(
            """INSERT INTO application_responses 
            (application_id, executor_id, status, created_at) 
            VALUES (?, ?, 'rejected', datetime('now'))""",
            (application_id, user_id)
        )

        response_id = db.fetch_one(
            "SELECT last_insert_rowid() as id"
        )['id']

        # Если заявка была назначена, обновляем ее статус
        if was_assigned:
            db.execute_query(
                "UPDATE applications SET status = 'urgent', assigned_to = NULL WHERE id = ?",
                (application_id,)
            )

            executor_info = db.get_user_by_telegram_id(user_id)


            # Уведомляем логиста в Telegram
            logist_id = application['created_by']
            try:
                message_text = f"""
⚠️ **Перевозчик отказался от заявки!**

📦 Заявка #{application_id} была отклонена перевозчиком после принятия.

👤 **Перевозчик:** {executor_info['first_name']} {executor_info.get('last_name', '')}
📞 **Телефон:** {executor_info.get('phone', 'Не указан')}

Заявка возвращена в активные. Вы можете выбрать другого перевозчика.
                """.strip()
                bot.send_message(logist_id, message_text, parse_mode='Markdown')
            except Exception as e:
                print(f"Не удалось уведомить логиста: {e}")

        try:
            from handlers.application_handlers.google_sheets_export import export_response_to_google_sheets
            export_response_to_google_sheets(
                db=db,
                application_id=application_id,
                response_id=response_id,
                executor_id=user_id,
                response_type='rejected',
                payment_options={}
            )
        except Exception as e:
            print(f"Ошибка экспорта отклонения: {e}")

        # Удаляем сообщение с заявкой
        bot.delete_message(call.message.chat.id, call.message.message_id)

        if was_assigned:
            bot.answer_callback_query(call.id, "❌ Заявка отклонена. Ваш рейтинг снижен на 10 баллов.")
        else:
            bot.answer_callback_query(call.id, "❌ Заявка отклонена")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('accept-fixed_'))
    def handle_accept_fixed(call):
        """Обработка нажатия кнопки 'ПРИНЯТЬ' для фиксированной заявки"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[1])
        user = db.get_user_by_telegram_id(user_id)

        if (user['first_name'] is None) or (user['last_name'] is None) or (user['company_id'] is None) or (user['phone'] is None):
            bot.send_message(
                user_id,
                "❌ **Недостаточно данных для принятия заявок**\n\n"
                "📋 **Для работы с заявками необходимо заполнить:**\n"
                "• 👤 Имя\n"
                "• 👤 Фамилия\n"
                "• 🏢 Компания\n"
                "• 📞 Телефон\n\n"
                "⚙️ **Как исправить:**\n"
                "1. Откройте меню ⚙️**Настройки**\n"
                "2. Выберите 👤**Мой профиль**\n"
                "3. Добавьте недостающие данные\n\n"
                "✅ После заполнения всех полей вы сможете принимать заявки!"
            )
            return

        # Получаем заявку
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        # Сохраняем ID заявки для следующего шага
        if user_id not in application_temp_data:
            application_temp_data[user_id] = {}

        application_temp_data[user_id]['responding_application'] = application_id
        application_temp_data[user_id]['application_type'] = 'fixed'
        application_temp_data[user_id]['action'] = 'accept'
        application_temp_data[user_id]['selected_payments'] = {}

        # Получаем варианты оплаты из заявки
        payment_options = {}
        if application.get('payment_options'):
            try:
                payment_options = ast.literal_eval(application['payment_options'])
            except Exception as e:
                print(f"Ошибка парсинга payment_options в handle_accept_fixed: {e}")
                print(f"Данные: {application['payment_options']}")

        # Добавляем временную метку для уникальности сообщения
        import time
        timestamp = int(time.time())

        # Показываем варианты оплаты для выбора
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💰 **Выберите варианты оплаты:**\n\n"
                 "Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n"
                 "✅ - означает, что вариант выбран\n\n"
                 "Нажмите на вариант оплаты, чтобы выбрать или снять выбор:\n"
                 f"⠀",  # Невидимый символ для уникальности
            reply_markup=get_payment_options_keyboard(application_id, payment_options, 'accept-fixed'),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('bid-auction_'))
    def handle_bid_auction(call):
        """Обработка нажатия кнопки 'ВСТРЕЧНОЕ' для аукциона"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[1])

        # Получаем заявку
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        # Сохраняем ID заявки для следующего шага
        if user_id not in application_temp_data:
            application_temp_data[user_id] = {}

        application_temp_data[user_id]['responding_application'] = application_id
        application_temp_data[user_id]['application_type'] = 'auction'
        application_temp_data[user_id]['action'] = 'counter_offer'
        application_temp_data[user_id]['selected_payments'] = {}

        # Получаем варианты оплаты из заявки
        payment_options = {}
        if application.get('payment_options'):
            try:
                payment_options = ast.literal_eval(application['payment_options'])
            except:
                pass

        # Показываем варианты оплаты для ввода ставок
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💰 **Введите ваши ставки:**\n\n"
                 "Вы можете ввести ставки для одного или нескольких вариантов оплата.\n"
                 "✅ - означает, что ставка введена\n\n"
                 "Нажмите на вариант оплаты, чтобы ввести ставку:\n"
                 f"⠀",  # Невидимый символ для уникальности
            reply_markup=get_payment_options_keyboard(application_id, payment_options, 'bid-auction'),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('accept-auction_'))
    def handle_accept_auction(call):
        """Обработка нажатия кнопки 'ПРИНЯТЬ' для аукциона (по бюджету)"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[1])
        user = db.get_user_by_telegram_id(user_id)

        if (user['first_name'] is None) or (user['last_name'] is None) or (user['company_id'] is None) or (
                user['phone'] is None):
            bot.send_message(
                user_id,
                "❌ **Недостаточно данных для принятия заявок**\n\n"
                "📋 **Для работы с заявками необходимо заполнить:**\n"
                "• 👤 Имя\n"
                "• 👤 Фамилия\n"
                "• 🏢 Компания\n"
                "• 📞 Телефон\n\n"
                "⚙️ **Как исправить:**\n"
                "1. Откройте меню ⚙️**Настройки**\n"
                "2. Выберите 👤**Мой профиль**\n"
                "3. Добавьте недостающие данные\n\n"
                "✅ После заполнения всех полей вы сможете принимать заявки!"
            )
            return
        # Получаем заявку
        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        # Сохраняем ID заявки для следующего шага
        if user_id not in application_temp_data:
            application_temp_data[user_id] = {}

        application_temp_data[user_id]['responding_application'] = application_id
        application_temp_data[user_id]['application_type'] = 'auction'
        application_temp_data[user_id]['action'] = 'accept_budget'
        application_temp_data[user_id]['budget'] = float(application.get('desired_budget', 0))
        application_temp_data[user_id]['selected_payments'] = {}

        # Получаем варианты оплаты из заявки
        payment_options = {}
        if application.get('payment_options'):
            try:
                payment_options = ast.literal_eval(application['payment_options'])
            except:
                pass

        # Показываем варианты оплаты для выбора
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💰 **Выберите варианты оплаты:**\n\n"
                 f"Бюджет заявки: {float(application.get('desired_budget', 0)):,.0f} руб.\n\n"
                 "Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n"
                 "✅ - означает, что вариант выбран\n\n"
                 "Нажмите на вариант оплаты, чтобы выбрать или снять выбор:\n"
                 f"⠀",  # Невидимый символ для уникальности
            reply_markup=get_payment_options_keyboard(application_id, payment_options, 'accept-auction'),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('select_payment_'))
    def handle_select_payment(call):
        """Обработка выбора варианта оплаты"""
        user_id = call.from_user.id
        data_parts = call.data.split('_')
        action_type = data_parts[2]  # accept-fixed, accept-auction, bid-auction
        application_id = int(data_parts[3])
        payment_type = data_parts[4]
        user = db.get_user_by_telegram_id(user_id)

        if (user['first_name'] is None) or (user['last_name'] is None) or (user['company_id'] is None) or (
                user['phone'] is None):
            bot.send_message(
                user_id,
                "❌ **Недостаточно данных для принятия заявок**\n\n"
                "📋 **Для работы с заявками необходимо заполнить:**\n"
                "• 👤 Имя\n"
                "• 👤 Фамилия\n"
                "• 🏢 Компания\n"
                "• 📞 Телефон\n\n"
                "⚙️ **Как исправить:**\n"
                "1. Откройте меню ⚙️**Настройки**\n"
                "2. Выберите 👤**Мой профиль**\n"
                "3. Добавьте недостающие данные\n\n"
                "✅ После заполнения всех полей вы сможете принимать заявки!"
            )
            return

        if user_id not in application_temp_data or application_temp_data[user_id].get(
                'responding_application') != application_id:
            bot.answer_callback_query(call.id, "❌ Сессия истекла. Начните заново.")
            return

        # Для встречного предложения - запрашиваем ввод ставки через редактирование сообщения
        if action_type == 'bid-auction':
            if 'selected_payments' not in application_temp_data[user_id]:
                application_temp_data[user_id]['selected_payments'] = {}

            # Редактируем сообщение для запроса ввода ставки
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"💵 **Введите ставку для {get_payment_type_name(payment_type)} (в рублях):**\n\n"
                     "Введите сумму цифрами (например: 50000)\n"
                     "↩️ Для отмены нажмите кнопку ниже",
                reply_markup=get_back_to_payments_keyboard(application_id, action_type),
                parse_mode='Markdown'
            )

            set_user_state(user_id, f'waiting_for_executor_{payment_type}_price')
            application_temp_data[user_id]['current_payment_type'] = payment_type
            application_temp_data[user_id]['last_message_id'] = call.message.message_id

            bot.answer_callback_query(call.id)
            return

        # Для принятия заявки (фиксированной или аукциона) - переключаем выбор
        if 'selected_payments' not in application_temp_data[user_id]:
            application_temp_data[user_id]['selected_payments'] = {}

        # Сохраняем старое состояние для проверки изменений
        old_selected = dict(application_temp_data[user_id]['selected_payments'])

        if payment_type in application_temp_data[user_id]['selected_payments']:
            # Удаляем из выбранных
            del application_temp_data[user_id]['selected_payments'][payment_type]
        else:
            # Добавляем в выбранных
            if action_type == 'accept-fixed':
                # Для фиксированной заявки берем цену из заявки
                application = db.fetch_one("SELECT payment_options FROM applications WHERE id = ?", (application_id,))
                if application and application['payment_options']:
                    try:
                        payment_options = ast.literal_eval(application['payment_options'])
                        if payment_type in payment_options:
                            application_temp_data[user_id]['selected_payments'][payment_type] = float(
                                payment_options[payment_type])
                    except Exception as e:
                        print(f"Ошибка парсинга payment_options в handle_select_payment: {e}")
                        bot.answer_callback_query(call.id, "❌ Ошибка загрузки вариантов оплаты")
                        return
            elif action_type == 'accept-auction':
                # Для аукциона берем бюджет заявки
                application = db.fetch_one("SELECT desired_budget FROM applications WHERE id = ?", (application_id,))
                if application:
                    application_temp_data[user_id]['selected_payments'][payment_type] = float(
                        application.get('desired_budget', 0))

        # Проверяем, изменилось ли состояние
        new_selected = application_temp_data[user_id]['selected_payments']
        if old_selected == new_selected:
            # Если состояние не изменилось, просто отвечаем на запрос
            bot.answer_callback_query(call.id)
            return

        # Обновляем клавиатуру
        application = db.fetch_one("SELECT payment_options FROM applications WHERE id = ?", (application_id,))
        payment_options = {}
        if application and application['payment_options']:
            try:
                # Используем ast.literal_eval для консистентности
                payment_options = ast.literal_eval(application['payment_options'])
            except:
                pass

        # Формируем информацию о выбранных вариантах
        selected_count = len(application_temp_data[user_id]['selected_payments'])
        selected_info = ""
        if selected_count > 0:
            selected_info = f"✅ Выбрано вариантов: {selected_count}\n\n"

        # Получаем текст в зависимости от типа действия
        if action_type == 'accept-fixed':
            text = f"💰 **Выберите варианты оплаты:**\n\n{selected_info}Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n✅ - означает, что вариант выбран\n\nНажмите на вариант оплаты, чтобы выбрать или снять выбор:\n⠀"
        elif action_type == 'accept-auction':
            text = f"💰 **Выберите варианты оплаты:**\n\nБюджет заявки: {float(application_temp_data[user_id].get('budget', 0)):,.0f} руб.\n\n{selected_info}Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n✅ - означает, что вариант выбран\n\nНажмите на вариант оплаты, чтобы выбрать или снять выбор:\n⠀"
        else:
            text = "💰 **Введите ваши ставки:**\n\nВы можете ввести ставки для одного или нескольких вариантов оплаты.\n✅ - означает, что ставка введена\n\nНажмите на вариант оплаты, чтобы ввести ставку:\n⠀"

        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=get_payment_options_keyboard(
                    application_id,
                    payment_options,
                    action_type,
                    application_temp_data[user_id]['selected_payments']
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            # Если произошла ошибка "message not modified", игнорируем ее
            if "message is not modified" not in str(e):
                print(f"Ошибка при редактировании сообщения: {e}")

        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id).startswith(
        'waiting_for_executor_') and '_price' in get_user_state(message.from_user.id))
    def handle_price_input(message):
        user_id = message.from_user.id
        current_state = get_user_state(user_id)

        if user_id not in application_temp_data:
            bot.send_message(message.chat.id, "❌ Сессия истекла. Начните заново.")
            set_user_state(user_id, '')
            return

        # Извлекаем тип оплаты из состояния
        payment_type = current_state.replace('waiting_for_executor_', '').replace('_price', '')

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0. Введите корректную сумму:")
                return

            # Сохраняем ставку
            if 'selected_payments' not in application_temp_data[user_id]:
                application_temp_data[user_id]['selected_payments'] = {}

            application_temp_data[user_id]['selected_payments'][payment_type] = price

            # Получаем ID последнего сообщения
            last_message_id = application_temp_data[user_id].get('last_message_id')

            # Возвращаемся к выбору вариантов оплаты
            application_id = application_temp_data[user_id]['responding_application']

            # Получаем варианты оплаты из заявки
            application = db.fetch_one("SELECT payment_options FROM applications WHERE id = ?", (application_id,))
            payment_options = {}
            if application and application['payment_options']:
                try:
                    payment_options = ast.literal_eval(application['payment_options'])
                except:
                    pass

            # Формируем информацию о введенных ставках
            entered_count = len(application_temp_data[user_id]['selected_payments'])
            entered_info = ""
            if entered_count > 0:
                entered_info = f"✅ Введено ставок: {entered_count}\n\n"

            # Удаляем сообщение с вводом суммы
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass

            # Редактируем предыдущее сообщение
            if last_message_id:
                try:
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=last_message_id,
                        text=f"💰 **Введите ваши ставки:**\n\n{entered_info}"
                             "Вы можете ввести ставки для одного или нескольких вариантов оплаты.\n"
                             "✅ - означает, что ставка введена\n\n"
                             "Нажмите на вариант оплаты, чтобы ввести ставку:\n"
                             f"⠀",  # Невидимый символ для уникальности
                        reply_markup=get_payment_options_keyboard(
                            application_id,
                            payment_options,
                            'bid-auction',
                            application_temp_data[user_id]['selected_payments']
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    # Если не удалось отредактировать, отправляем новое
                    bot.send_message(
                        message.chat.id,
                        f"💰 **Введите ваши ставки:**\n\n{entered_info}"
                        "Вы можете ввести ставки для одного или нескольких вариантов оплаты.\n"
                        "✅ - означает, что ставка введена\n\n"
                        "Нажмите на вариант оплаты, чтобы ввести ставку:\n"
                        f"⠀",
                        reply_markup=get_payment_options_keyboard(
                            application_id,
                            payment_options,
                            'bid-auction',
                            application_temp_data[user_id]['selected_payments']
                        ),
                        parse_mode='Markdown'
                    )
            else:
                # Если нет ID предыдущего сообщения, отправляем новое
                bot.send_message(
                    message.chat.id,
                    f"💰 **Введите ваши ставки:**\n\n{entered_info}"
                    "Вы можете ввести ставки для одного или нескольких вариантов оплаты.\n"
                    "✅ - означает, что ставка введена\n\n"
                    "Нажмите на вариант оплаты, чтобы ввести ставку:\n"
                    f"⠀",
                    reply_markup=get_payment_options_keyboard(
                        application_id,
                        payment_options,
                        'bid-auction',
                        application_temp_data[user_id]['selected_payments']
                    ),
                    parse_mode='Markdown'
                )

            set_user_state(user_id, '')

        except ValueError:
            bot.send_message(message.chat.id, "❌ Пожалуйста, введите корректную сумму (только цифры):")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_payments_'))
    def handle_confirm_payments(call):
        """Обработка подтверждения выбора оплаты"""
        user_id = call.from_user.id
        data_parts = call.data.split('_')
        action_type = data_parts[2]  # accept-fixed, accept-auction, bid-auction
        application_id = int(data_parts[3])

        if user_id not in application_temp_data or application_temp_data[user_id].get(
                'responding_application') != application_id:
            bot.answer_callback_query(call.id, "❌ Сессия истекла. Начните заново.")
            return

        selected_payments = application_temp_data[user_id].get('selected_payments', {})

        if not selected_payments:
            bot.answer_callback_query(call.id, "❌ Выберите хотя бы один вариант оплаты")
            return

        # Показываем подтверждение компании
        user_info = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        company_info = db.fetch_one("SELECT * FROM companies WHERE id = ?",
                                    (user_info.get('company_id'),)) if user_info.get('company_id') else None

        if not company_info:
            bot.answer_callback_query(call.id, "❌ Компания не найдена. Заполните данные компании в профиле.")
            return

        # Формируем текст с выбранными варианты оплаты
        payments_text = ""
        total_selected = len(selected_payments)
        for payment_type, amount in selected_payments.items():
            payments_text += f"• {get_payment_type_name(payment_type)}: {amount:,.0f} руб.\n"

        # Определяем текст в зависимости от типа действия
        if action_type == 'accept-fixed':
            action_desc = "принял заявку"
        elif action_type == 'accept-auction':
            action_desc = "принял заявку по бюджету"
        else:
            action_desc = "сделал встречное предложение"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🏢 **Подтвердите отправку отклика:**\n\n"
                 f"**Вы {action_desc} со следующими условиями:**\n\n"
                 f"**Выбранные варианты оплаты ({total_selected}):**\n{payments_text}\n"
                 f"**Ваша компания:** {company_info.get('name', 'Не указана')}\n"
                 f"**ИНН:** {company_info.get('inn', 'Не указан')}\n\n"
                 f"Нажмите '✅ ПОДТВЕРДИТЬ' для отправки отклика логисту.\n"
                 f"⠀",  # Невидимый символ для уникальности
            reply_markup=get_company_confirmation_keyboard(application_id, action_type),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    if is_google_sheets_enabled():
        from config.google_sheets_config import GOOGLE_SHEETS_CONFIG
        init_google_sheets(
            GOOGLE_SHEETS_CONFIG['spreadsheet_url'],
            GOOGLE_SHEETS_CONFIG['worksheet_name']
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_company_'))
    def handle_confirm_company(call):
        """Обработка подтверждения компании"""
        user_id = call.from_user.id
        data_parts = call.data.split('_')
        action_type = data_parts[2]  # accept-fixed, accept-auction, bid-auction
        application_id = int(data_parts[3])

        if user_id not in application_temp_data or application_temp_data[user_id].get(
                'responding_application') != application_id:
            bot.answer_callback_query(call.id, "❌ Сессия истекла. Начните заново.")
            return

        # Получаем информацию о пользователе и компании
        user_info = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        company_info = db.fetch_one("SELECT * FROM companies WHERE id = ?",
                                    (user_info.get('company_id'),)) if user_info.get('company_id') else None

        selected_payments = application_temp_data[user_id].get('selected_payments', {})

        # Сохраняем отклик в базу данных
        if action_type == 'accept-fixed':
            status = 'accepted'
            # Обновляем статус заявки на 'assigned'
            db.execute_query(
                "UPDATE applications SET status = 'assigned', assigned_to = ? WHERE id = ?",
                (user_id, application_id)
            )

            # Начисляем бонус за принятие фиксированной заявки (2 баллов)
            bonus_data = db.fetch_one("select value from rating_rules "
                                      "where rule_type = 'executor'"
                                      "and rule_name = 'Принятие заявки'"
                                      "and is_active = 1")
            bonus_amount = bonus_data['value'] if bonus_data else 2.0
            update_user_rating_on_completion(db, user_id, application_id, bonus_amount, "Принятие заявки", 'executor')

        elif action_type == 'accept-auction':
            status = 'accepted_budget'
            # Бонус за принятие аукционной заявки по бюджету (3 балла)
            rating_type = ''
            if user_info['role'] == ['executor', 'external_executor']:
                rating_type = 'executor'
            rating_data = db.fetch_one("""
                SELECT current_rating FROM user_ratings 
                WHERE user_id = ? AND rating_type = ?
            """, (user_id, rating_type))

            bonus_data = db.fetch_one("select value from rating_rules "
                                      "where rule_type = 'executor'"
                                      "and rule_name = 'Принятие заявки'"
                                      "and is_active = 1")
            bonus_amount = bonus_data['value'] if bonus_data else 2.0
            update_user_rating_on_completion(db, user_id, application_id, bonus_amount, "Принятие заявки", 'executor')
        else:  # bid-auction
            status = 'counter_offer'
            # Бонус за активность - встречное предложение (2 балла)
            rating_type = ''
            if user_info['role'] == ['executor', 'external_executor']:
                rating_type = 'executor'
        # Сохраняем отклик
        db.execute_query(
            """INSERT INTO application_responses 
            (application_id, executor_id, status, payment_options, company_inn, created_at) 
            VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (application_id, user_id, status,
             json.dumps(selected_payments),
             company_info.get('inn', '') if company_info else '')
        )

        response_id = db.fetch_one(
            "SELECT last_insert_rowid() as id"
        )['id']

        # Отправляем уведомление логисту
        notify_logist_about_response(bot, db, application_id, user_id, status, selected_payments)

        # Экспортируем в Google Sheets
        try:
            export_response_to_google_sheets(db, application_id, response_id, user_id, status, selected_payments)
            print(f"✅ Ответ на заявку #{application_id} экспортирован в Google Sheets")
        except Exception as e:
            print(f"❌ Ошибка экспорта в Google Sheets: {e}")

        # Показываем сообщение об успехе с информацией о рейтинге
        if action_type == 'accept-fixed':
            success_text = f"✅ **Заявка принята!**\n\nЗаявка успешно принята. Логист свяжется с вами для уточнения деталей.\n"
        elif action_type == 'accept-auction':
            success_text = f"✅ **Заявка принята по бюджету!**\n\nВаше предложение отправлено логисту. Ожидайте ответа.\n"
        else:  # bid-auction
            success_text = f"✅ **Встречное предложение отправлено!**\n\nВаше ценовое предложение отправлено логисту. Ожидайте ответа.\n"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=success_text,
            parse_mode='Markdown'
        )

        # Очищаем временные данные
        if user_id in application_temp_data:
            del application_temp_data[user_id]

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

    # Обработчики для ввода ставок
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id).startswith(
        'waiting_for_executor_') and '_price' in get_user_state(message.from_user.id))
    def handle_price_input(message):
        user_id = message.from_user.id
        current_state = get_user_state(user_id)

        if user_id not in application_temp_data:
            bot.send_message(message.chat.id, "❌ Сессия истекла. Начните заново.")
            set_user_state(user_id, '')
            return

        # Извлекаем тип оплаты из состояния
        payment_type = current_state.replace('waiting_for_executor_', '').replace('_price', '')

        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            if price <= 0:
                bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0. Введите корректную сумму:")
                return

            # Сохраняем ставку
            if 'selected_payments' not in application_temp_data[user_id]:
                application_temp_data[user_id]['selected_payments'] = {}

            application_temp_data[user_id]['selected_payments'][payment_type] = price

            # Возвращаемся к выбору вариантов оплаты
            application_id = application_temp_data[user_id]['responding_application']

            # Получаем варианты оплаты из заявки
            application = db.fetch_one("SELECT payment_options FROM applications WHERE id = ?", (application_id,))
            payment_options = {}
            if application and application['payment_options']:
                try:
                    payment_options = ast.literal_eval(application['payment_options'])
                except:
                    pass

            # Формируем информацию о введенных ставках
            entered_count = len(application_temp_data[user_id]['selected_payments'])
            entered_info = ""
            if entered_count > 0:
                entered_info = f"✅ Введено ставок: {entered_count}\n\n"

            bot.send_message(
                message.chat.id,
                f"💰 **Введите ваши ставки:**\n\n{entered_info}"
                "Вы можете ввести ставки для одного или нескольких вариантов оплаты.\n"
                "✅ - означает, что ставка введена\n\n"
                "Нажмите на вариант оплаты, чтобы ввести ставку:\n"
                f"⠀",  # Невидимый символ для уникальности
                reply_markup=get_payment_options_keyboard(
                    application_id,
                    payment_options,
                    'bid-auction',
                    application_temp_data[user_id]['selected_payments']
                ),
                parse_mode='Markdown'
            )

            set_user_state(user_id, '')

        except ValueError:
            bot.send_message(message.chat.id, "❌ Пожалуйста, введите корректную сумму (только цифры):")


def get_payment_type_name(payment_type):
    """Возвращает читаемое название типа оплаты"""
    names = {
        'nds': 'С НДС',
        'ip': 'Без НДС',
        'cash': 'Наличные'
    }
    return names.get(payment_type, payment_type)


def get_application_preview_keyboard(application_id):
    """Создает клавиатуру для предпросмотра заявки"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📋 ОЗНАКОМИТЬСЯ", callback_data=f"view_application_{application_id}"),
    )
    return keyboard


def get_fixed_application_keyboard(application_id, map_url=None, logist_phone=None):
    """Создает клавиатуру для фиксированной заявки"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Первый ряд: основные действия
    row1 = [
        InlineKeyboardButton("✅ ПРИНЯТЬ", callback_data=f"accept-fixed_{application_id}"),
        InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_application_{application_id}")
    ]
    keyboard.add(*row1)

    # Второй ряд: дополнительные действия
    row2 = []
    if map_url:
        row2.append(InlineKeyboardButton("🗺️ Построить маршрут", url=map_url))
    if logist_phone:
        row2.append(InlineKeyboardButton("📞 ПОЗВОНИТЬ", callback_data=f"call_logist_{application_id}"))

    if row2:
        keyboard.add(*row2)
    keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_applications"))
    return keyboard


def get_auction_application_keyboard(application_id, map_url=None, logist_phone=None):
    """Создает клавиатуру для аукционной заявки"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Первый ряд: основные действия
    row1 = [
        InlineKeyboardButton("✅ ПРИНЯТЬ", callback_data=f"accept-auction_{application_id}"),
        InlineKeyboardButton("💰 ВСТРЕЧНОЕ", callback_data=f"bid-auction_{application_id}")
    ]
    keyboard.add(*row1)

    # Второй ряд: дополнительные действия
    row2 = [
        InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_application_{application_id}")
    ]
    keyboard.add(*row2)

    # Третий ряд: вспомогательные действия
    row3 = []
    if map_url:
        row3.append(InlineKeyboardButton("🗺️ Построить маршрут", url=map_url))
    if logist_phone:
        row3.append(InlineKeyboardButton("📞 ПОЗВОНИТЬ", callback_data=f"call_logist_{application_id}"))

    if row3:
        keyboard.add(*row3)
    keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_applications"))

    return keyboard


def get_payment_options_keyboard(application_id, payment_options, action_type, selected_payments=None):
    """Создает клавиатуру для выбора вариантов оплаты"""
    if selected_payments is None:
        selected_payments = {}

    keyboard = InlineKeyboardMarkup(row_width=2)

    parsed_options = {}
    if payment_options:
        try:
            # Используем ast.literal_eval для консистентности
            if isinstance(payment_options, str):
                parsed_options = ast.literal_eval(payment_options)
            else:
                parsed_options = payment_options
        except Exception as e:
            print(f"Ошибка парсинга payment_options в клавиатуре: {e}")
            parsed_options = {}

    # Добавляем кнопки для каждого варианта оплата
    buttons = []
    for payment_type in ['nds', 'ip', 'cash']:
        # Проверяем, нужно ли показывать этот вариант оплаты
        should_show = False

        if action_type == 'accept-fixed':
            # Для фиксированной заявки показываем только те варианты, которые есть в заявке
            should_show = payment_type in parsed_options
        elif action_type == 'accept-auction':
            # Для принятия аукциона по бюджету показываем все варианты
            should_show = True
        elif action_type == 'bid-auction':
            # Для встречного предложения показываем все варианты
            should_show = True

        if not should_show:
            continue

        display_name = get_payment_type_name(payment_type)

        # Формируем текст кнопки в зависимости от типа действия
        if action_type == 'bid-auction':
            # Для встречного предложения
            if payment_type in selected_payments:
                button_text = f"✅ {display_name}: {selected_payments[payment_type]:,.0f} руб."
            else:
                button_text = f"{display_name} (ввести ставку)"
        elif action_type == 'accept-fixed':
            # Для фиксированной заявки
            price = parsed_options.get(payment_type, 0)
            if payment_type in selected_payments:
                button_text = f"✅ {display_name}: {float(price):,.0f} руб."
            else:
                button_text = f"{display_name}: {float(price):,.0f} руб."
        elif action_type == 'accept-auction':
            # Для принятия аукциона по бюджету
            if payment_type in selected_payments:
                button_text = f"✅ {display_name}"
            else:
                button_text = f"{display_name}"

        buttons.append(InlineKeyboardButton(
            button_text,
            callback_data=f"select_payment_{action_type}_{application_id}_{payment_type}"
        ))

    # Добавляем кнопки в клавиатуру
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.add(buttons[i], buttons[i + 1])
        else:
            keyboard.add(buttons[i])

    # Кнопка подтверждения (только если есть выбранные варианты или это встречное предложение)
    if selected_payments or action_type in ['accept-fixed', 'accept-auction']:
        keyboard.add(InlineKeyboardButton(
            "✅ ПОДТВЕРДИТЬ ВЫБОР",
            callback_data=f"confirm_payments_{action_type}_{application_id}"
        ))

    return keyboard


def get_back_to_payments_keyboard(application_id, action_type):
    """Создает клавиатуру для возврата к выбору оплаты"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("↩️ Назад к выбору оплаты", callback_data=f"bid-auction_{application_id}")
    )
    return keyboard


def get_company_confirmation_keyboard(application_id, action_type):
    """Создает клавиатуру для подтверждения компании"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("✅ ПОДТВЕРДИТЬ", callback_data=f"confirm_company_{action_type}_{application_id}")
    )
    return keyboard


def get_cargo_info(application):
    """Возвращает информацию о грузе в форматированном виде"""
    cargo_type = application.get('cargo_custom_type', 'Не указан') if application.get('cargo_type') == 'ПРОЧЕЕ' else application.get('cargo_type', 'Не указан')
    # cargo_type = application.get('cargo_custom_type') or application.get('cargo_type', 'Не указан')

    return {
        'type': cargo_type,
        'weight': application.get('weight', 'Не указан'),
        'volume': application.get('volume', 'Не указан'),
    }


def format_detailed_application(db, application, loading_points, unloading_points, cargo_info, logist_info,
                                payment_deadline=None):
    """
    Форматирует детальную информацию о заявке с учетом нескольких точек погрузки и выгрузки
    """
    from utils.helpers import format_datetime

    # Создаем текстовое представление заявки
    detailed_text = f"""
📋 **ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ЗАЯВКЕ**

🎯 **Заявка #{application['id']}**
📅 Дата создания: {format_datetime(application['created_at'])}

"""

    # Тип заявки
    if application['application_type'] == 'fixed':
        detailed_text += f"📦 **Тип:** СТАНДАРТНАЯ (с фиксированной ставкой)\n"
    else:
        detailed_text += f"🏷️ **Тип:** ЗАПРОС СТАВОК (Аукцион)\n"
        desired_budget = application.get('desired_budget')
        if desired_budget:
            detailed_text += f"🎯 **Бюджет:** {float(desired_budget):,.0f} руб.\n"

    detailed_text += "\n"

    # Маршрут с несколькими точками
    detailed_text += "🗺️ **МАРШРУТ:**\n"

    if loading_points:
        detailed_text += f"📍 **Точки погрузки ({len(loading_points)}):**\n"
        for i, point in enumerate(loading_points, 1):
            city = point.get('city', 'Не указан')
            address = point.get('address', 'Не указан')
            detailed_text += f"   {i}. **{city}**\n"
            detailed_text += f"      📍 Адрес: {address}\n"

            # Получаем дату и время из поля point_datetime
            point_datetime = point.get('point_datetime')
            if point_datetime:
                try:
                    if isinstance(point_datetime, str):
                        # Пробуем разные форматы
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d.%m.%Y %H:%M']:
                            try:
                                dt = datetime.strptime(point_datetime, fmt)
                                detailed_text += f"      📅 Дата/время: {dt.strftime('%d.%m.%Y %H:%M')}\n"
                                break
                            except:
                                continue
                        else:
                            detailed_text += f"      📅 Дата/время: {point_datetime}\n"
                    else:
                        # Если это datetime объект
                        detailed_text += f"      📅 Дата/время: {point_datetime.strftime('%d.%m.%Y %H:%M')}\n"
                except:
                    detailed_text += f"      📅 Дата/время: {point_datetime}\n"

            # Координаты, если есть
            if point.get('coordinates'):
                try:
                    coords = json.loads(point['coordinates'])
                    detailed_text += f"      🗺️ Координаты: {coords['lat']:.6f}, {coords['lon']:.6f}\n"
                except:
                    pass

            detailed_text += "\n"

    if unloading_points:
        detailed_text += f"🏁 **Точки выгрузки ({len(unloading_points)}):**\n"
        for i, point in enumerate(unloading_points, 1):
            city = point.get('city', 'Не указан')
            address = point.get('address', 'Не указан')
            detailed_text += f"   {i}. **{city}**\n"
            detailed_text += f"      📍 Адрес: {address}\n"

            # Получаем дату и время из поля point_datetime
            point_datetime = point.get('point_datetime')
            if point_datetime:
                try:
                    if isinstance(point_datetime, str):
                        # Пробуем разные форматы
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d.%m.%Y %H:%M']:
                            try:
                                dt = datetime.strptime(point_datetime, fmt)
                                detailed_text += f"      📅 Дата/время: {dt.strftime('%d.%m.%Y %H:%M')}\n"
                                break
                            except:
                                continue
                        else:
                            detailed_text += f"      📅 Дата/время: {point_datetime}\n"
                    else:
                        detailed_text += f"      📅 Дата/время: {point_datetime.strftime('%d.%m.%Y %H:%M')}\n"
                except:
                    detailed_text += f"      📅 Дата/время: {point_datetime}\n"

            # Координаты, если есть
            if point.get('coordinates'):
                try:
                    coords = json.loads(point['coordinates'])
                    detailed_text += f"      🗺️ Координаты: {coords['lat']:.6f}, {coords['lon']:.6f}\n"
                except:
                    pass

            if i < len(unloading_points):
                detailed_text += "\n"

    detailed_text += "\n"

    # Добавляем информацию о грузе
    detailed_text += f"📦 **ИНФОРМАЦИЯ О ГРУЗЕ:**\n"

    # Тип груза
    cargo_type = cargo_info.get('type', 'Не указан')
    if cargo_type == "ПРОЧЕЕ" and application.get('cargo_custom_type'):
        cargo_type = application['cargo_custom_type']

    from utils.dicts import CARGO_TYPE_REVERSE_MAPPING
    detailed_text += f"   🏷️ **Тип:** {CARGO_TYPE_REVERSE_MAPPING.get(cargo_type, cargo_type)}\n"

    # Транспорт
    from utils.dicts import VEHICLE_TYPE_REVERSE_MAPPING
    vehicle_type = application.get('vehicle_type', 'Не указан')
    detailed_text += f"   🚛 **Требуемый транспорт:** {VEHICLE_TYPE_REVERSE_MAPPING.get(vehicle_type, vehicle_type)}\n"

    # Вес и объем
    detailed_text += f"   ⚖️ **Вес:** {cargo_info.get('weight', 'Не указан')} т\n"
    detailed_text += f"   📦 **Объем:** {cargo_info.get('volume', 'Не указан')} м³\n\n"

    # Срок оплаты
    if payment_deadline:
        try:
            if isinstance(payment_deadline, str):
                # Пробуем разные форматы даты
                for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S']:
                    try:
                        deadline_date = datetime.strptime(payment_deadline, fmt)
                        detailed_text += f"📅 **Срок оплаты:** до {deadline_date.strftime('%d.%m.%Y')}\n\n"
                        break
                    except:
                        continue
                else:
                    detailed_text += f"📅 **Срок оплаты:** до {payment_deadline}\n\n"
            else:
                detailed_text += f"📅 **Срок оплаты:** до {payment_deadline.strftime('%d.%m.%Y')}\n\n"
        except:
            detailed_text += f"📅 **Срок оплаты:** до {payment_deadline}\n\n"

    # Примечания
    if application.get('notes'):
        detailed_text += f"📝 **Примечания:** {application['notes']}\n\n"

    # Информация о логисте
    if logist_info:
        detailed_text += "👤 **ЛОГИСТ:**\n"
        full_name = f"{logist_info.get('first_name', '')} {logist_info.get('last_name', '')}".strip()
        if full_name:
            detailed_text += f"   👤 **ФИО:** {full_name}\n"
        if logist_info.get('phone'):
            detailed_text += f"   📞 **Телефон:** {logist_info['phone']}\n"
        if logist_info.get('email'):
            detailed_text += f"   📧 **Email:** {logist_info['email']}\n"

        # Информация о компании логиста
        if logist_info.get('company_id'):
            company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (logist_info['company_id'],))
            if company:
                detailed_text += f"   🏢 **Компания:** {company.get('name', 'Не указана')}\n"
                if company.get('ati_code'):
                    detailed_text += f"   🔢 **ATI код:** {company['ati_code']}\n"

    return detailed_text

def notify_logist_about_response(bot, db, application_id, executor_id, response_type, payment_options):
    """Уведомляет логиста о response перевозчика"""
    application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
    executor = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (executor_id,))
    company_info = db.fetch_one("SELECT * FROM companies WHERE id = ?",
                                (executor.get('company_id'),)) if executor.get('company_id') else None

    if not application or not executor:
        return

    logist_id = application['created_by']

    # Формируем текст с вариантами оплаты
    payments_text = ""
    for payment_type, amount in payment_options.items():
        payments_text += f"• {get_payment_type_name(payment_type)}: {amount:,.0f} руб.\n"

    # Получаем информацию о заявке для текста
    app_budget = application.get('desired_budget', 0)
    try:
        budget_value = float(app_budget)
        budget_text = f"{budget_value:,.0f} руб."
    except (ValueError, TypeError):
        budget_text = "не указан"

    if response_type == 'accepted':
        message_text = f"""
✅ **Перевозчик принял вашу заявку!**

📦 Заявка #{application_id}
👤 **Перевозчик:** {executor['first_name']} {executor.get('last_name', '')}
🏢 **Компания:** {company_info.get('name', 'Не указана') if company_info else 'Не указана'}
🏢 **ИНН:** {company_info.get('inn', 'Не указан') if company_info else 'Не указан'}
📞 **Телефон:** {executor.get('phone', 'Не указан')}

**Выбранные варианты оплаты:**
{payments_text}

Свяжитесь с перевозчиком для уточнения деталей.
        """.strip()
    elif response_type == 'accepted_budget':
        message_text = f"""
✅ **Перевозчик принял заявку по бюджету!**

📦 Заявка #{application_id}
💰 **Бюджет заявки:** {budget_text}
👤 **Перевозчик:** {executor['first_name']} {executor.get('last_name', '')}
🏢 **Компания:** {company_info.get('name', 'Не указана') if company_info else 'Не указана'}
📞 **Телефон:** {executor.get('phone', 'Не указан')}

**Выбранные варианты оплаты:**
{payments_text}

Свяжитесь с перевозчиком для уточнения деталей.
        """.strip()
    else:  # counter_offer
        message_text = f"""
💵 **Новое встречное предложение!**

📦 Заявка #{application_id}
💰 **Бюджет заявки:** {budget_text}
👤 **Перевозчик:** {executor['first_name']} {executor.get('last_name', '')}
🏢 **Компания:** {company_info.get('name', 'Не указана') if company_info else 'Не указана'}
📞 **Телефон:** {executor.get('phone', 'Не указан')}

**Предложенные ставки:**
{payments_text}

Рассмотрите предложение и свяжитесь с перевозчиком.
        """.strip()

    try:
        bot.send_message(logist_id, message_text, parse_mode='Markdown')
    except Exception as e:
        print(f"Не удалось уведомить логиста {logist_id}: {e}")


def notify_executor_about_selection(bot, db, application_id, executor_id):
    """Уведомляет перевозчика о выборе его предложения"""
    application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
    logist = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (application['created_by'],))

    if not application or not logist:
        return

    message_text = f"""
🎉 **Ваше предложение выбрано!**

📦 Заявка #{application_id} принята в работу.

👤 **Логист:** {logist['first_name']} {logist.get('last_name', '')}
📞 **Телефон:** {logist.get('phone', 'Не указан')}
📧 **Email:** {logist.get('email', 'Не указан')}

Свяжитесь с логистом для уточнения деталей выполнения заявки.
    """.strip()

    try:
        bot.send_message(executor_id, message_text, parse_mode='Markdown')
    except Exception as e:
        print(f"Не удалось уведомить перевозчика {executor_id}: {e}")


def notify_other_executors_about_rejection(bot, db, application_id, selected_executor_id):
    """Уведомляет остальных перевозчиков об отказе"""
    # Получаем всех перевозчиков, кроме выбранного
    other_executors = db.fetch_all("""
        SELECT DISTINCT executor_id 
        FROM application_responses 
        WHERE application_id = ? 
            AND executor_id != ? 
            AND status IN ('counter_offer', 'accepted_budget')
    """, (application_id, selected_executor_id))

    application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))

    if not application:
        return

    for executor in other_executors:
        executor_id = executor['executor_id']
        message_text = f"""
ℹ️ **По заявке #{application_id} выбран другой перевозчик.**

К сожалению, ваше предложение не было выбрано для выполнения заявки.

Спасибо за участи! Вы можете продолжить поиск других заявок в разделе "🔔 Новые заявки".
        """.strip()

        try:
            bot.send_message(executor_id, message_text, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить перевозчика {executor_id}: {e}")


def generate_yandex_maps_url(loading_points, unloading_points):
    """
    Генерирует URL для Яндекс.Карт с поддержкой нескольких точек погрузки и выгрузки
    """
    all_points = loading_points + unloading_points
    valid_points = []

    # Собираем все точки с координатами
    for point in all_points:
        if point.get('coordinates'):
            try:
                coords = json.loads(point['coordinates'])
                if 'lat' in coords and 'lon' in coords:
                    valid_points.append({
                        'coords': coords,
                        'type': point['point_type'],
                        'city': point.get('city', ''),
                        'address': point.get('address', '')
                    })
            except (json.JSONDecodeError, TypeError):
                continue

    if not valid_points:
        return None

    # Если точек больше одной, строим маршрут с несколькими точками
    if len(valid_points) >= 2:
        # Сортируем: сначала точки погрузки, потом выгрузки
        loading_coords = [p for p in valid_points if p['type'] == 'loading']
        unloading_coords = [p for p in valid_points if p['type'] == 'unloading']

        # Формируем rtext: координаты через ~
        coordinates_list = []
        labels_list = []

        # Добавляем точки погрузки
        for i, point in enumerate(loading_coords):
            coord_str = f"{point['coords']['lat']},{point['coords']['lon']}"
            coordinates_list.append(coord_str)
            if point.get('city'):
                labels_list.append(f"Погрузка {i + 1}: {point['city']}")
            else:
                labels_list.append(f"Погрузка {i + 1}")

        # Добавляем точки выгрузки
        for i, point in enumerate(unloading_coords):
            coord_str = f"{point['coords']['lat']},{point['coords']['lon']}"
            coordinates_list.append(coord_str)
            if point.get('city'):
                labels_list.append(f"Выгрузка {i + 1}: {point['city']}")
            else:
                labels_list.append(f"Выгрузка {i + 1}")

        if coordinates_list:
            rtext = "~".join(coordinates_list)
            # Формируем pt строку для маркеров на карте
            pt_str = "~".join(coordinates_list)

            # Рассчитываем средние координаты для центра карты
            avg_lat = sum(float(c.split(',')[0]) for c in coordinates_list) / len(coordinates_list)
            avg_lon = sum(float(c.split(',')[1]) for c in coordinates_list) / len(coordinates_list)

            # Формируем URL с поддержкой нескольких точек
            map_url = f"https://yandex.ru/maps/?ll={avg_lon},{avg_lat}&mode=routes&pt={pt_str}&rtext={rtext}&rtt=auto"
            return map_url
    elif len(valid_points) == 1:
        # Если только одна точка, показываем ее
        point = valid_points[0]
        map_url = f"https://yandex.ru/maps/?ll={point['coords']['lon']},{point['coords']['lat']}&z=12"
        return map_url

    return None