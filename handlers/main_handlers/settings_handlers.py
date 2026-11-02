from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from handlers.admin_handlers.pending_moderations_handlers import send_pending_moderations
from handlers.main_handlers.settings_rating_handlers import get_rating_management_keyboard
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from keyboards.main_menus import get_main_menu
from keyboards.settings_keyboard import get_setting_keyboard, get_settings_company_keyboard


def register_settings_handlers(bot, db):

    @bot.message_handler(func=lambda message: message.text=='⚙️ Настройки')
    def handler_settings(message):
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
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None


        bot.send_message(
            chat_id,
            "⚙️ Вы вошли в настройки\n"
            "Выберите действие:",
            reply_markup = get_setting_keyboard(role)
        )

    @bot.message_handler(func=lambda message: message.text == '🏢 Управление компаниями')
    def handler_settings(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None

        set_user_state(user_id, 'waiting_for_settings_company_action')
        bot.send_message(
            chat_id,
            '🏢 Управление компаниями\n'
            'Выберите действие:',
            reply_markup=get_settings_company_keyboard(role)
        )

    @bot.message_handler(func=lambda message: message.text == '📊 Настройка процентов')
    def handler_settings(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None

        set_user_state(user_id, 'waiting_for_settings_percent_action')
        bot.send_message(
            chat_id,
            '📊 Настройка процентов\n'
            'Выберите действие:',
            reply_markup=get_settings_company_keyboard(role)
        )

    @bot.message_handler(func=lambda message: message.text == '⭐ Настройка рейтинга')
    def show_rating_management(message):
        """Показывает меню управления рейтингом"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Проверяем, что пользователь - администратор
        user_role = db.get_user_role(user_id)
        if user_role['role'] not in ['admin', 'external_admin']:
            bot.send_message(
                chat_id,
                "❌ Эта функция доступна только администраторам.",
                reply_markup=get_main_menu(user_role['role'])
            )
            return

        bot.send_message(
            chat_id,
            "⭐ **Управление рейтингом**\n\n"
            "Здесь вы можете настроить бонусы и штрафы для рейтинговой системы.\n\n"
            "Выберите категорию для настройки:",
            reply_markup=get_rating_management_keyboard(),
            parse_mode='Markdown'
        )
        set_user_state(user_id, 'waiting_for_rating_category')


    @bot.message_handler(func=lambda message: message.text == '📋 Модерация заявок')
    def handler_settings(message):
        chat_id = message.chat.id
        send_pending_moderations(bot, db, chat_id)

    @bot.message_handler(func=lambda message: message.text == '🕹 Главное меню')
    def handler_settings(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None
        set_user_state(user_id, '')
        bot.send_message(chat_id, 'Выберите действие:', reply_markup=get_main_menu(role))






