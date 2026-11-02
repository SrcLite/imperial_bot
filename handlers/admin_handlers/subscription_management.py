from datetime import datetime

from telebot.types import KeyboardButton, ReplyKeyboardMarkup


def register_subscription_management(bot, db):
    @bot.message_handler(func=lambda message: message.text == "💵 правление подпиской")
    def handle_subscription_management(message):
        user_id = message.from_user.id
        user = db.get_user_by_telegram_id(user_id)

        bot.send_message(
            user_id,
            "🕐 Этот раздел в процессе разработки"
        )

    #     if user['role'] not in ['admin', 'external_admin']:
    #         bot.send_message(message.chat.id, "❌ Эта функция доступна только администраторам.")
    #         return
    #
    #     # Получаем статистику по подпискам
    #     stats = db.fetch_one(
    #         """
    #         SELECT
    #             COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count,
    #             COUNT(CASE WHEN status = 'expired' THEN 1 END) as expired_count,
    #             COUNT(CASE WHEN subscription_type = 'trial' THEN 1 END) as trial_count,
    #             COUNT(CASE WHEN subscription_type = 'paid' THEN 1 END) as paid_count
    #         FROM subscriptions
    #         """
    #     )
    #
    #     # Получаем список истекающих подписок
    #     expiring_subs = db.fetch_all(
    #         """
    #         SELECT s.*, u.telegram_id, u.first_name, u.last_name, u.role, c.name as company_name
    #         FROM subscriptions s
    #         JOIN users u ON s.user_id = u.id
    #         LEFT JOIN companies c ON u.company_id = c.id
    #         WHERE s.status = 'active'
    #         AND s.end_date BETWEEN datetime('now') AND datetime('now', '+7 days')
    #         ORDER BY s.end_date ASC
    #         LIMIT 10
    #         """
    #     )
    #
    #     stats_text = f"""
    # 📊 **Статистика подписок:**
    #
    # • Активных: {stats['active_count']}
    # • Истекших: {stats['expired_count']}
    # • Пробных: {stats['trial_count']}
    # • Платных: {stats['paid_count']}
    #
    # 🔔 **Скоро истекают ({len(expiring_subs)}):**
    # """
    #
    #     for sub in expiring_subs:
    #         end_date = datetime.strptime(sub['end_date'], '%Y-%m-%d %H:%M:%S')
    #         days_left = (end_date - datetime.now()).days
    #         stats_text += f"\n• {sub['first_name']} {sub['last_name']} ({sub['role']}) - {days_left} дней"
    #
    #     keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    #     keyboard.add(KeyboardButton("📋 Список всех подписок"))
    #     keyboard.add(KeyboardButton("➕ Продлить подписку"))
    #     keyboard.add(KeyboardButton("📧 Отправить напоминание"))
    #     keyboard.add(KeyboardButton("⬅️ Назад в меню"))
    #
    #     bot.send_message(
    #         message.chat.id,
    #         stats_text,
    #         reply_markup=keyboard,
    #         parse_mode='Markdown'
    #     )