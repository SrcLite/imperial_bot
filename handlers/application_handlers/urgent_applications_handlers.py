import json
import ast
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from handlers.application_handlers.display_application_handlers import format_application_for_executor
from handlers.application_handlers.executor_application_handlers import format_detailed_application
from handlers.application_handlers.google_sheets_export import export_response_to_google_sheets
from handlers.registration_handlers.registration_user_handlers import get_user_state
from utils.helpers import update_user_rating_on_completion

application_temp_data = {}


def register_urgent_applications_handlers(bot, db):
    """Регистрация обработчиков для срочных заявок"""

    # Словарь для хранения временных данных (аналогично user_application_data)
    urgent_application_data = {}

    @bot.message_handler(func=lambda message: message.text == '🚨 Срочные заявки')
    def show_urgent_applications(message):
        """Показывает срочные заявки перевозчику с постраничной навигацией"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)

        if user['status'] != 'active':
            bot.send_message(chat_id, "❌ Администратор не подтвердил вашу учетную запись.",
                             reply_markup=ReplyKeyboardRemove())
            return

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['executor', 'external_executor']:
            bot.send_message(chat_id, "❌ Эта функция доступна только перевозчикам.")
            return

        # Получаем срочные заявки, исключая те, которые пользователь уже отклонил или откликнулся
        applications = db.fetch_all("""
                SELECT DISTINCT a.*, u.first_name, u.last_name, u.phone as logist_phone, u.email,
                       -- Получаем минимальную дату погрузки (первая точка погрузки)
                       (
                           SELECT MIN(point_datetime) 
                           FROM application_points 
                           WHERE application_id = a.id AND point_type = 'loading'
                       ) as first_loading_datetime
                FROM applications a 
                JOIN users u ON a.created_by = u.telegram_id 
                LEFT JOIN application_responses ar ON a.id = ar.application_id AND ar.executor_id = ?
                WHERE a.status = 'urgent' 
                AND (ar.id IS NULL OR (ar.status NOT IN ('rejected', 'rejected_by_executor')))
                AND a.created_by != ?  -- Исключаем свои собственные заявки
                AND (
                    -- Проверяем, что дата первой погрузки не просрочена (с запасом 1 час)
                    EXISTS (
                        SELECT 1 FROM application_points 
                        WHERE application_id = a.id 
                        AND point_type = 'loading' 
                        AND point_datetime > datetime('now', '-1 hour')
                    )
                    OR NOT EXISTS ( -- Если нет точек погрузки, считаем валидной
                        SELECT 1 FROM application_points 
                        WHERE application_id = a.id AND point_type = 'loading'
                    )
                )
                ORDER BY 
                    CASE 
                        -- Сначала заявки, где погрузка в ближайшие 24 часа
                        WHEN EXISTS (
                            SELECT 1 FROM application_points 
                            WHERE application_id = a.id 
                            AND point_type = 'loading' 
                            AND point_datetime BETWEEN datetime('now') AND datetime('now', '+1 day')
                        ) THEN 1
                        ELSE 2
                    END,
                    a.created_at DESC
            """, (user_id, user_id))

        if not applications:
            bot.send_message(chat_id, "📭 Срочных заявок нет. Все срочные заявки уже обработаны.")
            return

        # Сохраняем заявки для этого пользователя
        if user_id not in urgent_application_data:
            urgent_application_data[user_id] = {}

        urgent_application_data[user_id]['applications'] = applications
        urgent_application_data[user_id]['current_index'] = 0
        urgent_application_data[user_id]['message_id'] = None

        # Показываем первую срочную заявку
        show_urgent_application_page(user_id, chat_id, 0, is_new=True)

    def show_urgent_application_page(user_id, chat_id, index, is_new=False):
        """Показывает срочную заявку по указанному индексу"""
        if user_id not in urgent_application_data or not urgent_application_data[user_id].get('applications'):
            bot.send_message(chat_id, "❌ Данные о срочных заявках устарели. Нажмите '🚨 Срочные заявки' снова.")
            return

        applications = urgent_application_data[user_id]['applications']

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

        # Добавляем заголовок срочности и нумерацию страниц
        urgency_header = "🚨 **СРОЧНАЯ ЗАЯВКА** 🚨\n\n"

        page_info = f"\n\n📄 Страница {index + 1} из {len(applications)}"
        full_text = urgency_header + application_text + page_info

        # Создаем клавиатуру с навигацией для срочных заявок
        keyboard = get_urgent_application_navigation_keyboard(app['id'], index, len(applications))

        if is_new:
            # Отправляем новое сообщение
            msg = bot.send_message(
                chat_id,
                full_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            urgent_application_data[user_id]['message_id'] = msg.message_id
        else:
            # Редактируем существующее сообщение
            message_id = urgent_application_data[user_id].get('message_id')
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
                    urgent_application_data[user_id]['message_id'] = msg.message_id

        # Обновляем текущий индекс
        urgent_application_data[user_id]['current_index'] = index

    def get_urgent_application_navigation_keyboard(application_id, current_index, total_count):
        """Создает клавиатуру с навигацией по срочным заявкам"""
        keyboard = InlineKeyboardMarkup(row_width=3)

        # Кнопки навигации
        nav_buttons = []

        if current_index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"urgent_nav_prev_{current_index}"))

        nav_buttons.append(
            InlineKeyboardButton("📋 ОЗНАКОМИТЬСЯ", callback_data=f"urgent_view_application_{application_id}"))

        if current_index < total_count - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"urgent_nav_next_{current_index}"))

        keyboard.add(*nav_buttons)

        # Кнопка закрыть
        keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_urgent_applications"))

        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_nav_'))
    def handle_urgent_navigation(call):
        """Обработка навигации по срочным заявкам"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        direction = data_parts[2]  # prev или next
        current_index = int(data_parts[3])

        if user_id not in urgent_application_data:
            bot.answer_callback_query(call.id, "❌ Сессия просмотра истекла")
            return

        applications = urgent_application_data[user_id].get('applications', [])

        if not applications:
            bot.answer_callback_query(call.id, "❌ Нет доступных срочных заявок")
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
        show_urgent_application_page(user_id, chat_id, new_index, is_new=False)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'close_urgent_applications')
    def handle_close_urgent_applications(call):
        """Закрывает просмотр срочных заявок"""
        user_id = call.from_user.id

        # Удаляем сообщение с заявками
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Очищаем данные пользователя
        if user_id in urgent_application_data:
            del urgent_application_data[user_id]

        bot.answer_callback_query(call.id, "✅ Просмотр срочных заявок завершен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_view_application_'))
    def handle_urgent_view_application(call):
        """Обработка нажатия кнопки 'ОЗНАКОМИТЬСЯ' для срочных заявок"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[3])

        # Очищаем данные о просмотре заявок
        if user_id in urgent_application_data:
            del urgent_application_data[user_id]

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

        # Формируем ссылку для Яндекс.Карт
        map_url = generate_yandex_maps_url(loading_points, unloading_points)

        # Получаем информацию о грузе
        cargo_info = get_cargo_info(application)

        # Получаем контактные данные логиста
        logist_info = db.fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?",
            (application['created_by'],)
        )

        # Форматируем детальную информацию о заявке с пометкой срочности
        detailed_text = format_urgent_detailed_application(
            db, application, loading_points, unloading_points, cargo_info, logist_info
        )

        # Создаем клавиатуру в зависимости от типа заявки
        if application['application_type'] == 'fixed':
            keyboard = get_urgent_fixed_application_keyboard(application_id, map_url,
                                                             logist_info.get('phone') if logist_info else None)
        else:
            keyboard = get_urgent_auction_application_keyboard(application_id, map_url,
                                                               logist_info.get('phone') if logist_info else None)

        # Редактируем сообщение с заявкой
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=detailed_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "📋 Подробная информация о срочной заявке")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_reject_application_'))
    def handle_urgent_reject_application(call):
        """Обработка нажатия кнопки 'ОТКЛОНИТЬ' для срочных заявок"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[3])

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

        # Экспортируем в Google Sheets
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

        bot.answer_callback_query(call.id, "❌ Срочная заявка отклонена")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_accept-fixed_'))
    def handle_urgent_accept_fixed(call):
        """Обработка нажатия кнопки 'ПРИНЯТЬ' для срочной фиксированной заявки"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[2])

        from handlers.application_handlers.creation_application_handlers import application_temp_data

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
        application_temp_data[user_id]['is_urgent'] = True  # Флаг, что это срочная заявка

        # Получаем варианты оплаты из заявки
        payment_options = {}
        if application.get('payment_options'):
            try:
                payment_options = ast.literal_eval(application['payment_options'])
            except Exception as e:
                print(f"Ошибка парсинга payment_options в handle_urgent_accept_fixed: {e}")
                print(f"Данные: {application['payment_options']}")

        # Показываем варианты оплаты для выбора
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💰 **Выберите варианты оплаты (СРОЧНАЯ ЗАЯВКА):**\n\n"
                 "Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n"
                 "✅ - означает, что вариант выбран\n\n"
                 "Нажмите на вариант оплаты, чтобы выбрать или снять выбор:\n"
                 f"⠀",
            reply_markup=get_urgent_payment_options_keyboard(application_id, payment_options, 'accept-fixed'),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_bid-auction_'))
    def handle_urgent_bid_auction(call):
        """Обработка нажатия кнопки 'ВСТРЕЧНОЕ' для срочного аукциона"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[2])

        from handlers.application_handlers.creation_application_handlers import application_temp_data

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
        application_temp_data[user_id]['is_urgent'] = True  # Флаг, что это срочная заявка

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
            text="💰 **Введите ваши ставки (СРОЧНАЯ ЗАЯВКА):**\n\n"
                 "Вы можете ввести ставки для одного или нескольких вариантов оплата.\n"
                 "✅ - означает, что ставка введена\n\n"
                 "Нажмите на вариант оплаты, чтобы ввести ставку:\n"
                 f"⠀",
            reply_markup=get_urgent_payment_options_keyboard(application_id, payment_options, 'bid-auction'),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_accept-auction_'))
    def handle_urgent_accept_auction(call):
        """Обработка нажатия кнопки 'ПРИНЯТЬ' для срочного аукциона (по бюджету)"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[2])

        from handlers.application_handlers.creation_application_handlers import application_temp_data

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
        application_temp_data[user_id]['is_urgent'] = True  # Флаг, что это срочная заявка

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
            text=f"💰 **Выберите варианты оплаты (СРОЧНАЯ ЗАЯВКА):**\n\n"
                 f"Бюджет заявки: {float(application.get('desired_budget', 0)):,.0f} руб.\n\n"
                 "Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n"
                 "✅ - означает, что вариант выбран\n\n"
                 "Нажмите на вариант оплаты, чтобы выбрать или снять выбор:\n"
                 f"⠀",
            reply_markup=get_urgent_payment_options_keyboard(application_id, payment_options, 'accept-auction'),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    # Обработчики для кнопок оплаты (используем те же, что и для обычных заявок, но с префиксом urgent_)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_select_payment_'))
    def handle_urgent_select_payment(call):
        """Обработка выбора варианта оплаты для срочных заявок"""
        user_id = call.from_user.id
        data_parts = call.data.split('_')
        action_type = data_parts[3]  # accept-fixed, accept-auction, bid-auction
        application_id = int(data_parts[4])
        payment_type = data_parts[5]

        from handlers.application_handlers.creation_application_handlers import application_temp_data

        if user_id not in application_temp_data or application_temp_data[user_id].get(
                'responding_application') != application_id:
            bot.answer_callback_query(call.id, "❌ Сессия истекла. Начните заново.")
            return

        # Для встречного предложения - запрашиваем ввод ставки
        if action_type == 'bid-auction':
            if 'selected_payments' not in application_temp_data[user_id]:
                application_temp_data[user_id]['selected_payments'] = {}

            bot.send_message(
                call.message.chat.id,
                f"💵 **Введите ставку для {get_payment_type_name(payment_type)} (в рублях, СРОЧНАЯ ЗАЯВКА):**",
                reply_markup=get_urgent_back_to_payments_keyboard(application_id, action_type)
            )
            from handlers.registration_handlers.registration_user_handlers import set_user_state
            set_user_state(user_id, f'waiting_for_executor_urgent_{payment_type}_price')
            application_temp_data[user_id]['current_payment_type'] = payment_type

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
                        print(f"Ошибка парсинга payment_options в handle_urgent_select_payment: {e}")
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
            bot.answer_callback_query(call.id)
            return

        # Обновляем клавиатуру
        application = db.fetch_one("SELECT payment_options FROM applications WHERE id = ?", (application_id,))
        payment_options = {}
        if application and application['payment_options']:
            try:
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
            text = f"💰 **Выберите варианты оплаты (СРОЧНАЯ ЗАЯВКА):**\n\n{selected_info}Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n✅ - означает, что вариант выбран\n\nНажмите на вариант оплаты, чтобы выбрать или снять выбор:\n⠀"
        elif action_type == 'accept-auction':
            text = f"💰 **Выберите варианты оплаты (СРОЧНАЯ ЗАЯВКА):**\n\nБюджет заявки: {float(application_temp_data[user_id].get('budget', 0)):,.0f} руб.\n\n{selected_info}Вы можете выбрать один или несколько вариантов оплаты, которые вам подходят.\n✅ - означает, что вариант выбран\n\nНажмите на вариант оплаты, чтобы выбрать или снять выбор:\n⠀"
        else:
            text = "💰 **Введите ваши ставки (СРОЧНАЯ ЗАЯВКА):**\n\nВы можете ввести ставки для одного или нескольких вариантов оплаты.\n✅ - означает, что ставка введена\n\nНажмите на вариант оплаты, чтобы ввести ставку:\n⠀"

        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=get_urgent_payment_options_keyboard(
                    application_id,
                    payment_options,
                    action_type,
                    application_temp_data[user_id]['selected_payments']
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                print(f"Ошибка при редактировании сообщения: {e}")

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_confirm_payments_'))
    def handle_urgent_confirm_payments(call):
        """Обработка подтверждения выбора оплаты для срочных заявок"""
        user_id = call.from_user.id
        data_parts = call.data.split('_')
        action_type = data_parts[3]  # accept-fixed, accept-auction, bid-auction
        application_id = int(data_parts[4])

        from handlers.application_handlers.creation_application_handlers import application_temp_data

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

        # Формируем текст с выбранными вариантами оплаты
        payments_text = ""
        total_selected = len(selected_payments)
        for payment_type, amount in selected_payments.items():
            payments_text += f"• {get_payment_type_name(payment_type)}: {amount:,.0f} руб.\n"

        # Определяем текст в зависимости от типа действия
        if action_type == 'accept-fixed':
            action_desc = "принял срочную заявку"
        elif action_type == 'accept-auction':
            action_desc = "принял срочную заявку по бюджету"
        else:
            action_desc = "сделал встречное предложение по срочной заявке"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🏢 **Подтвердите отправку отклика (СРОЧНАЯ ЗАЯВКА):**\n\n"
                 f"**Вы {action_desc} со следующими условиями:**\n\n"
                 f"**Выбранные варианты оплаты ({total_selected}):**\n{payments_text}\n"
                 f"**Ваша компания:** {company_info.get('name', 'Не указана')}\n"
                 f"**ИНН:** {company_info.get('inn', 'Не указан')}\n\n"
                 f"Нажмите '✅ ПОДТВЕРДИТЬ' для отправки отклика логисту.\n"
                 f"⠀",
            reply_markup=get_urgent_company_confirmation_keyboard(application_id, action_type),
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_confirm_company_'))
    def handle_urgent_confirm_company(call):
        """Обработка подтверждения компании для срочных заявок"""
        user_id = call.from_user.id
        data_parts = call.data.split('_')
        action_type = data_parts[3]  # accept-fixed, accept-auction, bid-auction
        application_id = int(data_parts[4])

        from handlers.application_handlers.creation_application_handlers import application_temp_data

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
            # Обновляем статус заявки на 'assigned' и убираем срочность
            db.execute_query(
                "UPDATE applications SET status = 'assigned', assigned_to = ? WHERE id = ?",
                (user_id, application_id)
            )

            # Начисляем бонус за принятие срочной фиксированной заявки (дополнительные баллы)
            bonus_data = db.fetch_one("select value from rating_rules "
                                      "where rule_type = 'executor' "
                                      "and rule_name = 'Принятие срочной заявки' "
                                      "and is_active = 1")
            bonus_amount = bonus_data['value'] if bonus_data else 4.0  # Больше баллов за срочную
            update_user_rating_on_completion(db, user_id, application_id, bonus_amount, "Принятие срочной заявки",
                                             'executor')

        elif action_type == 'accept-auction':
            status = 'accepted_budget'
            # Бонус за принятие срочной аукционной заявки по бюджету
            bonus_data = db.fetch_one("select value from rating_rules "
                                      "where rule_type = 'executor' "
                                      "and rule_name = 'Принятие срочной заявки' "
                                      "and is_active = 1")
            bonus_amount = bonus_data['value'] if bonus_data else 4.0
            update_user_rating_on_completion(db, user_id, application_id, bonus_amount, "Принятие срочной заявки",
                                             'executor')

        else:  # bid-auction
            status = 'counter_offer'
            # Бонус за активность - встречное предложение по срочной заявке
            bonus_data = db.fetch_one("select value from rating_rules "
                                      "where rule_type = 'executor' "
                                      "and rule_name = 'Отклик на срочную заявку' "
                                      "and is_active = 1")
            bonus_amount = bonus_data['value'] if bonus_data else 3.0
            update_user_rating_on_completion(db, user_id, application_id, bonus_amount, "Отклик на срочную заявку",
                                             'executor')

        # Сохраняем отклик
        db.execute_query(
            """INSERT INTO application_responses 
            (application_id, executor_id, status, payment_options, company_inn, created_at, is_urgent) 
            VALUES (?, ?, ?, ?, ?, datetime('now'), 1)""",
            (application_id, user_id, status,
             json.dumps(selected_payments),
             company_info.get('inn', '') if company_info else '')
        )

        response_id = db.fetch_one(
            "SELECT last_insert_rowid() as id"
        )['id']

        # Отправляем уведомление логисту (специальное для срочных заявок)
        notify_logist_about_urgent_response(bot, db, application_id, user_id, status, selected_payments)

        # Экспортируем в Google Sheets
        try:
            export_response_to_google_sheets(db, application_id, response_id, user_id, status, selected_payments)
            print(f"✅ Ответ на срочную заявку #{application_id} экспортирован в Google Sheets")
        except Exception as e:
            print(f"❌ Ошибка экспорта в Google Sheets: {e}")

        # Показываем сообщение об успехе с информацией о рейтинге
        if action_type == 'accept-fixed':
            success_text = f"✅ **Срочная заявка принята!**\n\nЗаявка успешно принята. Вы получили дополнительный бонус к рейтингу за оперативность!\nЛогист свяжется с вами для уточнения деталей.\n"
        elif action_type == 'accept-auction':
            success_text = f"✅ **Срочная заявка принята по бюджету!**\n\nВаше предложение отправлено логисту. Вы получили дополнительный бонус к рейтингу за оперативность!\nОжидайте ответа.\n"
        else:  # bid-auction
            success_text = f"✅ **Встречное предложение по срочной заявке отправлено!**\n\nВаше ценовое предложение отправлено логисту. Вы получили бонус к рейтингу за активность!\nОжидайте ответа.\n"

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

    @bot.callback_query_handler(func=lambda call: call.data.startswith('urgent_call_logist_'))
    def handle_urgent_call_logist(call):
        """Обработка нажатия кнопки 'ПОЗВОНИТЬ' для срочных заявок"""
        application_id = int(call.data.split('_')[3])

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
                f"📞 **Телефон логиста (СРОЧНАЯ ЗАЯВКА):** {phone_number}\n\n"
                f"Вы можете скопировать номер и позвонить.\n"
                f"Или используйте ссылку для звонка: [tel:{phone_number}](tel:{phone_number})",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(call.message.chat.id, "❌ Телефон логиста не указан.")

        bot.answer_callback_query(call.id)

    # Обработчики для ввода ставок для срочных заявок
    @bot.message_handler(func=lambda message:
    message.from_user.id in application_temp_data and
    application_temp_data[message.from_user.id].get('is_urgent') and
    any(state in get_user_state(message.from_user.id) for state in [
        'waiting_for_executor_urgent_nds_price',
        'waiting_for_executor_urgent_ip_price',
        'waiting_for_executor_urgent_self-employed_price',
        'waiting_for_executor_urgent_cash_price'
    ]))
    def handle_urgent_price_input(message):
        """Обработка ввода ставок для срочных заявок"""
        from handlers.application_handlers.creation_application_handlers import application_temp_data
        from handlers.registration_handlers.registration_user_handlers import get_user_state, set_user_state

        user_id = message.from_user.id
        current_state = get_user_state(user_id)

        if user_id not in application_temp_data:
            bot.send_message(message.chat.id, "❌ Сессия истекла. Начните заново.")
            set_user_state(user_id, '')
            return

        # Извлекаем тип оплаты из состояния
        payment_type = current_state.replace('waiting_for_executor_urgent_', '').replace('_price', '')

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
                f"💰 **Введите ваши ставки (СРОЧНАЯ ЗАЯВКА):**\n\n{entered_info}"
                "Вы можете ввести ставки для одного или нескольких вариантов оплаты.\n"
                "✅ - означает, что ставка введена\n\n"
                "Нажмите на вариант оплаты, чтобы ввести ставку:\n"
                f"⠀",
                reply_markup=get_urgent_payment_options_keyboard(
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


# Вспомогательные функции для срочных заявок

def get_urgent_fixed_application_keyboard(application_id, map_url=None, logist_phone=None):
    """Создает клавиатуру для срочной фиксированной заявки"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Первый ряд: основные действия
    row1 = [
        InlineKeyboardButton("✅ ПРИНЯТЬ", callback_data=f"urgent_accept-fixed_{application_id}"),
        InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"urgent_reject_application_{application_id}")
    ]
    keyboard.add(*row1)

    # Второй ряд: дополнительные действия
    row2 = []
    if map_url:
        row2.append(InlineKeyboardButton("🗺️ Построить маршрут", url=map_url))
    if logist_phone:
        row2.append(InlineKeyboardButton("📞 ПОЗВОНИТЬ", callback_data=f"urgent_call_logist_{application_id}"))

    if row2:
        keyboard.add(*row2)

    return keyboard


def get_urgent_auction_application_keyboard(application_id, map_url=None, logist_phone=None):
    """Создает клавиатуру для срочной аукционной заявки"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Первый ряд: основные действия
    row1 = [
        InlineKeyboardButton("✅ ПРИНЯТЬ", callback_data=f"urgent_accept-auction_{application_id}"),
        InlineKeyboardButton("💰 ВСТРЕЧНОЕ", callback_data=f"urgent_bid-auction_{application_id}")
    ]
    keyboard.add(*row1)

    # Второй ряд: дополнительные действия
    row2 = [
        InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"urgent_reject_application_{application_id}")
    ]
    keyboard.add(*row2)

    # Третий ряд: вспомогательные действия
    row3 = []
    if map_url:
        row3.append(InlineKeyboardButton("🗺️ Построить маршрут", url=map_url))
    if logist_phone:
        row3.append(InlineKeyboardButton("📞 ПОЗВОНИТЬ", callback_data=f"urgent_call_logist_{application_id}"))

    if row3:
        keyboard.add(*row3)

    return keyboard


def get_urgent_payment_options_keyboard(application_id, payment_options, action_type, selected_payments=None):
    """Создает клавиатуру для выбора вариантов оплаты для срочных заявок"""
    if selected_payments is None:
        selected_payments = {}

    keyboard = InlineKeyboardMarkup(row_width=2)

    parsed_options = {}
    if payment_options:
        try:
            if isinstance(payment_options, str):
                parsed_options = ast.literal_eval(payment_options)
            else:
                parsed_options = payment_options
        except Exception as e:
            print(f"Ошибка парсинга payment_options в клавиатуре срочных заявок: {e}")
            parsed_options = {}

    # Добавляем кнопки для каждого варианта оплаты
    buttons = []
    for payment_type in ['nds', 'ip', 'self-employed', 'cash']:
        # Проверяем, нужно ли показывать этот вариант оплаты
        should_show = False

        if action_type == 'accept-fixed':
            should_show = payment_type in parsed_options
        elif action_type == 'accept-auction':
            should_show = True
        elif action_type == 'bid-auction':
            should_show = True

        if not should_show:
            continue

        display_name = get_payment_type_name(payment_type)

        # Формируем текст кнопки в зависимости от типа действия
        if action_type == 'bid-auction':
            if payment_type in selected_payments:
                button_text = f"✅ {display_name}: {selected_payments[payment_type]:,.0f} руб."
            else:
                button_text = f"{display_name} (ввести ставку)"
        elif action_type == 'accept-fixed':
            price = parsed_options.get(payment_type, 0)
            if payment_type in selected_payments:
                button_text = f"✅ {display_name}: {float(price):,.0f} руб."
            else:
                button_text = f"{display_name}: {float(price):,.0f} руб."
        elif action_type == 'accept-auction':
            if payment_type in selected_payments:
                button_text = f"✅ {display_name}"
            else:
                button_text = f"{display_name}"

        buttons.append(InlineKeyboardButton(
            button_text,
            callback_data=f"urgent_select_payment_{action_type}_{application_id}_{payment_type}"
        ))

    # Добавляем кнопки в клавиатуру
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.add(buttons[i], buttons[i + 1])
        else:
            keyboard.add(buttons[i])

    # Кнопка подтверждения
    if selected_payments or action_type in ['accept-fixed', 'accept-auction']:
        keyboard.add(InlineKeyboardButton(
            "✅ ПОДТВЕРДИТЬ ВЫБОР",
            callback_data=f"urgent_confirm_payments_{action_type}_{application_id}"
        ))

    return keyboard


def get_urgent_back_to_payments_keyboard(application_id, action_type):
    """Создает клавиатуру для возврата к выбору оплаты для срочных заявок"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("↩️ Назад к выбору оплаты", callback_data=f"urgent_{action_type}_{application_id}")
    )
    return keyboard


def get_urgent_company_confirmation_keyboard(application_id, action_type):
    """Создает клавиатуру для подтверждения компании для срочных заявок"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("✅ ПОДТВЕРДИТЬ", callback_data=f"urgent_confirm_company_{action_type}_{application_id}")
    )
    return keyboard


def format_urgent_detailed_application(db, application, loading_points, unloading_points, cargo_info, logist_info):
    """Форматирует детальную информацию о срочной заявке"""
    # Используем существующую функцию, но добавляем заголовок срочности
    detailed_text = format_detailed_application(db, application, loading_points, unloading_points, cargo_info,
                                                logist_info)

    # Добавляем заголовок срочности в начало
    urgency_header = "🚨 **СРОЧНАЯ ЗАЯВКА** 🚨\n\n"

    return urgency_header + detailed_text


def get_cargo_info(application):
    """Возвращает информацию о грузе в форматированном виде"""
    cargo_type = application.get('cargo_custom_type') or application.get('cargo_type', 'Не указан')
    cargo_category = application.get('cargo_custom_category') or application.get('cargo_category', 'Не указан')

    return {
        'type': cargo_type,
        'category': cargo_category,
        'weight': application.get('weight', 'Не указан'),
        'volume': application.get('volume', 'Не указан'),
        'loading_method': application.get('loading_method', 'Не указан')
    }


def get_payment_type_name(payment_type):
    """Возвращает читаемое название типа оплаты"""
    names = {
        'nds': 'С НДС',
        'ip': 'Без НДС',
        'self-employed': 'Самозанятый',
        'cash': 'Наличные'
    }
    return names.get(payment_type, payment_type)


def notify_logist_about_urgent_response(bot, db, application_id, executor_id, response_type, payment_options):
    """Уведомляет логиста о response перевозчика на срочную заявку"""
    application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
    executor = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (executor_id,))
    company_info = db.fetch_one("SELECT * FROM companies WHERE id = ?",
                                (executor.get('company_id'),)) if executor.get('company_id') else None

    if not application or not executor:
        return

    logist_id = application['created_by']

    # Получаем точки маршрута для отображения
    points = db.fetch_all(
        "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
        (application_id,)
    )
    loading_points = [p for p in points if p['point_type'] == 'loading']
    unloading_points = [p for p in points if p['point_type'] == 'unloading']

    first_loading_city = loading_points[0]['city'] if loading_points else "Не указано"
    last_unloading_city = unloading_points[-1]['city'] if unloading_points else "Не указано"

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

    urgency_notice = "🚨 **НОВЫЙ ОТКЛИК НА СРОЧНУЮ ЗАЯВКУ!** 🚨\n\n"

    if response_type == 'accepted':
        message_text = f"""
{urgency_notice}
✅ **Перевозчик принял вашу срочную заявку!**

📦 Заявка #{application_id}
📍 Маршрут: {first_loading_city} → {last_unloading_city}
👤 **Перевозчик:** {executor['first_name']} {executor.get('last_name', '')}
🏢 **Компания:** {company_info.get('name', 'Не указана') if company_info else 'Не указана'}
📞 **Телефон:** {executor.get('phone', 'Не указан')}

**Выбранные варианты оплаты:**
{payments_text}

⚠️ *Это срочная заявка - свяжитесь с перевозчиком как можно скорее!*
        """.strip()
    elif response_type == 'accepted_budget':
        message_text = f"""
{urgency_notice}
✅ **Перевозчик принял срочную заявку по бюджету!**

📦 Заявка #{application_id}
📍 Маршрут: {first_loading_city} → {last_unloading_city}
💰 **Бюджет заявки:** {budget_text}
👤 **Перевозчик:** {executor['first_name']} {executor.get('last_name', '')}
🏢 **Компания:** {company_info.get('name', 'Не указана') if company_info else 'Не указана'}
📞 **Телефон:** {executor.get('phone', 'Не указан')}

**Выбранные варианты оплаты:**
{payments_text}

⚠️ *Это срочная заявка - свяжитесь с перевозчиком как можно скорее!*
        """.strip()
    else:  # counter_offer
        message_text = f"""
{urgency_notice}
💵 **Новое встречное предложение по срочной заявке!**

📦 Заявка #{application_id}
📍 Маршрут: {first_loading_city} → {last_unloading_city}
💰 **Бюджет заявки:** {budget_text}
👤 **Перевозчик:** {executor['first_name']} {executor.get('last_name', '')}
🏢 **Компания:** {company_info.get('name', 'Не указана') if company_info else 'Не указана'}
📞 **Телефон:** {executor.get('phone', 'Не указан')}

**Предложенные ставки:**
{payments_text}

⚠️ *Это срочная заявка - рассмотрите предложение как можно скорее!*
        """.strip()

    try:
        bot.send_message(logist_id, message_text, parse_mode='Markdown')
    except Exception as e:
        print(f"Не удалось уведомить логиста {logist_id} о срочном отклике: {e}")


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

        # Добавляем точки погрузки
        for i, point in enumerate(loading_coords):
            coord_str = f"{point['coords']['lat']},{point['coords']['lon']}"
            coordinates_list.append(coord_str)

        # Добавляем точки выгрузки
        for i, point in enumerate(unloading_coords):
            coord_str = f"{point['coords']['lat']},{point['coords']['lon']}"
            coordinates_list.append(coord_str)

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