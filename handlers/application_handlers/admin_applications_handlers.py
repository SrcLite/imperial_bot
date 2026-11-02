from telebot.types import ReplyKeyboardRemove

from handlers.main_handlers.common import handle_start
from keyboards.application_keyboards import get_management_application
from keyboards.main_menus import get_start_menu
from utils.helpers import check_user_exists


def register_admin_applications_handlers(bot, db):
    @bot.message_handler(func=lambda message: message.text == '📋 Управление заявками')
    def handle_admin_applications(message):
        user_id = message.from_user.id
        user = db.get_user_by_telegram_id(user_id)
        if not user and user['status'] != 'active':
            bot.send_message(
                user_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        bot.send_message(
            user_id,
            '📋 Управление заявками\n'
            'Выберите действие:',
            reply_markup=get_management_application()
        )

    # @bot.message_handler(func=lambda message: message.text== "🕹 Главное меню")
    # def handle_main_menu(message):
    #     handle_start(bot, message, db)