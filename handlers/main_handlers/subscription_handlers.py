from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from datetime import datetime, timedelta
import logging

from utils.dicts import role_names, subscription_status_map, subscription_type_map
from utils.subscription_manager import SubscriptionManager


def register_subscription_handlers(bot, db):
    @bot.message_handler(func=lambda message: message.text == "💳 Моя подписка")
    def handle_pay_subscription(message):
        user_id = message.from_user.id
        user = db.get_user_by_telegram_id(user_id)

        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь не найден. Пожалуйста, зарегистрируйтесь.")
            return

        if user['role'] not in ['external_admin', 'external_logist', 'external_executor']:
            bot.send_message(
                message.chat.id,
                f"❌ Оплата подписки для сотрудников компании 'Империал' не требуется."
            )
            return

        # Получаем информацию о текущей подписке
        subscription_manager = SubscriptionManager(db)
        subscription_info = subscription_manager.get_subscription_info(user_id)

        # Определяем базовую цену в зависимости от роли
        base_price = 1200 if user['role'] in ['external_admin', 'external_logist'] else 700

        # Проверяем, был ли уже пробный период
        had_trial = db.fetch_one(
            "SELECT * FROM subscriptions WHERE user_id = ? AND subscription_type = 'trial'",
            (user['telegram_id'],)
        )

        # Формируем текст с информацией
        if subscription_info and subscription_info['status'] == 'active':
            days_left = subscription_info['days_left']
            if days_left > 0:
                payment_text = f"""
💳 **Продление подписки**

📋 **Ваша текущая подписка:**
• Статус: {subscription_status_map.get(subscription_info['status'])}
• Тип: {subscription_type_map.get(subscription_info['subscription_type'])}
• Действует до: {subscription_info['end_date']}
• Осталось дней: {days_left}
• Стоимость: {subscription_info['price']} ₽/месяц

"""
                if days_left <= 7:
                    payment_text += "⚠️ **Внимание!** Подписка скоро истекает. Рекомендуем продлить заранее.\n\n"
                payment_text += "📊 **Выберите способ продления:**"
            else:
                payment_text = f"""
💳 **Подписка истекла**

📋 **Последняя подписка:**
• Действовала до: {subscription_info['end_date']}
• Стоимость: {subscription_info['price']} ₽/месяц

📊 **Выберите способ оплаты для возобновления подписки:**
"""
        else:
            if had_trial:
                payment_text = f"""
💳 **Оформление платной подписки**

📊 **Для роли {role_names.get(user['role'])}:**
• Стоимость: {base_price} ₽/месяц

⚠️ Вы уже использовали пробный период.
Теперь доступна только платная подписка.

Выберите способ оплаты:
"""
            else:
                payment_text = f"""
💳 **Оформление подписки**

🎁 **Вам доступен пробный период!**
• Пробный период: 3 месяца бесплатно
• После пробного периода: {base_price} ₽/месяц

📊 **Выберите вариант:**
"""

        # Создаем inline-клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)

        # Добавляем кнопки оплаты
        buttons = []

        # Если пробный период еще не использован, показываем его первым
        if not had_trial:
            buttons.append(InlineKeyboardButton(
                "🎁 Пробный период (3 мес)",
                callback_data="sub_trial"
            ))

        buttons.extend([
            InlineKeyboardButton("💳 Картой (1200₽)", callback_data="sub_card"),
            InlineKeyboardButton("💰 С НДС (1500₽)", callback_data="sub_vat"),
            InlineKeyboardButton("📄 Без НДС (1200₽)", callback_data="sub_no_vat")
        ])

        # Распределяем кнопки по рядам
        if not had_trial:
            keyboard.row(buttons[0])
            keyboard.row(buttons[1], buttons[2])
            keyboard.row(buttons[3])
        else:
            keyboard.row(buttons[0], buttons[1])
            keyboard.row(buttons[2])

        # Добавляем служебные кнопки
        keyboard.row(
            InlineKeyboardButton("📋 Проверить статус", callback_data="sub_check_status"),
            # InlineKeyboardButton("📞 Поддержка", callback_data="sub_support")
        )
        keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="sub_close"))

        bot.send_message(
            message.chat.id,
            payment_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('sub_'))
    def handle_subscription_callbacks(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        user = db.get_user_by_telegram_id(user_id)

        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return

        # Обработка закрытия
        if call.data == "sub_close":
            bot.delete_message(chat_id, message_id)
            bot.answer_callback_query(call.id)
            return

        # Обработка поддержки
        if call.data == "sub_support":
            support_text = """
📞 **Служба поддержки**

Если у вас возникли вопросы по оплате или использованию платформы:

• **Email:** support@imperial.ru
• **Telegram:** @imperial_support
• **Телефон:** 8 (800) 123-45-67

🕒 **Время работы:** Пн-Пт с 9:00 до 20:00 МСК
            """

            keyboard = InlineKeyboardMarkup()
            keyboard.row(InlineKeyboardButton("📝 Оставить заявку", callback_data="sub_create_ticket"))
            keyboard.row(InlineKeyboardButton("◀️ Назад", callback_data="sub_back_to_payment"))
            keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="sub_close"))

            bot.edit_message_text(
                support_text,
                chat_id,
                message_id,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return

        # Обработка проверки статуса
        if call.data == "sub_check_status":
            show_payment_status(bot, db, chat_id, message_id, user, call)
            return

        # Обработка возврата к оплате
        if call.data == "sub_back_to_payment":
            handle_pay_subscription(call.message)
            bot.answer_callback_query(call.id)
            return

        # Маппинг способов оплаты
        payment_map = {
            "sub_card": {
                "type": "card",
                "price": 1200,
                "months": 1,
                "description": "Оплата банковской картой",
                "details": "Мгновенная активация после подтверждения"
            },
            "sub_vat": {
                "type": "vat",
                "price": 1500,
                "months": 1,
                "description": "Оплата с НДС (для юр. лиц)",
                "details": "Предоставляются закрывающие документы"
            },
            "sub_no_vat": {
                "type": "no_vat",
                "price": 1200,
                "months": 1,
                "description": "Оплата без НДС",
                "details": "Для ИП и самозанятых"
            },
            "sub_trial": {
                "type": "trial",
                "price": 0,
                "months": 3,
                "description": "Пробный период 3 месяца",
                "details": "Полный функционал платформы"
            }
        }

        selected = payment_map.get(call.data)
        if not selected:
            bot.answer_callback_query(call.id, "❌ Неверный способ оплаты", show_alert=True)
            return

        # Если выбран пробный период, проверяем, был ли он уже использован
        if selected['type'] == 'trial':
            existing_trial = db.fetch_one(
                """
                SELECT * FROM subscriptions 
                WHERE user_id = ? AND subscription_type = 'trial'
                """,
                (user['telegram_id'],)
            )

            if existing_trial:
                bot.answer_callback_query(
                    call.id,
                    "❌ Вы уже использовали пробный период",
                    show_alert=True
                )
                return

        # Создаем запись о платеже в БД
        order_id = f"sub_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        db.execute_query(
            """
            INSERT INTO payments 
            (user_id, amount, order_id, status, payment_method, created_at)
            VALUES (?, ?, ?, 'pending', ?, CURRENT_TIMESTAMP)
            """,
            (user['telegram_id'], selected['price'], order_id, selected['type'])
        )

        # Формируем текст в зависимости от типа оплаты
        if selected['type'] == 'trial':
            payment_text = f"""
🎁 **Активация пробного периода**

📋 **Детали:**
• Период: 3 месяца бесплатно
• Доступ: полный функционал
• Автопродление: не подключено

✅ **Для активации нажмите кнопку "Активировать пробный период"**

После активации вы сможете пользоваться всеми функциями платформы.
Через 3 месяца можно будет подключить платную подписку.
            """

            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton(
                    "✅ Активировать пробный период",
                    callback_data=f"activate_trial_{order_id}"
                )
            )
            keyboard.row(
                InlineKeyboardButton("📋 Проверить статус", callback_data="sub_check_status"),
                # InlineKeyboardButton("📞 Поддержка", callback_data="sub_support")
            )
            keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="sub_close"))
        else:
            payment_text = f"""
💳 **Запрос на оплату**

📋 **Детали платежа:**
• Тариф: {selected['description']}
• Сумма: {selected['price']} ₽
• Период: {selected['months']} мес.
• Номер заказа: `{order_id}`
• {selected['details']}

💳 **Реквизиты для оплаты:**
Получатель: ООО «ИМПЕРИАЛ»
Банк: ПАО СБЕРБАНК
Расчетный счет: 40702810123450001234
Корр. счет: 30101810400000000225
БИК: 044525225
ИНН: 7701234567
КПП: 770101001

📝 **Назначение платежа:**
`Оплата подписки {order_id} для {user['telegram_id']}`

📤 **После оплаты:**
1. Сохраните чек об оплате
2. Нажмите кнопку "✅ Я оплатил"
3. Отправьте фото чека (если потребуется)

⏱️ Подписка будет активирована в течение 24 часов после подтверждения.
            """

            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton(
                    "✅ Я оплатил",
                    callback_data=f"confirm_payment_{order_id}"
                )
            )
            keyboard.row(
                InlineKeyboardButton("📋 Проверить статус", callback_data="sub_check_status"),
                # InlineKeyboardButton("📞 Поддержка", callback_data="sub_support")
            )
            keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="sub_close"))

        bot.edit_message_text(
            payment_text,
            chat_id,
            message_id,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('activate_trial_'))
    def handle_trial_activation(call):
        user_id = call.from_user.id
        order_id = call.data.replace('activate_trial_', '')
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        user = db.get_user_by_telegram_id(user_id)

        # Получаем информацию о платеже
        payment = db.fetch_one(
            "SELECT * FROM payments WHERE order_id = ? AND user_id = ?",
            (order_id, user_id)
        )

        if not payment:
            bot.answer_callback_query(
                call.id,
                "❌ Запрос не найден",
                show_alert=True
            )
            return

        # Проверяем, не активирован ли уже пробный период
        existing_trial = db.fetch_one(
            "SELECT * FROM subscriptions WHERE user_id = ? AND subscription_type = 'trial'",
            (payment['user_id'],)
        )

        if existing_trial:
            bot.answer_callback_query(
                call.id,
                "❌ Пробный период уже был активирован ранее",
                show_alert=True
            )
            return

        # Активируем пробный период
        start_date = datetime.now()
        end_date = start_date + timedelta(days=90)  # 3 месяца

        db.execute_query(
            """
            INSERT INTO subscriptions 
            (user_id, company_id, subscription_type, price_per_month, start_date, end_date, status)
            VALUES (?, ?, 'trial', ?, ?, ?, 'active')
            """,
            (
                payment['user_id'],
                user['company_id'],
                1200 if user['role'] in ['external_admin', 'external_logist'] else 700,
                start_date,
                end_date
            )
        )

        # Обновляем статус платежа
        db.execute_query(
            "UPDATE payments SET status = 'completed', payment_date = CURRENT_TIMESTAMP WHERE id = ?",
            (payment['id'],)
        )

        # Отправляем подтверждение
        success_text = f"""
🎉 **Пробный период активирован!**

✅ **Ваш пробный период:**
• Начало: {start_date.strftime('%d.%m.%Y')}
• Окончание: {end_date.strftime('%d.%m.%Y')}
• Осталось дней: 90

🚀 **Что дальше?**
• Пользуйтесь всеми функциями платформы
• За 7 дней до окончания мы напомним о продлении
• После окончания можно подключить платную подписку

Спасибо, что выбрали нашу платформу!
        """

        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("📋 В главное меню", callback_data="sub_back_to_main"),
            InlineKeyboardButton("❌ Закрыть", callback_data="sub_close")
        )

        bot.edit_message_text(
            success_text,
            chat_id,
            message_id,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "✅ Пробный период активирован!")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_payment_'))
    def handle_payment_confirmation(call):
        user_id = call.from_user.id
        order_id = call.data.replace('confirm_payment_', '')
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Получаем информацию о платеже
        payment = db.fetch_one(
            "SELECT * FROM payments WHERE order_id = ? AND user_id = ?",
            (order_id, user_id)
        )

        if not payment:
            bot.answer_callback_query(
                call.id,
                "❌ Платеж не найден",
                show_alert=True
            )
            return

        if payment['status'] == 'completed':
            bot.answer_callback_query(
                call.id,
                "✅ Платеж уже был подтвержден ранее",
                show_alert=True
            )
            return

        # Обновляем статус платежа
        db.execute_query(
            "UPDATE payments SET status = 'completed', payment_date = CURRENT_TIMESTAMP WHERE id = ?",
            (payment['id'],)
        )

        # Создаем или продлеваем подписку
        user = db.get_user_by_telegram_id(user_id)

        # Определяем количество месяцев
        months = 1

        # Рассчитываем даты
        start_date = datetime.now()
        end_date = start_date + timedelta(days=30 * months)

        # Проверяем, есть ли уже активная подписка
        existing_sub = db.fetch_one(
            "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active'",
            (user['telegram_id'],)
        )

        if existing_sub:
            # Продлеваем существующую подписку
            new_end_date = datetime.strptime(existing_sub['end_date'], '%Y-%m-%d %H:%M:%S') + timedelta(
                days=30 * months)
            db.execute_query(
                """
                UPDATE subscriptions SET 
                end_date = ?,
                status = 'active',
                updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_end_date, existing_sub['id'])
            )
            end_date = new_end_date
        else:
            # Создаем новую подписку
            db.execute_query(
                """
                INSERT INTO subscriptions 
                (user_id, company_id, subscription_type, price_per_month, start_date, end_date, status)
                VALUES (?, ?, 'paid', ?, ?, ?, 'active')
                """,
                (
                    user['telegram_id'],
                    user['company_id'],
                    payment['amount'],
                    start_date,
                    end_date
                )
            )

        # Отправляем подтверждение
        success_text = f"""
✅ **Платеж подтвержден!**

🎉 **Ваша подписка успешно активирована!**

📅 **Детали подписки:**
• Статус: Активна
• Действует до: {end_date.strftime('%d.%m.%Y')}
• Сумма: {payment['amount']} ₽
• Способ оплаты: {payment['payment_method']}

💡 **Что дальше?**
• Пользуйтесь всеми функциями платформы
• За 7 дней до окончания мы напомним о продлении
• В личном кабинете можно сменить тариф

Спасибо за доверие к нашей платформе!
        """

        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("📋 В главное меню", callback_data="sub_back_to_main"),
            InlineKeyboardButton("❌ Закрыть", callback_data="sub_close")
        )

        bot.edit_message_text(
            success_text,
            chat_id,
            message_id,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id, "✅ Подписка активирована!")

    @bot.callback_query_handler(func=lambda call: call.data == "sub_back_to_main")
    def handle_back_to_main(call):
        from keyboards.main_menus import get_main_menu

        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Удаляем сообщение с подпиской
        bot.delete_message(chat_id, message_id)

        # Отправляем новое сообщение с главным меню
        user = db.get_user_by_telegram_id(call.from_user.id)
        bot.send_message(
            chat_id,
            "Главное меню:",
            reply_markup=get_main_menu(user['role'])
        )

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "sub_create_ticket")
    def handle_create_ticket(call):
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        ticket_text = """
📝 **Создание заявки в поддержку**

Опишите вашу проблему или вопрос, и мы свяжемся с вами в ближайшее время.

Для создания заявки напишите на email: support@imperial.ru
Или в Telegram: @imperial_support
        """

        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton("◀️ Назад", callback_data="sub_support"))
        keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="sub_close"))

        bot.edit_message_text(
            ticket_text,
            chat_id,
            message_id,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        bot.answer_callback_query(call.id)


def show_payment_status(bot, db, chat_id, message_id, user, call):
    """Показывает статус платежей и подписки"""

    # Получаем последний платеж пользователя
    last_payment = db.fetch_one(
        """
        SELECT * FROM payments 
        WHERE user_id = ? 
        ORDER BY created_at DESC LIMIT 1
        """,
        (user['telegram_id'],)
    )

    # Получаем информацию о подписке
    subscription = db.fetch_one(
        "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active'",
        (user['telegram_id'],)
    )

    response_text = "📊 **Статус ваших платежей и подписки**\n\n"

    if subscription:
        end_date = datetime.strptime(subscription['end_date'], '%Y-%m-%d %H:%M:%S')
        days_left = (end_date - datetime.now()).days

        response_text += f"""
✅ **Активная подписка:**
• Тип: {subscription_type_map.get(subscription['subscription_type'])}
• Действует до: {subscription['end_date']}
• Осталось дней: {days_left}
• Стоимость: {subscription['price_per_month']} ₽/месяц
"""
        if days_left <= 7:
            response_text += "\n⚠️ **Подписка скоро истекает!** Рекомендуем продлить.\n"
    else:
        response_text += "❌ **Нет активной подписки**\n\n"

    if last_payment:
        status_text = {
            'pending': '⏳ Ожидает подтверждения',
            'completed': '✅ Оплачен',
            'failed': '❌ Ошибка оплаты'
        }

        response_text += f"""
📋 **Последний платеж:**
• Номер заказа: `{last_payment['order_id']}`
• Сумма: {last_payment['amount']} ₽
• Статус: {status_text.get(last_payment['status'], 'Неизвестно')}
• Дата: {last_payment['created_at']}
"""
        if last_payment['status'] == 'pending':
            response_text += "\n⏳ Ваш платеж проверяется. Обычно это занимает до 24 часов."
    else:
        response_text += "\n📭 У вас пока нет платежей."

    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("💳 Оплатить подписку", callback_data="sub_back_to_payment"),
        # InlineKeyboardButton("📞 Поддержка", callback_data="sub_support")
    )
    keyboard.row(InlineKeyboardButton("❌ Закрыть", callback_data="sub_close"))

    bot.edit_message_text(
        response_text,
        chat_id,
        message_id,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    bot.answer_callback_query(call.id)


# Функция для проверки доступа пользователя (из примера с rates_handlers)
def check_user_access(bot, user_id, db):
    """Проверяет, имеет ли пользователь доступ к боту"""
    user = db.get_user_by_telegram_id(user_id)
    if not user or user['status'] != 'active':
        bot.send_message(
            user_id,
            "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
            reply_markup=ReplyKeyboardRemove()
        )
        return False
    return True