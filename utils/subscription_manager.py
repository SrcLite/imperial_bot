from datetime import datetime, timedelta
import logging


class SubscriptionManager:
    def __init__(self, db):
        self.db = db

    def check_subscription_status(self, user_id):
        """Проверяет статус подписки пользователя"""

        user = self.db.get_user_by_telegram_id(user_id)
        if not user:
            return {'has_active_subscription': False, 'message': 'Пользователь не найден'}

        # Внутренним пользователям всегда доступно
        if user['role'] not in ['external_admin', 'external_logist', 'external_executor']:
            return {
                'has_active_subscription': True,
                'type': 'internal',
                'days_left': None
            }

        subscription = self.db.fetch_one(
            """
            SELECT * FROM subscriptions 
            WHERE user_id = ? AND status = 'active' 
            ORDER BY end_date DESC LIMIT 1
            """,
            (user['telegram_id'],)
        )

        if not subscription:
            return {
                'has_active_subscription': False,
                'message': 'Подписка не найдена',
                'days_left': 0
            }

        end_date = datetime.strptime(subscription['end_date'], '%Y-%m-%d %H:%M:%S')
        now = datetime.now()

        if now > end_date:
            # Подписка истекла
            self.db.execute_query(
                "UPDATE subscriptions SET status = 'expired' WHERE id = ?",
                (subscription['id'],)
            )

            return {
                'has_active_subscription': False,
                'message': 'Подписка истекла',
                'days_left': 0,
                'subscription_type': subscription['subscription_type'],
                'price': subscription['price_per_month']
            }

        days_left = (end_date - now).days

        return {
            'has_active_subscription': True,
            'subscription_type': subscription['subscription_type'],
            'end_date': end_date,
            'days_left': days_left,
            'price': subscription['price_per_month']
        }


    def calculate_subscription_price(self, user_id, role):
        """Рассчитывает стоимость подписки с учетом количества пользователей"""

        user = self.db.fetch_one(
            "SELECT company_id FROM users WHERE telegram_id = ?",
            (user_id,)
        )

        if not user:
            return 0

        company_id = user['company_id']

        # Базовая цена в зависимости от роли
        if role == 'external_executor':
            base_price = 700
        elif role in ['external_admin', 'external_logist']:
            base_price = 1200
        else:
            return 0

        # Для external_admin считаем количество внешних логистов в компании
        if role == 'external_admin':
            external_logists_count = self.db.fetch_one(
                """
                SELECT COUNT(*) as count FROM users 
                WHERE company_id = ? AND role IN ('external_logist', 'external_admin')
                """,
                (company_id,)
            )['count']

            # Доплата за второго и последующих пользователей
            additional_users = max(0, external_logists_count - 1)
            total_price = base_price + (additional_users * 100)
        else:
            total_price = base_price

        return total_price

    def get_subscription_info(self, user_id):
        """Получает информацию о подписке пользователя"""

        user = self.db.get_user_by_telegram_id(user_id)
        if not user:
            return None

        subscription = self.db.fetch_one(
            """
            SELECT s.*, 
                   c.name as company_name
            FROM subscriptions s
            LEFT JOIN companies c ON s.company_id = c.id
            WHERE s.user_id = ? AND s.status = 'active'
            ORDER BY s.end_date DESC LIMIT 1
            """,
            (user['telegram_id'],)
        )

        if not subscription:
            return None

        # Форматируем даты
        end_date = datetime.strptime(subscription['end_date'], '%Y-%m-%d %H:%M:%S')
        days_left = (end_date - datetime.now()).days

        return {
            'subscription_type': subscription['subscription_type'],
            'end_date': end_date.strftime('%d.%m.%Y'),
            'days_left': days_left,
            'price': subscription['price_per_month'],
            'company_name': subscription['company_name'],
            'status': subscription['status']
        }

    def create_paid_subscription(self, user_id, months=1):
        """Создает платную подписку"""

        user = self.db.get_user_by_telegram_id(user_id)
        if not user:
            return False

        # Получаем текущую активную подписку
        current_sub = self.db.fetch_one(
            "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active'",
            (user['telegram_id'],)
        )

        start_date = datetime.now()

        # Если есть активная подписка, продлеваем с даты окончания
        if current_sub:
            start_date = datetime.strptime(current_sub['end_date'], '%Y-%m-%d %H:%M:%S')

        end_date = start_date + timedelta(days=30 * months)
        price = self.calculate_subscription_price(user['id'], user['role'])

        self.db.execute_query(
            """
            INSERT INTO subscriptions 
            (user_id, company_id, subscription_type, price_per_month, start_date, end_date, status)
            VALUES (?, ?, 'paid', ?, ?, ?, 'active')
            """,
            (user['telegram_id'], user['company_id'], price, start_date, end_date)
        )

        return True

    def create_trial_subscription(self, user_id, role):
        """Создает пробную подписку на 3 месяца"""

        user = self.db.get_user_by_telegram_id(user_id)
        if not user:
            return False

        # Проверяем, не было ли уже пробной подписки
        existing_trial = self.db.fetch_one(
            "SELECT * FROM subscriptions WHERE user_id = ? AND subscription_type = 'trial'",
            (user['telegram_id'],)
        )

        if existing_trial:
            return False

        trial_period = self.db.fetch_one("select value from rates where rate_type = 'trial'")
        start_date = datetime.now()
        end_date = (start_date + timedelta(days=int(trial_period['value'])*30)).strftime('%Y-%m-%d %H:%M:%S')

        # Определяем цену для будущей оплаты
        price = 0

        self.db.execute_query(
            """
            INSERT INTO subscriptions 
            (user_id, company_id, subscription_type, price_per_month, start_date, end_date, status)
            VALUES (?, ?, 'trial', ?, ?, ?, 'active')
            """,
            (user['telegram_id'], user['company_id'], price, start_date, end_date)
        )

        return True
