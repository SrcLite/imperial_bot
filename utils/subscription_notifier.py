# subscription_notifier.py
from datetime import datetime, timedelta
import logging


class SubscriptionNotifier:
    def __init__(self, db, bot):
        self.db = db
        self.bot = bot

    def check_expiring_subscriptions(self):
        """Проверяет истекающие подписки и отправляет уведомления"""

        # Подписки, которые истекают через 7, 3 и 1 день
        check_dates = [7, 3, 1]

        for days in check_dates:
            check_date = datetime.now() + timedelta(days=days)

            subscriptions = self.db.fetch_all(
                """
                SELECT s.*, u.telegram_id, u.role, u.first_name
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status = 'active'
                AND DATE(s.end_date) = DATE(?)
                AND u.role IN ('external_admin', 'external_logist', 'external_executor')
                """,
                (check_date.strftime('%Y-%m-%d'),)
            )

            for sub in subscriptions:
                self.send_expiration_notification(
                    sub['telegram_id'],
                    sub['first_name'],
                    days,
                    sub['end_date'],
                    sub['price_per_month']
                )

        # Проверяем истекшие подписки
        expired_subs = self.db.fetch_all(
            """
            SELECT s.*, u.telegram_id, u.role, u.first_name
            FROM subscriptions s
            JOIN users u ON s.user_id = u.id
            WHERE s.status = 'active'
            AND s.end_date < datetime('now')
            AND u.role IN ('external_admin', 'external_logist', 'external_executor')
            """
        )

        for sub in expired_subs:
            self.send_expired_notification(
                sub['telegram_id'],
                sub['first_name'],
                sub['price_per_month']
            )

            # Обновляем статус подписки
            self.db.execute_query(
                "UPDATE subscriptions SET status = 'expired' WHERE id = ?",
                (sub['id'],)
            )

    def send_expiration_notification(self, telegram_id, first_name, days_left, end_date, price):
        """Отправляет уведомление об истечении подписки"""

        message = f"""
🔔 **Уведомление о подписке**

Привет, {first_name}!

Ваша подписка истекает через {days_left} дней.
Дата окончания: {end_date}
Стоимость продления: {price} ₽/месяц

Пожалуйста, оплатите подписку для продолжения работы.
        """

        try:
            self.bot.send_message(telegram_id, message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {telegram_id}: {e}")

    def send_expired_notification(self, telegram_id, first_name, price):
        """Отправляет уведомление об истекшей подписке"""

        message = f"""
⏰ **Подписка истекла**

Привет, {first_name}!

Ваша подписка закончилась.
Для продолжения работы необходимо оплатить подписку.

Стоимость: {price} ₽/месяц

Без активной подписки доступ к функциям бота ограничен.
        """

        try:
            self.bot.send_message(telegram_id, message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {telegram_id}: {e}")