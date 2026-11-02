from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from utils.google_sheets import get_google_sheets_manager
from config.google_sheets_config import is_google_sheets_enabled


def register_google_sheets_handlers(bot, db):
    """Регистрация обработчиков для работы с Google Sheets"""

    @bot.message_handler(func=lambda message: message.text == '📤 Экспорт в Google Таблицы')
    def handle_google_sheets_export_menu(message):
        """Меню экспорта в Google Sheets"""
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

        # Проверяем, что пользователь - администратор
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.send_message(chat_id, "❌ Эта функция доступна только администраторам.")
            return

        if not is_google_sheets_enabled():
            bot.send_message(
                chat_id,
                "❌ **Интеграция с Google Sheets отключена**\n\n"
                "Для включения настройте переменные окружения:\n"
                "1. GOOGLE_SHEETS_ENABLED=True\n"
                "2. GOOGLE_SPREADSHEET_URL=ссылка_на_таблицу\n"
                "3. GOOGLE_CREDENTIALS_PATH=путь_к_credentials.json",
                parse_mode='Markdown'
            )
            return

        # Проверяем подключение
        manager = get_google_sheets_manager()
        status = "✅ Подключено" if manager else "❌ Не подключено"

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("🔄 Экспортировать все заявки", callback_data="export_all_to_sheets"),
            InlineKeyboardButton("📊 Проверить подключение", callback_data="check_sheets_connection"),
            InlineKeyboardButton("⚙️ Настройки экспорта", callback_data="sheets_settings")
        )

        bot.send_message(
            chat_id,
            f"📤 **Экспорт данных в Google Sheets**\n\n"
            f"**Статус:** {status}\n\n"
            f"Вы можете экспортировать все данные о ставках перевозчиков в Google Таблицу.\n"
            f"Это позволит анализировать данные, строить графики и делиться информацией с коллегами.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    @bot.callback_query_handler(func=lambda call: call.data == 'export_all_to_sheets')
    def handle_export_all_to_sheets(call):
        """Экспорт всех данных в Google Sheets"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        if not is_google_sheets_enabled():
            bot.answer_callback_query(call.id, "❌ Интеграция с Google Sheets отключена")
            return

        manager = get_google_sheets_manager()
        if not manager:
            bot.answer_callback_query(call.id, "❌ Google Sheets не подключен")
            return

        # Отправляем сообщение о начале экспорта
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔄 **Начинаем экспорт данных...**\n\n"
                 "Пожалуйста, подождите. Это может занять несколько минут.",
            parse_mode='Markdown'
        )

        # Запускаем экспорт
        try:
            total_exported = manager.export_all_applications(db)

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ **Экспорт завершен!**\n\n"
                     f"Экспортировано записей: **{total_exported}**\n\n"
                     f"Все данные о ставках перевозчиков успешно загружены в Google Таблицу.",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ **Ошибка экспорта**\n\n"
                     f"Произошла ошибка при экспорте данных:\n"
                     f"`{str(e)}`",
                parse_mode='Markdown'
            )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'check_sheets_connection')
    def handle_check_sheets_connection(call):
        """Проверка подключения к Google Sheets"""
        user_id = call.from_user.id

        # Проверяем права
        user_role = db.get_user_role(user_id)
        if user_role['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
            return

        if not is_google_sheets_enabled():
            bot.answer_callback_query(call.id, "❌ Интеграция с Google Sheets отключена")
            return

        manager = get_google_sheets_manager()

        if manager and manager.worksheet:
            # Пытаемся получить информацию о листе
            try:
                title = manager.worksheet.title
                row_count = len(manager.worksheet.get_all_values())

                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"✅ **Подключение установлено**\n\n"
                         f"**Таблица:** {title}\n"
                         f"**Записей в таблице:** {row_count - 1} (без заголовка)\n"
                         f"**Статус:** Активно\n\n"
                         f"Ссылка на таблицу будет отправлена в следующем сообщении.",
                    parse_mode='Markdown'
                )

                # Отправляем ссылку на таблицу
                from config.google_sheets_config import GOOGLE_SHEETS_CONFIG
                bot.send_message(
                    call.message.chat.id,
                    f"🔗 **Ссылка на Google Таблицу:**\n\n"
                    f"{GOOGLE_SHEETS_CONFIG['spreadsheet_url']}",
                    parse_mode='Markdown'
                )

            except Exception as e:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"❌ **Ошибка подключения**\n\n"
                         f"Не удалось получить информацию о таблице:\n"
                         f"`{str(e)}`",
                    parse_mode='Markdown'
                )
        else:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ **Не подключено**\n\n"
                     "Google Sheets менеджер не инициализирован. "
                     "Проверьте настройки подключения.",
                parse_mode='Markdown'
            )

        bot.answer_callback_query(call.id)