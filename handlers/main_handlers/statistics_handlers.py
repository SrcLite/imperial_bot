import json
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from utils.dicts import role_names


def register_statistics_handlers(bot, db):
    """Регистрация обработчиков для системы статистики"""

    # Словарь для хранения ID последних сообщений пользователей
    last_stats_messages = {}

    def send_or_edit_stats_message(chat_id, user_id, text, reply_markup=None, parse_mode=None):
        """Отправляет новое сообщение или редактирует последнее, если оно существует"""
        if user_id in last_stats_messages:
            try:
                # Пробуем отредактировать существующее сообщение
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=last_stats_messages[user_id],
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return last_stats_messages[user_id]
            except Exception as e:
                # Если не удалось отредактировать, удаляем старый ID
                if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                    del last_stats_messages[user_id]
                pass

        # Отправляем новое сообщение
        msg = bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        last_stats_messages[user_id] = msg.message_id
        return msg.message_id

    @bot.message_handler(func=lambda message: message.text == '📊 Статистика')
    def handle_statistics_menu(message):
        """Показывает меню статистики в зависимости от роли пользователя"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        set_user_state(user_id, '')

        # Очищаем предыдущее сообщение пользователя из словаря
        if user_id in last_stats_messages:
            try:
                bot.delete_message(chat_id, last_stats_messages[user_id])
            except:
                pass
            del last_stats_messages[user_id]

        user = db.get_user_by_telegram_id(user_id)
        if not user and user['status'] != 'active':
            send_or_edit_stats_message(
                chat_id,
                user_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        # Получаем информацию о пользователе
        user_info = db.get_user_by_telegram_id(user_id)
        if not user_info:
            send_or_edit_stats_message(chat_id, user_id, "❌ Пользователь не найден.")
            return

        user_role = user_info['role']

        # Создаем клавиатуру в зависимости от роли
        keyboard = InlineKeyboardMarkup(row_width=1)

        if user_role in ['admin', 'external_admin']:
            # Администраторы видят статистику компаний и общую статистику
            keyboard.add(
                InlineKeyboardButton("🏢 Статистика компаний", callback_data="company_statistics"),
                InlineKeyboardButton("👥 Статистика пользователей", callback_data="user_statistics"),
                InlineKeyboardButton("📦 Общая статистика заявок", callback_data="general_statistics"),
                InlineKeyboardButton("📈 Статистика по периодам", callback_data="period_statistics"),
                InlineKeyboardButton("💰 Финансовая статистика", callback_data="financial_statistics")
            )

            send_or_edit_stats_message(
                chat_id,
                user_id,
                f"📊 **Статистика для администратора**\n\n"
                f"👤 Ваша роль: **{get_role_display_name(user_role)}**\n\n"
                f"Выберите тип статистики для просмотра:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )

        elif user_role in ['logist', 'external_logist']:
            # Логисты видят свою личную статистику
            keyboard.add(
                InlineKeyboardButton("📦 Мои заявки", callback_data="my_applications_stats"),
                InlineKeyboardButton("👥 Мои перевозчики", callback_data="my_executors_stats"),
                InlineKeyboardButton("📊 Эффективность", callback_data="efficiency_stats"),
                InlineKeyboardButton("📅 Статистика по периодам", callback_data="my_period_stats")
            )

            send_or_edit_stats_message(
                chat_id,
                user_id,
                f"📊 **Личная статистика логиста**\n\n"
                f"👤 Имя: **{user_info['first_name']} {user_info.get('last_name', '')}**\n"
                f"🏢 Роль: **{get_role_display_name(user_role)}**\n\n"
                f"Выберите раздел статистики:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )

        elif user_role in ['executor', 'external_executor']:
            # Перевозчики видят свою личную статистику
            keyboard.add(
                InlineKeyboardButton("📦 Мои отклики", callback_data="my_responses_stats"),
                InlineKeyboardButton("✅ Выполненные заявки", callback_data="completed_applications"),
                InlineKeyboardButton("💰 Финансовая статистика", callback_data="executor_financial_stats"),
                InlineKeyboardButton("📈 Рейтинг эффективности", callback_data="executor_efficiency")
            )

            # Получаем компанию перевозчика
            company_info = None
            if user_info.get('company_id'):
                company_info = db.get_company_by_id(user_info['company_id'])

            company_text = f"\n🏢 Компания: **{company_info['name'] if company_info else 'Не указана'}**" if company_info else ""

            send_or_edit_stats_message(
                chat_id,
                user_id,
                f"📊 **Личная статистика перевозчика**\n\n"
                f"👤 Имя: **{user_info['first_name']} {user_info.get('last_name', '')}**\n"
                f"🎯 Роль: **{get_role_display_name(user_role)}**{company_text}\n\n"
                f"Выберите раздел статистики:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )

        else:
            send_or_edit_stats_message(chat_id, user_id, "❌ Ваша роль не поддерживает просмотр статистики.")

    # ========== ОБРАБОТЧИКИ ДЛЯ АДМИНИСТРАТОРОВ ==========

    @bot.callback_query_handler(func=lambda call: call.data == 'company_statistics')
    def handle_company_statistics(call):
        """Статистика компаний для администратора"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Получаем статистику компаний
        companies_stats = db.fetch_all("""
            SELECT 
                c.id,
                c.name,
                c.company_type,
                c.status,
                COUNT(DISTINCT u.id) as user_count,
                COUNT(DISTINCT a.id) as application_count,
                COUNT(DISTINCT ar.id) as response_count,
                SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) as completed_count
            FROM companies c
            LEFT JOIN users u ON c.id = u.company_id
            LEFT JOIN applications a ON u.telegram_id = a.created_by
            LEFT JOIN application_responses ar ON u.telegram_id = ar.executor_id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """)

        # Общая статистика
        total_stats = db.fetch_one("""
            SELECT 
                COUNT(DISTINCT c.id) as total_companies,
                COUNT(DISTINCT CASE WHEN c.status = 'approved' THEN c.id END) as approved_companies,
                COUNT(DISTINCT CASE WHEN c.status = 'pending' THEN c.id END) as pending_companies,
                COUNT(DISTINCT u.id) as total_users,
                COUNT(DISTINCT a.id) as total_applications
            FROM companies c
            LEFT JOIN users u ON c.id = u.company_id
            LEFT JOIN applications a ON u.telegram_id = a.created_by
        """)

        # Формируем текст
        text = f"🏢 **Статистика компаний**\n\n"
        text += f"📊 **Общая статистика:**\n"
        text += f"• Всего компаний: **{total_stats['total_companies']}**\n"
        text += f"• Одобренных: **{total_stats['approved_companies']}**\n"
        text += f"• На модерации: **{total_stats['pending_companies']}**\n"
        text += f"• Всего пользователей: **{total_stats['total_users']}**\n"
        text += f"• Всего заявок: **{total_stats['total_applications']}**\n\n"

        text += f"📋 **Детали по компаниям:**\n"
        for i, company in enumerate(companies_stats[:10], 1):  # Показываем первые 10
            status_emoji = "✅" if company['status'] == 'approved' else "⏳" if company['status'] == 'pending' else "❌"
            text += f"\n**{i}. {company['name']}** {status_emoji}\n"
            text += f"   👥 Пользователей: {company['user_count']}\n"
            text += f"   📦 Заявок создано: {company['application_count']}\n"
            text += f"   💰 Откликов: {company['response_count']}\n"
            text += f"   ✅ Выполнено: {company['completed_count']}\n"

        if len(companies_stats) > 10:
            text += f"\n... и еще {len(companies_stats) - 10} компаний"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("👥 Статистика пользователей", callback_data="user_statistics"),
            InlineKeyboardButton("📦 Общая статистика", callback_data="general_statistics")
        )
        keyboard.add(InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'user_statistics')
    def handle_user_statistics(call):
        """Статистика пользователей для администратора"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Получаем статистику пользователей
        users_stats = db.fetch_all("""
            SELECT 
                u.role,
                u.status,
                COUNT(*) as count,
                COUNT(DISTINCT a.id) as application_count,
                COUNT(DISTINCT ar.id) as response_count,
                SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) as completed_count
            FROM users u
            LEFT JOIN applications a ON u.telegram_id = a.created_by
            LEFT JOIN application_responses ar ON u.telegram_id = ar.executor_id
            GROUP BY u.role, u.status
        """)

        # Статистика по ролям
        roles_stats = db.fetch_all("""
            SELECT 
                role,
                COUNT(*) as count,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count
            FROM users
            GROUP BY role
            ORDER BY count DESC
        """)

        # Новые пользователи за последние 7 дней
        new_users = db.fetch_one("""
            SELECT COUNT(*) as count
            FROM users
            WHERE created_at >= datetime('now', '-7 days')
        """)

        # Формируем текст
        text = f"👥 **Статистика пользователей**\n\n"

        text += f"📊 **По ролям:**\n"
        for role_stat in roles_stats:
            role_name = get_role_display_name(role_stat['role'])
            text += f"• **{role_name}**: {role_stat['count']} (активных: {role_stat['active_count']})\n"

        text += f"\n📈 **Активность:**\n"
        text += f"• Новых пользователей за 7 дней: **{new_users['count']}**\n"

        # Детальная статистика
        text += f"\n📋 **Детальная статистика:**\n"
        for stat in users_stats:
            role_name = get_role_display_name(stat['role'])
            status_name = "✅ Активен" if stat['status'] == 'active' else "⏳ Ожидает" if stat[
                                                                                            'status'] == 'pending' else "❌ Заблокирован"
            text += f"\n**{role_name} - {status_name}**: {stat['count']} чел.\n"
            if stat['application_count'] > 0:
                text += f"   📦 Заявок: {stat['application_count']}\n"
            if stat['response_count'] > 0:
                text += f"   💰 Откликов: {stat['response_count']}\n"
            if stat['completed_count'] > 0:
                text += f"   ✅ Выполнено: {stat['completed_count']}\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🏢 Статистика компаний", callback_data="company_statistics"),
            InlineKeyboardButton("📦 Общая статистика", callback_data="general_statistics")
        )
        keyboard.add(InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'general_statistics')
    def handle_general_statistics(call):
        """Общая статистика заявок для администратора"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Общая статистика заявок
        applications_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'assigned' THEN 1 END) as assigned,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled,
                COUNT(CASE WHEN application_type = 'fixed' THEN 1 END) as fixed,
                COUNT(CASE WHEN application_type = 'auction' THEN 1 END) as auction,
                AVG(desired_budget) as avg_budget,
                SUM(desired_budget) as total_budget
            FROM applications
        """)

        # Статистика по откликам
        responses_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as total_responses,
                COUNT(DISTINCT executor_id) as unique_executors,
                COUNT(CASE WHEN status = 'counter_offer' THEN 1 END) as counter_offers,
                COUNT(CASE WHEN status = 'accepted_budget' THEN 1 END) as accepted_budget,
                COUNT(CASE WHEN status = 'selected' THEN 1 END) as selected,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected
            FROM application_responses
        """)

        # Заявки за последние 7 дней
        weekly_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as applications_7d,
                COUNT(DISTINCT created_by) as active_users_7d,
                COUNT(DISTINCT ar.executor_id) as active_executors_7d
            FROM applications a
            LEFT JOIN application_responses ar ON a.id = ar.application_id
            WHERE a.created_at >= datetime('now', '-7 дней')
        """)

        # Формируем текст
        text = f"📦 **Общая статистика заявок**\n\n"

        text += f"📊 **Заявки:**\n"
        text += f"• Всего заявок: **{applications_stats['total']}**\n"
        text += f"• Активных: **{applications_stats['active']}**\n"
        text += f"• Назначенных: **{applications_stats['assigned']}**\n"
        text += f"• Выполненных: **{applications_stats['completed']}**\n"
        text += f"• Отмененных: **{applications_stats['cancelled']}**\n"
        text += f"• Фиксированных: **{applications_stats['fixed']}**\n"
        text += f"• Аукционных: **{applications_stats['auction']}**\n"

        if applications_stats['avg_budget']:
            text += f"• Средний бюджет: **{float(applications_stats['avg_budget']):,.0f} руб.**\n"
            text += f"• Общий бюджет: **{float(applications_stats['total_budget']):,.0f} руб.**\n"

        text += f"\n💰 **Отклики:**\n"
        text += f"• Всего откликов: **{responses_stats['total_responses']}**\n"
        text += f"• Уникальных перевозчиков: **{responses_stats['unique_executors']}**\n"
        text += f"• Встречных предложений: **{responses_stats['counter_offers']}**\n"
        text += f"• Принятых по бюджету: **{responses_stats['accepted_budget']}**\n"
        text += f"• Выбранных: **{responses_stats['selected']}**\n"
        text += f"• Отклоненных: **{responses_stats['rejected']}**\n"

        text += f"\n📈 **Активность за 7 дней:**\n"
        text += f"• Новых заявок: **{weekly_stats['applications_7d']}**\n"
        text += f"• Активных пользователей: **{weekly_stats['active_users_7d']}**\n"
        text += f"• Активных перевозчиков: **{weekly_stats['active_executors_7d']}**\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🏢 Статистика компаний", callback_data="company_statistics"),
            InlineKeyboardButton("👥 Статистика пользователей", callback_data="user_statistics")
        )
        keyboard.add(InlineKeyboardButton("📈 По периодам", callback_data="period_statistics"))
        keyboard.add(InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'period_statistics')
    def handle_period_statistics(call):
        """Статистика по периодам для администратора"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Статистика за сегодня
        today_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as applications_today,
                COUNT(DISTINCT created_by) as users_today,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_today
            FROM applications
            WHERE DATE(created_at) = DATE('now')
        """)

        # Статистика за текущую неделю
        week_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as applications_week,
                COUNT(DISTINCT created_by) as users_week,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_week
            FROM applications
            WHERE created_at >= datetime('now', 'start of day', '-6 days')
        """)

        # Статистика за текущий месяц
        month_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as applications_month,
                COUNT(DISTINCT created_by) as users_month,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_month
            FROM applications
            WHERE created_at >= datetime('now', 'start of month')
        """)

        # Динамика по дням (последние 7 дней)
        daily_stats = db.fetch_all("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as applications,
                COUNT(DISTINCT created_by) as unique_users
            FROM applications
            WHERE created_at >= datetime('now', '-7 дней')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """)

        # Формируем текст
        text = f"📅 **Статистика по периодам**\n\n"

        text += f"📊 **Сегодня:**\n"
        text += f"• Заявок: **{today_stats['applications_today'] or 0}**\n"
        text += f"• Пользователей: **{today_stats['users_today'] or 0}**\n"
        text += f"• Выполнено: **{today_stats['completed_today'] or 0}**\n"

        text += f"\n📊 **Текущая неделя:**\n"
        text += f"• Заявок: **{week_stats['applications_week'] or 0}**\n"
        text += f"• Пользователей: **{week_stats['users_week'] or 0}**\n"
        text += f"• Выполнено: **{week_stats['completed_week'] or 0}**\n"

        text += f"\n📊 **Текущий месяц:**\n"
        text += f"• Заявок: **{month_stats['applications_month'] or 0}**\n"
        text += f"• Пользователей: **{month_stats['users_month'] or 0}**\n"
        text += f"• Выполнено: **{month_stats['completed_month'] or 0}**\n"

        text += f"\n📈 **Динамика за 7 дней:**\n"
        for stat in daily_stats[:5]:  # Показываем последние 5 дней
            date_obj = datetime.strptime(stat['date'], '%Y-%m-%d')
            date_str = date_obj.strftime('%d.%m')
            text += f"• **{date_str}**: {stat['applications']} заявок, {stat['unique_users']} пользователей\n"

        if len(daily_stats) > 5:
            text += f"• ... и еще {len(daily_stats) - 5} дней\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📦 Общая статистика", callback_data="general_statistics"),
            InlineKeyboardButton("💰 Финансовая", callback_data="financial_statistics")
        )
        keyboard.add(InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'financial_statistics')
    def handle_financial_statistics(call):
        """Финансовая статистика для администратора"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Финансовая статистика по заявкам
        financial_stats = db.fetch_one("""
            SELECT 
                SUM(CASE WHEN status = 'completed' THEN desired_budget ELSE 0 END) as total_completed_budget,
                AVG(CASE WHEN status = 'completed' THEN desired_budget ELSE NULL END) as avg_completed_budget,
                SUM(CASE WHEN status = 'assigned' THEN desired_budget ELSE 0 END) as total_assigned_budget,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_count,
                COUNT(CASE WHEN status = 'assigned' THEN 1 END) as assigned_count
            FROM applications
        """)

        # Статистика по типам оплаты
        payment_stats = db.fetch_all("""
            SELECT 
                a.application_type,
                COUNT(*) as count,
                AVG(a.desired_budget) as avg_budget,
                SUM(a.desired_budget) as total_budget
            FROM applications a
            WHERE a.status IN ('completed', 'assigned')
            GROUP BY a.application_type
        """)

        # Формируем текст
        text = f"💰 **Финансовая статистика**\n\n"

        text += f"📊 **Завершенные заявки:**\n"
        text += f"• Количество: **{financial_stats['completed_count'] or 0}**\n"
        if financial_stats['total_completed_budget']:
            text += f"• Общая сумма: **{float(financial_stats['total_completed_budget']):,.0f} руб.**\n"
            text += f"• Средняя сумма: **{float(financial_stats['avg_completed_budget'] or 0):,.0f} руб.**\n"

        text += f"\n📊 **Назначенные заявки:**\n"
        text += f"• Количество: **{financial_stats['assigned_count'] or 0}**\n"
        if financial_stats['total_assigned_budget']:
            text += f"• Общая сумма: **{float(financial_stats['total_assigned_budget']):,.0f} руб.**\n"

        text += f"\n📊 **По типам заявок:**\n"
        for stat in payment_stats:
            type_name = "Фиксированная" if stat['application_type'] == 'fixed' else "Аукцион"
            text += f"• **{type_name}**: {stat['count']} заявок\n"
            if stat['avg_budget']:
                text += f"  Средняя: {float(stat['avg_budget']):,.0f} руб.\n"
                text += f"  Общая: {float(stat['total_budget']):,.0f} руб.\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📅 По периодам", callback_data="period_statistics"),
            InlineKeyboardButton("📦 Общая статистика", callback_data="general_statistics")
        )
        keyboard.add(InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    # ========== ОБРАБОТЧИКИ ДЛЯ ЛОГИСТОВ ==========

    @bot.callback_query_handler(func=lambda call: call.data == 'my_applications_stats')
    def handle_my_applications_stats(call):
        """Статистика заявок логиста"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - логист
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'external_logist']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Статистика заявок логиста
        applications_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'assigned' THEN 1 END) as assigned,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled,
                COUNT(CASE WHEN application_type = 'fixed' THEN 1 END) as fixed,
                COUNT(CASE WHEN application_type = 'auction' THEN 1 END) as auction,
                AVG(desired_budget) as avg_budget,
                SUM(desired_budget) as total_budget
            FROM applications
            WHERE created_by = ?
        """, (user_id,))

        # Статистика по откликам на заявки логиста
        responses_stats = db.fetch_one("""
            SELECT 
                COUNT(DISTINCT ar.id) as total_responses,
                COUNT(DISTINCT ar.executor_id) as unique_executors,
                COUNT(CASE WHEN ar.status = 'counter_offer' THEN 1 END) as counter_offers,
                COUNT(CASE WHEN ar.status = 'accepted_budget' THEN 1 END) as accepted_budget,
                COUNT(CASE WHEN ar.status = 'selected' THEN 1 END) as selected
            FROM applications a
            JOIN application_responses ar ON a.id = ar.application_id
            WHERE a.created_by = ?
        """, (user_id,))

        # Формируем текст
        user_info = db.get_user_by_telegram_id(user_id)

        text = f"📦 **Статистика ваших заявок**\n\n"
        text += f"👤 **Логист:** {user_info['first_name']} {user_info.get('last_name', '')}\n\n"

        text += f"📊 **Всего заявок:** **{applications_stats['total'] or 0}**\n"
        text += f"• Активных: **{applications_stats['active'] or 0}**\n"
        text += f"• Назначенных: **{applications_stats['assigned'] or 0}**\n"
        text += f"• Выполненных: **{applications_stats['completed'] or 0}**\n"
        text += f"• Отмененных: **{applications_stats['cancelled'] or 0}**\n"
        text += f"• Фиксированных: **{applications_stats['fixed'] or 0}**\n"
        text += f"• Аукционных: **{applications_stats['auction'] or 0}**\n"

        if applications_stats['avg_budget']:
            text += f"• Средний бюджет: **{float(applications_stats['avg_budget']):,.0f} руб.**\n"
            text += f"• Общий бюджет: **{float(applications_stats['total_budget'] or 0):,.0f} руб.**\n"

        text += f"\n💰 **Отклики на ваши заявки:**\n"
        text += f"• Всего откликов: **{responses_stats['total_responses'] or 0}**\n"
        text += f"• Уникальных перевозчиков: **{responses_stats['unique_executors'] or 0}**\n"
        text += f"• Встречных предложений: **{responses_stats['counter_offers'] or 0}**\n"
        text += f"• Принятых по бюджету: **{responses_stats['accepted_budget'] or 0}**\n"
        text += f"• Выбранных перевозчиков: **{responses_stats['selected'] or 0}**\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("👥 Мои перевозчики", callback_data="my_executors_stats"),
            InlineKeyboardButton("📊 Эффективность", callback_data="efficiency_stats"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'my_executors_stats')
    def handle_my_executors_stats(call):
        """Статистика перевозчиков логиста"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - логист
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'external_logist']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Перевозчики, которые откликались на заявки логиста
        executors_stats = db.fetch_all("""
            SELECT 
                u.telegram_id,
                u.first_name,
                u.last_name,
                c.name as company_name,
                COUNT(DISTINCT ar.id) as responses_count,
                COUNT(DISTINCT CASE WHEN ar.status = 'selected' THEN a.id END) as selected_count,
                COUNT(DISTINCT a.id) as applications_count
            FROM application_responses ar
            JOIN applications a ON ar.application_id = a.id
            JOIN users u ON ar.executor_id = u.telegram_id
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE a.created_by = ?
            GROUP BY u.telegram_id
            ORDER BY responses_count DESC
            LIMIT 10
        """, (user_id,))

        # Формируем текст
        text = f"👥 **Перевозчики ваших заявок**\n\n"

        if not executors_stats:
            text += "У вас еще нет перевозчиков, которые откликались на ваши заявки.\n"
        else:
            text += f"**Топ перевозчиков:**\n"
            for i, executor in enumerate(executors_stats, 1):
                name = f"{executor['first_name']} {executor.get('last_name', '')}"
                company = executor['company_name'] if executor['company_name'] else "Без компании"
                text += f"\n**{i}. {name}**\n"
                text += f"   🏢 {company}\n"
                text += f"   📊 Откликов: {executor['responses_count']}\n"
                text += f"   ✅ Выбрано: {executor['selected_count']}\n"
                text += f"   📦 Заявок: {executor['applications_count']}\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📦 Мои заявки", callback_data="my_applications_stats"),
            InlineKeyboardButton("📊 Эффективность", callback_data="efficiency_stats"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'efficiency_stats')
    def handle_efficiency_stats(call):
        """Статистика эффективности логиста"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - логист
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'external_logist']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Эффективность логиста
        efficiency_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as total_applications,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_applications,
                COUNT(CASE WHEN status = 'assigned' THEN 1 END) as assigned_applications,
                ROUND(CAST(COUNT(CASE WHEN status IN ('completed', 'assigned') THEN 1 END) AS FLOAT) / COUNT(*) * 100, 1) as success_rate,
                AVG(CASE WHEN status = 'completed' THEN desired_budget END) as avg_completed_budget,
                SUM(CASE WHEN status = 'completed' THEN desired_budget END) as total_completed_budget
            FROM applications
            WHERE created_by = ?
        """, (user_id,))

        # Время выполнения заявок
        time_stats = db.fetch_one("""
            SELECT 
                AVG(julianday(updated_at) - julianday(created_at)) * 24 as avg_hours_to_complete
            FROM applications
            WHERE created_by = ? AND status = 'completed' AND updated_at IS NOT NULL
        """, (user_id,))

        # Формируем текст
        text = f"📊 **Эффективность работы**\n\n"

        if efficiency_stats['total_applications'] == 0:
            text += "У вас еще нет заявок для анализа эффективности.\n"
        else:
            text += f"📈 **Показатели:**\n"
            text += f"• Всего заявок: **{efficiency_stats['total_applications']}**\n"
            text += f"• Выполнено: **{efficiency_stats['completed_applications'] or 0}**\n"
            text += f"• Назначено: **{efficiency_stats['assigned_applications'] or 0}**\n"
            text += f"• Успешность: **{efficiency_stats['success_rate'] or 0}%**\n"

            if efficiency_stats['avg_completed_budget']:
                text += f"• Средний бюджет выполненной заявки: **{float(efficiency_stats['avg_completed_budget']):,.0f} руб.**\n"
                text += f"• Общая сумма выполненного: **{float(efficiency_stats['total_completed_budget'] or 0):,.0f} руб.**\n"

            if time_stats['avg_hours_to_complete']:
                text += f"• Среднее время выполнения: **{float(time_stats['avg_hours_to_complete']):.1f} часов**\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📦 Мои заявки", callback_data="my_applications_stats"),
            InlineKeyboardButton("👥 Мои перевозчики", callback_data="my_executors_stats"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'my_period_stats')
    def handle_my_period_stats(call):
        """Статистика логиста по периодам"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - логист
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'external_logist']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Заявки за разные периоды
        period_stats = db.fetch_all("""
            SELECT 
                CASE 
                    WHEN created_at >= datetime('now', 'start of day') THEN 'today'
                    WHEN created_at >= datetime('now', 'start of day', '-6 days') THEN 'week'
                    WHEN created_at >= datetime('now', 'start of month') THEN 'month'
                    ELSE 'older'
                END as period,
                COUNT(*) as applications,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed
            FROM applications
            WHERE created_by = ?
            GROUP BY period
        """, (user_id,))

        # Конвертируем в словарь для удобства
        stats_dict = {stat['period']: stat for stat in period_stats}

        # Формируем текст
        text = f"📅 **Статистика по периодам**\n\n"

        today = stats_dict.get('today', {'applications': 0, 'completed': 0})
        week = stats_dict.get('week', {'applications': 0, 'completed': 0})
        month = stats_dict.get('month', {'applications': 0, 'completed': 0})
        older = stats_dict.get('older', {'applications': 0, 'completed': 0})

        text += f"📊 **Сегодня:**\n"
        text += f"• Заявок: **{today['applications']}**\n"
        text += f"• Выполнено: **{today['completed']}**\n"

        text += f"\n📊 **Текущая неделя:**\n"
        text += f"• Заявок: **{week['applications']}**\n"
        text += f"• Выполнено: **{week['completed']}**\n"

        text += f"\n📊 **Текущий месяц:**\n"
        text += f"• Заявок: **{month['applications']}**\n"
        text += f"• Выполнено: **{month['completed']}**\n"

        text += f"\n📊 **Всего:**\n"
        total_apps = today['applications'] + week['applications'] + month['applications'] + older['applications']
        total_completed = today['completed'] + week['completed'] + month['completed'] + older['completed']
        text += f"• Заявок: **{total_apps}**\n"
        text += f"• Выполнено: **{total_completed}**\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📦 Мои заявки", callback_data="my_applications_stats"),
            InlineKeyboardButton("👥 Мои перевозчики", callback_data="my_executors_stats"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    # ========== ОБРАБОТЧИКИ ДЛЯ ПЕРЕВОЗЧИКОВ ==========

    @bot.callback_query_handler(func=lambda call: call.data == 'my_responses_stats')
    def handle_my_responses_stats(call):
        """Статистика откликов перевозчика"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['executor', 'external_executor']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Статистика откликов перевозчика
        responses_stats = db.fetch_one("""
            SELECT 
                COUNT(*) as total_responses,
                COUNT(CASE WHEN status = 'counter_offer' THEN 1 END) as counter_offers,
                COUNT(CASE WHEN status = 'accepted_budget' THEN 1 END) as accepted_budget,
                COUNT(CASE WHEN status = 'selected' THEN 1 END) as selected,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COUNT(DISTINCT application_id) as unique_applications
            FROM application_responses
            WHERE executor_id = ?
        """, (user_id,))

        # Статистика по типам заявок
        application_types_stats = db.fetch_all("""
            SELECT 
                a.application_type,
                COUNT(DISTINCT a.id) as applications_count,
                COUNT(DISTINCT CASE WHEN ar.status = 'selected' THEN a.id END) as selected_count
            FROM application_responses ar
            JOIN applications a ON ar.application_id = a.id
            WHERE ar.executor_id = ?
            GROUP BY a.application_type
        """, (user_id,))

        # Формируем текст
        user_info = db.get_user_by_telegram_id(user_id)
        company_info = None
        if user_info.get('company_id'):
            company_info = db.get_company_by_id(user_info['company_id'])

        text = f"📊 **Статистика ваших откликов**\n\n"
        text += f"👤 **Перевозчик:** {user_info['first_name']} {user_info.get('last_name', '')}\n"
        if company_info:
            text += f"🏢 **Компания:** {company_info['name']}\n"
        text += f"\n"

        text += f"💰 **Всего откликов:** **{responses_stats['total_responses'] or 0}**\n"
        text += f"• Встречных предложений: **{responses_stats['counter_offers'] or 0}**\n"
        text += f"• Принятых по бюджету: **{responses_stats['accepted_budget'] or 0}**\n"
        text += f"• Выбранных: **{responses_stats['selected'] or 0}**\n"
        text += f"• Отклоненных: **{responses_stats['rejected'] or 0}**\n"
        text += f"• Уникальных заявок: **{responses_stats['unique_applications'] or 0}**\n"

        if responses_stats['selected'] > 0:
            success_rate = (responses_stats['selected'] / responses_stats['total_responses']) * 100
            text += f"• Успешность: **{success_rate:.1f}%**\n"

        text += f"\n📋 **По типам заявок:**\n"
        for stat in application_types_stats:
            type_name = "Фиксированная" if stat['application_type'] == 'fixed' else "Аукцион"
            text += f"• **{type_name}**: {stat['applications_count']} заявок\n"
            if stat['selected_count'] > 0:
                text += f"  Выбрано: {stat['selected_count']}\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("✅ Выполненные заявки", callback_data="completed_applications"),
            InlineKeyboardButton("💰 Финансовая статистика", callback_data="executor_financial_stats"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'completed_applications')
    def handle_completed_applications(call):
        """Выполненные заявки перевозчика"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['executor', 'external_executor']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Выполненные заявки перевозчика
        completed_stats = db.fetch_all("""
            SELECT 
                a.id,
                a.application_type,
                a.desired_budget,
                a.loading_datetime,
                a.unloading_datetime,
                a.status,
                u.first_name as logist_first_name,
                u.last_name as logist_last_name
            FROM applications a
            JOIN application_responses ar ON a.id = ar.application_id
            JOIN users u ON a.created_by = u.telegram_id
            WHERE ar.executor_id = ? 
                AND ar.status = 'selected'
                AND a.status IN ('completed', 'assigned')
            ORDER BY a.created_at DESC
            LIMIT 10
        """, (user_id,))

        # Общая статистика по выполненным
        total_stats = db.fetch_one("""
            SELECT 
                COUNT(DISTINCT a.id) as total_completed,
                SUM(a.desired_budget) as total_budget,
                AVG(a.desired_budget) as avg_budget
            FROM applications a
            JOIN application_responses ar ON a.id = ar.application_id
            WHERE ar.executor_id = ? 
                AND ar.status = 'selected'
                AND a.status IN ('completed', 'assigned')
        """, (user_id,))

        # Формируем текст
        text = f"✅ **Ваши выполненные заявки**\n\n"

        if not completed_stats:
            text += "У вас еще нет выполненных заявок.\n"
        else:
            text += f"📊 **Общая статистика:**\n"
            text += f"• Всего выполнено: **{total_stats['total_completed'] or 0}**\n"
            if total_stats['total_budget']:
                text += f"• Общая сумма: **{float(total_stats['total_budget']):,.0f} руб.**\n"
                text += f"• Средняя сумма: **{float(total_stats['avg_budget'] or 0):,.0f} руб.**\n"

            text += f"\n📋 **Последние заявки:**\n"
            for i, app in enumerate(completed_stats, 1):
                type_name = "Фиксированная" if app['application_type'] == 'fixed' else "Аукцион"
                logist_name = f"{app['logist_first_name']} {app['logist_last_name']}"
                status = "✅ Выполнена" if app['status'] == 'completed' else "⏳ В работе"

                text += f"\n**{i}. Заявка #{app['id']}** ({type_name})\n"
                text += f"   👤 Логист: {logist_name}\n"
                text += f"   💰 Сумма: {float(app['desired_budget']):,.0f} руб.\n"
                text += f"   📅 Загрузка: {app['loading_datetime'][:16] if app.get('loading_datetime') else 'Не указана'}\n"
                text += f"   🏁 Выгрузка: {app['unloading_datetime'][:16] if app.get('unloading_datetime') else 'Не указана'}\n"
                text += f"   📊 Статус: {status}\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📦 Мои отклики", callback_data="my_responses_stats"),
            InlineKeyboardButton("💰 Финансовая статистика", callback_data="executor_financial_stats"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'executor_financial_stats')
    def handle_executor_financial_stats(call):
        """Финансовая статистика перевозчика"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['executor', 'external_executor']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Финансовая статистика
        financial_stats = db.fetch_one("""
            SELECT 
                COUNT(DISTINCT CASE WHEN a.status = 'completed' THEN a.id END) as completed_count,
                SUM(CASE WHEN a.status = 'completed' THEN a.desired_budget ELSE 0 END) as completed_budget,
                COUNT(DISTINCT CASE WHEN a.status = 'assigned' THEN a.id END) as assigned_count,
                SUM(CASE WHEN a.status = 'assigned' THEN a.desired_budget ELSE 0 END) as assigned_budget,
                AVG(CASE WHEN a.status = 'completed' THEN a.desired_budget END) as avg_completed_budget
            FROM applications a
            JOIN application_responses ar ON a.id = ar.application_id
            WHERE ar.executor_id = ? AND ar.status = 'selected'
        """, (user_id,))

        # Статистика по месяцам
        monthly_stats = db.fetch_all("""
            SELECT 
                strftime('%Y-%m', a.created_at) as month,
                COUNT(DISTINCT a.id) as applications,
                SUM(a.desired_budget) as total_budget
            FROM applications a
            JOIN application_responses ar ON a.id = ar.application_id
            WHERE ar.executor_id = ? 
                AND ar.status = 'selected'
                AND a.status IN ('completed', 'assigned')
            GROUP BY strftime('%Y-%m', a.created_at)
            ORDER BY month DESC
            LIMIT 6
        """, (user_id,))

        # Формируем текст
        text = f"💰 **Ваша финансовая статистика**\n\n"

        text += f"📊 **Выполненные заявки:**\n"
        text += f"• Количество: **{financial_stats['completed_count'] or 0}**\n"
        if financial_stats['completed_budget']:
            text += f"• Общая сумма: **{float(financial_stats['completed_budget']):,.0f} руб.**\n"
            if financial_stats['avg_completed_budget']:
                text += f"• Средняя сумма: **{float(financial_stats['avg_completed_budget']):,.0f} руб.**\n"

        text += f"\n📊 **Заявки в работе:**\n"
        text += f"• Количество: **{financial_stats['assigned_count'] or 0}**\n"
        if financial_stats['assigned_budget']:
            text += f"• Общая сумма: **{float(financial_stats['assigned_budget']):,.0f} руб.**\n"

        total_budget = (financial_stats['completed_budget'] or 0) + (financial_stats['assigned_budget'] or 0)
        if total_budget > 0:
            text += f"\n💰 **Общая сумма всех заявок:** **{float(total_budget):,.0f} руб.**\n"

        if monthly_stats:
            text += f"\n📅 **По месяцам:**\n"
            for stat in monthly_stats:
                month_str = datetime.strptime(stat['month'], '%Y-%m').strftime('%m.%Y')
                text += f"• **{month_str}**: {stat['applications']} заявок, {float(stat['total_budget']):,.0f} руб.\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📦 Мои отклики", callback_data="my_responses_stats"),
            InlineKeyboardButton("✅ Выполненные заявки", callback_data="completed_applications"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'executor_efficiency')
    def handle_executor_efficiency(call):
        """Рейтинг эффективности перевозчика"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['executor', 'external_executor']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Рейтинг среди всех перевозчиков
        ranking_stats = db.fetch_one("""
            WITH executor_stats AS (
                SELECT 
                    ar.executor_id,
                    COUNT(*) as total_responses,
                    COUNT(CASE WHEN ar.status = 'selected' THEN 1 END) as selected_count,
                    ROUND(CAST(COUNT(CASE WHEN ar.status = 'selected' THEN 1 END) AS FLOAT) / COUNT(*) * 100, 1) as success_rate,
                    COUNT(DISTINCT a.id) as completed_count,
                    SUM(CASE WHEN a.status = 'completed' THEN a.desired_budget ELSE 0 END) as completed_budget
                FROM application_responses ar
                LEFT JOIN applications a ON ar.application_id = a.id AND ar.status = 'selected'
                GROUP BY ar.executor_id
            )
            SELECT 
                (SELECT COUNT(*) FROM executor_stats) as total_executors,
                (SELECT COUNT(*) FROM executor_stats WHERE completed_count > 0) as active_executors,
                (SELECT RANK() OVER (ORDER BY completed_budget DESC) FROM executor_stats WHERE executor_id = ?) as budget_rank,
                (SELECT RANK() OVER (ORDER BY success_rate DESC) FROM executor_stats WHERE executor_id = ?) as success_rank,
                (SELECT success_rate FROM executor_stats WHERE executor_id = ?) as my_success_rate,
                (SELECT completed_budget FROM executor_stats WHERE executor_id = ?) as my_completed_budget,
                (SELECT completed_count FROM executor_stats WHERE executor_id = ?) as my_completed_count
        """, (user_id, user_id, user_id, user_id, user_id))

        # Формируем текст
        text = f"📈 **Ваш рейтинг эффективности**\n\n"

        if ranking_stats['my_success_rate'] is None:
            text += "У вас еще нет достаточно данных для формирования рейтинга.\n"
            text += "Начните откликаться на заявки, чтобы увидеть свою статистику.\n"
        else:
            text += f"📊 **Ваши показатели:**\n"
            text += f"• Успешность откликов: **{ranking_stats['my_success_rate']}%**\n"
            text += f"• Выполнено заявок: **{ranking_stats['my_completed_count'] or 0}**\n"
            if ranking_stats['my_completed_budget']:
                text += f"• Общая сумма выполненного: **{float(ranking_stats['my_completed_budget']):,.0f} руб.**\n"

            text += f"\n🏆 **Ваше место среди перевозчиков:**\n"
            text += f"• Всего перевозчиков: **{ranking_stats['total_executors']}**\n"
            text += f"• Активных перевозчиков: **{ranking_stats['active_executors']}**\n"

            if ranking_stats['budget_rank']:
                text += f"• Место по объему выполненного: **#{ranking_stats['budget_rank']}**\n"

            if ranking_stats['success_rank']:
                text += f"• Место по успешности: **#{ranking_stats['success_rank']}**\n"

            # Даем рекомендации
            text += f"\n💡 **Рекомендации:**\n"
            if ranking_stats['my_success_rate'] < 30:
                text += "• Старайтесь делать более конкурентные предложения\n"
                text += "• Улучшайте качество откликов\n"
            elif ranking_stats['my_success_rate'] < 60:
                text += "• Хорошие показатели! Продолжайте в том же духе\n"
                text += "• Увеличивайте количество откликов\n"
            else:
                text += "• Отличные результаты! Вы один из лучших перевозчиков\n"
                text += "• Продолжайте поддерживать высокое качество работы\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📦 Мои отклики", callback_data="my_responses_stats"),
            InlineKeyboardButton("✅ Выполненные заявки", callback_data="completed_applications"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_stats_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    # ========== ОБЩИЙ ОБРАБОТЧИК ДЛЯ КНОПКИ "НАЗАД" ==========

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_stats_menu')
    def handle_back_to_stats_menu(call):
        """Возвращает в главное меню статистики"""
        user_id = call.from_user.id

        # Создаем фиктивное сообщение для вызова главного меню
        fake_message = type('FakeMessage', (), {
            'from_user': type('FakeUser', (), {'id': user_id})(),
            'chat': type('FakeChat', (), {'id': call.message.chat.id})(),
            'text': '📊 Статистика'
        })()

        # Удаляем старое сообщение из словаря, чтобы новое меню отправилось как новое сообщение
        if user_id in last_stats_messages:
            try:
                bot.delete_message(call.message.chat.id, last_stats_messages[user_id])
            except:
                pass
            del last_stats_messages[user_id]

        # Вызываем главное меню статистики
        handle_statistics_menu(fake_message)
        bot.answer_callback_query(call.id)


def get_role_display_name(role):
    """Возвращает читаемое название роли"""
    role_names = {
        'admin': 'Администратор',
        'logist': 'Логист',
        'executor': 'Перевозчик',
        'external_admin': 'Внешний администратор',
        'external_logist': 'Внешний логист',
        'external_executor': 'Внешний перевозчик'
    }
    return role_names.get(role, role)