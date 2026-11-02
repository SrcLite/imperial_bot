import glob
import os
import time
from datetime import datetime

from requests import delete

from handlers.admin_handlers.pending_moderations_handlers import remove_pending_moderation, add_pending_moderation
from handlers.main_handlers.settings_company_handlers import edit_requests
from handlers.registration_handlers.registration_user_handlers import set_user_state, get_user_state
from keyboards.admin_keyboards import *
from keyboards.main_menus import get_main_menu
from utils.subscription_manager import SubscriptionManager
from utils.helpers import init_user_rating
from utils.subscription_manager import SubscriptionManager

moderation_data = {}
role_names = {
    'admin': '👑 Администратор',
    'logist': '📊 Логист',
    'executor': '🚛 Перевозчик',
    'external_admin': '👑 Администратор',
    'external_logist': '📊 Логист',
    'external_executor': '🚛 Перевозчик'
}
field_names = {
    'first_name': 'Имя',
    'last_name': 'Фамилия',
    'patronymic': 'Отчество',
    'position': 'Должность',
    'phone': 'Телефон',
    'email': 'Email',
    'birth_date': 'Дата рождения',
    'passport_series': 'Серия паспорта',
    'passport_number': 'Номер паспорта',
    'passport_issue_date': 'Дата выдачи паспорта',
    'registration_address': 'Адрес регистрации',
    'ati_code': 'Код АТИ',
    'role': 'Роль'
}

tax_to_text_map = {
    'osn': '📊 ОСНО',
    'usn': '📊 УСН',
    'eshn': '📊 ЕСХН',
    'psn': '📊 ПСН',
    'npd': '📊 НПД',
    'ausn': '📊 АУСН'
}
type_to_text_map = {
    'legal': '🏛️ Юридическое лицо',
    'individual': '👤 ИП',
    'self_employed': '💼 Самозанятый'
}

tax_to_data_map = {
    '📊 ОСНО': 'osn',
    '📊 УСН': 'usn',
    '📊 ЕСХН': 'eshn',
    '📊 ПСН': 'psn',
    '📊 НПД': 'npd',
    '📊 АУСН': 'ausn'
}

type_to_data_map = {
    '🏛️ Юридическое лицо': 'legal',
    '👤 ИП': 'individual',
    '💼 Самозанятый': 'self_employed'
}

company_field_names = {
    'name': 'Название компании',
    'company_type': 'Тип компании',
    'inn': 'ИНН',
    'kpp': 'КПП',
    'ogrn': 'ОГРН',
    'director_first_name': 'Имя директора',
    'director_last_name': 'Фамилия директора',
    'legal_address': 'Юридический адрес',
    'contact_phone': 'Контактный телефон',
    'contact_email': 'Контактный email',
    'note': 'Примечание',
    'bik': 'БИК',
    'payment_account': 'Расчетный счет',
    'correspondent_account': 'Корреспондентский счет',
    'okpo': 'ОКПО'
}

def register_admin_moderation_handlers(bot, db):
    @bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_user_', 'reject_user_')))
    def handle_user_moderation(call):
        admin_id = call.from_user.id
        admin = db.get_user_role(admin_id)

        if not admin or admin['role'] != "admin":
            bot.answer_callback_query(call.id, "❌ У вас нет прав для выполнения этого действия")
            return

        action, user_id = call.data.split('_')[0], int(call.data.split('_')[2])
        user = db.get_user_by_telegram_id(user_id)
        if 'last_name' in user and user.get('last_name') is None:
            user['last_name'] = ''

        # Проверяем статус пользователя перед обработкой
        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден")
            return

        # Если пользователь уже обработан (активен или отклонен)
        if user['status'] in ['active', 'blocked', 'approved']:
            # Показываем сообщение и удаляем кнопки
            if user['status'] == 'active':
                status_text = "одобрена"
            elif user['status'] == 'blocked':
                status_text = "отклонена"
            elif user['status'] == 'approved':
                status_text = "одобрена (подтверждена)"

            bot.answer_callback_query(
                call.id,
                f"❌ Заявка уже была {status_text} другим администратором"
            )
            time.sleep(1)  # Даем время прочитать сообщение

            # Удаляем сообщение с кнопками
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass  # Если сообщение уже удалено

            return

        user_creator = db.fetch_one(
            "select created_by from users where telegram_id = ?", (user_id,)
        )
        creator_id = user_creator['created_by'] if user_creator and 'created_by' in user_creator else None

        if action == 'approve':
            if user['status'] == 'added_pending':
                success = db.execute_query("update users set status = 'added' where telegram_id = ?", (user_id,))
            elif user['status'] == 'added':
                success = db.execute_query("UPDATE users SET approved_by = ? WHERE telegram_id = ?",
                                           (admin_id, user_id))
            else:
                success = db.execute_query("UPDATE users SET status = 'active', approved_by = ? WHERE telegram_id = ?",
                                           (admin_id, user_id))
                init_user_rating(db, user['telegram_id'], user['role'])

            if success:
                bot.edit_message_text(
                    f"✅ Пользователь {user['first_name']} {user.get('last_name', '')} одобрен.",
                    call.message.chat.id,
                    call.message.message_id
                )
                remove_pending_moderation('user_registration', user_id)

                if creator_id != user_id:
                    if user['status'] == 'added':
                        notify_user_about_status(bot, user, user_id)
                    else:
                        reason = ''
                        notify_creator_about_status(bot, user, creator_id, 'approved', reason)
                else:
                    notify_user_about_status(bot, user, user_id)
                if user['role'] in ['external_admin', 'external_logist', 'external_executor']:
                    subscription_manager = SubscriptionManager(db)
                    user = db.get_user_by_telegram_id(user_id)
                    print(f"Создание пробной подписки для пользователя {user_id}, роль: {user['role']}")
                    subscription_manager.create_trial_subscription(user_id, user['role'])
                success = db.fetch_one('select * from subscriptions where user_id = ?', (user_id,))
                if success:
                    print('Подписка успешно активирована')
                else:
                    print('Не удалось создать подписку')

            else:
                bot.answer_callback_query(call.id, "❌ Ошибка при одобрении пользователя")

        elif action == "reject":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                f"❌ Пользователь {user['first_name']} {user.get('last_name', '')} отклонен\n\n"
                "Укажите причину отклонения:",
                reply_markup=get_cancel_moderation_keyboard(user_id, 'user')
            )
            set_user_state(admin_id, 'waiting_for_rejection_reason')

            # Сохраняем временные данные для модерации
            moderation_data[admin_id] = {
                'type': 'user',
                'id': user_id,
                'action': 'reject',
                'message_id': call.message.message_id,
                'creator_id': creator_id
            }

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(('approve_delete_photos_', 'reject_delete_photos_')))
    def handle_delete_photos_moderation(call):
        admin_id = call.from_user.id
        admin = db.get_user_role(admin_id)

        if not admin or admin['role'] != "admin":
            bot.answer_callback_query(call.id, "❌ У вас нет прав для выполнения этого действия")
            return

        action, user_id = call.data.split('_')[0], int(call.data.split('_')[3])
        user = db.get_user_by_telegram_id(user_id)

        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден")
            return

        if action == 'approve':
            # Одобряем удаление фото
            folder_path = f"data/documents/users/{user_id}"

            # Удаляем все фото
            existing_photos = glob.glob(os.path.join(folder_path, "*.jpg")) + glob.glob(
                os.path.join(folder_path, "*.jpeg")) + glob.glob(os.path.join(folder_path, "*.png"))

            deleted_count = 0
            for photo_path in existing_photos:
                try:
                    os.remove(photo_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"Ошибка при удалении файла {photo_path}: {e}")

            # Уведомляем администратора
            bot.edit_message_text(
                f"✅ Фотографии пользователя {user['first_name']} {user['last_name']} удалены",
                call.message.chat.id,
                call.message.message_id
            )
            remove_pending_moderation('user_photos_delete', user_id)

            # Уведомляем пользователя
            bot.send_message(
                user_id,
                "✅ Ваш запрос на удаление фотографий одобрен. Все фотографии удалены."
            )

        elif action == 'reject':
            # Запрашиваем причину отклонения
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                f"❌ Удаление фотографий пользователя {user['first_name']} {user['last_name']} отклонено\n\n"
                "Укажите причину отклонения:",
                reply_markup=get_cancel_moderation_keyboard(user_id, 'delete_photos')
            )
            set_user_state(admin_id, 'waiting_for_rejection_reason')

            # Сохраняем временные данные для модерации
            moderation_data[admin_id] = {
                'type': 'delete_photos',
                'id': user_id,
                'action': 'reject',
                'message_id': call.message.message_id
            }

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(('approve_delete_company_photos_', 'reject_delete_company_photos_')))
    def handle_delete_company_photos_moderation(call):
        admin_id = call.from_user.id
        admin = db.get_user_role(admin_id)

        if not admin or admin['role'] != "admin":
            bot.answer_callback_query(call.id, "❌ У вас нет прав для выполнения этого действия")
            return

        action, company_id, user_id = call.data.split('_')[0], int(call.data.split('_')[4]), int(call.data.split('_')[5])
        user = db.get_user_by_telegram_id(user_id)
        company = db.get_company_by_id(company_id)

        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден")
            return

        if action == 'approve':
            # Одобряем удаление фото
            folder_path = f"data/documents/companies/{company_id}"

            # Удаляем все фото
            existing_photos = glob.glob(os.path.join(folder_path, "*.jpg")) + glob.glob(
                os.path.join(folder_path, "*.jpeg")) + glob.glob(os.path.join(folder_path, "*.png"))

            deleted_count = 0
            for photo_path in existing_photos:
                try:
                    os.remove(photo_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"Ошибка при удалении файла {photo_path}: {e}")

            # Уведомляем администратора
            bot.edit_message_text(
                f"✅ Фотографии компании {company['name']} удалены",
                call.message.chat.id,
                call.message.message_id
            )
            remove_pending_moderation('company_photos_delete', user_id)

            # Уведомляем пользователя
            bot.send_message(
                user_id,
                "✅ Ваш запрос на удаление фотографий одобрен. Все фотографии удалены."
            )

        elif action == 'reject':
            # Запрашиваем причину отклонения
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                f"❌ Удаление фотографий компании {company['name']} отклонено\n\n"
                "Укажите причину отклонения:",
                reply_markup=get_cancel_moderation_keyboard(user_id, 'company-delete')
            )
            set_user_state(admin_id, 'waiting_for_rejection_reason')

            # Сохраняем временные данные для модерации
            moderation_data[admin_id] = {
                'type': 'company-delete',
                'id': user_id,
                'action': 'reject',
                'company_id': company_id,
                'message_id': call.message.message_id
            }

    def handle_delete_company_photos_rejection(bot, db, admin_id, user_id, company_id, reason):
        """Обработка отклонения удаления фотографий"""
        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        company = db.get_company_by_id(company_id)
        if not user:
            bot.send_message(admin_id, "❌ Пользователь не найден")
            return

        bot.send_message(admin_id,
                         f"✅ Удаление фотографий компании {company['name']} отклонено")
        remove_pending_moderation('company_photos_delete', user_id)
        # Уведомляем пользователя
        bot.send_message(
            user_id,
            f"❌ Ваш запрос на удаление фотографий отклонен администратором.\n"
            f"Причина: {reason}"
        )

    def handle_delete_photos_rejection(bot, db, admin_id, user_id, reason):
        """Обработка отклонения удаления фотографий"""
        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if not user:
            bot.send_message(admin_id, "❌ Пользователь не найден")
            return

        bot.send_message(admin_id,
                         f"✅ Удаление фотографий пользователя {user['first_name']} {user['last_name']} отклонено")

        # Уведомляем пользователя
        bot.send_message(
            user_id,
            f"❌ Ваш запрос на удаление фотографий отклонен администратором.\n"
            f"Причина: {reason}"
        )
        remove_pending_moderation('user_photos_delete', user_id)


    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(('approve-company-edit-req-', 'reject-company-edit-req-')))
    def handle_company_request_edit_moderation(call):
        print('Сработал обработчик заявок по ID')
        admin_id = call.from_user.id
        admin = db.get_user_role(admin_id)

        if not admin or admin['role'] != "admin":
            bot.answer_callback_query(call.id, "❌ У вас нет прав для выполнения этого действия")
            return

        # Извлекаем action и request_id
        print(call.data)
        parts = call.data.split('-req-')
        action = parts[0]  # 'approve-company-edit' или 'reject-company-edit'
        request_id = parts[1]

        # Получаем данные запроса из временного хранилища
        if request_id not in edit_requests:
            bot.answer_callback_query(call.id, "❌ Запрос не найден или устарел")
            return

        request_data = edit_requests[request_id]
        company_id = request_data['company_id']
        field = request_data['field']
        new_value = request_data['new_value']
        editor_id = request_data['editor_id']
        query = request_data.get('query')  # Может быть None для компаний или банковских реквизитов

        company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
        if not company:
            bot.answer_callback_query(call.id, "❌ Компания не найдена")
            return

        if action == 'approve-company-edit':
            # Применяем изменение к компании
            if query:
                # Для банковских реквизитов
                success = db.execute_query(query, [new_value, company_id])
            else:
                # Для основных полей компании
                success = db.execute_query(
                    f"UPDATE companies SET {field} = ? WHERE id = ?",
                    (new_value, company_id)
                )

            if success:
                bot.edit_message_text(
                    f"✅ Изменение компании '{company['name']}' применено",
                    call.message.chat.id,
                    call.message.message_id
                )
                # Удаляем запрос из временного хранилища
                del edit_requests[request_id]
                # Уведомляем пользователя, который запросил изменение
                notify_company_editor_about_approve(bot, company, editor_id, field, new_value)
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка при применении изменения")

        elif action == 'reject-company-edit':
            # Запрашиваем причину отклонения
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                f"❌ Изменение компании '{company['name']}' отклонено\n\n"
                "Укажите причину отклонения:",
                reply_markup=get_cancel_moderation_keyboard(company_id, 'company-edit')
            )
            set_user_state(admin_id, 'waiting_for_rejection_reason')

            # Сохраняем временные данные для модерации
            moderation_data[admin_id] = {
                'type': 'company-edit',
                'id': company_id,
                'action': 'reject',
                'message_id': call.message.message_id,
                'editor_id': editor_id,
                'field': field,
                'new_value': new_value,
                'request_id': request_id  # Сохраняем для последующего удаления
            }
    def apply_company_edit(db, company_id, field, new_value):
        """Применяет изменение к компании в базе данных"""
        try:
            # Для банковских реквизитов используем отдельную таблицу
            if field in ['bik', 'payment_account', 'correspondent_account', 'okpo']:
                # Проверяем, есть ли уже банковские реквизиты
                bank_details = db.fetch_one("SELECT * FROM company_bank_details WHERE company_id = ?", (company_id,))
                if bank_details:
                    query = f"UPDATE company_bank_details SET {field} = ? WHERE company_id = ?"
                else:
                    query = f"INSERT INTO company_bank_details ({field}, company_id) VALUES (?, ?)"

                return db.execute_query(query, (new_value, company_id))
            else:
                # Для основных полей компании
                query = f"UPDATE companies SET {field} = ?, updated_at = datetime('now') WHERE id = ?"
                return db.execute_query(query, (new_value, company_id))
        except Exception as e:
            print(f"Ошибка при применении изменения компании: {e}")
            return False

    def notify_company_editor_about_approve(bot, company, editor_id, field, new_value):
        """Уведомляет пользователя об одобрении изменения компании"""
        field_display = company_field_names.get(field, field)

        # Форматируем значение для отображения
        if field == 'company_type':
            value_display = type_to_text_map.get(new_value, new_value)
        elif field == 'tax_system':
            value_display = tax_to_text_map.get(new_value, new_value)
        else:
            value_display = new_value

        message_text = f"""
            ✅ **Изменение данных компании одобрено!**

            🏢 **Компания:** {company['name']}
            📋 **Измененное поле:** {field_display}
            🔄 **Новое значение:** {value_display}
            """

        try:
            bot.send_message(editor_id, message_text, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить пользователя {editor_id}: {e}")

    def notify_company_editor_about_reject(bot, company, editor_id, field, reason):
        """Уведомляет пользователя об отклонении изменения компании"""
        field_display = company_field_names.get(field, field)

        message_text = f"""
            ❌ **Изменение данных компании отклонено**

            🏢 **Компания:** {company['name']}
            📋 **Изменяемое поле:** {field_display}

            **Причина отклонения:** {reason or 'не указана'}

            Вы можете повторно отправить запрос на изменение, исправив указанные замечания.
            """

        try:
            bot.send_message(editor_id, message_text, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить пользователя {editor_id}: {e}")

    # Обновляем обработчик восстановления сообщений для поддержки company_edit
    @bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_moderation_'))
    def handle_cancel_moderation(call):
        """Обработка отмены модерации"""
        admin_id = call.from_user.id
        parts = call.data.split('_')
        entity_type = parts[2]  # 'user', 'company', 'delete', 'edit', 'company_edit'
        entity_id = (parts[3])


        # Получаем данные из moderation_data до удаления
        data = moderation_data.get(admin_id, {})

        # Очищаем временные данные
        if admin_id in moderation_data:
            del moderation_data[admin_id]

        # Очищаем состояние администратора
        set_user_state(admin_id, '')

        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Восстанавливаем оригинальное сообщение с кнопками в зависимости от типа
        if entity_type == 'user':
            restore_user_moderation_message(bot, db, call.message.chat.id, entity_id)
        elif entity_type == 'company':
            restore_company_moderation_message(bot, db, call.message.chat.id, entity_id)
        elif entity_type == 'delete':
            restore_delete_moderation_message(bot, db, call.message.chat.id, entity_id, admin_id, data['deleter_id'])
        elif entity_type == 'delete_photos':
            restore_delete_photos_moderation_message(bot, db, call.message.chat.id, entity_id)
        elif entity_type == 'edit':
            if data and data['type'] == 'edit':
                restore_edit_moderation_message(bot, db, call.message.chat.id, data)
            else:
                bot.send_message(call.message.chat.id, "❌ Данные для восстановления редактирования не найдены (edit)")
        elif entity_type == 'company-edit':
            if data and data['type'] == 'company-edit':
                restore_company_edit_moderation_message(bot, db, call.message.chat.id, data)
            else:
                bot.send_message(call.message.chat.id, "❌ Данные для восстановления редактирования компании не найдены (company_edit)")
        elif entity_type == 'company-delete':
            if data and data['type'] == 'company-delete':
                restore_delete_company_photos_moderation_message(bot, db, call.message.chat.id, call.from_user.id, data)


    def restore_delete_photos_moderation_message(bot, db, chat_id, user_id):
        user = db.fetch_one('select * from users where telegram_id=?', (user_id,))
        if user:
            bot.send_message(
                chat_id,
                f"""📝 **ЗАЯВКА НА УДАЛЕНИЕ ФОТОГРАФИЙ**

        👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
        🆔 **Telegram ID:** {user_id}
        🏢 **Роль:** {role_names.get(user['role'])}

        ❗️ **Запросил удаление всех своих фотографий.**

        ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

        Для подтверждения или отклонения используйте кнопки ниже.""",
                reply_markup=get_approve_reject_delete_photos_keyboard(user_id)
            )
            # ДОБАВЛЯЕМ ЗАЯВКУ
            add_pending_moderation('user_photos_delete', user_id)

    def restore_delete_company_photos_moderation_message(bot, db, chat_id, user_id, data):
        company_id = data['company_id']
        company = db.get_company_by_id(company_id)
        user = db.get_user_by_telegram_id(user_id)
        messsage_text =  f"""
                   📝 **ЗАЯВКА НА УДАЛЕНИЕ ФОТОГРАФИЙ**

                   👤 **Компания:** {company.get('name', '')}
                   🆔 **ИНН:** {company.get('inn', '')}
                   🏢 **Директор:** {company.get('director_first_name','')} {company.get('director_last_name', '')}

                   ❗️ **Запросил удаление всех своих фотографий: {user.get('username','')}**

                   ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

                   Для подтверждения или отклонения используйте кнопки ниже.
                   """
        bot.send_message(chat_id, messsage_text, reply_markup = get_approve_reject_delete_company_photos_keyboard(company_id, user_id))
        add_pending_moderation('company_photos_delete', user_id)

    def restore_company_edit_moderation_message(bot, db, chat_id, data):
        """Восстанавливает сообщение о запросе на редактирование данных компании"""
        company_id = data['id']
        field = data['field']
        new_value = data['new_value']
        editor_id = data['editor_id']

        company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
        if not company:
            bot.send_message(chat_id, "❌ Компания не найдена")
            return

        # Получаем старое значение
        if field in ['bik', 'payment_account', 'correspondent_account', 'okpo']:
            bank_details = db.fetch_one("SELECT * FROM company_bank_details WHERE company_id = ?", (company_id,))
            old_value = bank_details.get(field, 'Не указано') if bank_details else 'Не указано'
        else:
            old_value = company.get(field, 'Не указано')

        # Форматируем значения для отображения
        if field == 'company_type':
            old_value_display = type_to_text_map.get(old_value, old_value)
            new_value_display = type_to_text_map.get(new_value, new_value)
            parameter = company_field_names.get(field, field)
        elif field == 'tax_system':
            old_value_display = tax_to_text_map.get(old_value, old_value)
            new_value_display = tax_to_text_map.get(new_value, new_value)
            parameter = company_field_names.get(field, field)
        else:
            old_value_display = old_value
            new_value_display = new_value
            parameter = company_field_names.get(field, field)

        # Получаем информацию о редакторе
        editor = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (editor_id,))
        editor_name = f"{editor.get('first_name', '')} {editor.get('last_name', '')}" if editor else "Неизвестно"

        message_text = f"""
    📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ ДАННЫХ КОМПАНИИ**

    🏢 **Компания:** {company['name']}
    👤 **Запросил:** {editor_name}
    🆔 **Telegram ID редактора:** {editor_id}

    📋 **Изменяемое поле:** {(parameter)}
    📄 **Старое значение:** {old_value_display}
    🔄 **Новое значение:** {new_value_display}

    ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

    Для подтверждения или отклонения изменения используйте кнопки ниже.
    """

        bot.send_message(chat_id, message_text,
                         reply_markup=get_approve_reject_company_edit_keyboard(company_id, new_value, field, editor_id),
                         parse_mode='Markdown')
        add_pending_moderation('company_edit', chat_id,{
            'field': parameter,
            'new_value': new_value,
            'editor_id': editor_id
        })

    # Обновляем обработчик причин отклонения для поддержки company_edit
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_rejection_reason')
    def handle_rejection_reason(message):
        admin_id = message.from_user.id
        data = moderation_data.get(admin_id, {})

        if not data:
            print('Нет данных для модерации')
            return

        reason = message.text.strip()

        if data["type"] == 'user':
            handle_user_rejection(bot, db, admin_id, data['id'], reason)
        elif data['type'] == 'company':
            handle_company_rejection(bot, db, admin_id, data['id'], reason)
        elif data['type'] == 'delete':
            handle_delete_rejection(bot, db, admin_id, data['id'], data['deleter_id'], reason)
        elif data['type'] == 'edit':
            handle_edit_rejection(bot, db, admin_id, data['id'], reason, data['editor_id'])
        elif data['type'] == 'delete_photos':
            handle_delete_photos_rejection(bot, db, admin_id, data['id'], reason)
        elif data['type'] == 'company-edit':
            handle_company_edit_rejection(bot, db, admin_id, data['id'], reason, data['editor_id'], data['field'])
        elif data['type'] == 'company-delete':
            handle_delete_company_photos_rejection(bot, db, admin_id, moderation_data[admin_id]['id'], moderation_data[admin_id]['company_id'], reason)

        # Очищаем состояние и временные данные
        set_user_state(admin_id, '')
        if admin_id in moderation_data:
            del moderation_data[admin_id]

    def handle_company_edit_rejection(bot, db, admin_id, company_id, reason, editor_id, field):
        """Обработка отклонения изменения компании"""
        company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
        if not company:
            bot.send_message(admin_id, "❌ Компания не найдена")
            return

        bot.send_message(admin_id, f"✅ Изменение компании '{company['name']}' отклонено")
        remove_pending_moderation('company_edit', editor_id)
        # Уведомляем пользователя
        notify_company_editor_about_reject(bot, company, editor_id, field, reason)

    def restore_user_moderation_message(bot, db, chat_id, user_id):
        """Восстанавливает сообщение о модерации пользователя"""
        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if not user:
            bot.send_message(chat_id, "❌ Пользователь не найден")
            return

        company = db.fetch_one("SELECT name FROM companies WHERE id = ?", (user['company_id'],))
        company_name = company['name'] if company else "Не указана"

        message_text = format_user_moderation_message(user, company_name)
        bot.send_message(chat_id, message_text,
                         reply_markup=get_approve_reject_user_keyboard(user_id),
                         parse_mode='Markdown')
        add_pending_moderation('user_registration', user_id)

    def restore_company_moderation_message(bot, db, chat_id, company_id):
        """Восстанавливает сообщение о модерации компании"""
        company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
        if not company:
            bot.send_message(chat_id, "❌ Компания не найдена")
            return

        message_text = format_company_moderation_message(company)
        bot.send_message(chat_id, message_text,
                         reply_markup=get_approve_reject_company_keyboard(company_id),
                         parse_mode='Markdown')
        add_pending_moderation('company_registration', company_id)

    def restore_delete_moderation_message(bot, db, chat_id, user_id, admin_id, deleter_id):
        """Восстанавливает сообщение о запросе на удаление пользователя"""
        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if not user:
            bot.send_message(chat_id, "❌ Пользователь не найден")
            return

        # Получаем информацию о том, кто запросил удаление
        requester_info = db.fetch_one(
            "SELECT u.username FROM users u WHERE u.telegram_id = ?",
            (user.get('deletion_requested_by', admin_id),)
        )
        username = requester_info['username'] if requester_info else "неизвестно"

        message_text = (
            f"❗️ Запрос на удаление пользователя {user['first_name']}, Telegram ID:{user['telegram_id']}!!!\n"
            f"Username: @{user.get('username', 'N/A')}, 💼 Должность: {role_names.get(user['role'], user['role'])}\n\n"
            f"Запросил @{username}"
        )

        bot.send_message(chat_id, message_text,
                         reply_markup=get_approve_reject_delete_keyboard(user_id, deleter_id))
        add_pending_moderation('user_delete', user_id)

    def restore_edit_moderation_message(bot, db, chat_id, data):
        """Восстанавливает сообщение о запросе на редактирование данных"""
        user_id = data['id']
        field = data['field']
        new_value = data['new_value']
        editor_id = data['editor_id']

        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if not user:
            bot.send_message(chat_id, "❌ Пользователь не найден")
            return

        old_value = user.get(field, 'Не указано')

        # Форматируем значения для отображения
        if field == 'role':
            old_value_display = role_names.get(old_value, old_value)
            new_value_display = role_names.get(new_value, new_value)
            parameter = field_names.get(field, field)
        else:
            old_value_display = old_value
            new_value_display = new_value
            parameter = field_names.get(field, field)

        message_text = f"""
📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ ДАННЫХ**

👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
🆔 **Telegram ID:** {user_id}
🏢 **Роль:** {role_names.get(user['role'], user['role'])}

📋 **Изменяемое поле:** {parameter}
📄 **Старое значение:** {old_value_display}
🔄 **Новое значение:** {new_value_display}

⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

Для подтверждения или отклонения изменения используйте панель администратора.
"""

        bot.send_message(chat_id, message_text,
                         reply_markup=get_approve_reject_edit_keyboard(user_id, new_value, field, editor_id),
                         parse_mode='Markdown')
        add_pending_moderation('user_edit', user_id, {
            'field': field,
            'new_value': new_value,
            'editor_id': editor_id
        })

    # Остальные обработчики остаются без изменений...
    @bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_company_', 'reject_company_')))
    def handle_company_moderation(call):
        """Обработка модерации заявок на регистрацию компании"""
        admin_id = call.from_user.id

        # Проверяем, что пользователь - администратор
        admin = db.fetch_one("SELECT role FROM users WHERE telegram_id = ?", (admin_id,))
        if not admin or admin['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для выполнения этого действия")
            return

        action, company_id = call.data.split('_')[0], int(call.data.split('_')[2])
        company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))

        if not company:
            bot.answer_callback_query(call.id, "❌ Компания не найдена")
            return

        # Проверяем статус компании перед обработкой
        if company['status'] in ['approved', 'rejected']:
            # Показываем сообщение и удаляем кнопки
            if company['status'] == 'approved':
                status_text = "одобрена"
            elif company['status'] == 'rejected':
                status_text = "отклонена"

            bot.answer_callback_query(
                call.id,
                f"❌ Заявка на компанию '{company['name']}' уже была {status_text} другим администратором"
            )
            time.sleep(1)

            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass

            return

        if action == 'approve':
            # Одобряем компанию
            success = db.execute_query(
                "UPDATE companies SET status = 'approved', moderated_by = ?, moderated_at = datetime('now') WHERE id = ?",
                (admin_id, company_id)
            )

            if success:
                # Уведомляем администратора
                bot.edit_message_text(
                    f"✅ Компания '{company['name']}' одобрена (админ: {admin_id})",
                    call.message.chat.id,
                    call.message.message_id
                )

                remove_pending_moderation('company_registration', company_id)

                # Уведомляем пользователя, который создал компанию
                notify_user_about_company_status(bot, db, company_id, 'approved')

            else:
                bot.answer_callback_query(call.id, "❌ Ошибка при одобрении компании")

        elif action == 'reject':
            # Запрашиваем причину отклонения
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                f"❌ Компания '{company['name']}' отклонена\n\n"
                "Укажите причину отклонения:",
                reply_markup=get_cancel_moderation_keyboard(company_id, 'company')
            )
            set_user_state(admin_id, 'waiting_for_rejection_reason')

            moderation_data[admin_id] = {
                'type': 'company',
                'id': company_id,
                'action': 'reject',
                'message_id': call.message.message_id,
                'creator_id': company['created_by']
            }


    @bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_delete_', 'reject_delete_')))
    def handle_delete_moderation(call):
        admin_id = call.from_user.id
        admin = db.fetch_one("SELECT role FROM users WHERE telegram_id = ?", (admin_id,))
        if not admin or admin['role'] != 'admin':
            bot.answer_callback_query(call.id, "❌ У вас нет прав для выполнения этого действия")
            return
        print(call.data)
        action, user_id, deleter_id = call.data.split('_')[0], call.data.split('_')[2], call.data.split('_')[3]
        user = db.get_user_by_telegram_id(user_id)
        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден")
            return

        if action == 'approve':
            print('Удаляем пользователя')
            # Одобряем удаление
            success = db.execute_query(
                "delete from users where telegram_id = ?",
                (str(user_id),)
            )
            if success:
                # Уведомляем администратора
                bot.edit_message_text(
                    f"✅ Пользователь '{user['username']}' удален",
                    call.message.chat.id,
                    call.message.message_id
                )
                bot.send_message(
                    deleter_id,
                    f"✅ Пользователь '{user['username']}' удален"
                    )
                remove_pending_moderation('user_delete', user_id)
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка при удалении пользователя")

        elif action == 'reject':
            # Запрашиваем причину отклонения
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                f"❌ Удаление пользователя '{user['username']}' отклонено\n\n"
                f"Укажите причину:",
                reply_markup=get_cancel_moderation_keyboard(user_id, 'delete')
            )

            set_user_state(admin_id, 'waiting_for_rejection_reason')

            user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
            if not user:
                bot.send_message(admin_id, "❌ Пользователь не найден")
                return

            # Сохраняем временные данные для модерации
            moderation_data[admin_id] = {
                'type': 'delete',
                'id': user_id,
                'action': 'reject',
                'message_id': call.message.message_id,
                'deleter_id': deleter_id
            }

    @bot.callback_query_handler(func=lambda call: call.data.startswith(('approve-edit-', 'reject-edit-')))
    def handle_edit_moderation(call):
        admin_id = call.from_user.id
        action, user_id, value, field, editor_id = call.data.split('-')[0], (call.data.split('-')[2]), \
        call.data.split('-')[3], call.data.split('-')[4], call.data.split('-')[5]
        user = db.get_user_by_telegram_id(user_id)
        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден")
            return
        if action == 'approve':
            print('Изменяем данные')
            # Одобряем изменение
            success = db.execute_query(
                f"update users set {field} = ? where telegram_id = ?",
                (value, user_id,)
            )
            if success:
                # Уведомляем администратора
                bot.edit_message_text(
                    f"✅ Данные пользователя {user['username']} успешно изменены!",
                    call.message.chat.id,
                    call.message.message_id
                )
                remove_pending_moderation('user_edit', user_id)
                if editor_id:
                    notify_editor_about_approve(bot, user, editor_id, 'approved', field, value)
                else:
                    notify_editor_about_approve(bot, user, user_id, editor_id, 'rejected', field, value)
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка при одобрении компании")

        elif action == 'reject':
            # Запрашиваем причину отклонения
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                f"❌ Изменение данных пользователя '{user['username']}' отклонено\n"
                "Укажите причину:",
                reply_markup=get_cancel_moderation_keyboard(user_id, 'edit')
            )
            set_user_state(admin_id, 'waiting_for_rejection_reason')
            # Сохраняем временные данные для модерации
            moderation_data[admin_id] = {
                'type': 'edit',
                'id': user_id,
                'action': 'reject',
                'message_id': call.message.message_id,
                'editor_id': editor_id,
                'new_value': value,
                'field': field
            }

    def handle_user_rejection(bot, db, admin_id, user_id, reason):
        """Обработка отклонения пользователя"""
        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if not user:
            bot.send_message(admin_id, "❌ Пользователь не найден")
            return

        # Отклоняем пользователя
        success = db.execute_query(
            "UPDATE users SET status = 'blocked' WHERE telegram_id = ?", (user_id,)
        )

        if success:
            bot.send_message(admin_id, f"✅ Пользователь {user['first_name']} {user['last_name']} отклонен")

            remove_pending_moderation('user_registration', user_id)
            if 'creator_id' in moderation_data.get(admin_id, {}):
                notify_creator_about_status(bot, user, moderation_data[admin_id]['creator_id'], 'rejected', reason)
            else:
                notify_user_about_rejection(bot, user, user_id, reason)
        else:
            bot.send_message(admin_id, "❌ Ошибка при отклонении пользователя")

    def handle_company_rejection(bot, db, admin_id, company_id, reason):
        """Обработка отклонения компании"""
        company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
        if not company:
            bot.send_message(admin_id, "❌ Компания не найдена")
            return

        # Отклоняем компанию
        success = db.execute_query(
            "UPDATE companies SET status = 'rejected' WHERE id = ?",
            (company_id,)
        )

        if success:
            bot.send_message(admin_id, f"✅ Компания '{company['name']}' отклонена")

            remove_pending_moderation('company_registration', company_id)

            # Уведомляем пользователя
            notify_user_about_company_status(bot, db, company_id, 'rejected', reason)
        else:
            bot.send_message(admin_id, "❌ Ошибка при отклонении компании")

    def handle_delete_rejection(bot, db, admin_id, user_id, deleter_id, reason):
        print('Запущена функция отказа')
        print(user_id)
        print(admin_id)
        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if not user:
            bot.send_message(admin_id, "❌ Пользователь не найден")
            return
        bot.send_message(admin_id, '❌ Вы отклонили удаление пользователя.')
        bot.send_message(deleter_id,
                         "❌ Администратор отменил удаление пользователя по следующей причине:\n\n"
                         f"{reason}")
        remove_pending_moderation('user_delete', user_id)

    def handle_edit_rejection(bot, db, admin_id, user_id, reason, editor_id):
        user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if not user:
            bot.send_message(admin_id, "❌ Пользователь не найден")
            return
        notify_editor_about_reject(bot, user, reason, editor_id)
        bot.send_message(admin_id,
                         "✅ **Редактирование отклонено!**")
        remove_pending_moderation('user_edit', user_id)

    def notify_user_about_status(bot, user, user_id):
        """Уведомляет пользователя о статусе модерации"""
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None
        if not user:
            return
        message_text = f"""
        ✅ **Ваша регистрация одобрена!**

        👤 {user['first_name']} {user['last_name']}

        Теперь вы можете пользоваться системой. Добро пожаловать!
        """
        try:
            bot.send_message(user_id, message_text, reply_markup=get_main_menu(role))
        except Exception as e:
            print(f"Не удалось уведомить пользователя {user_id}: {e}")

    def notify_user_about_rejection(bot, user, user_id, reason=None):
        """Уведомляет пользователя об отклонении регистрации"""
        if not user:
            return

        message_text = f"""
        ❌ **Ваша регистрация отклонена**

        👤 {user['first_name']} {user['last_name']}

        **Причина:** {reason or 'не указана'}

        Вы можете повторно зарегистрироваться, исправив указанные замечания.
        """

        try:
            bot.send_message(user_id, message_text)
        except Exception as e:
            print(f"Не удалось уведомить пользователя {user_id}: {e}")

    def notify_creator_about_status(bot, user, user_id, status, reason):
        """Уведомляет создателя о статусе модерации"""
        if not user:
            return

        if status == 'approved':
            message_text = f"""
        ✅ **Регистрация пользователя одобрена!**

        👤 {user['first_name']} {role_names.get(user['role'])}
        """
        else:
            message_text = f"""
        ❌ **Регистрация пользователя отклонена**

        👤 {user['first_name']} {role_names.get(user['role'])}

        **Причина:** {reason or 'не указана'}

        Вы можете повторно зарегистрировать пользователя, исправив указанные замечания.
        """

        try:
            bot.send_message(user_id, message_text, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить пользователя {user_id}: {e}")

    def notify_user_about_company_status(bot, db, company_id, status, reason=None):
        """Уведомляет пользователя о статусе модерации компании"""
        company = db.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))
        if not company:
            return

        user_id = company.get('created_by')
        if not user_id:
            return

        if status == 'approved':
            message_text = f"""
            ✅ **Ваша компания одобрена!**

            🏢 {company['name']}

            Теперь ваша компания доступна для выбора при регистрации пользователей.
            Вы можете начать пользоваться системой.
            """
        else:
            message_text = f"""
            ❌ **Ваша компания отклонена**

            🏢 {company['name']}

            **Причина:** {reason or 'не указана'}

            Вы можете повторно зарегистрировать компанию, исправив указанные замечания.
            """

        try:
            bot.send_message(user_id, message_text, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить пользователя {user_id}: {e}")

    def notify_editor_about_approve(bot, user, user_id, status, field, value, reason=None):
        if not user:
            return
        if field == 'role':
            message_text = f"""
            ✅ **Изменение данных одобрено!**

            👤 {user['first_name']} {role_names.get(user['role'])}

            {field_names.get(field)} изменено на {role_names.get(value)}.
            """
        else:
            message_text = f"""
            ✅ **Изменение данных одобрено!**

            👤 {user['first_name']} {role_names.get(user['role'])}

            {field_names.get(field)} изменено на {value}.
            """

        try:
            bot.send_message(user_id, message_text, parse_mode='Markdown')
        except Exception as e:
            print(f"Не удалось уведомить пользователя {user_id}: {e}")

    def notify_editor_about_reject(bot, user, reason, editor_id):
        if not user:
            return
        message_text = f"""
                ❌ **Изменение данных пользователя {user['username']}**\n 
                ФИО: {user['first_name']} {user['last_name']} {user.get('patronymic', '')}\n
                Должность: {role_names.get(user['role'])} 
                ❌ОТКЛОНЕНО❌\n
                ПРИЧИНА: '{reason}'"""
        bot.send_message(editor_id, message_text)

    def format_company_moderation_message(company):
        company_type_map = {
            'legal': 'Юридическое лицо',
            'individual': 'Индивидуальный предприниматель',
            'self_employed': 'Самозанятый'
        }

        tax_system_map = {
            'osn': 'ОСНО',
            'usn': 'УСН',
            'eshn': 'ЕСХН',
            'psn': 'ПСН',
            'npd': 'НПД',
            'ausn': 'АУСН'
        }

        return f"""
        🆕 **НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ КОМПАНИИ**

        🏢 **Данные компании:**
        • Название: {company['name']}
        • Тип: {company_type_map.get(company['company_type'], company['company_type'])}
        • ИНН: {company.get('inn', 'Не указан')}
        • КПП: {company.get('kpp', 'Не указан')}
        • ОГРН: {company.get('ogrn', 'Не указан')}

        👤 **Руководитель:**
        • ФИО: {company.get('director_surname', '')} {company.get('director_name', '')}

        📍 **Юридический адрес:** {company.get('legal_address', 'Не указан')}
        💳 **Система налогообложения:** {tax_system_map.get(company.get('tax_system'), 'Не указана')}
        📞 **Телефон:** {company.get('contact_phone', 'Не указан')}
        📧 **Email:** {company.get('contact_email', 'Не указан')}

        ⏰ **Дата подачи заявки:** {company.get('created_at', 'Не указана')}

        Выберите действие:
        """

    def format_user_moderation_message(user, company_name):
        """Форматирует сообщение для модерации пользователя"""
        role_descriptions = {
            "logist": "👨‍💼 Логист",
            "external_logist": "👔 Внешний логист",
            "executor": "🚛 Перевозчик",
            "admin": "👑 Администратор"
        }

        return f"""
        🆕 **НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ ПОЛЬЗОВАТЕЛЯ**

        👤 **Данные пользователя:**
        • **ФИО:** {user['last_name']} {user['first_name']} {user.get('patronymic', '')}
        • **Телеграм:** @{user.get('username', 'Не указан')}
        • **Телефон:** {user.get('phone', 'Не указан')}
        • **Email:** {user.get('email', 'Не указан')}
        • **Дата рождения:** {user.get('birth_date', 'Не указана')}

        📘 **Паспортные данные:**
        • **Серия/Номер:** {user.get('passport_series', 'Не указана')} {user.get('passport_number', 'Не указан')}
        • **Дата выдачи:** {user.get('passport_issue_date', 'Не указана')}

        🔢 **Код АТИ:** {user.get('ati_code', 'Не указан')}

        🏢 **Компания:** {company_name}
        👔 **Роль:** {role_descriptions.get(user.get('role'), user.get('role', 'Не указана'))}

        ⏰ **Дата подачи заявки:** {user.get('created_at', 'Не указана')}

        Выберите действие:
        """