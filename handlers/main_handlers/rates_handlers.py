from telebot.types import ReplyKeyboardRemove

from handlers.admin_handlers.admin_rates_handlers import get_current_rates, format_user_rates_message


def register_rates_handlers(bot, db):
    @bot.message_handler(func=lambda message: message.text == '💵Прайс-лист')
    def rates_handlers(message):
        user_id = message.from_user.id
        user = db.get_user_by_telegram_id(user_id)
        rates = get_current_rates(db)
        rate_text = format_user_rates_message(rates)
        if not user and user['status'] != 'active':
            bot.send_message(
                user_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        bot.send_message(
            user_id,
            rate_text
        )