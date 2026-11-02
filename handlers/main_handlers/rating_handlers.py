from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from handlers.registration_handlers.registration_user_handlers import set_user_state
from utils.dicts import logist_rating_rules, executor_rating_rules, role_names


def register_rating_handlers(bot, db):
    """Регистрация обработчиков для системы рейтингов"""

    @bot.message_handler(func=lambda message: message.text == '🏆 Рейтинг')
    def handle_rating_menu(message):
        """Показывает меню рейтингов в зависимости от роли пользователя"""
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

        # Получаем информацию о пользователе
        user_info = db.get_user_by_telegram_id(user_id)
        if not user_info:
            bot.send_message(chat_id, "❌ Пользователь не найден.")
            return

        user_role = user_info['role']

        # Создаем клавиатуру в зависимости от роли
        keyboard = InlineKeyboardMarkup(row_width=1)

        if user_role in ['admin', 'external_admin']:
            # Администраторы видят все рейтинги
            keyboard.add(
                InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="admin_logist_rating"),
                InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="admin_executor_rating"),
                # InlineKeyboardButton("🏅 Мои рейтинги", callback_data="my_ratings")
            )

            # Получаем текущий рейтинг из базы (если есть)
            rating_type = 'logist' if user_role == 'admin' else 'external_admin'
            rating_data = db.fetch_one("""
                SELECT current_rating FROM user_ratings 
                WHERE user_id = ? AND rating_type = ?
            """, (user_id, rating_type))

            current_rating = rating_data['current_rating'] if rating_data else 0.0

            bot.send_message(
                chat_id,
                f"🏆 **Система рейтингов**\n\n"
                f"👤 Ваша роль: **{role_names.get(user_role)}**\n"
                f"⭐ **Текущий рейтинг:** {current_rating:.1f}/100.0\n"
                f"🏅 **Уровень:** {get_rating_level(current_rating)}\n\n"
                f"Выберите рейтинг для просмотра:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )

        elif user_role in ['logist', 'external_logist']:
            # Логисты видят рейтинги перевозчиков и свой рейтинг
            keyboard.add(
                InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="logist_executor_rating"),
                InlineKeyboardButton("🏆 Мой рейтинг", callback_data="my_logist_rating"),
                InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="logists_rating"),
            )

            # Получаем текущий рейтинг логиста из базы
            rating_info = get_logist_rating(user_id, db)
            bot.send_message(
                chat_id,
                f"🏆 **Система рейтингов**\n\n"
                f"👤 **Логист:** {user_info['first_name']} {user_info.get('last_name', '')}\n"
                f"⭐ **Текущий рейтинг:** {rating_info.get('current_rating', 0.0):.1f}/100.0\n"
                f"🏅 **Уровень:** {rating_info.get('level', 'Начинающий')}\n\n"
                f"Выберите рейтинг для просмотра:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        elif user_role in ['executor', 'external_executor']:
            # Перевозчики видят рейтинги и свой рейтинг
            keyboard.add(
                InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="executors_rating"),
                InlineKeyboardButton("🏆 Мой рейтинг", callback_data="my_executor_rating"),
                InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="executor_logist_rating"),
            )

            # Получаем текущий рейтинг перевозчика из базы
            rating_info = get_executor_rating(user_id, db)

            bot.send_message(
                chat_id,
                f"🏆 **Система рейтингов**\n\n"
                f"👤 **Перевозчик:** {user_info['first_name']} {user_info.get('last_name', '')}\n"
                f"⭐ **Текущий рейтинг:** {rating_info.get('current_rating', 0.0):.1f}/100.0\n"
                f"🏅 **Уровень:** {rating_info.get('level', 'Начинающий')}\n"
                f"📊 **Место в рейтинге:** #{rating_info.get('rank', '?')}\n\n"
                f"Выберите рейтинг для просмотра:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            bot.send_message(chat_id, "❌ Ваша роль не поддерживает просмотр рейтингов.")

    def get_logist_rating_info(user_id, db):
        """Получение информации о рейтинге логиста из базы данных"""
        user_info = db.get_user_by_telegram_id(user_id)
        rating_type = ''
        if user_info['role'] in ['logist', 'external_logist', 'admin', 'external_admin']:
            rating_type = 'logist'

        rating_data = db.fetch_one("""
            SELECT * FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))

        if not rating_data:
            return {
                'current_rating': 0.0,
                'level': get_rating_level(0.0),
                'rank': get_logist_rank(user_id, db)
            }

        # Получаем место в рейтинге
        rank = get_logist_rank(user_id, db)

        return {
            'current_rating': rating_data.get('current_rating', 0.0),
            'level': get_rating_level(rating_data.get('current_rating', 0.0)),
            'rank': rank,
        }

    def update_logist_rating_in_db(user_id, db):
        """Обновление рейтинга логиста в базе данных"""
        user_info = db.get_user_by_telegram_id(user_id)
        rating_type = ''

        if user_info['role'] in ['logist', 'external_logist']:
            rating_type = 'logist'

        rating_all = db.get_rating(user_id)

        # Проверяем, существует ли запись
        existing_rating = db.fetch_one("""
            SELECT id FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))

        if existing_rating:
            # Обновляем существующую запись
            db.execute_query("""
                UPDATE user_ratings 
                SET current_rating = ?
                    updated_at = datetime('now')
                WHERE user_id = ? AND rating_type = ?
            """, (rating_all['current_rating'], user_id, rating_type))
        else:
            # Создаем новую запись
            db.execute_query("""
                INSERT INTO user_ratings (user_id, rating_type, current_rating)
                VALUES (?, ?, ?)
            """, (user_id, rating_type, rating_all))

    def get_logist_rank(user_id, db):
        """Получение места логиста в общем рейтинге"""
        user_info = db.get_user_by_telegram_id(user_id)

        all_logists = db.fetch_all("""
            SELECT ur.user_id, ur.current_rating
            FROM user_ratings ur
            JOIN users u ON ur.user_id = u.telegram_id
            WHERE ur.rating_type IN ('logist', 'external_logist')
            ORDER BY ur.current_rating DESC
        """)

        # Находим место текущего пользователя
        for i, logist in enumerate(all_logists, 1):
            if logist['user_id'] == user_id:
                return i

        return None

    @bot.callback_query_handler(func=lambda call: call.data == 'my_logist_rating')
    def handle_my_logist_rating(call):
        """Показывает рейтинг логиста"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - логист
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['logist', 'external_logist', 'admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Получаем информацию о пользователе
        user_info = db.get_user_by_telegram_id(user_id)

        # Получаем рейтинг
        rating_info = get_logist_rating_info(user_id, db)
        print(rating_info)

        # Формируем текст
        text = f"🏆 **Ваш рейтинг как логиста**\n\n"
        text += f"👤 **Логист:** {user_info['first_name']} {user_info.get('last_name', '')}\n\n"

        text += f"⭐ **Общий рейтинг:** **{rating_info['current_rating']:.1f}/100.0**\n"
        text += f"🏅 **Уровень:** **{rating_info['level']}**\n"
        if rating_info['rank']:
            text += f"📊 **Место в рейтинге:** **#{rating_info['rank']}**\n"



        text += f"\n"

        # Рекомендации по улучшению
        text += f"💡 **Рекомендации для улучшения рейтинга:**\n"
        if rating_info['current_rating'] < 50:
            text += "• Создавайте больше заявок\n"
            text += "• Улучшайте описание заявок для привлечения перевозчиков\n"
            text += "• Быстрее выбирайте перевозчиков\n"
        elif rating_info['current_rating'] < 70:
            text += "• Увеличивайте долю выполненных заявок\n"
            text += "• Снижайте время на выбор перевозчика\n"
            text += "• Привлекайте больше перевозчиков к каждой заявке\n"
        elif rating_info['current_rating'] < 90:
            text += "• Поддерживайте высокое качество заявок\n"
            text += "• Оптимизируйте бюджеты заявок\n"
            text += "• Создавайте долгосрочные отношения с перевозчиками\n"
        else:
            text += "• Отличные результаты! Продолжайте в том же духе\n"
            text += "• Делитесь опытом с другими логистами\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="logist_executor_rating"),
            InlineKeyboardButton("🏆 Рейтинг среди логистов", callback_data="logists_rating"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_rating_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'logists_rating')
    def handle_logists_rating(call):
        """Показывает рейтинг всех логистов"""
        user_id = call.from_user.id

        # Получаем всех логистов с их рейтингами
        logists = db.fetch_all("""
            SELECT 
                u.telegram_id, 
                u.first_name, 
                u.last_name, 
                u.role,
                ur.current_rating
            FROM users u
            LEFT JOIN user_ratings ur ON u.telegram_id = ur.user_id 
                AND ur.rating_type = CASE 
                    WHEN u.role = 'logist' THEN 'logist' 
                    WHEN u.role = 'external_logist' THEN 'logist' 
                    WHEN u.role = 'admin' THEN 'logist'
                    WHEN u.role = 'external_admin' THEN 'logist'
                    ELSE NULL 
                END
            WHERE u.role IN ('logist', 'external_logist')
            ORDER BY COALESCE(ur.current_rating, 0) DESC
        """)

        print(logists)

        # Формируем текст
        text = f"🏆 **Рейтинг логистов**\n\n"

        if not logists:
            text += "Нет данных о логистах.\n"
        else:
            text += "**Топ логистов по рейтингу:**\n\n"

            # Медали для топ-3
            medals = ["🥇", "🥈", "🥉"]

            for i, logist in enumerate(logists[:20], 1):
                medal = medals[i - 1] if i <= 3 else f"{i}."
                role_emoji = "👔" if logist['role'] == 'logist' else "🌐"

                # Рассчитываем уровень динамически
                current_rating = logist['current_rating'] or 0
                level = get_rating_level(current_rating)

                text += f"{medal} **{logist['first_name']} {logist['last_name']}** {role_emoji}\n"
                text += f"   ⭐ Рейтинг: **{current_rating:.1f}/100.0**\n"
                text += f"   🏅 Уровень: **{level}**\n"

                # Если это текущий пользователь, выделяем
                if logist['telegram_id'] == user_id:
                    text += f"   👈 **Это вы!**\n"

                text += "\n"

            if len(logists) > 20:
                text += f"\n... и еще {len(logists) - 20} логистов\n"


        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        if db.get_user_role(user_id)['role'] in ['logist', 'external_logist']:
            keyboard.add(
                InlineKeyboardButton("🏆 Мой рейтинг", callback_data="my_logist_rating")
            )
        keyboard.add(
        InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="logist_executor_rating"),
        InlineKeyboardButton("↩️ Назад", callback_data="back_to_rating_menu")
        )


        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    # ========== РЕЙТИНГ перевозчиков ==========

    def get_executor_rating_info(user_id, db):
        """Получение информации о рейтинге перевозчика из базы данных"""
        user_info = db.get_user_by_telegram_id(user_id)
        rating_type = ''
        if user_info['role'] == 'executor' or user_info['role']== 'external_executor':
            rating_type = 'executor'

        rating_data = db.fetch_one("""
            SELECT * FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))
        print(rating_data)
        if not rating_data:
            return {
                'current_rating': 0.0,
                'level': get_rating_level(0.0),
                'rank': get_executor_rank(user_id, db)
            }

        # Получаем место в рейтинге
        rank = get_executor_rank(user_id, db)

        return {
            'current_rating': rating_data.get('current_rating', 0.0),
            'level': get_rating_level(rating_data.get('current_rating', 0.0)),
            'rank': rank,
        }

    def update_executor_rating_in_db(user_id, db):
        """Обновление рейтинга перевозчика в базе данных"""
        user_info = db.get_user_by_telegram_id(user_id)
        rating_type = ''
        if user_info['role'] == 'executor' or user_info['role'] == 'external_executor':
            rating_type = 'executor'

        # Рассчитываем общий рейтинг
        rating_all = db.get_rating(user_id)

        # Проверяем, существует ли запись
        existing_rating = db.fetch_one("""
            SELECT id FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))

        if existing_rating:
            # Обновляем существующую запись
            db.execute_query("""
                UPDATE user_ratings 
                SET current_rating = ?
                    updated_at = datetime('now')
                WHERE user_id = ? AND rating_type = ?
            """, (rating_all['current_rating'], user_id, rating_type))
        else:
            # Создаем новую запись
            db.execute_query("""
                INSERT INTO user_ratings (user_id, rating_type, current_rating)
                VALUES (?, ?, ?)
            """, (user_id, rating_type, rating_all))

    def get_executor_rank(user_id, db):
        """Получение места перевозчика в общем рейтинге"""
        user_info = db.get_user_by_telegram_id(user_id)

        all_executors = db.fetch_all("""
            SELECT ur.user_id, ur.current_rating
            FROM user_ratings ur
            JOIN users u ON ur.user_id = u.telegram_id
            WHERE ur.rating_type IN ('executor', 'external_executor')
            ORDER BY ur.current_rating DESC
        """)

        # Находим место текущего пользователя
        for i, executor in enumerate(all_executors, 1):
            if executor['user_id'] == user_id:
                return i

        return None

    @bot.callback_query_handler(func=lambda call: call.data == 'my_executor_rating')
    def handle_my_executor_rating(call):
        """Показывает рейтинг перевозчика"""
        user_id = call.from_user.id

        # Проверяем, что пользователь - перевозчик
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['executor', 'external_executor']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Обновляем рейтинг в базе
        update_executor_rating_in_db(user_id, db)

        # Получаем информацию о пользователе
        user_info = db.get_user_by_telegram_id(user_id)

        # Получаем рейтинг
        rating_info = get_executor_rating_info(user_id, db)

        # Формируем текст
        text = f"🏆 **Ваш рейтинг как перевозчика**\n\n"
        text += f"👤 **Перевозчик:** {user_info['first_name']} {user_info.get('last_name', '')}\n\n"

        text += f"⭐ **Общий рейтинг:** **{rating_info['current_rating']:.1f}/100.0**\n"
        text += f"🏅 **Уровень:** **{rating_info['level']}**\n"
        if rating_info['rank']:
            text += f"📊 **Место в рейтинге:** **#{rating_info['rank']}**\n"



        text += f"\n"

        # Рекомендации по улучшению
        text += f"💡 **Рекомендации для улучшения рейтинга:**\n"
        if rating_info['current_rating'] < 50:
            text += "• Увеличивайте количество откликов\n"
            text += "• Делайте более конкурентные предложения\n"
            text += "• Откликайтесь на разные типы заявок\n"
        elif rating_info['current_rating'] < 70:
            text += "• Повышайте качество откликов\n"
            text += "• Улучшайте скорость выполнения заявок\n"
            text += "• Работайте с разными логистами\n"
        elif rating_info['current_rating'] < 90:
            text += "• Поддерживайте высокое качество работы\n"
            text += "• Оптимизируйте время выполнения\n"
            text += "• Создавайте долгосрочные отношения с логистами\n"
        else:
            text += "• Отличные результаты! Продолжайте в том же духе\n"
            text += "• Делитесь опытом с другими перевозчиками\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="executors_rating"),
            InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="executor_logist_rating"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_rating_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'executors_rating')
    def handle_executors_rating(call):
        """Показывает рейтинг всех перевозчиков"""
        user_id = call.from_user.id
        user_role = db.get_user_role(user_id)

        # Получаем всех перевозчиков с их рейтингами
        executors = db.fetch_all("""
            SELECT 
                u.telegram_id, 
                u.first_name, 
                u.last_name, 
                u.role, 
                c.name as company_name,
                ur.current_rating
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.id
            LEFT JOIN user_ratings ur ON u.telegram_id = ur.user_id 
                AND ur.rating_type = CASE 
                    WHEN u.role = 'executor' THEN 'executor' 
                    WHEN u.role = 'external_executor' THEN 'executor' 
                    ELSE NULL 
                END
            WHERE u.role IN ('executor', 'external_executor')
            ORDER BY COALESCE(ur.current_rating, 0) DESC
        """)

        # Формируем текст
        text = f"🏆 **Рейтинг перевозчиков**\n\n"

        if not executors:
            text += "Нет данных об перевозчиках.\n"
        else:
            text += "**Топ перевозчиков по рейтингу:**\n\n"

            # Медали для топ-3
            medals = ["🥇", "🥈", "🥉"]

            for i, executor in enumerate(executors[:20], 1):
                medal = medals[i - 1] if i <= 3 else f"{i}."
                role_emoji = "👷" if executor['role'] == 'executor' else "🌐"
                company_text = f"🏢 {executor['company_name']}" if executor['company_name'] else ""

                # Рассчитываем уровень динамически
                current_rating = executor['current_rating'] or 0
                level = get_rating_level(current_rating)

                text += f"{medal} **{executor['first_name']} {executor['last_name']}** {role_emoji}\n"
                text += f"   ⭐ Рейтинг: **{current_rating:.1f}/100.0**\n"
                text += f"   🏅 Уровень: **{level}**\n"
                if company_text:
                    text += f"   {company_text}\n"

                # Если это текущий пользователь, выделяем
                if executor['telegram_id'] == user_id:
                    text += f"   👈 **Это вы!**\n"

                text += "\n"

            if len(executors) > 20:
                text += f"\n... и еще {len(executors) - 20} перевозчиков\n"


        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        if user_role['role'] not in ['admin', 'external_admin']:
            keyboard.add(
               InlineKeyboardButton("🏆 Мой рейтинг", callback_data="my_executor_rating")
            )
        keyboard.add(
            InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="executor_logist_rating"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_rating_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    # ========== ОБЩИЕ ОБРАБОТЧИКИ ==========

    @bot.callback_query_handler(func=lambda call: call.data == 'logist_executor_rating')
    def handle_logist_executor_rating(call):
        """Рейтинг перевозчиков для логистов"""
        handle_executors_rating(call)

    @bot.callback_query_handler(func=lambda call: call.data == 'executor_logist_rating')
    def handle_executor_logist_rating(call):
        """Рейтинг логистов для перевозчиков"""
        handle_logists_rating(call)

    @bot.callback_query_handler(func=lambda call: call.data == 'refresh_executor_rating')
    def handle_refresh_executor_rating(call):
        """Обновление рейтинга перевозчика"""
        user_id = call.from_user.id
        update_executor_rating_in_db(user_id, db)
        bot.answer_callback_query(call.id, "✅ Рейтинг обновлен")
        handle_my_executor_rating(call)

    # ========== ОБРАБОТЧИКИ ДЛЯ АДМИНИСТРАТОРОВ ==========

    @bot.callback_query_handler(func=lambda call: call.data == 'admin_logist_rating')
    def handle_admin_logist_rating(call):
        """Рейтинг логистов для администратора"""
        handle_logists_rating(call)

    @bot.callback_query_handler(func=lambda call: call.data == 'admin_executor_rating')
    def handle_admin_executor_rating(call):
        """Рейтинг перевозчиков для администратора"""
        handle_executors_rating(call)

    @bot.callback_query_handler(func=lambda call: call.data == 'my_ratings')
    def handle_my_ratings(call):
        """Мои рейтинги для администратора"""
        user_id = call.from_user.id

        # Проверяем права
        user_info = db.get_user_by_telegram_id(user_id)
        if user_info['role'] not in ['admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        text = f"🏆 **Мои рейтинги**\n\n"

        # Получаем рейтинг админа (если есть)
        rating_type = 'admin' if user_info['role'] == 'admin' else 'external_admin'
        rating_data = db.fetch_one("""
            SELECT * FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))

        text += f"👑 **Как администратор:**\n"
        text += f"⭐ Ваша роль: **{role_names.get(user_info['role'])}**\n"

        if rating_data:
            text += f"⭐ Общий рейтинг: **{rating_data['current_rating']:.1f}/100**\n"
            text += f"🏅 Уровень: **{get_rating_level(rating_data['current_rating'])}**\n"

        else:
            text += "⭐ Общий рейтинг: **0.0/100**\n"
            text += "🏅 Уровень: **На старте**\n"

        text += f"\n📊 У вас есть доступ ко всем рейтингам системы\n"

        # Получаем информацию о рейтингах в системе
        system_stats = db.fetch_one("""
            SELECT 
                COUNT(DISTINCT CASE WHEN rating_type IN ('logist', 'external_logist') THEN user_id END) as total_logists,
                COUNT(DISTINCT CASE WHEN rating_type IN ('executor', 'external_executor') THEN user_id END) as total_executors,
                AVG(CASE WHEN rating_type IN ('logist', 'external_logist') THEN current_rating END) as avg_logist_rating,
                AVG(CASE WHEN rating_type IN ('executor', 'external_executor') THEN current_rating END) as avg_executor_rating
            FROM user_ratings
        """)

        if system_stats:
            text += f"\n📈 **Статистика системы:**\n"
            text += f"• Всего логистов в рейтинге: **{system_stats['total_logists']}**\n"
            text += f"• Всего перевозчиков в рейтинге: **{system_stats['total_executors']}**\n"
            if system_stats['avg_logist_rating']:
                text += f"• Средний рейтинг логистов: **{system_stats['avg_logist_rating']:.1f}/100**\n"
            if system_stats['avg_executor_rating']:
                text += f"• Средний рейтинг перевозчиков: **{system_stats['avg_executor_rating']:.1f}/100**\n"

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="admin_logist_rating"),
            InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="admin_executor_rating"),
            InlineKeyboardButton("↩️ Назад", callback_data="back_to_rating_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'refresh_all_ratings')
    def handle_refresh_all_ratings(call):
        """Обновление всех рейтингов"""
        user_id = call.from_user.id

        # Проверяем права
        user_info = db.get_user_by_telegram_id(user_id)
        if user_info['role'] not in ['admin', 'external_admin']:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        # Обновляем рейтинг
        bot.answer_callback_query(call.id, "🔄 Обновляем все рейтинги...")

        # Обновляем рейтинг админа
        rating_type = 'admin' if user_info['role'] == 'admin' else 'external_admin'
        existing_rating = db.fetch_one("""
            SELECT id FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))

        if existing_rating:
            db.execute_query("""
                UPDATE user_ratings 
                SET current_rating = current_rating
                    updated_at = datetime('now')
                WHERE user_id = ? AND rating_type = ?
            """, (user_id, rating_type))
        else:
            db.execute_query("""
                INSERT INTO user_ratings (user_id, rating_type, current_rating)
                VALUES (?, ?, ?)
            """, (user_id, rating_type, 0.0))

        # Показываем обновленные данные
        handle_my_ratings(call)

    # ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

    def get_rating_level(rating):
        """Определение уровня по рейтингу (100-балльная система)"""
        rating = float(rating) if rating else 0.0
        if rating >= 90.0:
            return "Эксперт"
        elif rating >= 80.0:
            return "Профессионал"
        elif rating >= 70.0:
            return "Опытный"
        elif rating >= 60.0:
            return "Средний"
        elif rating >= 50.0:
            return "Начинающий"
        elif rating >= 30.0:
            return "Новичок"
        else:
            return "На старте"

    def get_logist_rating(user_id, db):
        """Быстрое получение рейтинга логиста из базы"""
        user_info = db.get_user_by_telegram_id(user_id)
        if not user_info:
            return {'current_rating': 0.0}

        rating_type = 'logist' if user_info['role'] == 'logist' else 'external_logist'

        rating_data = db.fetch_one("""
            SELECT current_rating
            FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))

        current_rating = rating_data['current_rating'] if rating_data else 0.0

        return {
            'current_rating': current_rating,
            'level': get_rating_level(current_rating)
        }

    def get_executor_rating(user_id, db):
        """Быстрое получение рейтинга перевозчика из базы"""
        user_info = db.get_user_by_telegram_id(user_id)
        rating_type = ''
        if not user_info:
            return {'current_rating': 0.0, 'rank': None}

        if user_info['role'] in ['executor', 'external_executor']:
            rating_type = 'executor'

        rating_data = db.fetch_one("""
            SELECT current_rating
            FROM user_ratings 
            WHERE user_id = ? AND rating_type = ?
        """, (user_id, rating_type))

        rank = get_executor_rank(user_id, db)
        current_rating = rating_data['current_rating'] if rating_data else 0.0

        return {
            'current_rating': current_rating,
            'level': get_rating_level(current_rating),
            'rank': rank
        }

    # ========== ОБЩИЙ ОБРАБОТЧИК ДЛЯ КНОПКИ "НАЗАД" ==========

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_rating_menu')
    def handle_back_to_rating_menu(call):
        """Возвращает в главное меню рейтингов"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Получаем информацию о пользователе
        user_info = db.get_user_by_telegram_id(user_id)
        if not user_info:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Пользователь не найден."
            )
            bot.answer_callback_query(call.id)
            return

        user_role = user_info['role']

        # Создаем клавиатуру в зависимости от роли
        keyboard = InlineKeyboardMarkup(row_width=1)

        if user_role in ['admin', 'external_admin']:
            # Администраторы видят все рейтинги
            keyboard.add(
                InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="admin_logist_rating"),
                InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="admin_executor_rating"),
                # InlineKeyboardButton("🏅 Мои рейтинги", callback_data="my_ratings")
            )

            # Получаем текущий рейтинг из базы (если есть)
            rating_type = 'logist' if user_role == 'admin' else 'external_admin'
            rating_data = db.fetch_one("""
                SELECT current_rating FROM user_ratings 
                WHERE user_id = ? AND rating_type = ?
            """, (user_id, rating_type))

            current_rating = rating_data['current_rating'] if rating_data else 0.0

            text = (f"🏆 **Система рейтингов**\n\n"
                    f"👤 Ваша роль: **{role_names.get(user_role)}**\n"
                    f"⭐ **Текущий рейтинг:** {current_rating:.1f}/100.0\n"
                    f"🏅 **Уровень:** {get_rating_level(current_rating)}\n\n"
                    f"Выберите рейтинг для просмотра:")

        elif user_role in ['logist', 'external_logist']:
            # Логисты видят рейтинги перевозчиков и свой рейтинг
            keyboard.add(
                InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="logist_executor_rating"),
                InlineKeyboardButton("🏆 Мой рейтинг", callback_data="my_logist_rating"),
                InlineKeyboardButton("🏆 Рейтинг среди логистов", callback_data="logists_rating"),
            )

            # Получаем текущий рейтинг логиста из базы
            rating_info = get_logist_rating(user_id, db)
            text = (f"🏆 **Система рейтингов**\n\n"
                    f"👤 **Логист:** {user_info['first_name']} {user_info.get('last_name', '')}\n"
                    f"⭐ **Текущий рейтинг:** {rating_info.get('current_rating', 0.0):.1f}/100.0\n"
                    f"🏅 **Уровень:** {rating_info.get('level', 'Начинающий')}\n\n"
                    f"Выберите рейтинг для просмотра:")

        elif user_role in ['executor', 'external_executor']:
            # Перевозчики видят рейтинги и свой рейтинг
            keyboard.add(
                InlineKeyboardButton("🏆 Рейтинг перевозчиков", callback_data="executors_rating"),
                InlineKeyboardButton("🏆 Мой рейтинг", callback_data="my_executor_rating"),
                InlineKeyboardButton("🏆 Рейтинг логистов", callback_data="executor_logist_rating"),
            )

            # Получаем текущий рейтинг перевозчика из базы
            rating_info = get_executor_rating(user_id, db)
            text = (f"🏆 **Система рейтингов**\n\n"
                    f"👤 **Перевозчик:** {user_info['first_name']} {user_info.get('last_name', '')}\n"
                    f"⭐ **Текущий рейтинг:** {rating_info.get('current_rating', 0.0):.1f}/100.0\n"
                    f"🏅 **Уровень:** {rating_info.get('level', 'Начинающий')}\n"
                    f"📊 **Место в рейтинге:** #{rating_info.get('rank', '?')}\n\n"
                    f"Выберите рейтинг для просмотра:")

        else:
            text = "❌ Ваша роль не поддерживает просмотр рейтингов."

        # Редактируем существующее сообщение
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)