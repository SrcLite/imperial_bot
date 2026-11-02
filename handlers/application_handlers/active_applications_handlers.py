import json
import ast
from datetime import datetime
from handlers.application_handlers.display_application_handlers import format_application_for_executor
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from utils.dicts import CARGO_TYPE_REVERSE_MAPPING, VEHICLE_TYPE_REVERSE_MAPPING
import pytz
from datetime import timedelta


def register_active_application_handlers(bot, db):
    user_application_data = {}  # Храним данные о просматриваемых заявках для каждого пользователя

    @bot.message_handler(func=lambda message: message.text == '📋 Активные заявки')
    def show_active_applications(message):
        """Показывает активные заявки перевозчику с постраничной навигацией"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)

        if user['status'] != 'active':
            bot.send_message(chat_id, "❌ Администратор не подтвердил вашу учетную запись.",
                             reply_markup=ReplyKeyboardRemove())
            return

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'logist', 'external_admin', 'external_logist']:
            bot.send_message(chat_id, "❌ Эта функция доступна только перевозчикам.")
            return

        # Получаем текущее московское время с учетом часового пояса
        msk_tz = pytz.timezone('Europe/Moscow')
        current_msk = datetime.now(msk_tz)

        # Вычитаем 1 час для запаса (на случай небольших опозданий)
        current_msk_minus_hour = current_msk - timedelta(hours=1)
        current_msk_str = current_msk_minus_hour.strftime('%Y-%m-%d %H:%M:%S')

        # Получаем активные заявки, исключая те, которые пользователь уже отклонил
        applications = db.fetch_all("""
            SELECT DISTINCT a.*, u.first_name, u.last_name, u.phone as logist_phone, u.email 
            FROM applications a 
            JOIN users u ON a.created_by = u.telegram_id 
            LEFT JOIN application_responses ar ON a.id = ar.application_id AND ar.executor_id = ?
            WHERE a.status = 'active' or a.status = 'urgent' 
            AND (ar.status IS NULL OR ar.status != 'rejected')
            ORDER BY a.created_at DESC
        """, (user_id,))

        if not applications:
            bot.send_message(chat_id, "📭 На данный момент активных заявок нет.")
            return

        # Дополнительная фильтрация на случай некорректных данных в БД
        valid_applications = []
        msk_tz = pytz.timezone('Europe/Moscow')
        current_msk = datetime.now(msk_tz)

        for app in applications:
            # Получаем первую точку погрузки для проверки даты
            first_loading_point = db.fetch_one("""
                SELECT point_datetime FROM application_points 
                WHERE application_id = ? AND point_type = 'loading' 
                ORDER BY point_order LIMIT 1
            """, (app['id'],))

            # Если нет точек погрузки или даты, считаем заявку валидной
            if not first_loading_point or not first_loading_point.get('point_datetime'):
                valid_applications.append(app)
                continue

            try:
                loading_datetime = first_loading_point['point_datetime']

                # Пытаемся распарсить дату погрузки
                if isinstance(loading_datetime, str):
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                        try:
                            loading_dt = datetime.strptime(loading_datetime, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        continue
                else:
                    loading_dt = loading_datetime

                # Применяем московский часовой пояс
                loading_dt_msk = msk_tz.localize(loading_dt) if loading_dt.tzinfo is None else loading_dt.astimezone(
                    msk_tz)

                # Проверяем, что дата не просрочена (с запасом в 1 час)
                one_hour = timedelta(hours=1)
                if loading_dt_msk >= (current_msk - one_hour):
                    valid_applications.append(app)
                else:
                    # Обновляем статус просроченной заявки
                    db.execute_query(
                        "UPDATE applications SET status = 'expired' WHERE id = ?",
                        (app['id'],)
                    )

            except Exception as e:
                print(f"Ошибка при обработке даты заявки #{app['id']}: {e}")
                continue

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
            bot.send_message(chat_id, "❌ Данные о заявках устарели. Нажмите '📋 Активные заявки' снова.")
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

        # Добавляем информацию о времени до первой погрузки
        time_info = ""
        first_loading_point = db.fetch_one("""
            SELECT point_datetime FROM application_points 
            WHERE application_id = ? AND point_type = 'loading' 
            ORDER BY point_order LIMIT 1
        """, (app['id'],))

        if first_loading_point and first_loading_point.get('point_datetime'):
            try:
                msk_tz = pytz.timezone('Europe/Moscow')
                current_msk = datetime.now(msk_tz)
                loading_datetime = first_loading_point['point_datetime']

                if isinstance(loading_datetime, str):
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                        try:
                            loading_dt = datetime.strptime(loading_datetime, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        loading_dt = None
                else:
                    loading_dt = loading_datetime

                if loading_dt:
                    loading_dt_msk = msk_tz.localize(loading_dt) if loading_dt.tzinfo is None else loading_dt

                    if loading_dt_msk > current_msk:
                        time_diff = loading_dt_msk - current_msk
                        days = time_diff.days
                        hours = time_diff.seconds // 3600
                        minutes = (time_diff.seconds % 3600) // 60

                        time_parts = []
                        if days > 0:
                            time_parts.append(f"{days} д.")
                        if hours > 0:
                            time_parts.append(f"{hours} ч.")
                        if minutes > 0 and days == 0:
                            time_parts.append(f"{minutes} мин.")

                        time_info = f"\n⏳ **До первой погрузки:** {' '.join(time_parts)}"
            except Exception as e:
                print(f"Ошибка при расчете времени до погрузки: {e}")

        # Добавляем нумерацию страниц
        page_info = f"\n\n📄 Страница {index + 1} из {len(applications)}"
        full_text = application_text + time_info + page_info

        # Создаем клавиатуру с навигацией
        keyboard = get_application_navigation_keyboard(app['id'], index, len(applications))

        if is_new:
            msg = bot.send_message(
                chat_id,
                full_text,
                reply_markup=keyboard,
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
                    )
                except Exception as e:
                    msg = bot.send_message(
                        chat_id,
                        full_text,
                        reply_markup=keyboard,
                    )
                    user_application_data[user_id]['message_id'] = msg.message_id

        user_application_data[user_id]['current_index'] = index

    def get_application_navigation_keyboard(application_id, current_index, total_count):
        """Создает клавиатуру с навигацией по заявкам"""
        keyboard = InlineKeyboardMarkup(row_width=3)

        nav_buttons = []

        if current_index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"active_nav_prev_{current_index}"))

        nav_buttons.append(
            InlineKeyboardButton("📋 ОЗНАКОМИТЬСЯ", callback_data=f"view_active_application_{application_id}"))

        if current_index < total_count - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"active_nav_next_{current_index}"))

        keyboard.add(*nav_buttons)
        keyboard.add(InlineKeyboardButton("❌ Закрыть", callback_data="active_close_applications"))

        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data.startswith('active_nav_'))
    def handle_navigation(call):
        """Обработка навигации по активным заявкам"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        data_parts = call.data.split('_')
        direction = data_parts[2]
        current_index = int(data_parts[3])

        if user_id not in user_application_data:
            bot.answer_callback_query(call.id, "❌ Сессия просмотра истекла")
            return

        applications = user_application_data[user_id].get('applications', [])

        if not applications:
            bot.answer_callback_query(call.id, "❌ Нет доступных заявок")
            return

        if direction == 'prev':
            new_index = current_index - 1
        else:
            new_index = current_index + 1

        if new_index < 0 or new_index >= len(applications):
            bot.answer_callback_query(call.id)
            return

        show_application_page(user_id, chat_id, new_index, is_new=False)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'active_close_applications')
    def handle_close_applications(call):
        """Закрывает просмотр активных заявок"""
        user_id = call.from_user.id

        bot.delete_message(call.message.chat.id, call.message.message_id)

        if user_id in user_application_data:
            del user_application_data[user_id]

        bot.answer_callback_query(call.id, "✅ Просмотр заявок завершен")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('view_active_application_'))
    def handle_view_application(call):
        """Обработка нажатия кнопки 'ОЗНАКОМИТЬСЯ' - показывает только информацию и маршрут"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[3])

        application = db.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))
        if not application:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена")
            return

        points = db.fetch_all(
            "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
            (application_id,)
        )

        loading_points = [p for p in points if p['point_type'] == 'loading']
        unloading_points = [p for p in points if p['point_type'] == 'unloading']

        # Формируем ссылку для Яндекс.Карт
        map_url = generate_yandex_maps_url(loading_points, unloading_points)

        cargo_info = get_cargo_info(application)

        logist_info = db.fetch_one(
            "SELECT phone, email FROM users WHERE telegram_id = ?",
            (application['created_by'],)
        )

        detailed_text = format_detailed_application(
            application, loading_points, unloading_points, cargo_info, logist_info
        )

        # Добавляем информацию о времени до первой погрузки
        if loading_points and loading_points[0].get('point_datetime'):
            try:
                msk_tz = pytz.timezone('Europe/Moscow')
                current_msk = datetime.now(msk_tz)
                loading_datetime = loading_points[0]['point_datetime']

                if isinstance(loading_datetime, str):
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                        try:
                            loading_dt = datetime.strptime(loading_datetime, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        loading_dt = None
                else:
                    loading_dt = loading_datetime

                if loading_dt:
                    loading_dt_msk = msk_tz.localize(loading_dt) if loading_dt.tzinfo is None else loading_dt

                    if loading_dt_msk > current_msk:
                        time_diff = loading_dt_msk - current_msk
                        days = time_diff.days
                        hours = time_diff.seconds // 3600
                        minutes = (time_diff.seconds % 3600) // 60

                        time_parts = []
                        if days > 0:
                            time_parts.append(f"{days} дней")
                        if hours > 0:
                            time_parts.append(f"{hours} часов")
                        if minutes > 0 and days == 0:
                            time_parts.append(f"{minutes} минут")

                        if time_parts:
                            detailed_text += f"\n\n⏳ **До первой погрузки осталось:** {' '.join(time_parts)}"
            except Exception as e:
                print(f"Ошибка при расчете времени до погрузки в подробном просмотре: {e}")

        detailed_text += "\n\n⚠️ *Эта заявка предоставлена для ознакомления*"

        keyboard = get_view_only_keyboard(map_url)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=detailed_text,
            reply_markup=keyboard,
        )

        bot.answer_callback_query(call.id, "📋 Подробная информация о заявке")


def get_view_only_keyboard(map_url):
    """Создает клавиатуру только для просмотра заявки с кнопкой маршрута"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    if map_url:
        keyboard.add(
            InlineKeyboardButton("🗺️ ПОСТРОИТЬ МАРШРУТ", url=map_url),
        )
    keyboard.add(
        InlineKeyboardButton("❌ Закрыть", callback_data="active_close_applications")
    )
    return keyboard


def get_cargo_info(application):
    """Возвращает информацию о грузе в форматированном виде"""
    cargo_type = application.get('cargo_custom_type') or application.get('cargo_type', 'Не указан')

    return {
        'type': cargo_type,
        'weight': application.get('weight', 'Не указан'),
        'volume': application.get('volume', 'Не указан'),
    }


def format_detailed_application(application, loading_points, unloading_points, cargo_info, logist_info, payment_options_responses = None):
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
            loading_text += f"   {i}. **{point['city']}**, {point['address']}\n"

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
            unloading_text += f"   {i}. **{point['city']}**, {point['address']}\n"

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
    vehicle_type_display = VEHICLE_TYPE_REVERSE_MAPPING.get(application.get('vehicle_type'),
                                                            application.get('vehicle_type', 'Не указан'))

    transport_text = f"""
🚛 **Тип кузова:** {vehicle_type_display}
    """.strip()

    # Оплата
    payment_options = application.get('payment_options')
    payment_text = "💰 **Варианты оплаты:**\n"
    if payment_options:
        try:
            if isinstance(payment_options, str):
                parsed_options = ast.literal_eval(payment_options)
            else:
                parsed_options = payment_options

            payments = []
            if parsed_options.get('nds'):
                payments.append(f"• С НДС: {float(parsed_options['nds']):,.0f} ₽")
            if parsed_options.get('ip'):
                payments.append(f"• ИП без НДС: {float(parsed_options['ip']):,.0f} ₽")
            if parsed_options.get('self-employed'):
                payments.append(f"• Самозанятый: {float(parsed_options['self-employed']):,.0f} ₽")
            if parsed_options.get('cash'):
                payments.append(f"• Наличные: {float(parsed_options['cash']):,.0f} ₽")

            payment_text += "\n".join(payments) if payments else "Не указаны"
        except Exception as e:
            print(f"Ошибка парсинга payment_options: {e}")
            payment_text += "Не указаны"
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


def generate_yandex_maps_url(loading_points, unloading_points):
    """
    Генерирует URL для Яндекс.Карт с поддержкой нескольких точек
    """
    all_points = loading_points + unloading_points
    valid_points = []

    for point in all_points:
        if point.get('coordinates'):
            try:
                coords = json.loads(point['coordinates'])
                if 'lat' in coords and 'lon' in coords:
                    valid_points.append({
                        'coords': coords,
                        'type': point['point_type'],
                        'city': point.get('city', '')
                    })
            except (json.JSONDecodeError, TypeError):
                continue

    if len(valid_points) >= 2:
        # Сортируем: сначала точки погрузки, потом выгрузки
        loading_coords = [p for p in valid_points if p['type'] == 'loading']
        unloading_coords = [p for p in valid_points if p['type'] == 'unloading']

        coordinates_list = []

        for point in loading_coords:
            coordinates_list.append(f"{point['coords']['lat']},{point['coords']['lon']}")

        for point in unloading_coords:
            coordinates_list.append(f"{point['coords']['lat']},{point['coords']['lon']}")

        if coordinates_list:
            rtext = "~".join(coordinates_list)
            map_url = f"https://yandex.ru/maps/?rtext={rtext}&rtt=auto"
            return map_url
    elif len(valid_points) == 1:
        point = valid_points[0]
        map_url = f"https://yandex.ru/maps/?ll={point['coords']['lon']},{point['coords']['lat']}&z=12"
        return map_url

    return None