from telebot.types import ReplyKeyboardRemove

from keyboards.admin_keyboards import  *
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from keyboards.main_menus import get_main_menu, get_start_menu
from utils.helpers import check_user_exists


def register_main_admin_handler(bot, db):
    @bot.message_handler(func=lambda message: message.text == '👥 Управление пользователями')
    def user_management(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(user_id)
        user = db.get_user_by_telegram_id(user_id)
        role = user_role['role'] if user_role else None
        if not user and user['status'] != 'active':
            bot.send_message(
                user_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        if role not in ['admin', 'external_admin', 'logist', 'external_logist']:
            bot.send_message(
                chat_id,
                "❌ У вас нет прав на выполнение этого действия.",
                reply_markup=get_main_menu(role)
            )
            return
        else:
            bot.send_message(
                chat_id,
                "Выберите группу пользователей:",
                reply_markup=get_user_management_keyboard(role)
            )
            set_user_state(user_id, 'waiting_for_group_management')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_group_management')
    def group_management(message):
        admin_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(admin_id)
        role = user_role['role'] if user_role else None
        if role not in ['admin', 'external_admin', 'logist', 'external_logist']:
            bot.send_message(
                chat_id,
                "❌ У вас нет прав на выполнение этого действия.",
                reply_markup=get_main_menu(role)
            )
            return
        if message.text == "📊 Управление логистами":
            bot.send_message(
                chat_id,
                "👥 Управление логистами\n\n"
                "Выберите действие:",
                reply_markup=get_logist_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_logist_management_action')
        elif message.text == "🚛 Управление перевозчиками":
            bot.send_message(
                chat_id,
                "🚛 Управление перевозчиками\n\n"
                "Выберите действие:",
                reply_markup=get_executor_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_executor_management_action')
        elif message.text == "👥 Управление пользователями сторонних компаний":
            bot.send_message(
                chat_id,
                "👥 Управление сторонними грузовладельцами\n\n"
                "Выберите действие:",
                reply_markup = get_external_user_management_keyboard()
            )
            set_user_state(admin_id, 'waiting_for_ext_management_action')
        elif message.text == "🕹 Главное меню":
            bot.send_message(
                chat_id,
                '🕹 Выберите действие из меню:',
                reply_markup=get_main_menu(role)
            )
            set_user_state(admin_id, '')

