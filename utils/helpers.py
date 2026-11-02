from datetime import datetime

from utils.dicts import role_rating_type

def update_user_rating_on_completion(db, executor_id, application_id, bonus_amount, rule_name, rating_type):
    """Обновляет рейтинг перевозчика при успешном выполнении заявки"""

    # Получаем текущий рейтинг
    current_rating = db.fetch_one(
        "SELECT current_rating FROM user_ratings WHERE user_id = ? AND rating_type = ?",
        (executor_id, rating_type)
    )

    if current_rating:
        new_rating = min(100.0, current_rating['current_rating'] + bonus_amount)

        # Обновляем рейтинг
        db.execute_query(
            """UPDATE user_ratings 
            SET current_rating = ?, 
                updated_at = datetime('now') 
            WHERE user_id = ? AND rating_type = ?""",
            (new_rating, executor_id, rating_type)
        )

        # Записываем в историю
        db.execute_query(
            """INSERT INTO rating_history 
            (user_id, rating_type, old_rating, new_rating, change_reason, change_source, application_id) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (executor_id, rating_type, current_rating['current_rating'], new_rating,
             rule_name, 'application_completion_confirmation',
             application_id)
        )

def update_user_rating_on_rejection(db, executor_id, application_id, penalty_amount, rule_name, reason, rating_type):
    """Обновляет рейтинг перевозчика при отклонении выполнения"""
    # Получаем текущий рейтинг
    current_rating = db.fetch_one(
        "SELECT current_rating FROM user_ratings WHERE user_id = ? AND rating_type = ?",
        (executor_id, rating_type)
    )

    if current_rating:
        new_rating = max(0, current_rating['current_rating'] + penalty_amount)

        # Обновляем рейтинг
        db.execute_query(
            """UPDATE user_ratings 
            SET current_rating = ?, 
                updated_at = datetime('now') 
            WHERE user_id = ? AND rating_type = ?""",
            (new_rating, executor_id, rating_type)
        )

        # Записываем в историю
        db.execute_query(
            """INSERT INTO rating_history 
            (user_id, rating_type, old_rating, new_rating, change_reason, change_source, application_id) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (executor_id, rating_type, current_rating['current_rating'], new_rating,
             f'{rule_name}: {reason}', 'application_completion_rejection', application_id)
        )


def notify_executor_about_completion_confirmation(bot, db, application_id, executor_id, payment_deadline = 'Не указана'):
    """Уведомляет перевозчика о подтверждении выполнения"""
    # Получаем информацию о логисте и заявке
    application = db.fetch_one("""
        SELECT a.*, u.first_name as logist_first_name, u.last_name as logist_last_name, u.phone as logist_phone
        FROM applications a
        JOIN users u ON a.created_by = u.telegram_id
        WHERE a.id = ?
    """, (application_id,))

    if not application:
        return

    # Получаем информацию о выбранных способах оплаты перевозчика
    payment_data = db.fetch_one("""
        SELECT payment_options 
        FROM application_responses 
        WHERE application_id = ? AND executor_id = ?
    """, (application_id, executor_id))

    logist_name = f"{application['logist_first_name']} {application['logist_last_name']}"
    logist_phone = application.get('logist_phone', 'Не указан')

    # Формируем информацию об оплате
    payment_info = "Не указана"

    if payment_data and payment_data.get('payment_options'):
        try:
            payment_options = payment_data['payment_options']
            if payment_options:
                # Парсим JSON строку с выбранными способами оплаты
                import json
                payments = json.loads(payment_options)

                if payments:
                    # Создаем читаемое представление способов оплаты
                    payment_methods = {
                        'cash': 'Наличные',
                        'nds': 'С НДС',
                        'ip': 'ИП'
                    }

                    payment_details = []
                    total_amount = 0

                    for method, amount in payments.items():
                        if method in payment_methods and amount:
                            amount_float = float(amount)
                            total_amount += amount_float
                            payment_details.append(f"  • {payment_methods[method]}: {amount_float:,.0f} руб.")

                    if payment_details:
                        if len(payment_details) == 1:
                            # Если выбран только один способ оплаты
                            payment_info = f"{payment_details[0].replace('  • ', '')}"
                        else:
                            # Если выбрано несколько способов оплаты
                            payment_info = "\n".join(payment_details)
                            payment_info += f"\n\n💰 **Итого:** {total_amount:,.0f} руб."
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            print(f"Ошибка при обработке payment_options: {e}")
            # В случае ошибки используем старый метод
            payment_info = f"{float(application.get('fixed_price') or application.get('desired_budget', 0)):,.0f} руб."

    message = f"""
🎉 **Заявка подтверждена!**

Логист подтвердил выполнение заявки #{application_id}.

👤 **Логист:** {logist_name}
📞 **Телефон логиста:** {logist_phone}

💳 **Оплата:**
{payment_info}

🗓**Сроки оплаты:**
До {payment_deadline}

Спасибо за работу! Вы можете принимать новые заявки.
"""

    try:
        bot.send_message(executor_id, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Не удалось уведомить перевозчика {executor_id}: {e}")


def init_user_rating(db, user_id, rating_type):
    """Инициализирует рейтинг пользователя"""
    existing = db.fetch_one(
        "SELECT * FROM user_ratings WHERE user_id = ? AND rating_type = ?",
        (user_id, rating_type)
    )

    if not existing:
        # Начальный рейтинг в зависимости от типа
        initial_rating = 30.0  # Базовый рейтинг

        db.execute_query("""
            INSERT INTO user_ratings 
            (user_id, rating_type, current_rating)
            VALUES (?, ?, ?)
        """, (user_id, role_rating_type[rating_type], initial_rating))

def format_datetime(date):
    dt = datetime.fromisoformat(date.replace("+03:00", "+03:00"))

    formatted_date = dt.strftime("%d.%m.%Y %H:%M")
    return formatted_date

def check_user_exists(db, telegram_id):
    """Проверяет, существует ли пользователь в базе данных"""
    query = "SELECT COUNT(*) as user_exists FROM users WHERE telegram_id = ?"
    result = db.fetch_one(query, (telegram_id,))
    return result['user_exists'] > 0 if result else False




