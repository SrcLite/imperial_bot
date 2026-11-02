import glob
import logging
import re
import os
from datetime import datetime
import time
from collections import defaultdict
from telebot.types import ReplyKeyboardRemove, InputMediaPhoto
from handlers.admin_handlers.pending_moderations_handlers import add_pending_moderation
from keyboards.admin_keyboards import get_approve_reject_user_keyboard
from keyboards.registration_company_keyboards import get_company_type_keyboard
from keyboards.registration_user_keyboards import *
from PIL import Image
import io
from dadata import Dadata
from utils.dicts import role_names, company_type_map
from utils.email_sender import send_email_notification
from utils.subscription_manager import SubscriptionManager

DADATA_API_KEY = "8fe6625dc9396570532c2f2e02872290a7d7cd3c"
DADATA_SECRET_KEY = "1cc317ec14b123c6b9c20624564e18340d382d8a"
dadata_client = Dadata(DADATA_API_KEY)


# Настройка логирования
def setup_logging():
    """Настройка логирования в файл"""
    try:
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_file = os.path.join(log_dir, f"user_registration_{datetime.now().strftime('%Y%m%d')}.log")

        # Создаем логгер
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)

        # Очищаем существующие обработчики
        if logger.handlers:
            logger.handlers.clear()

        # Форматтер
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')

        # Файловый обработчик
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        # Консольный обработчик (опционально)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        # Добавляем обработчики
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        logger.info(f"Логирование инициализировано. Файл логов: {log_file}")
        return logger

    except Exception as e:
        print(f"Ошибка при настройке логирования: {e}")
        # Возвращаем базовый логгер в случае ошибки
        return logging.getLogger(__name__)


# Инициализация логгера
logger = setup_logging()

# Проверяем, что логгер работает
logger.info("Модуль регистрации пользователей загружен")

user_states = {}
user_data = {}
photo_info = {}
processed_media_groups = defaultdict(bool)


def register_user_handlers(bot, db):
    logger.info("Регистрация обработчиков пользователей начата")

    @bot.callback_query_handler(func=lambda call: call.data == 'reject_terms')
    def handle_reject_terms(call):
        user_id = call.from_user.id
        logger.info(f"Пользователь {user_id} отклонил условия")

        if user_id in user_states:
            del user_states[user_id]
        if user_id in user_data:
            del user_data[user_id]
        db.execute_query("update users set accepted_terms = 'false' where telegram_id = ? ",
                         (user_id,))

        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(
            call.message.chat.id,
            "❌ Вы отклонили условия платформы.\n\n"
            "Регистрация недоступна, пока вы не примите условия работы на платформе.",
            reply_markup=get_terms_keyboard()
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == 'agree_terms')
    def handle_agree_terms(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        logger.info(f"Пользователь {user_id} принял условия платформы")

        # Получаем пользователя из базы данных
        user = db.get_user_by_telegram_id(user_id)
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None

        # Проверяем существование пользователя
        if user:
            # Если пользователь уже существует - обновляем accepted_terms
            logger.info(f"Пользователь {user_id} уже существует, обновляем accepted_terms")
            db.execute_query(
                "UPDATE users SET accepted_terms = 'true', username = ? WHERE telegram_id = ?",
                (call.from_user.username, user_id)
            )
        else:
            # Если пользователя нет - создаем новую запись
            logger.info(f"Пользователь {user_id} не найден, создаем новую запись")
            db.execute_query(
                "INSERT INTO users (telegram_id, username, accepted_terms) VALUES (?, ?, ?)",
                (user_id, call.from_user.username, 'true')
            )

        # Инициализируем состояние и данные пользователя
        user_data[user_id] = {}
        user_data[user_id]['accepted_terms'] = 'true'
        bot.delete_message(chat_id, call.message.message_id)
        logger.info(f"Пользователь {user_id}: состояние = {user_states.get(user_id, '')}")

        if user != None:
            if role in ['logist', 'external_logist'] and user['status'] == 'added':
                user_states[user_id] = 'waiting_for_log_last_name'
                logger.info(f"Пользователь {user_id} продолжает регистрацию как логист")
                bot.send_message(
                    chat_id,
                    "✅ Вы приняли условия платформы.\n\n"
                    f"{user.get('first_name')}, вас уже частично зарегистрировали, продолжите регистрацию для начла работы в системе.\n"
                    "📝 Введите вашу фамилию:",
                    reply_markup=ReplyKeyboardRemove()
                )
            elif role in ['executor', 'external_executor'] and user['status'] == 'added':
                set_user_state(user_id, '')
                logger.info(f"Пользователь {user_id} уже зарегистрирован, роль: {role}, обработка фотографий паспорта")
                set_user_state(user_id, 'waiting_for_end_passport_main_photo')
                bot.send_message(
                    chat_id,
                    "✅ Вы приняли условия платформы.\n\n"
                    f"Вас уже зарегистрировали, для работы в системе вам необходимо добавить фото паспорта\n"
                    "Сначала отправьте фото 1 страницы паспорта (с фото и данными):",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                user_states[user_id] = 'waiting_for_user_role'
                logger.info(f"Пользователь {user_id} начал новую регистрацию")
                bot.send_message(
                    chat_id,
                    "✅ Вы приняли условия платформы.\n\n"
                    "Теперь выберите тип пользователя:",
                    reply_markup=get_select_role_keyboard()
                )
                bot.answer_callback_query(call.id)
        else:
            user_states[user_id] = 'waiting_for_user_role'
            logger.info(f"Пользователь {user_id} начал новую регистрацию")
            bot.send_message(
                chat_id,
                "✅ Вы приняли условия платформы.\n\n"
                "Теперь выберите тип пользователя:",
                reply_markup=get_select_role_keyboard()
            )
            bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "read_terms")
    def handle_read_terms(call):
        logger.info(f"Пользователь {call.from_user.id} запросил чтение условий")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        terms_text = """
            📋 **УСЛОВИЯ РАБОТЫ НА ПЛАТФОРМЕ ООО «ИМПЕРИАЛ»**

            1. **ОБЩИЕ ПОЛОЖЕНИЯ**
               - Все данные должны быть достоверными и актуальными
               - Регистрация требует подтверждения администратора
               - Платформа предназначена для профессиональной деятельности

            2. **ДЛЯ ПЕРЕВОЗЧИКОВ**
               - Рейтинг перевозчиков влияет на приоритет в получении заказов
               - Обязательное соблюдение сроков выполнения заявок
               - Ответственность за сохранность груза

            3. **ДЛЯ ГРУЗОВЛАДЕЛЬЦЕВ**
               - Для сторонних компании предусмотрена комиссия
               - Обязательность оплаты принятых заявок
               - Предоставление точной информации о грузе

            4. **СОГЛАСОВАНИЕ ИЗМЕНЕНИЙ**
               - Изменение данных возможно только через согласование
               - Все правки проверяются администрацией
               - Контроль мошеннических действий

            5. **КОНФИДЕНЦИАЛЬНОСТЬ**
               - Ваши данные защищены и не передаются третьим лицам
               - Контакты перевозчиков скрыты до момента оплаты

            **Нажимая «Принять условия», вы соглашаетесь с правилами платформы.**
                    """
        bot.send_message(call.message.chat.id, terms_text, reply_markup=get_registration_agreement_keyboard(),
                         parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_user_role')
    def handle_role_selection(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        current_state = get_user_state(user_id)
        logger.info(f"Пользователь {user_id}: состояние = {current_state}")
        logger.info(f"Пользователь {user_id}: текст сообщения = '{message.text}'")

        role_map = {"🚛 Я ПЕРЕВОЗЧИК": "executor",
                    "📦 Я ГРУЗОВЛАДЕЛЕЦ": "logist",
                    "👑 Я АДМИНИСТРАТОР": "admin"}

        if message.text not in role_map:
            logger.warning(f"Пользователь {user_id}: неверный выбор роли: {message.text}")
            bot.send_message(chat_id, "Пожалуйста, выберите роль из предложенных вариантов.")
            return

        selected_role = role_map[message.text]
        logger.info(f"Пользователь {user_id}: выбрал роль {selected_role}")

        # Обновляем состояние и данные пользователя
        set_user_state(user_id, 'waiting_for_company_selection')
        user_data[user_id]['selected_role'] = selected_role

        query = db.execute_query('update users set role = ? where telegram_id = ?', (selected_role, user_id))
        if query:
            logger.info(f"Запрос на обновление роли {user_id} успешно выполнен!")

        logger.info(f'Пользователь {user_id}: ожидание выбора компании')

        approved_companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )

        if approved_companies:
            companies_text = "🏢 **Выберите вашу компанию из списка:**\n\n"
            for company in approved_companies:
                companies_text += f"• {company['name']}\n"

            companies_text += "\nИли зарегистрируйте новую компанию:"

            bot.send_message(
                chat_id,
                companies_text,
                reply_markup=get_company_selection_keyboard(approved_companies),
                parse_mode="Markdown"
            )
        else:
            logger.info("Нет зарегистрированных компаний, переход к регистрации компании")
            bot.send_message(
                chat_id,
                "📋 **Регистрация компании**\n\n"
                "В системе пока нет зарегистрированных компаний. "
                "Необходимо зарегистрировать компанию для продолжения.",
                reply_markup=get_reg_company_keyboard(),
                parse_mode="Markdown"
            )
            set_user_state(user_id, 'waiting_for_company_reg')

    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'waiting_for_company_selection')
    def handle_company_selection(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        current_state = get_user_state(user_id)
        logger.info(f"Пользователь {user_id}: состояние = {current_state}")

        if current_state == 'waiting_for_company_selection':
            logger.info(f"Пользователь {user_id}: запущена функция выбора компании")

            if message.text == '⬅️ Назад к выбору роли':
                logger.info(f"Пользователь {user_id}: возврат к выбору роли")
                bot.send_message(
                    chat_id,
                    'Пожалуйста, выберите роль из предложенных вариантов.',
                    reply_markup=get_select_role_keyboard()
                )
                set_user_state(user_id, 'waiting_for_user_role')
                return

            if message.text == '🔍Поиск по ИНН':
                logger.info(f"Пользователь {user_id}: поиск компании по ИНН")
                bot.send_message(
                    chat_id,
                    'Введите ИНН компании, которую хотите выбрать:',
                    reply_markup=ReplyKeyboardRemove()
                )
                set_user_state(user_id, 'waiting_for_company_inn')
                return
            elif message.text == "🟢 Зарегистрировать новую компанию":
                logger.info(f"Пользователь {user_id}: регистрация новой компании")
                bot.send_message(
                    chat_id,
                    'Переходим к регистрации компании...\n'
                    'Выберите тип компании:',
                    reply_markup=get_company_type_keyboard()
                )
                set_user_state(user_id, 'waiting_for_company_type')
                return
            else:
                # Убираем эмодзи из названия компании
                company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text
                logger.info(f"Пользователь {user_id}: выбрал компанию '{company_name}'")

                company = db.fetch_one(
                    "SELECT id, name FROM companies WHERE name = ? AND status = 'approved'",
                    (company_name,)
                )
                approved_companies = db.fetch_all(
                    "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
                )

                if not company:
                    logger.warning(f"Компания '{company_name}' не найдена для пользователя {user_id}")
                    bot.send_message(chat_id, "❌ Компания не найдена. Пожалуйста, выберите компанию из списка.", get_company_selection_keyboard(approved_companies))
                    return

                company_id = company['id']
                company_name = company['name']
                logger.info(f"Найдена компания: ID={company_id}, название='{company_name}'")

                selected_role = user_data[user_id].get('selected_role')
                final_role = determine_final_role(selected_role, company_id)
                logger.info(f"Определена финальная роль: {final_role}")

                # Сохраняем данные компании
                user_data[user_id]['final_role'] = final_role
                user_data[user_id]['company_id'] = company_id
                user_data[user_id]['company_name'] = company_name

                continue_user_registration(bot, db, user_id, chat_id, final_role, company_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_inn')
    def handle_company_inn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        inn = message.text.strip()
        logger.info(f"Пользователь {user_id} ищет компанию по ИНН: {message.text}")
        company_data_local = db.get_approved_one_company_by_inn(inn)

        if message.text == '⬅️ Назад':
            set_user_state(user_id, 'waiting_for_company_selection')
            approved_companies = db.fetch_all(
                "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
            )

            if approved_companies:
                companies_text = "🏢 **Выберите вашу компанию из списка:**\n\n"
                for company in approved_companies:
                    companies_text += f"• {company['name']}\n"

                companies_text += "\nИли зарегистрируйте новую компанию:"

                bot.send_message(
                    chat_id,
                    companies_text,
                    reply_markup=get_company_selection_keyboard(approved_companies),
                )
            return

        print(company_data_local)

        if company_data_local:
            logger.info(f"Компания найдена в локальной БД для пользователя {user_id}")
            bot.send_message(
                chat_id,
                '✅ Компания найдена в нашей базе:\n\n'
                f"🏢 **{company_data_local['name']}**\n"
                f"📍 {company_data_local.get('address', 'Адрес не указан')}\n"
                f"📄 ИНН: {company_data_local['inn']}"
            )
            bot.send_message(
                chat_id,
                'Выберите компанию:',
                reply_markup=get_founded_company_selection_keyboard(company_data_local)
            )
            set_user_state(user_id, 'waiting_for_company_selection')
            return

        bot.send_message(chat_id, "🔍 Ищем компанию во внешних источниках...")

        try:
            if not inn.isdigit() or len(inn) not in [10, 12]:
                bot.send_message(
                    chat_id,
                "❌ Неверный формат ИНН. Введите 10 цифр (для юр.лиц) или 12 цифр (для ИП).\n\n"
                "Попробуйте еще раз или вернитесь назад:",
                reply_markup=get_back_keyboard()
                )
                return

            result =  dadata_client.find_by_id('party', inn)
            if not result or not result[0]:
                bot.send_message(
                    chat_id,
                    "❌ Компания не найдена. Проверьте ИНН или попробуйте позже.\n\n"
                    "Попробуйте другой ИНН или вернитесь назад:",
                    reply_markup=get_back_keyboard()
                )
                return

            company_data = result[0]
            data = company_data.get('data', {})
            print(data)

            company_type = determine_company_type(data, inn)

            company_info = {
                'inn': data.get('inn', ''),
                'kpp': data.get('kpp', ''),
                'ogrn': data.get('ogrn', ''),
                'name_full': data.get('name', {}).get('full_with_opf', ''),
                'name_short': data.get('name', {}).get('short_with_opf', company_data.get('value', '')),
                'address': data.get('address', {}).get('value', ''),
                'management_name': data.get('management', {}).get('name', ''),
                'management_post': data.get('management', {}).get('post', ''),
                'company_type': company_type,
            }

            company_type_display = company_type_map.get(company_type)

            formatted_info = f"""
            🏢 **{company_info['name_full']}**
            📋 **Тип:** {company_type_display}
    
            📊 **Реквизиты:**
            • ИНН: `{company_info['inn']}`
            • КПП: `{company_info['kpp']}`
            • ОГРН: `{company_info['ogrn']}`
    
            📍 **Адрес:** {company_info['address']}
    
            👨‍💼 **Руководство:**
            • {company_info['management_name']}
            • {company_info['management_post']}
            """

            # Показываем найденную информацию
            bot.send_message(
                chat_id,
                formatted_info,
                parse_mode='Markdown'
            )

            # Предлагаем сохранить и выбрать компанию
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("✅ Сохранить и выбрать", callback_data=f"save_company_{inn}"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_company_search")
            )

            bot.send_message(
                chat_id,
                "📝 Хотите сохранить эту компанию в базу и выбрать её?",
                reply_markup=keyboard
            )

            # Сохраняем данные компании во временное хранилище
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['last_external_company'] = company_info

        except Exception as e:
            logger.error(f"Ошибка поиска компании по ИНН {inn}: {e}")
            bot.send_message(
                chat_id,
                f"❌ Ошибка при поиске компании: {str(e)}\n\n"
                "Попробуйте позже или вернитесь назад:",
                reply_markup=get_back_keyboard()
            )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('save_company_'))
    def handle_save_company_callback(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        inn = call.data.split('_')[2]

        if user_id not in user_data or 'last_external_company' not in user_data[user_id]:
            bot.answer_callback_query(call.id, "❌ Данные компании не найдены")
            return

        company_info = user_data[user_id]['last_external_company']

        try:
            # Сохраняем компанию в базу данных
            # Сначала проверяем, существует ли уже компания
            existing = db.fetch_one(
                "SELECT id FROM companies WHERE inn = ?",
                (company_info['inn'],)
            )

            print(company_info)

            if existing:
                # Обновляем существующую запись
                db.execute_query("""
                    UPDATE companies SET 
                        name = ?,
                        kpp = ?,
                        ogrn = ?,
                        address = ?,
                        management_name = ?,
                        management_post = ?,
                        status = 'pending',
                        company_type = ?,
                        updated_at = datetime('now')
                    WHERE inn = ?
                """, (
                    company_info['name_short'],
                    company_info['kpp'],
                    company_info['ogrn'],
                    company_info['address'],
                    company_info['management_name'],
                    company_info['management_post'],
                    company_info['company_type'],
                    company_info['inn']
                ))
                company_id = existing['id']
            else:
                # Создаем новую запись
                db.execute_query("""
                    INSERT INTO companies (
                        inn, kpp, ogrn, name, 
                        address, management_name, management_post,
                        status, company_type, 
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, datetime('now', '+3 hours'), datetime('now', '+3 hours'))
                """, (
                    company_info['inn'],
                    company_info['kpp'],
                    company_info['ogrn'],
                    company_info['name_short'],
                    company_info['address'],
                    company_info['management_name'],
                    company_info['management_post'],
                    company_info['company_type'],
                ))

                # Получаем ID новой компании
                company_row = db.fetch_one("SELECT id from companies where inn = ?", (company_info['inn'],))
                company_id = company_row['id'] if company_row else None
                print(company_row['id'])

            # Получаем обновленные данные компании
            saved_company = db.fetch_one(
                "SELECT * FROM companies WHERE id = ?",
                (company_id,)
            )

            # Удаляем сообщение с кнопками
            bot.delete_message(chat_id, call.message.message_id)
            user = db.get_user_by_telegram_id(user_id)

            # Сохраняем выбор пользователя
            selected_role = user_data[user_id].get('selected_role', user.get('role'))
            final_role = determine_final_role(selected_role, company_id)

            user_data[user_id]['final_role'] = final_role
            user_data[user_id]['company_id'] = company_id
            user_data[user_id]['company_name'] = saved_company['name']

            company = db.fetch_one('select * from companies where id = ?', (company_id,))
            bank_details = db.fetch_one("SELECT * FROM company_bank_details WHERE company_id = ?", (company_id,))

            # Проверяем наличие обязательных полей
            required_fields_missing = []

            if not company.get('contact_phone'):
                required_fields_missing.append('contact_phone')
            if not company.get('contact_email'):
                required_fields_missing.append('contact_email')
            if not bank_details:
                required_fields_missing.extend(['bik', 'payment_account', 'correspondent_account'])
            else:
                if not bank_details.get('bik'):
                    required_fields_missing.append('bik')
                if not bank_details.get('payment_account'):
                    required_fields_missing.append('payment_account')
                if not bank_details.get('correspondent_account'):
                    required_fields_missing.append('correspondent_account')

            if required_fields_missing:
                # Предлагаем продолжить регистрацию компании
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton("📝 Продолжить регистрацию компании", callback_data = 'continue_company_registration'))

                db.execute_query('update users set company_id = ?, role = ? where telegram_id =?', (user_data[user_id]['company_id'], user_data[user_id]['final_role'], user_id))

                bot.send_message(
                    chat_id,
                    f"✅ Компания сохранена!\n\n"
                    f"Для завершения регистрации компании необходимо заполнить дополнительные данные.\n"
                    f"Нажмите кнопку, чтобы продолжить",
                    reply_markup=keyboard
                )
                set_user_state(user_id, 'waiting_for_continue_company_reg')
            else:
                # Все поля заполнены, продолжаем регистрацию пользователя
                continue_user_registration(bot, db, user_id, chat_id, final_role, company_id)

            bot.answer_callback_query(call.id, "✅ Компания сохранена и выбрана")

        except Exception as e:
            logger.error(f"Ошибка сохранения компании: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка сохранения компании")

    @bot.callback_query_handler(func=lambda call: call.data == 'continue_company_registration')
    def continue_company_registration(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Редактируем сообщение, убирая inline-клавиатуру
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="📝 **Продолжение регистрации компании**\n\n"
                 "Введите контактный телефон компании:",
            reply_markup=None  # Убираем клавиатуру
        )

        set_user_state(user_id, 'waiting_for_company_partial_contact_phone')
        bot.answer_callback_query(call.id)

    def determine_company_type(company_data, inn):
        company_type = company_data.get('type', '')

        if len(inn) == 12:
            if company_type.lower() in ['individual', 'ip']:
                ogrn = company_data.get('ogrn', '')
                if not ogrn:
                    return 'self_employed'
                else:
                    return 'individual'
            else:
                return 'individual'
        elif len(inn) == 10:
            if company_type.lower() in ['legal', 'ul']:
                return 'legal'

            opf = company_data.get('opf', {})
            opf_code = opf.get('code', '')
            opf_full = opf.get('full', '').lower()

            legal_opf_codes = ['12247', '12267', '12300', '13000', '14000']
            legal_opf_keywords = ['общество', 'акционерное', 'товарищество', 'производственный']

            if opf_code in legal_opf_codes:
                return 'legal'

            if any(keyword in opf_full for keyword in legal_opf_keywords):
                return 'legal'

            # По умолчанию считаем юридическим лицом
            return 'legal'

        else:
            # По умолчанию для неопределенных случаев
            return 'legal'

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel_company_search')
    def handle_cancel_company_search(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Удаляем сообщение с кнопками
        bot.delete_message(chat_id, call.message.message_id)

        # Возвращаем к выбору компании
        approved_companies = db.fetch_all(
            "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
        )

        bot.send_message(
            chat_id,
            "Выберите компанию или выполните поиск:",
            reply_markup=get_company_selection_keyboard(approved_companies)
        )
        set_user_state(user_id, 'waiting_for_company_selection')

        bot.answer_callback_query(call.id, "Поиск отменен")


    def determine_final_role(selected_role, company_id):
        if selected_role == "logist":
            if company_id == 1:
                return "logist"
            else:
                return "external_logist"
        elif selected_role == "executor":
            if company_id == 1:
                return "executor"
            else:
                return "external_executor"
        elif selected_role == "admin":
            if company_id == 1:
                return "admin"
            else:
                return "external_admin"
        else:
            return selected_role

    def continue_user_registration(bot, db, user_id, chat_id, final_role, company_id):
        logger.info(f"Продолжение регистрации пользователя {user_id}, роль: {final_role}, компания: {company_id}")

        # Сохраняем пользователя в БД с временным статусом
        existing_user = db.fetch_one('SELECT * FROM users WHERE telegram_id = ?', (user_id,))

        if existing_user:
            logger.info(f"Обновление существующего пользователя {user_id}")
            db.execute_query(
                "UPDATE users SET role = ?, company_id = ? WHERE telegram_id = ?",
                (final_role, company_id, user_id)
            )
        else:
            logger.info(f"Создание нового пользователя {user_id}")
            from_user = bot.get_chat(user_id)
            db.execute_query(
                "INSERT INTO users (telegram_id, first_name, username, role, company_id) VALUES (?, ?, ?, ?, ?)",
                (user_id, from_user.first_name, from_user.username, final_role, company_id)
            )

        # Переходим к вводу личных данных
        bot.send_message(
            chat_id,
            '✅ Отлично!\n'
            'Теперь перейдем к основному этапу регистрации.\n'
            'Введите ваше имя:',
            reply_markup=get_back_keyboard()
        )
        set_user_state(user_id, 'waiting_for_first_name')

    # Обработчики для личных данных

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_first_name')
    def handle_first_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        if user_id not in user_data:
            user_data[user_id] = {}


        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к выбору компании")
            # Возврат к выбору компании
            approved_companies = db.fetch_all(
                "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
            )
            companies_text = "🏢 **Выберите вашу компанию из списка:**\n\n"
            for company in approved_companies:
                companies_text += f"• {company['name']}\n"

            bot.send_message(
                chat_id,
                companies_text,
                reply_markup=get_company_selection_keyboard(approved_companies)
            )
            set_user_state(user_id, 'waiting_for_company_selection')
            return

        # Простая валидация имени
        if not message.text.isalpha() or len(message.text) < 2:
            logger.warning(f"Пользователь {user_id}: неверный формат имени: {message.text}")
            bot.send_message(chat_id,
                             "❌ Имя должно содержать только буквы и быть не короче 2 символов. Попробуйте еще раз:")
            return

        # Сохраняем имя
        user_data[user_id]['first_name'] = message.text.strip()
        logger.info(f'Пользователь {user_id}: имя "{message.text.strip()}" записано')

        bot.send_message(
            chat_id,
            "📝 Введите вашу фамилию:",
            reply_markup=get_back_keyboard()
        )
        set_user_state(user_id, 'waiting_for_last_name')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_last_name', 'waiting_for_log_last_name'])
    def handle_last_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к вводу имени")
            bot.send_message(chat_id, "📝 Введите ваше имя:", reply_markup=get_back_keyboard())
            set_user_state(user_id, 'waiting_for_first_name')
            return

        if not message.text.isalpha() or len(message.text) < 2:
            logger.warning(f"Пользователь {user_id}: неверный формат фамилии: {message.text}")
            bot.send_message(chat_id,
                             "❌ Фамилия должна содержать только буквы и быть не короче 2 символов. Попробуйте еще раз:")
            return

        user_data[user_id]['last_name'] = message.text.strip()
        logger.info(f'Пользователь {user_id}: фамилия "{message.text.strip()}" записана')

        if get_user_state(user_id) == 'waiting_for_log_last_name':
            user = db.get_user_by_telegram_id(user_id)
            user_data[user_id]['first_name'] = user['first_name']
            user_data[user_id]['final_role'] = user['role']
            user_data[user_id]['email'] = user['email']
            user_data[user_id]['phone'] = user['phone']
            user_data[user_id]['company_id'] = user['company_id']
            company = db.get_company_by_id(user['company_id'])
            user_data[user_id]['company_name'] = company['name']
            set_user_state(user_id, 'waiting_for_log_patronymic')
        else:
            set_user_state(user_id, 'waiting_for_patronymic')
        bot.send_message(
            chat_id,
            "📝 Введите ваше отчество (если есть):",
            reply_markup=get_skip_back_keyboard()
        )


    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_patronymic', 'waiting_for_log_patronymic'])
    def handle_patronymic(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к вводу фамилии")
            bot.send_message(chat_id, "📝 Введите вашу фамилию:", reply_markup=get_back_keyboard())
            if get_user_state(user_id) == 'waiting_for_log_patronymic':
                set_user_state(user_id, 'waiting_for_log_last_name')
            else:
                set_user_state(user_id, 'waiting_for_last_name')
            return

        if message.text == "⏭️ Пропустить":
            logger.info(f"Пользователь {user_id}: пропустил ввод отчества")
            user_data[user_id]['patronymic'] = ''
        else:
            if not message.text.isalpha() or len(message.text) < 2:
                logger.warning(f"Пользователь {user_id}: неверный формат отчества: {message.text}")
                bot.send_message(chat_id,
                                 "❌ Отчество должно содержать только буквы. Попробуйте еще раз или пропустите:")
                return
            user_data[user_id]['patronymic'] = message.text.strip()
            logger.info(f'Пользователь {user_id}: отчество "{message.text.strip()}" записано')

        if get_user_state(user_id) == "waiting_for_log_patronymic":
            logger.info(f"Пользователь {user_id}: переход к дате рождения")
            bot.send_message(
                chat_id,
                "🎂 Введите вашу дату рождения (в формате ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_log_birth_date')
        else:
            logger.info(f"Пользователь {user_id}: переход к телефону")
            bot.send_message(
                chat_id,
                "📞 Введите ваш номер телефона (в формате +7XXXXXXXXXX или 8XXXXXXXXXX):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_phone')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_phone')
    def handle_phone(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к вводу отчества")
            bot.send_message(chat_id, "📝 Введите ваше отчество:", reply_markup=get_skip_back_keyboard())
            set_user_state(user_id, 'waiting_for_patronymic')
            return

        # Валидация номера телефона
        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            logger.warning(f"Пользователь {user_id}: неверный формат телефона: {message.text}")
            bot.send_message(chat_id,
                             "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:")
            return

        user_data[user_id]['phone'] = phone
        logger.info(f'Пользователь {user_id}: телефон "{phone}" записан')

        bot.send_message(
            chat_id,
            "📧 Введите ваш email адрес:",
            reply_markup=get_back_keyboard()
        )
        set_user_state(user_id, 'waiting_for_email')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_email')
    def handle_email(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к вводу телефона")
            bot.send_message(chat_id, "📞 Введите ваш номер телефона:", reply_markup=get_back_keyboard())
            set_user_state(user_id, 'waiting_for_phone')
            return

        # Валидация email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', message.text):
            logger.warning(f"Пользователь {user_id}: неверный формат email: {message.text}")
            bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
            return

        user_data[user_id]['email'] = message.text.strip()
        logger.info(f'Пользователь {user_id}: email "{message.text.strip()}" записан')

        bot.send_message(
            chat_id,
            "🎂 Введите вашу дату рождения (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_back_keyboard()
        )
        set_user_state(user_id, 'waiting_for_birth_date')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_birth_date', 'waiting_for_log_birth_date'])
    def handle_birth_date(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к вводу email")
            bot.send_message(chat_id, "📧 Введите ваш email адрес:", reply_markup=get_back_keyboard())
            set_user_state(user_id, 'waiting_for_email')
            return

        # Валидация даты рождения
        try:
            birth_date = datetime.strptime(message.text, '%d.%m.%Y')
            # Проверка, что дата не в будущем и не слишком старая
            if birth_date > datetime.now():
                logger.warning(f"Пользователь {user_id}: дата рождения в будущем: {message.text}")
                bot.send_message(chat_id, "❌ Дата рождения не может быть в будущем. Попробуйте еще раз:")
                return
            if birth_date.year < 1900:
                logger.warning(f"Пользователь {user_id}: дата рождения слишком старая: {message.text}")
                bot.send_message(chat_id, "❌ Дата рождения не может быть раньше 1900 года. Попробуйте еще раз:")
                return
        except ValueError:
            logger.warning(f"Пользователь {user_id}: неверный формат даты рождения: {message.text}")
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        user_data[user_id]['birth_date'] = message.text
        logger.info(f'Пользователь {user_id}: дата рождения "{message.text}" записана')

        if get_user_state(user_id) == 'waiting_for_log_birth_date':
            set_user_state(user_id, 'waiting_for_log_passport_series')
        else:
            set_user_state(user_id, 'waiting_for_passport_series')
        bot.send_message(
            chat_id,
            "📘 Введите серию паспорта (4 цифры):",
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_passport_series', 'waiting_for_log_passport_series'])
    def handle_passport_series(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к дате рождения")
            bot.send_message(chat_id, "🎂 Введите вашу дату рождения:", reply_markup=get_back_keyboard())
            if get_user_state(user_id) == 'waiting_for_log_passport_series':
                set_user_state(user_id, 'waiting_for_log_birth_date')
            else:
                set_user_state(user_id, 'waiting_for_birth_date')
            return

        # Валидация серии паспорта (4 цифры)
        if not (message.text.isdigit() and len(message.text) == 4):
            logger.warning(f"Пользователь {user_id}: неверный формат серии паспорта: {message.text}")
            bot.send_message(chat_id, "❌ Серия паспорта должна состоять из 4 цифр. Попробуйте еще раз:")
            return

        user_data[user_id]['passport_series'] = message.text
        logger.info(f'Пользователь {user_id}: серия паспорта "{message.text}" записана')

        if get_user_state(user_id) == 'waiting_for_log_passport_series':
            set_user_state(user_id, 'waiting_for_log_passport_number')
        else:
            set_user_state(user_id, 'waiting_for_passport_number')
        bot.send_message(
            chat_id,
            "📘 Введите номер паспорта (6 цифр):",
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_passport_number', 'waiting_for_log_passport_number'])
    def handle_passport_number(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к серии паспорта")
            bot.send_message(chat_id, "📘 Введите серию паспорта:", reply_markup=get_back_keyboard())
            if get_user_state(user_id) == 'waiting_for_log_passport_number':
                set_user_state(user_id, 'waiting_for_log_passport_series')
            else:
                set_user_state(user_id, 'waiting_for_passport_series')
            return

        # Валидация номера паспорта (6 цифр)
        if not (message.text.isdigit() and len(message.text) == 6):
            logger.warning(f"Пользователь {user_id}: неверный формат номера паспорта: {message.text}")
            bot.send_message(chat_id, "❌ Номер паспорта должен состоять из 6 цифр. Попробуйте еще раз:")
            return

        user_data[user_id]['passport_number'] = message.text
        logger.info(f'Пользователь {user_id}: номер паспорта "{message.text}" записан')

        if get_user_state(user_id) == 'waiting_for_log_passport_number':
            set_user_state(user_id, 'waiting_for_log_passport_issue_date')
        else:
            set_user_state(user_id, 'waiting_for_passport_issue_date')
        bot.send_message(
            chat_id,
            "📅 Введите дату выдачи паспорта (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_passport_issue_date', 'waiting_for_log_passport_issue_date'])
    def handle_passport_issue_date(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к номеру паспорта")
            bot.send_message(chat_id, "📘 Введите номер паспорта:", reply_markup=get_back_keyboard())
            if get_user_state(user_id) == 'waiting_for_log_passport_issue_date':
                set_user_state(user_id, 'waiting_for_log_passport_number')
            else:
                set_user_state(user_id, 'waiting_for_passport_number')
            return

        # Валидация даты выдачи паспорта
        try:
            issue_date = datetime.strptime(message.text, '%d.%m.%Y')
            # Проверка, что дата не в будущем и не слишком старая
            if issue_date > datetime.now():
                logger.warning(f"Пользователь {user_id}: дата выдачи паспорта в будущем: {message.text}")
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
            if issue_date.year < 1990:
                logger.warning(f"Пользователь {user_id}: дата выдачи паспорта слишком старая: {message.text}")
                bot.send_message(chat_id, "❌ Дата выдачи не может быть раньше 1990 года. Попробуйте еще раз:")
                return
        except ValueError:
            logger.warning(f"Пользователь {user_id}: неверный формат даты выдачи паспорта: {message.text}")
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        user_data[user_id]['passport_issue_date'] = message.text
        logger.info(f'Пользователь {user_id}: дата выдачи паспорта "{message.text}" записана')

        if get_user_state(user_id) == 'waiting_for_log_passport_issue_date':
            set_user_state(user_id, 'waiting_for_log_registration_address')
        else:
            set_user_state(user_id, 'waiting_for_registration_address')
        bot.send_message(
            chat_id,
            "📍 Введите адрес регистрации",
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_registration_address', 'waiting_for_log_registration_address'])
    def handle_registration_address(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)
        if 'final_role' not in user_data[user_id]:
            user_data[user_id]['final_role'] = user['role']

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к дате выдачи паспорта")
            bot.send_message(chat_id, "📅 Введите дату выдачи паспорта:", reply_markup=get_back_keyboard())
            if get_user_state(user_id) == 'waiting_for_log_registration_address':
                set_user_state(user_id, 'waiting_for_log_issue_date')
            else:
                set_user_state(user_id, 'waiting_for_passport_issue_date')
            return
        if message.text == "⏭️ Пропустить":
            logger.info(f"Пользователь {user_id}: пропустил адрес регистрации")
            user_data[user_id]['registration_address'] = 'Не указан'
        else:
            user_data[user_id]['registration_address'] = message.text.strip()
            logger.info(f"Пользователь {user_id}: адрес регистрации: {user_data[user_id]['registration_address']}")
        if get_user_state(user_id) == 'waiting_for_log_registration_address':
            if user_data[user_id]['final_role'] in ['external_admin', 'external_logist', 'external_executor']:
                bot.send_message(
                    chat_id,
                    '🔢 Введите ваш код АТИ:',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_log_ati_code')
            else:
                bot.send_message(
                    chat_id,
                    '🔢 Введите ваш код АТИ:',
                    reply_markup=get_skip_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_log_ati_code')
        else:
            if user_data[user_id]['final_role'] in ['external_admin', 'external_logist', 'external_executor']:
                bot.send_message(
                    chat_id,
                    '🔢 Введите ваш код АТИ:',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_log_ati_code')
            else:
                bot.send_message(
                    chat_id,
                    '🔢 Введите ваш код АТИ:',
                    reply_markup=get_skip_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_log_ati_code')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_ati_code', 'waiting_for_log_ati_code'])
    def handle_ati_code(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к адресу регистрации")
            bot.send_message(chat_id, "📍 Введите адрес регистрации", reply_markup=get_back_keyboard())
            if get_user_state(user_id) == 'waiting_for_log_ati_code':
                set_user_state(user_id, 'waiting_for_log_registration_address')
            else:
                set_user_state(user_id, 'waiting_for_registration_address')
            return

        if message.text == "⏭️ Пропустить":
            logger.info(f"Пользователь {user_id}: пропустил код АТИ")
            user_data[user_id]['ati_code'] = "Не указан"
        else:
            # Валидация кода АТИ (должен быть числом)
            if not message.text.isdigit():
                logger.warning(f"Пользователь {user_id}: неверный формат кода АТИ: {message.text}")
                bot.send_message(chat_id, "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз или пропустите:")
                return
            user_data[user_id]['ati_code'] = message.text.strip()
            logger.info(f'Пользователь {user_id}: код АТИ "{message.text.strip()}" записан')

        # Переходим к загрузке фото документов
        logger.info(f"Пользователь {user_id}: переход к загрузке фото документов")
        if get_user_state(user_id) == 'waiting_for_log_ati_code':
            set_user_state(user_id, 'waiting_for_log_passport_main_photo')
            bot.send_message(
                chat_id,
                "📷 **Загрузка документов**\n\n"
                "Сначала отправьте фото 1 страницы паспорта (с фото и данными):",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            set_user_state(user_id, 'waiting_for_passport_main_photo')
            bot.send_message(
                chat_id,
                "📷 **Загрузка документов**\n\n"
                "Сначала отправьте фото 1 страницы паспорта (с фото и данными):",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'waiting_for_passport_photos_upload' and message.text)
    def handle_passport_photos_text(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⏭️ Пропустить":
            logger.info(f"Пользователь {user_id}: пропустил загрузку документов")
            # Показываем сводку без документов
            show_user_summary(bot, user_id, chat_id)
        elif message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к коду АТИ")
            bot.send_message(
                chat_id,
                "🔢 Введите ваш код АТИ (если есть, или пропустите):",
                reply_markup=get_skip_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_ati_code')


    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'waiting_for_passport_main_photo' and message.text)
    def handle_passport_main_photo_text(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к коду АТИ")
            bot.send_message(
                chat_id,
                "🔢 Введите ваш код АТИ (если есть, или пропустите):",
                reply_markup=get_skip_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_ati_code')
        elif message.text == "⏭️ Пропустить":
            logger.info(f"Пользователь {user_id}: пропустил загрузку документов")
            # Показываем сводку без документов
            show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(content_types=['photo'],
                         func=lambda message: get_user_state(
                             message.from_user.id) in ['waiting_for_passport_main_photo', 'waiting_for_end_passport_main_photo', 'waiting_for_log_passport_main_photo'])
    def handle_passport_main_photo(message):
        """Обработка фото 1 страницы паспорта"""
        logger.info('Запущен обработчик фото 1 страницы паспорта')
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Получаем текущие данные пользователя

        photo_info[user_id] = {}

        if not photo_info[user_id] and'passport_photos' not in photo_info[user_id]:
            photo_info[user_id]['passport_photos'] = {
                'main': None,
                'registration': None
            }

        if message.photo:
            file_id = message.photo[-1].file_id

            # Удаляем старые фото 1 страницы паспорта перед сохранением новых
            delete_old_passport_photos(user_id, 'passport_main')

            # Сохраняем основное фото
            success = save_and_compress_photos(bot, file_id, user_id, 'passport_main')

            if success:
                photo_info[user_id]['passport_photos']['main'] = True
                logger.info(f"Пользователь {user_id}: фото 1 страницы паспорта сохранено (старые фото удалены)")


                if get_user_state(user_id) == 'waiting_for_end_passport_main_photo':
                    set_user_state(user_id, 'waiting_for_end_passport_registration_photo')
                    bot.send_message(
                        chat_id,
                        "✅ Фото 1 страницы паспорта успешно сохранено!\n\n"
                        "Теперь отправьте фото страницы с пропиской:",
                        reply_markup=ReplyKeyboardRemove()
                    )
                elif get_user_state(user_id) == 'waiting_for_log_passport_main_photo':
                    set_user_state(user_id, 'waiting_for_log_passport_registration_photo')
                    bot.send_message(
                        chat_id,
                        "✅ Фото 1 страницы паспорта успешно сохранено!\n\n"
                        "Теперь отправьте фото страницы с пропиской:",
                        reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    set_user_state(user_id, 'waiting_for_passport_registration_photo')
                    bot.send_message(
                        chat_id,
                        "✅ Фото 1 страницы паспорта успешно сохранено!\n\n"
                        "Теперь отправьте фото страницы с пропиской:",
                        reply_markup=get_back_keyboard()
                    )
            else:
                bot.send_message(
                    chat_id,
                    "❌ Ошибка при сохранении фото. Попробуйте отправить фото еще раз:",
                    reply_markup=get_back_keyboard()
                )

    @bot.message_handler(content_types=['photo'],
                         func=lambda message: get_user_state(
                             message.from_user.id) in ['waiting_for_passport_registration_photo', 'waiting_for_end_passport_registration_photo', 'waiting_for_log_passport_registration_photo'])
    def handle_passport_registration_photo(message):
        """Обработка фото страницы с пропиской"""
        logger.info('Запущен обработчик фото прописки')
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к загрузке 1 страницы паспорта")
            bot.send_message(
                chat_id,
                "📷 Отправьте фото 1 страницы паспорта (с фото и данными):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_passport_main_photo')
            return

        if message.photo:
            file_id = message.photo[-1].file_id

            # Удаляем старые фото прописки перед сохранением новых
            delete_old_passport_photos(user_id, 'passport_registration')

            # Сохраняем фото прописки
            success = save_and_compress_photos(bot, file_id, user_id, 'passport_registration')

            if success:
                photo_info[user_id]['passport_photos']['registration'] = True
                logger.info(f"Пользователь {user_id}: фото прописки сохранено (старые фото удалены)")

                bot.send_message(
                    chat_id,
                    "✅ Фото страницы с пропиской успешно сохранено!\n\n"
                    "Переходим к проверке данных...",
                    reply_markup=ReplyKeyboardRemove()
                )
                # Показываем сводку с документами
                show_user_summary(bot, user_id, chat_id)
            else:
                bot.send_message(
                    chat_id,
                    "❌ Ошибка при сохранении фото. Попробуйте отправить фото еще раз:",
                    reply_markup=get_back_keyboard()
                )

    def delete_old_passport_photos(user_id, photo_type):
        """Удаляет старые фотографии указанного типа для пользователя"""
        try:
            user_folder = f"data/documents/users/{user_id}"
            if not os.path.exists(user_folder):
                return

            # Ищем файлы с указанным типом
            pattern = f"{photo_type}_*.jpg"
            old_files = glob.glob(os.path.join(user_folder, pattern))

            # Удаляем файлы из файловой системы
            for file_path in old_files:
                try:
                    os.remove(file_path)
                    logger.info(f"Удален старый файл: {file_path}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла {file_path}: {e}")

            # Удаляем записи из базы данных
            db.execute_query(
                "DELETE FROM user_documents WHERE user_id = ? AND document_type = ?",
                (user_id, photo_type)
            )
            logger.info(f"Удалены старые записи документов типа '{photo_type}' для пользователя {user_id}")

        except Exception as e:
            logger.error(f"Ошибка при удалении старых фотографий для пользователя {user_id}: {e}")

    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'waiting_for_passport_registration_photo' and message.text)
    def handle_passport_registration_text(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к загрузке 1 страницы паспорта")
            bot.send_message(
                chat_id,
                "📷 Отправьте фото 1 страницы паспорта (с фото и данными):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_passport_main_photo')

    @bot.message_handler(content_types=['photo'],
                         func=lambda message: get_user_state(
                             message.from_user.id) == 'waiting_for_passport_photos_upload')
    def handle_passport_photos(message):
        """Обработка фото документов с защитой от множественных срабатываний"""

        # Проверяем media_group_id для групповых отправок фото
        media_group_id = message.media_group_id

        if media_group_id:
            # Если эта группа медиа уже обрабатывалась - пропускаем
            if processed_media_groups[media_group_id]:
                logger.debug(f"Пропускаем повторную обработку media_group: {media_group_id}")
                return

            # Помечаем группу как обработанную
            processed_media_groups[media_group_id] = True
            logger.debug(f"Обрабатываем media_group: {media_group_id}")

        logger.info('Запущен обработчик фото')
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Получаем текущие данные пользователя
        if user_id not in photo_info:
            photo_info[user_id] = {}

        if 'passport_photos' not in photo_info[user_id]:
            photo_info[user_id]['passport_photos'] = {
                'main': None,
                'registration': None
            }

        # Очищаем старые записи media_group (старше 5 минут)
        cleanup_old_media_groups()

        # Обрабатываем фото
        if message.photo:
            photos_count = len(message.photo)
            logger.info(f"Пользователь {user_id}: получено фото: {photos_count} шт.")

            if photos_count >= 2:
                # Пользователь отправил оба фото сразу
                file_id_main = message.photo[-2].file_id  # Предпоследнее фото
                file_id_registration = message.photo[-1].file_id  # Последнее фото

                # Сохраняем оба фото за один вызов
                success_results = save_and_compress_photos(
                    bot,
                    [file_id_main, file_id_registration],
                    user_id,
                    ['passport_main', 'passport_registration']
                )
                logger.info(f"Результаты сохранения: {success_results}")

                if all(success_results):
                    photo_info[user_id]['passport_photos']['main'] = True
                    photo_info[user_id]['passport_photos']['registration'] = True

                    bot.send_message(
                        chat_id,
                        "✅ Оба фото паспорта успешно сохранены!\n\n"
                        "Переходим к проверке данных...",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    # Показываем сводку с документами
                    show_user_summary(bot, user_id, chat_id)
                else:
                    bot.send_message(
                        chat_id,
                        "❌ Ошибка при сохранении фото. Попробуйте отправить фото еще раз.",
                        reply_markup=get_skip_back_keyboard()
                    )

            else:
                # Пользователь отправил одно фото
                file_id = message.photo[-1].file_id

                # Определяем, какое фото еще не загружено
                if photo_info[user_id]['passport_photos']['main'] is None:
                    # Сохраняем как основное фото
                    success = save_and_compress_photos(bot, file_id, user_id, 'passport_main')
                    if success:
                        photo_info[user_id]['passport_photos']['main'] = True

                        # Проверяем, не загружены ли уже оба фото
                        if (photo_info[user_id]['passport_photos']['main'] and
                                photo_info[user_id]['passport_photos']['registration']):
                            bot.send_message(
                                chat_id,
                                "✅ Оба фото паспорта успешно сохранены!\n\n"
                                "Переходим к проверке данных...",
                                reply_markup=ReplyKeyboardRemove()
                            )
                            show_user_summary(bot, user_id, chat_id)
                        else:
                            bot.send_message(
                                chat_id,
                                "✅ Фото 1 страницы паспорта сохранено.\n\n"
                                "Теперь отправьте фото страницы с пропиской:",
                                reply_markup=get_back_keyboard()
                            )
                    else:
                        bot.send_message(chat_id, "❌ Ошибка при сохранении фото. Попробуйте еще раз.")

                elif photo_info[user_id]['passport_photos']['registration'] is None:
                    # Сохраняем как фото прописки
                    success = save_and_compress_photos(bot, file_id, user_id, 'passport_registration')
                    if success:
                        photo_info[user_id]['passport_photos']['registration'] = True

                        # Проверяем, не загружены ли уже оба фото
                        if (photo_info[user_id]['passport_photos']['main'] and
                                photo_info[user_id]['passport_photos']['registration']):
                            bot.send_message(
                                chat_id,
                                "✅ Оба фото паспорта успешно сохранены!\n\n"
                                "Переходим к проверке данных...",
                                reply_markup=ReplyKeyboardRemove()
                            )
                            show_user_summary(bot, user_id, chat_id)
                        else:
                            bot.send_message(
                                chat_id,
                                "✅ Фото страницы с пропиской сохранено.\n\n"
                                "Теперь отправьте фото 1 страницы паспорта:",
                                reply_markup=get_back_keyboard()
                            )
                    else:
                        bot.send_message(chat_id, "❌ Ошибка при сохранении фото. Попробуйте еще раз.")
                else:
                    # Оба фото уже загружены
                    bot.send_message(
                        chat_id,
                        "✅ Оба фото уже загружены. Переходим к проверке данных...",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    show_user_summary(bot, user_id, chat_id)

    def cleanup_old_media_groups():
        """Очистка старых записей о media_group (старше 5 минут)"""
        current_time = time.time()
        # Создаем копию ключей для безопасного удаления
        keys_to_remove = [key for key, timestamp in processed_media_groups.items()
                          if current_time - timestamp > 300]  # 5 минут

        for key in keys_to_remove:
            del processed_media_groups[key]
        if keys_to_remove:
            logger.debug(f"Очищено {len(keys_to_remove)} старых media_group записей")

    def save_and_compress_photos(bot, file_ids, user_id, document_types):
        # Поддерживаем как одиночные значения, так и списки
        if not isinstance(file_ids, list):
            file_ids = [file_ids]
        if not isinstance(document_types, list):
            document_types = [document_types]

        # Если типов документов меньше чем файлов, дополняем последним типом
        if len(document_types) < len(file_ids):
            last_type = document_types[-1] if document_types else 'document'
            document_types.extend([last_type] * (len(file_ids) - len(document_types)))

        results = []

        for i, (file_id, doc_type) in enumerate(zip(file_ids, document_types)):
            try:
                # Получаем информацию о файле
                file_info = bot.get_file(file_id)
                downloaded_file = bot.download_file(file_info.file_path)

                # Создаем папку для документов пользователя
                user_folder = f"data/documents/users/{user_id}"
                os.makedirs(user_folder, exist_ok=True)

                # Генерируем уникальное имя файла для сжатого изображения
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{doc_type}_{timestamp}_{i}_compressed.jpg"
                compressed_path = os.path.join(user_folder, filename)

                # Сжимаем фото и сохраняем сразу в сжатом виде
                success = compress_and_save_image(downloaded_file, compressed_path)

                if success:
                    # Сохраняем информацию в базу данных (только сжатый файл)
                    db.add_user_document(user_id, doc_type, compressed_path)
                    results.append(True)
                    logger.info(f"Фото {doc_type} успешно сохранено для пользователя {user_id}: {compressed_path}")
                else:
                    results.append(False)
                    logger.error(f"Ошибка при сохранении фото {doc_type} для пользователя {user_id}")

            except Exception as e:
                logger.error(f"Ошибка при сохранении фото {i} ({doc_type}) для пользователя {user_id}: {e}")
                results.append(False)

        # Возвращаем одиночный результат для одного файла, список для нескольких
        return results[0] if len(results) == 1 else results

    def compress_and_save_image(downloaded_file, output_path, quality=20, max_width=800):
        """Сжимает изображение из бинарных данных и сохраняет в файл"""
        try:
            # Открываем изображение из бинарных данных
            image = Image.open(io.BytesIO(downloaded_file))

            # Конвертируем в RGB если нужно
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')

            # Уменьшаем размер изображения (максимальная ширина 800px)
            if image.width > max_width:
                ratio = max_width / image.width
                new_height = int(image.height * ratio)
                image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)

            # Сохраняем с сжатием
            image.save(output_path, 'JPEG', optimize=True, quality=quality)
            logger.debug(f"Изображение успешно сжато и сохранено: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при сжатии изображения: {e}")
            return False

    def show_user_summary(bot, user_id, chat_id):
        """Показывает сводку данных пользователя с возможностью редактирования"""
        logger.info(f"Показана сводка данных для пользователя {user_id}")
        if get_user_state(user_id) == 'waiting_for_end_passport_registration_photo':
            data = db.get_user_by_telegram_id(user_id)
            data['company_name'] = db.get_company_by_user_id(user_id)['name']
        else:
            data = user_data[user_id]

        # Добавляем информацию о документах
        documents_text = ""
        passport_photos = photo_info[user_id].get('passport_photos', {})
        if passport_photos.get('main') and passport_photos.get('registration'):
            documents_text = "\n📎 **Документы:** оба фото паспорта загружены"
        elif passport_photos.get('main') or passport_photos.get('registration'):
            documents_text = "\n📎 **Документы:** частично загружены"
        else:
            documents_text = "\n📎 **Документы:** не загружены"

        user = db.get_user_by_telegram_id(user_id)
        company = db.get_company_by_id(user['company_id'])

        summary_text = f"""
        📋 **Проверьте введенные данные:**
        
        👤 **Личные данные:**
        **ФИО:** {data['last_name']} {data.get('first_name', user['first_name'])} {data.get('patronymic', user.get('patronymic', ''))}
        **Телефон:** {data.get('phone', user['phone'])}
        **Email:** {data.get('email', user['email'])}
        **Дата рождения:** {data.get('birth_date', user.get('birth_date','Не указана'))}
        
        📘 **Паспортные данные:**
        **Серия:** {data.get('passport_series', 'Не указана')}
        **Номер:** {data.get('passport_number', 'Не указана')}
        **Дата выдачи:** {data.get('passport_issue_date', 'Не указана')}
        
        🔢 **Код АТИ:** {data.get('ati_code', 'Не указан')}
        {documents_text}
        
        🏢 **Компания:** {data.get('company_name', company['name'])}
        💼 **Роль:** {role_names.get(data.get('role', user['role']), 'Не указана')}
        
        Если все данные верны, нажмите "✅ Подтвердить регистрацию".
        Если нужно что-то изменить, выберите поле для редактирования.
        """

        # Создаем клавиатуру для редактирования
        keyboard = get_edit_user_keyboard()
        if get_user_state(user_id) == 'waiting_for_end_passport_registration_photo':
            set_user_state(user_id, 'waiting_for_end_user_confirmation')
        else:
            set_user_state(user_id, 'waiting_for_user_confirmation')
        bot.send_message(
            chat_id,
            summary_text,
            reply_markup=keyboard
        )

    def get_edit_user_keyboard():
        """Клавиатура для редактирования данных пользователя"""
        from telebot.types import ReplyKeyboardMarkup, KeyboardButton

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

        # Основные данные
        keyboard.row(KeyboardButton("✏️ Редактировать ФИО"), KeyboardButton("✏️ Редактировать контакты"))
        keyboard.row(KeyboardButton("✏️ Редактировать паспорт"), KeyboardButton("✏️ Редактировать код АТИ"))
        keyboard.row(KeyboardButton("📷 Редактировать документы"))

        # Подтверждение
        keyboard.row(KeyboardButton("✅ Подтвердить регистрацию"))

        return keyboard

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_user_confirmation' or get_user_state(message.from_user.id) == 'waiting_for_end_user_confirmation')
    def handle_user_confirmation(message):
        user_id = message.from_user.id
        chat_id = message.chat.id


        if message.text == "✅ Подтвердить регистрацию":
            logger.info(f"Пользователь {user_id} подтвердил регистрацию")
            complete_user_registration(bot, db, user_id, chat_id)

        # Обработка кнопок редактирования
        elif message.text == "✏️ Редактировать ФИО":
            logger.info(f"Пользователь {user_id} редактирует ФИО")
            set_user_state(user_id, 'editing_user_name')
            bot.send_message(
                chat_id,
                "Выберите что редактировать:",
                reply_markup=get_edit_name_keyboard()
            )

        elif message.text == "✏️ Редактировать контакты":
            logger.info(f"Пользователь {user_id} редактирует контакты")
            set_user_state(user_id, 'editing_user_contacts')
            bot.send_message(
                chat_id,
                "Выберите что редактировать:",
                reply_markup=get_edit_contacts_keyboard()
            )

        elif message.text == "✏️ Редактировать паспорт":
            logger.info(f"Пользователь {user_id} редактирует паспорт")
            set_user_state(user_id, 'editing_user_passport')
            bot.send_message(
                chat_id,
                "Выберите что редактировать:",
                reply_markup=get_edit_passport_keyboard()
            )

        elif message.text == "✏️ Редактировать код АТИ":
            logger.info(f"Пользователь {user_id} редактирует код АТИ")
            set_user_state(user_id, 'editing_user_ati')
            bot.send_message(
                chat_id,
                f"Текущий код АТИ: {user_data[user_id].get('ati_code', 'Не указан')}\nВведите новый код АТИ:",
                reply_markup=get_back_keyboard()
            )

        elif message.text == "📷 Редактировать документы":
            logger.info(f"Пользователь {user_id} редактирует документы")
            bot.send_message(
                chat_id,
                "📷 **Загрузка документов**\n\n"
                "Сначала отправьте фото 1 страницы паспорта (с фото и данными):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_passport_main_photo')

    # Обработчики редактирования ФИО
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_user_name')
    def handle_editing_user_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            logger.info(f"Пользователь {user_id}: возврат к сводке")
            show_user_summary(bot, user_id, chat_id)
            return
        elif message.text == "👤 Редактировать имя":
            logger.info(f"Пользователь {user_id} редактирует имя")
            set_user_state(user_id, 'editing_first_name')
            bot.send_message(
                chat_id,
                f"Текущее имя: {user_data[user_id]['first_name']}\nВведите новое имя:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "👤 Редактировать фамилию":
            logger.info(f"Пользователь {user_id} редактирует фамилию")
            set_user_state(user_id, 'editing_last_name')
            bot.send_message(
                chat_id,
                f"Текущая фамилия: {user_data[user_id]['last_name']}\nВведите новую фамилию:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "👤 Редактировать отчество":
            logger.info(f"Пользователь {user_id} редактирует отчество")
            set_user_state(user_id, 'editing_patronymic')
            bot.send_message(
                chat_id,
                f"Текущее отчество: {user_data[user_id].get('patronymic', 'Не указано')}\nВведите новое отчество:",
                reply_markup=get_skip_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_first_name')
    def handle_editing_first_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_name')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_name_keyboard())
            return

        if not message.text.isalpha() or len(message.text) < 2:
            logger.warning(f"Пользователь {user_id}: неверный формат имени при редактировании: {message.text}")
            bot.send_message(chat_id,
                             "❌ Имя должно содержать только буквы и быть не короче 2 символов. Попробуйте еще раз:")
            return

        user_data[user_id]['first_name'] = message.text.strip()
        logger.info(f"Пользователь {user_id}: имя обновлено на '{message.text.strip()}'")
        show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_last_name')
    def handle_editing_last_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_name')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_name_keyboard())
            return

        if not message.text.isalpha() or len(message.text) < 2:
            logger.warning(f"Пользователь {user_id}: неверный формат фамилии при редактировании: {message.text}")
            bot.send_message(chat_id,
                             "❌ Фамилия должна содержать только буквы и быть не короче 2 символов. Попробуйте еще раз:")
            return

        user_data[user_id]['last_name'] = message.text.strip()
        logger.info(f"Пользователь {user_id}: фамилия обновлена на '{message.text.strip()}'")
        show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_patronymic')
    def handle_editing_patronymic(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_user_summary(bot, user_id, chat_id)
            return

        if not message.text.isalpha() or len(message.text) < 2:
            logger.warning(f"Пользователь {user_id}: неверный формат отчества при редактировании: {message.text}")
            bot.send_message(chat_id,
                             "❌ Отчество должно содержать только буквы. Попробуйте еще раз или пропустите:")
            return
        user_data[user_id]['patronymic'] = message.text.strip()
        logger.info(f"Пользователь {user_id}: отчество обновлено на '{message.text.strip()}'")
        show_user_summary(bot, user_id, chat_id)

    # Обработчики редактирования контактов
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_user_contacts')
    def handle_editing_user_contacts(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_user_summary(bot, user_id, chat_id)
            return
        elif message.text == "📞 Редактировать телефон":
            logger.info(f"Пользователь {user_id} редактирует телефон")
            set_user_state(user_id, 'editing_phone')
            bot.send_message(
                chat_id,
                f"Текущий телефон: {user_data[user_id]['phone']}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📧 Редактировать email":
            logger.info(f"Пользователь {user_id} редактирует email")
            set_user_state(user_id, 'editing_email')
            bot.send_message(
                chat_id,
                f"Текущий email: {user_data[user_id]['email']}\nВведите новый email:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "🎂 Редактировать дату рождения":
            logger.info(f"Пользователь {user_id} редактирует дату рождения")
            set_user_state(user_id, 'editing_birth_date')
            bot.send_message(
                chat_id,
                f"Текущая дата рождения: {user_data[user_id].get('birth_date', 'Не указана')}\nВведите новую дату рождения:",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_phone')
    def handle_editing_phone(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_contacts')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_contacts_keyboard())
            return

        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            logger.warning(f"Пользователь {user_id}: неверный формат телефона при редактировании: {message.text}")
            bot.send_message(chat_id,
                             "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:")
            return

        user_data[user_id]['phone'] = phone
        logger.info(f"Пользователь {user_id}: телефон обновлен на '{phone}'")
        show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_email')
    def handle_editing_email(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_contacts')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_contacts_keyboard())
            return

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', message.text):
            logger.warning(f"Пользователь {user_id}: неверный формат email при редактировании: {message.text}")
            bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
            return

        user_data[user_id]['email'] = message.text.strip()
        logger.info(f"Пользователь {user_id}: email обновлен на '{message.text.strip()}'")
        show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_birth_date')
    def handle_editing_birth_date(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_contacts')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_contacts_keyboard())
            return

        try:
            birth_date = datetime.strptime(message.text, '%d.%m.%Y')
            if birth_date > datetime.now():
                logger.warning(f"Пользователь {user_id}: дата рождения в будущем при редактировании: {message.text}")
                bot.send_message(chat_id, "❌ Дата рождения не может быть в будущем. Попробуйте еще раз:")
                return
            if birth_date.year < 1900:
                logger.warning(
                    f"Пользователь {user_id}: дата рождения слишком старая при редактировании: {message.text}")
                bot.send_message(chat_id, "❌ Дата рождения не может быть раньше 1900 года. Попробуйте еще раз:")
                return
        except ValueError:
            logger.warning(f"Пользователь {user_id}: неверный формат даты рождения при редактировании: {message.text}")
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        user_data[user_id]['birth_date'] = message.text
        logger.info(f"Пользователь {user_id}: дата рождения обновлена на '{message.text}'")
        show_user_summary(bot, user_id, chat_id)

    # Обработчики редактирования паспорта
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_user_passport')
    def handle_editing_user_passport(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_user_summary(bot, user_id, chat_id)
            return
        elif message.text == "📘 Редактировать серию паспорта":
            logger.info(f"Пользователь {user_id} редактирует серию паспорта")
            set_user_state(user_id, 'editing_passport_series')
            bot.send_message(
                chat_id,
                f"Текущая серия: {user_data[user_id].get('passport_series', 'Не указана')}\nВведите новую серию:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📘 Редактировать номер паспорта":
            logger.info(f"Пользователь {user_id} редактирует номер паспорта")
            set_user_state(user_id, 'editing_passport_number')
            bot.send_message(
                chat_id,
                f"Текущий номер: {user_data[user_id].get('passport_number', 'Не указан')}\nВведите новый номер:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📅 Редактировать дату выдачи":
            logger.info(f"Пользователь {user_id} редактирует дату выдачи паспорта")
            set_user_state(user_id, 'editing_passport_issue_date')
            bot.send_message(
                chat_id,
                f"Текущая дата выдачи: {user_data[user_id].get('passport_issue_date', 'Не указана')}\nВведите новую дату выдачи:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📍 Редактировать адрес регистрации":
            logger.info(f"Пользователь {user_id} редактирует адрес регистрации")
            set_user_state(user_id, 'editing_registration_address')
            bot.send_message(
                chat_id,
                f"Текущий адрес регистрации: {user_data[user_id].get('registration_address', 'Не указан')}\nВведите новый адрес регистрации:",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_passport_series')
    def handle_editing_passport_series(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_passport')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_passport_keyboard())
            return

        if not (message.text.isdigit() and len(message.text) == 4):
            logger.warning(f"Пользователь {user_id}: неверный формат серии паспорта при редактировании: {message.text}")
            bot.send_message(chat_id, "❌ Серия паспорта должна состоять из 4 цифр. Попробуйте еще раз:")
            return

        user_data[user_id]['passport_series'] = message.text
        logger.info(f"Пользователь {user_id}: серия паспорта обновлена на '{message.text}'")
        show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_passport_number')
    def handle_editing_passport_number(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_passport')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_passport_keyboard())
            return

        if not (message.text.isdigit() and len(message.text) == 6):
            logger.warning(
                f"Пользователь {user_id}: неверный формат номера паспорта при редактировании: {message.text}")
            bot.send_message(chat_id, "❌ Номер паспорта должен состоять из 6 цифр. Попробуйте еще раз:")
            return

        user_data[user_id]['passport_number'] = message.text
        logger.info(f"Пользователь {user_id}: номер паспорта обновлен на '{message.text}'")
        show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_passport_issue_date')
    def handle_editing_passport_issue_date(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_passport')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_passport_keyboard())
            return

        try:
            issue_date = datetime.strptime(message.text, '%d.%m.%Y')
            if issue_date > datetime.now():
                logger.warning(f"Пользователь {user_id}: дата выдачи в будущем при редактировании: {message.text}")
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
            if issue_date.year < 1990:
                logger.warning(f"Пользователь {user_id}: дата выдачи слишком старая при редактировании: {message.text}")
                bot.send_message(chat_id, "❌ Дата выдачи не может быть раньше 1990 года. Попробуйте еще раз:")
                return
        except ValueError:
            logger.warning(f"Пользователь {user_id}: неверный формат даты выдачи при редактировании: {message.text}")
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        user_data[user_id]['passport_issue_date'] = message.text
        logger.info(f"Пользователь {user_id}: дата выдачи паспорта обновлена на '{message.text}'")
        show_user_summary(bot, user_id, chat_id)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_editing_registration_address')
    def handle_editing_registration_address(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_user_passport')
            bot.send_message(chat_id, "Выберите что редактировать:", reply_markup=get_edit_passport_keyboard())
            return

        user_data[user_id]['registration_address'] = message.text.strip()
        logger.info(f"Пользователь {user_id}: адрес регистрации обновлен на '{message.text.strip()}'")
        show_user_summary(bot, user_id, chat_id)

    # Обработчик редактирования кода АТИ
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_user_ati')
    def handle_editing_user_ati(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_user_summary(bot, user_id, chat_id)
            return

        if not message.text.isdigit():
            logger.warning(f"Пользователь {user_id}: неверный формат кода АТИ при редактировании: {message.text}")
            bot.send_message(chat_id, "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз или пропустите:")
            return
        user_data[user_id]['ati_code'] = message.text.strip()
        logger.info(f"Пользователь {user_id}: код АТИ обновлен на '{message.text.strip()}'")
        show_user_summary(bot, user_id, chat_id)

    def complete_user_registration(bot, db, user_id, chat_id):
        """Завершение регистрации пользователя и отправка заявки администратору"""
        user = db.get_user_by_telegram_id(user_id)
        # Обновляем пользователя в БД
        if get_user_state(user_id) == 'waiting_for_end_user_confirmation':
            data = db.get_user_by_telegram_id(user_id)
            data['company_name'] = db.get_company_by_user_id(user_id)['name']
        else:
            data = user_data[user_id]
        try:


            subscription_manager = SubscriptionManager(db)

            if user.get('status') == 'active':
                logger.info(f"Обновление данных существующего активного пользователя {user_id}")
                db.update_user(
                    user_id,
                    username=data.get('username'),
                    first_name=data.get('first_name', user['first_name']),
                    last_name=data['last_name'],
                    patronymic=data.get('patronymic'),
                    phone=data.get('phone', user['phone']),
                    email=data.get('email', user['email']),
                    birth_date=data.get('birth_date'),
                    passport_series=data.get('passport_series'),
                    passport_number=data.get('passport_number'),
                    registration_address=data.get('registration_address'),
                    passport_issue_date=data.get('passport_issue_date'),
                    ati_code=data.get('ati_code'),
                    accepted_terms=data.get('accepted_terms')
                )

                # Создаем пробную подписку для внешних пользователей
                if user['role'] in ['external_admin', 'external_logist', 'external_executor']:
                    logger.info(f"Создание пробной подписки для пользователя {user_id}, роль: {user['role']}")
                    subscription_manager.create_trial_subscription(user_id, user['role'])
                success = db.fetch_one('select * from subscriptions where telegram_id = ?', (user_id,))
                if success:
                    print('Подписка успешно активирована')
                else:
                    print('Не удалось создать подписку')

                if user_id in user_states:
                    del user_states[user_id]
                if user_id in user_data:
                    del user_data[user_id]

            else:
                logger.info(f"Завершение регистрации нового пользователя {user_id}")
                db.update_user(
                    user_id,
                    first_name=data.get('first_name'),
                    last_name=data['last_name'],
                    patronymic=data.get('patronymic'),
                    phone=data.get('phone'),
                    email=data.get('email'),
                    birth_date=data.get('birth_date'),
                    passport_series=data.get('passport_series'),
                    passport_number=data.get('passport_number'),
                    registration_address=data.get('registration_address'),
                    passport_issue_date=data.get('passport_issue_date'),
                    created_by=user_id,
                    ati_code=data.get('ati_code'),
                    status='pending',
                    accepted_terms=data.get('accepted_terms')
                )
            bot.send_message(
                chat_id,
                "✅ Ваши данные отправлены на модерацию!\n\n"
                "После проверки администратором вы получите уведомление и сможете пользоваться системой.",
                reply_markup=ReplyKeyboardRemove()
            )


            logger.info(f"Пользователь {user_id}: регистрация завершена, отправлена на модерацию")

        except Exception as e:
            logger.error(f"Ошибка при завершении регистрации пользователя {user_id}: {e}", exc_info=True)
            bot.send_message(
                chat_id,
                "❌ Произошла ошибка при завершении регистрации. Пожалуйста, попробуйте позже."
            )

        send_user_to_admins(bot, db, user_id)
        company_name = db.get_company_by_user_id(user_id)['name']
        email_subject = """ Модерация нового пользователя"""
        email_message = f"""
                               НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ ПОЛЬЗОВАТЕЛЯ

                                Данные пользователя: 
                                ФИО: {data['last_name']} {data['first_name']} {data.get('patronymic', '')}

                                Телефон: {data.get('phone', 'Не указан')}
                                Email: {data.get('email', 'Не указан')}
                                Дата рождения: {data.get('birth_date', 'Не указана')}

                                Код АТИ: {user.get('ati_code', 'Не указан')}

                               Компания: {company_name}
                               Роль: {role_names.get(user.get('role'), user.get('role', 'Не указана'))}

                               Дата подачи заявки: {user.get('created_at', 'Не указана')}

                               Откройте чат с Телеграм-ботом, чтобы принять или отклонить регистрацию.
                               """
        admins = db.fetch_all("SELECT email FROM users WHERE role = 'admin' and status = 'active'")
        if not admins:
            logger.warning("Не найдены администраторы для отправки заявки")
            return

        for admin in admins:
            admin_email = admin.get('email')

            # Проверяем что email существует, не пустой и не None
            if not admin_email or not isinstance(admin_email, str) or not admin_email.strip():
                logger.warning(f"Пропускаем администратора с некорректным email: {admin}")
                continue

            # Убираем пробелы
            if not admin_email or not isinstance(admin_email, str) or not admin_email.strip():
                logger.warning(f"Пропускаем администратора с некорректным email: {admin}")
                continue

            try:
                # Отправляем email
                send_email_notification(email_subject, email_message, admin_email)
                logger.info(f"Email отправлен администратору: {admin_email}")
            except Exception as e:
                logger.error(f"Ошибка при отправке email администратору {admin_email}: {e}")
                # Продолжаем отправку остальным администраторам
                continue

        logger.info(f"Отправка email администраторам завершена. Обработано: {len(admins)} записей")



    def send_user_to_admins(bot, db, user_id):
        """Отправляет заявку на регистрацию пользователя всем администраторам"""
        try:
            # Получаем данные пользователя
            user = db.fetch_one("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
            if not user:
                logger.warning(f"Пользователь {user_id} не найден для отправки администраторам")
                return

            # Получаем компанию пользователя
            company = db.fetch_one("SELECT name FROM companies WHERE id = ?", (user['company_id'],))
            company_name = company['name'] if company else "Не указана"

            # Получаем всех администраторов
            admins = db.fetch_all("SELECT telegram_id FROM users WHERE role = 'admin' and status='active'")

            if not admins:
                logger.warning("Не найдены администраторы для отправки заявки")
                return

            # Формируем сообщение для администратора
            message_text = format_user_moderation_message(user, company_name)

            # Отправляем сообщение всем администраторам
            for admin in admins:
                try:
                    send_photo(bot, admin['telegram_id'], user_id)
                    bot.send_message(
                        admin['telegram_id'],
                        message_text,
                        reply_markup=get_approve_reject_user_keyboard(user_id),
                    )
                    add_pending_moderation('user_registration', user_id)
                    set_user_state(user_id, '')
                    logger.info(f"Заявка пользователя {user_id} отправлена администратору {admin['telegram_id']}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения администратору {admin['telegram_id']}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при отправке заявки администраторам для пользователя {user_id}: {e}", exc_info=True)

    def send_photo(bot, chat_id, user_id, max_photos=5):
        folder_path = f"data/documents/users/{user_id}"

        try:
            if not os.path.exists(folder_path):
                bot.send_message(chat_id, "❌ Папка с фотографиями не найдена")
                return False

            # Исправляем расширения файлов
            photo_extensions = ('*.jpg', '*.jpeg', '*.png')
            all_photos = []

            for extension in photo_extensions:
                all_photos.extend(glob.glob(os.path.join(folder_path, extension)))

            if not all_photos:
                bot.send_message(chat_id, "❌ Нет фотографий")
                # set_user_state(chat_id, 'waiting_for_user_photos_action')
                return False

            all_photos.sort()
            photos_to_send = all_photos[:max_photos]
            media_group = []

            # Сначала читаем все файлы и сохраняем их содержимое
            photo_data = []
            for photo_path in photos_to_send:
                try:
                    with open(photo_path, 'rb') as photo_file:
                        # Сохраняем данные файла в память
                        photo_data.append(photo_file.read())
                except Exception as e:
                    logger.error(f"Ошибка при чтении файла {photo_path}: {e}")
                    continue

            # Теперь создаем медиагруппу с сохраненными данными
            for i, data in enumerate(photo_data):
                if i == 0:
                    media_group.append(
                        InputMediaPhoto(
                            data,
                            caption=f"📸 Фото паспорта ({len(photo_data)} шт.)"
                        )
                    )
                else:
                    media_group.append(InputMediaPhoto(data))

            if not media_group:
                bot.send_message(chat_id, "❌ Не удалось загрузить ни одной фотографии")
                return False

            # Отправляем медиагруппу
            bot.send_media_group(chat_id, media_group)
            # set_user_state(user_id, 'waiting_for_user_photos_action')

            # Если фото больше, чем можно отправить в одном альбоме
            if len(all_photos) > max_photos:
                remaining = len(all_photos) - max_photos
                bot.send_message(
                    chat_id,
                    f"📋 Показано {max_photos} из {len(all_photos)} фотографий\n"
                    f"Остальные {remaining} фото не поместились в один альбом"
                )

            return True

        except Exception as e:
            error_msg = f"❌ Ошибка при отправке фотографий: {str(e)}"
            bot.send_message(chat_id, error_msg)
            logger.error(f"Ошибка при отправке фотографий пользователя {user_id}: {e}", exc_info=True)
            return False

    def format_user_moderation_message(user, company_name):
        """Форматирует сообщение для модерации пользователя"""

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
👔 **Роль:** {role_names.get(user.get('role'), user.get('role', 'Не указана'))}

⏰ **Дата подачи заявки:** {user.get('created_at', 'Не указана')}

Выберите действие:
"""


def set_user_state(user_id, state):
    """Установить состояние пользователя"""
    user_states[user_id] = state
    logger.info(f"Пользователь {user_id}: новое состояние = {state}")


def get_user_state(user_id):
    """Получить состояние пользователя"""
    return user_states.get(user_id, '')