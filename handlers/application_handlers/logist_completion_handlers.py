from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

user_application_data = {}
def register_logist_completion_handlers(bot, db):
    """Регистрация обработчиков для подтверждения выполнений заявок"""

    @bot.message_handler(func=lambda message: message.text == '📋 Заявки на подтверждение')
    def show_pending_completions(message):
        """Показывает заявки, ожидающие подтверждения выполнения"""
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

        # Получаем заявки, ожидающие подтверждения выполнения
        applications = db.fetch_all("""
            SELECT 
                a.*,
                u.first_name as executor_first_name,
                u.last_name as executor_last_name,
                u.phone as executor_phone,
                c.name as company_name,
                ac.executor_comment,
                ac.completion_requested_at
            FROM applications a
            JOIN users u ON a.assigned_to = u.telegram_id
            LEFT JOIN companies c ON u.company_id = c.id
            JOIN application_completions ac ON a.id = ac.application_id
            WHERE a.created_by = ? 
            AND ac.status = 'pending'
            ORDER BY ac.completion_requested_at ASC
        """, (user_id,))

        if not applications:
            bot.send_message(chat_id, "📭 Нет заявок, ожидающих подтверждения выполнения.")
            return

        # Формируем список заявок
        text = "📋 **Заявки, ожидающие подтверждения выполнения:**\n\n"

        for i, app in enumerate(applications, 1):
            executor_name = f"{app['executor_first_name']} {app['executor_last_name']}"
            company_name = app.get('company_name', 'Не указана')

            # Форматируем дату запроса
            request_date = app.get('completion_requested_at', 'Не указана')
            if isinstance(request_date, str) and request_date != 'Не указана':
                try:
                    from datetime import datetime
                    request_date = datetime.strptime(request_date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
                except:
                    pass

            text += f"{i}. **Заявка #{app['id']}**\n"
            text += f"   👤 Перевозчик: {executor_name}\n"
            text += f"   🏢 Компания: {company_name}\n"
            text += f"   📞 Телефон: {app.get('executor_phone', 'Не указан')}\n"
            # text += f"   📅 Запрос отправлен: {request_date}\n"
            text += f"   💬 Комментарий: {app.get('executor_comment', 'Нет')}\n\n"

            # Добавляем кнопки действий
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton(f"✅ Подтвердить #{app['id']}",
                                     callback_data=f"quick_confirm_{app['id']}"),
                InlineKeyboardButton(f"❌ Отклонить #{app['id']}",
                                     callback_data=f"quick_reject_{app['id']}")
            )

            # Отправляем каждую заявку отдельным сообщением
            bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode='Markdown')
            text = ""  # Сбрасываем текст для следующей заявки

        # Отправляем инструкцию
        bot.send_message(
            chat_id,
            "ℹ️ **Инструкция:**\n\n"
            "1. Нажмите '✅ Подтвердить' для подтверждения выполнения заявки\n"
            "2. Нажмите '❌ Отклонить' для отклонения выполнения (потребуется указать причину)\n"
            "3. Перевозчик получит уведомление о вашем решении",
            parse_mode='Markdown'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('quick_confirm_'))
    def handle_quick_confirm(call):
        """Быстрое подтверждение выполнения из списка"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[2])

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

        # Обновляем статус подтверждения
        db.execute_query(
            """UPDATE application_completions 
            SET status = 'confirmed', 
                completion_confirmed_at = datetime('now'),
                logist_id = ?
            WHERE application_id = ?""",
            (user_id, application_id)
        )

        # Обновляем статус заявки
        db.execute_query(
            """UPDATE applications 
            SET status = 'completed', 
                completion_status = 'confirmed',
                completion_confirmed_at = datetime('now')
            WHERE id = ?""",
            (application_id,)
        )

        # Получаем информацию об перевозчике
        executor_id = completion_request['executor_id']

        # Обновляем рейтинг перевозчика
        from handlers.application_handlers.assigned_executor_applications import update_user_rating_on_completion
        bonus_data = db.fetch_one("select value from rating_rules "
                                  "where rule_type = 'logist'"
                                  "and rule_name = 'Завершение заявки'"
                                  "and is_active = 1")
        bonus_amount = bonus_data['value'] if bonus_data else 5.0
        update_user_rating_on_completion(db, user_id, application_id, bonus_amount, "Принятие заявки", '')

        # Уведомляем перевозчика
        from handlers.application_handlers.assigned_executor_applications import notify_executor_about_completion_confirmation
        notify_executor_about_completion_confirmation(bot, db, application_id, executor_id)



        # Редактируем сообщение
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ **Выполнение подтверждено!**\n\n"
                 f"Заявка #{application_id} успешно подтверждена.",
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "✅ Подтверждено")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('quick_reject_'))
    def handle_quick_reject(call):
        """Быстрое отклонение выполнения из списка"""
        user_id = call.from_user.id
        application_id = int(call.data.split('_')[2])

        # Запрашиваем причину отклонения
        bot.send_message(
            call.message.chat.id,
            f"❌ **Укажите причину отклонения выполнения заявки #{application_id}:**",
            reply_markup=get_cancel_quick_rejection_keyboard(application_id)
        )

        # Сохраняем состояние
        if user_id not in user_application_data:
            user_application_data[user_id] = {}

        user_application_data[user_id]['waiting_for_quick_rejection_reason'] = True
        user_application_data[user_id]['quick_rejection_application_id'] = application_id

        bot.answer_callback_query(call.id)

    def get_cancel_quick_rejection_keyboard(application_id):
        """Клавиатура для отмены быстрого отклонения"""
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_quick_reject_{application_id}")
        )
        return keyboard