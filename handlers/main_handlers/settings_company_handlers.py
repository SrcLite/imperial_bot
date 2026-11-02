import glob
import io
import os
from datetime import datetime
from PIL import Image, ImageOps
from telebot.types import ReplyKeyboardRemove, InputMediaPhoto

from handlers.admin_handlers.pending_moderations_handlers import add_pending_moderation
from handlers.registration_handlers.registration_user_handlers import get_user_state, set_user_state
from keyboards.admin_keyboards import get_back_keyboard, get_approve_reject_company_edit_keyboard, \
    get_approve_reject_delete_company_photos_keyboard, get_id_request_approve_reject_company_edit_keyboard
from keyboards.main_menus import get_main_menu
from keyboards.settings_keyboard import get_company_edit_keyboard, get_settings_company_selection_keyboard, \
    get_setting_keyboard, get_company_type_keyboard, get_tax_system_keyboard, get_settings_company_keyboard, \
    get_edit_company_photo_keyboard
from utils.dicts import company_type_map, company_fields_display
from utils.email_sender import send_email_notification
edit_requests = {}
role_names = {
    'admin': '👑 Администратор',
    'logist': '📊 Логист',
    'executor': '🚛 Перевозчик',
    'external_admin': '👑 Администратор',
    'external_logist': '📊 Логист',
    'external_executor': '🚛 Перевозчик'
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

user_data = {}


def register_settings_company_handlers(bot, db):


    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_settings_company_action')
    def handle_settings_company_handler(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)
        if not user and user['status'] != 'active':
            bot.send_message(
                user_id,
                "❌ У вас нет прав для использования бота, так как вы не зарегистрированы, либо ваш аккаунт не подтвердил ГЛАВНЫЙ АДМИНИСТРАТОР!\n",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        user_data[user_id] = {
            'company_id': None
        }
        companies = db.fetch_all('select name from companies')
        if message.text == '🏢 Моя компания':
            set_user_state(user_id, 'waiting_for_user_own_company')
            user_company = db.get_company_by_user_id(user_id)
            user_data[user_id]['company_id'] = user_company['id']
            if user_company:
                bank_details = db.get_company_bank_details(user_company['id'])
                show_company_info(bot, user_id, user_company, bank_details)
            else:
                bot.send_message(user_id, "❌ Компания не найдена")
        elif message.text == '📋 Список компаний':
            set_user_state(user_id, 'waiting_for_settings_company_selection')
            companies = db.get_approved_companies()
            user_info = db.get_user_role(user_id)
            role = user_info['role'] if user_info else None
            if companies:
                companies_text = "🏢 **Выберите компанию из списка:**\n\n"
                for company in companies:
                    companies_text += f"{company['name']}\n"

                bot.send_message(
                    user_id,
                    companies_text,
                    reply_markup=get_settings_company_selection_keyboard(companies)
                )
            else:
                bot.send_message(
                    user_id,
                    '❌**В системе пока нет зарегистрированных компаний**',
                    reply_markup=get_settings_company_keyboard(role)
                )
        elif message.text == '⬅️ Назад':
            set_user_state(user_id, 'waiting_for_settings_action')
            user_info = db.get_user_role(user_id)
            role = user_info['role'] if user_info else None
            bot.send_message(chat_id, "Выберите действие:", reply_markup=get_setting_keyboard(role))

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_settings_company_selection')
    def handle_settings_company_selection(message):
        user_id = message.from_user.id

        if message.text == '⬅️ Назад':
            set_user_state(user_id, 'waiting_for_settings_company_action')
            user_info = db.get_user_role(user_id)
            role = user_info['role'] if user_info else None
            bot.send_message(
                user_id,
                '🏢 Управление компаниями\n'
                'Выберите действие:',
                reply_markup=get_settings_company_keyboard(role))
        elif message.text == '🔍Поиск по ИНН':
            bot.send_message(
                user_id,
                'Введите ИНН компании, которую хотите выбрать:',
                reply_markup=ReplyKeyboardRemove()
            )
            set_user_state(user_id, 'waiting_for_settings_company_inn')
            return
        else:
            # Убираем эмодзи из названия компании
            company_name = message.text[2:] if message.text.startswith("🏢 ") else message.text

            company = db.fetch_one(
                "SELECT * FROM companies WHERE name = ? AND status = 'approved'",
                (company_name,)
            )

            if not company:
                bot.send_message(user_id, "❌ Компания не найдена. Пожалуйста, выберите компанию из списка.")
                return
            user_data[user_id]['company_id'] = company['id']
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_settings_company_inn')
    def handle_company_inn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company_data = db.get_approved_company_by_inn(message.text)
        if not company_data:
            bot.send_message(chat_id, '❌ Компания с таким ИНН не найдена.')
            return

        bot.send_message(
            chat_id,
            'Выберите компанию:',
            reply_markup=get_settings_company_selection_keyboard(company_data)
        )
        set_user_state(user_id, 'waiting_for_settings_company_selection')

    def show_company_info(bot, user_id, company, bank_details):
        message_text = f"""
        🏢 **{company['name']}**
        📋 Тип: {type_to_text_map.get(company['company_type'], company['company_type'])}
        
        🔢 **Реквизиты:**
        • ИНН: {company.get('inn', 'Не указан')}
        • КПП: {company.get('kpp', 'Не указан')}  
        • ОГРН: {company.get('ogrn', 'Не указан')}
        
        👤 **Руководитель:**
        • {company.get('management_name', '')}
        
        📍 **Адрес:** {company.get('address', 'Не указан')}
        
        📞 **Контакты:**
        • Телефон: {company.get('contact_phone', 'Не указан')}
        • Email: {company.get('contact_email', 'Не указан')}
        
        🏦 **Банковские реквизиты:**
        • БИК: {bank_details.get('bik', 'Не указан') if bank_details else 'Не указан'}
        • Расчетный счет: {bank_details.get('payment_account', 'Не указан') if bank_details else 'Не указан'}
        • Корреспондентский счет: {bank_details.get('correspondent_account', 'Не указан') if bank_details else 'Не указан'}
        • ОКПО: {bank_details.get('okpo', 'Не указан') if bank_details else 'Не указан'}
        
        📝 **Примечание:** {company.get('note', 'Не указано')}
        """
        bot.send_message(user_id, message_text, reply_markup=get_company_edit_keyboard())
        set_user_state(user_id, 'waiting_for_settings_company_edit_action')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_settings_company_edit_action')
    def handle_company_action(message):
        user_id = message.from_user.id
        user = db.get_user_by_telegram_id(user_id)
        role = user['role']
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        bank_details = db.get_company_bank_details(company['id'])

        if message.text == "⬅️ Назад":
            set_user_state(user_id, "waiting_for_settings_company_action")
            bot.send_message(
                chat_id,
                '🏢 Управление компаниями\n'
                'Выберите действие:',
                reply_markup=get_settings_company_keyboard(role)
            )
            return

        elif message.text == "🏢 Название компании":
            bot.send_message(
                user_id,
                f"Текущее название: {company['name']}\nВведите новое название:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_name')

        elif message.text == "📋 Тип компании":
            current_type = type_to_text_map.get(company['company_type'])
            bot.send_message(
                user_id,
                f"Текущий тип: {current_type}\nВыберите новый тип:",
                reply_markup=get_company_type_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_type')

        elif message.text == "🔢 ИНН":
            bot.send_message(
                user_id,
                f"Текущий ИНН: {company.get('inn', 'Не указан')}\nВведите новый ИНН:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_inn')

        elif message.text == "🔢 КПП":
            bot.send_message(
                user_id,
                f"Текущий КПП: {company.get('kpp', 'Не указан')}\nВведите новый КПП:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_kpp')

        elif message.text == "🔢 ОГРН":
            bot.send_message(
                user_id,
                f"Текущий ОГРН: {company.get('ogrn', 'Не указан')}\nВведите новый ОГРН:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_ogrn')

        elif message.text == "👤 ФИО директора":
            bot.send_message(
                user_id,
                f"Текущее ФИО директора: {company.get('management_name', 'Не указано')}\nВведите новое ФИО:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_management_name')

        elif message.text == "📍 Юридический адрес":
            bot.send_message(
                user_id,
                f"Текущий адрес: {company.get('address', 'Не указан')}\nВведите новый адрес:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_legal_address')

        elif message.text == "📞 Контактный телефон":
            bot.send_message(
                user_id,
                f"Текущий телефон: {company.get('contact_phone', 'Не указан')}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_phone')

        elif message.text == "📧 Контактный email":
            bot.send_message(
                user_id,
                f"Текущий email: {company.get('contact_email', 'Не указан')}\nВведите новый email:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_email')

        elif message.text == "💼 Система налогообложения":
            current_tax = tax_to_text_map.get(company.get('tax_system', ''), 'Не указана')
            bot.send_message(
                user_id,
                f"Текущая система: {current_tax}\nВыберите новую систему:",
                reply_markup=get_tax_system_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_tax')

        elif message.text == "📝 Примечание":
            bot.send_message(
                user_id,
                f"Текущее примечание: {company.get('note', 'Не указано')}\nВведите новое примечание:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_note')

        elif message.text == "💰 БИК":
            current_bik = bank_details.get('bik', 'Не указано') if bank_details else 'Не указано'
            bot.send_message(
                user_id,
                f"Текущий БИК: {current_bik}\nВведите новый БИК:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_bik')

        elif message.text == "💰 Расчетный счёт":
            current_payment = bank_details.get('payment_account', 'Не указано') if bank_details else 'Не указано'
            bot.send_message(
                user_id,
                f"Текущий расчетный счет: {current_payment}\nВведите новый расчетный счет:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_payment_account')

        elif message.text == "💰 Корреспондентский счёт":
            current_correspondent = bank_details.get('correspondent_account',
                                                     'Не указано') if bank_details else 'Не указано'
            bot.send_message(
                user_id,
                f"Текущий корреспондентский счет: {current_correspondent}\nВведите новый корреспондентский счет:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_correspondent_account')

        elif message.text == "💰 ОКПО":
            current_okpo = bank_details.get('okpo', 'Не указано') if bank_details else 'Не указано'
            bot.send_message(
                user_id,
                f"Текущий ОКПО: {current_okpo}\nВведите новый ОКПО:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, f'settings_editing_company_okpo')
        elif message.text == "📷 Показать фото":
            set_user_state(user_id, 'waiting_for_settings_company_photos')
            send_photo(bot, chat_id, user_id, user_data[user_id]['company_id'])

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_settings_company_photos_action')
    def handle_user_photos_action(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None

        if message.text == '🔄 Добавить фотографии':
            set_user_state(user_id, 'waiting_for_edit_company_photos')
            bot.send_message(chat_id, "Прикрепите фото следующих документов:\n"
                                        "• Свидетельство о регистрации (ОГРН)\n"
                                        "• Свидетельство о постановке на налоговый учет (ИНН)\n"
                                        "• Устав компании (первая страница)\n\n",
                             reply_markup=get_back_keyboard())
        elif message.text == "📁 Удалить все фото":
            if role == 'admin':
                # Админы могут удалять сразу
                delete_all_photos(user_id, chat_id)
            else:
                # Обычные пользователи отправляют заявку на удаление
                send_delete_photos_request(bot, db, user_id, chat_id)
        elif message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_settings_company_photos_action')
            company = db.get_company_by_id(user_data[user_id]["company_id"])
            bank_details = db.get_company_bank_details(user_data[user_id]["company_id"])
            show_company_info(bot, user_id, company, bank_details)

    def send_photo(bot, chat_id, user_id, company_id, max_photos=5):
        folder_path = f"data/documents/companies/{company_id}"

        try:
            if not os.path.exists(folder_path):
                bot.send_message(chat_id, "❌ Папка с фотографиями не найдена")
                set_user_state(user_id, 'waiting_for_settings_company_edit_action')
                return False

            # Исправляем расширения файлов
            photo_extensions = ('*.jpg', '*.jpeg', '*.png')
            all_photos = []

            for extension in photo_extensions:
                all_photos.extend(glob.glob(os.path.join(folder_path, extension)))

            if not all_photos:
                bot.send_message(chat_id, "❌ В папке нет фотографий", reply_markup=get_edit_company_photo_keyboard())
                set_user_state(chat_id, 'waiting_for_settings_company_photos_action')
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
                    print(f"Ошибка при чтении файла {photo_path}: {e}")
                    continue

            # Теперь создаем медиагруппу с сохраненными данными
            for i, data in enumerate(photo_data):
                if i == 0:
                    media_group.append(
                        InputMediaPhoto(
                            data,
                            caption=f"📸 Фото компании ({len(photo_data)} шт.)"
                        )
                    )
                else:
                    media_group.append(InputMediaPhoto(data))

            if not media_group:
                bot.send_message(chat_id, "❌ Не удалось загрузить ни одной фотографии")
                return False

            # Отправляем медиагруппу
            bot.send_media_group(chat_id, media_group)
            bot.send_message(chat_id, "Выберите действие из меню:", reply_markup=get_edit_company_photo_keyboard())
            set_user_state(user_id, 'waiting_for_settings_company_photos_action')

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
            print(f"Ошибка: {e}")
            return False

    def send_delete_photos_request(bot, db, user_id, chat_id):
        """Отправляет заявку на удаление фото администраторам"""
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        user = db.get_user_by_telegram_id(user_id)
        admins = db.get_all_admins()

        email_subject = f"📝 Заявка на удаление фотографий"
        email_message = f"""
                   Компания: {company.get('name', '')}
                   ИНН:** {company.get('inn', '')}
                   **Директор:** {company.get('management_name','')} {company.get('management_name', '')}

                   **Запросил удаление всех своих фотографий: {user.get('username','')}**

                   **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

                   Откройте чат с Телеграм-ботом, чтобы принять или отклонить заявку.
                   """
        for admin in admins:
            admin_email = admin.get('email')

            bot.send_message(
                admin['telegram_id'],
                f"""
                   📝 **ЗАЯВКА НА УДАЛЕНИЕ ФОТОГРАФИЙ**

                   👤 **Компания:** {company.get('name', '')}
                   🆔 **ИНН:** {company.get('inn', '')}
                   🏢 **Директор:** {company.get('management_name','')} {company.get('management_name', '')}

                   ❗️ **Запросил удаление всех своих фотографий: {user.get('username','')}**

                   ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

                   Для подтверждения или отклонения используйте кнопки ниже.
                   """,
                reply_markup=get_approve_reject_delete_company_photos_keyboard(user_data[user_id]['company_id'], user_id)
            )
            add_pending_moderation('company_photos_delete', user_id)

            # Проверяем что email существует, не пустой и не None
            if not admin_email or not isinstance(admin_email, str) or not admin_email.strip():
                print(f"Пропускаем администратора с некорректным email: {admin}")
                continue

            # Убираем пробелы
            if not admin_email or not isinstance(admin_email, str) or not admin_email.strip():
                print(f"Пропускаем администратора с некорректным email: {admin}")
                continue

            try:
                # Отправляем email
                send_email_notification(email_subject, email_message, admin_email)
                print(f"Email отправлен администратору: {admin_email}")
            except Exception as e:
                print(f"Ошибка при отправке email администратору {admin_email}: {e}")
                # Продолжаем отправку остальным администраторам
                continue

        bot.send_message(
            chat_id,
            '🕐 **Запрос на удаление всех фотографий компании отправлен администратору на проверку.**\n'
            '**Вам придет уведомление о результате проверки.**',
            reply_markup=get_edit_company_photo_keyboard()
        )
        set_user_state(user_id, 'waiting_for_settings_company_photos_action')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_company_photos')
    def handle_edit_company_photos(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Проверяем, есть ли фото в папке
        folder_path = f"data/documents/companies/{user_data[user_id]['company_id']}"

        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)

        # Получаем список существующих фото
        existing_photos = glob.glob(os.path.join(folder_path, "*.jpg")) + glob.glob(
            os.path.join(folder_path, "*.jpeg")) + glob.glob(os.path.join(folder_path, "*.png"))

        if not existing_photos:
            # Если в папке нет фото, предлагаем добавить
            bot.send_message(
                chat_id,
                "📷 В вашей папке нет фотографий компании.\n\n"
                "Прикрепите фото следующих документов:\n"
                "• Свидетельство о регистрации (ОГРН)\n"
                "• Свидетельство о постановке на налоговый учет (ИНН)\n"
                "• Устав компании (первая страница)\n\n",
                reply_markup=get_edit_company_photo_keyboard()
            )
            return

        # Показываем текущие фото и предлагаем действия
        send_photo(bot, chat_id, user_id, user_data[user_id]['company_id'])

    @bot.message_handler(content_types=['photo', 'text'],
                         func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_company_photos')
    def handle_new_photos(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        folder_path = f"data/documents/companies/{user_data[user_id]['company_id']}"

        if message.text == '⬅️ Назад':
            bot.send_message(chat_id, 'Выберите действие:', reply_markup=get_edit_company_photo_keyboard())

        # Создаем папку если не существует
        os.makedirs(folder_path, exist_ok=True)

        # Получаем список существующих фото
        existing_photos = glob.glob(os.path.join(folder_path, "*.jpg")) + glob.glob(
            os.path.join(folder_path, "*.jpeg")) + glob.glob(os.path.join(folder_path, "*.png"))

        # Обрабатываем новое фото
        if message.photo:
            try:
                # Получаем информацию о файле
                file_info = bot.get_file(message.photo[-1].file_id)
                downloaded_file = bot.download_file(file_info.file_path)

                # Сжимаем фото
                compressed_data = compress_image(downloaded_file, max_width=800, quality=20)

                if compressed_data is None:
                    bot.send_message(chat_id, "❌ Ошибка при обработке фото")
                    return

                # Генерируем уникальное имя файла
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"company_photo_{timestamp}.jpg"

                # Сохраняем сжатый файл
                success, compressed_size = save_compressed_photo(compressed_data, folder_path, filename)

                if success:
                    # Отправляем информацию о сжатии
                    bot.send_message(
                        chat_id,
                        f"✅ Фото успешно добавлено!\n"
                    )
                else:
                    bot.send_message(chat_id, "✅ Фото успешно добавлено!")

            except Exception as e:
                bot.send_message(chat_id, f"❌ Ошибка при сохранении фото: {str(e)}")
                print(f"Ошибка при сохранении фото: {e}")

    def delete_all_photos(user_id, chat_id):
        folder_path = f"data/documents/companies/{user_data[user_id]['company_id']}"

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

        bot.send_message(
            chat_id,
            f"🗑️ Удалено {deleted_count} фотографий.\n\n"
            "Теперь вы можете добавить новые фото документов.",
            reply_markup=get_edit_company_photo_keyboard()
        )
        set_user_state(user_id, 'waiting_for_settings_company_photos_action')

    def compress_image(image_data, max_width=800, quality=20):
        """
        Сжимает изображение до указанного размера и качества
        """
        try:
            # Открываем изображение из бинарных данных
            image = Image.open(io.BytesIO(image_data))

            # Автоматически поворачиваем изображение согласно EXIF данным
            image = ImageOps.exif_transpose(image)

            # Конвертируем в RGB если нужно (для PNG с прозрачностью)
            if image.mode in ('RGBA', 'P', 'LA'):
                # Создаем белый фон
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')

            # Уменьшаем размер если нужно
            if image.width > max_width:
                ratio = max_width / image.width
                new_height = int(image.height * ratio)
                image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)

            # Сохраняем в буфер с сжатием
            output_buffer = io.BytesIO()
            image.save(output_buffer, 'JPEG', optimize=True, quality=quality)
            compressed_data = output_buffer.getvalue()
            output_buffer.close()

            return compressed_data

        except Exception as e:
            print(f"Ошибка при сжатии изображения: {e}")
            return None

    def save_compressed_photo(compressed_data, folder_path, filename):
        """
        Сохраняет сжатое изображение в файл
        """
        try:
            # Создаем папку если не существует
            os.makedirs(folder_path, exist_ok=True)

            # Сохраняем сжатое изображение
            file_path = os.path.join(folder_path, filename)
            with open(file_path, 'wb') as f:
                f.write(compressed_data)

            # Получаем размер файла для информации
            file_size = os.path.getsize(file_path) / 1024  # в KB

            print(f"✅ Фото сохранено: {filename} ({file_size:.1f} KB)")
            return True, file_size

        except Exception as e:
            print(f"Ошибка при сохранении сжатого фото: {e}")
            return False, 0

    # Обработчики для полей компании
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_name')
    def handle_editing_company_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        companies_names = db.get_companies_names()
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'name'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_settings_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        for company_name in companies_names:
            if message.text.strip() == company_name:
                bot.send_message(
                    user_id,
                    '❌ Компания с таким именем уже существует\n'
                    'Введите другое название:',
                    reply_markup = get_back_keyboard()
                )
                set_user_state(user_id, 'settings_editing_company_name')

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Название должно содержать минимум 2 символа. Введите название:")
            return

        query = 'UPDATE companies SET name = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company['name']

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_type')
    def handle_editing_company_type(message):
        user_id = message.from_user.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'company_type'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        new_value = type_to_data_map.get(message.text.strip())
        if not new_value:
            bot.send_message(user_id, "❌ Пожалуйста, выберите тип из предложенных вариантов")
            return

        query = 'UPDATE companies SET company_type = ? WHERE id = ?'
        old_value = company['company_type']

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_inn')
    def handle_editing_company_inn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'inn'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        query = 'UPDATE companies SET inn = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('inn', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_kpp')
    def handle_editing_company_kpp(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'kpp'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        query = 'UPDATE companies SET kpp = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('kpp', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_ogrn')
    def handle_editing_company_ogrn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'ogrn'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        query = 'UPDATE companies SET ogrn = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('ogrn', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_management_name')
    def handle_editing_company_management_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'management_name'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Имя не может быть пустым. Введите имя:")
            return

        query = 'UPDATE companies SET management_name = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('management_name', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    # @bot.message_handler(
    #     func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_director_last')
    # def handle_editing_company_director_last(message):
    #     user_id = message.from_user.id
    #     chat_id = message.chat.id
    #     company = db.get_company_by_id(user_data[user_id]['company_id'])
    #     if not company:
    #         bot.send_message(user_id, "❌ Компания не найдена")
    #         return
    #
    #     parameter = 'director_last_name'
    #
    #     if message.text == "⬅️ Назад":
    #         set_user_state(user_id, 'waiting_for_company_edit_action')
    #         bank_details = db.get_company_bank_details(company['id'])
    #         show_company_info(bot, user_id, company, bank_details)
    #         return
    #
    #     if not message.text.strip():
    #         bot.send_message(chat_id, "❌ Фамилия не может быть пустой. Введите фамилию:")
    #         return
    #
    #     query = 'UPDATE companies SET director_last_name = ? WHERE id = ?'
    #     new_value = message.text.strip()
    #     old_value = company.get('director_last_name', '')
    #
    #     edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_legal_address')
    def handle_editing_company_legal_address(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'address'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Адрес не может быть пустым. Введите адрес:")
            return

        query = 'UPDATE companies SET address = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('address', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_phone')
    def handle_editing_company_phone(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'contact_phone'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        query = 'UPDATE companies SET contact_phone = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('contact_phone', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_email')
    def handle_editing_company_email(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'contact_email'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        query = 'UPDATE companies SET contact_email = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('contact_email', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_tax')
    def handle_editing_company_tax(message):
        user_id = message.from_user.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'tax_system'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        new_value = tax_to_data_map.get(message.text.strip())
        if not new_value:
            bot.send_message(user_id, "❌ Пожалуйста, выберите систему налогообложения из предложенных вариантов")
            return

        query = 'UPDATE companies SET tax_system = ? WHERE id = ?'
        old_value = company.get('tax_system', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_note')
    def handle_editing_company_note(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        parameter = 'note'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            bank_details = db.get_company_bank_details(company['id'])
            show_company_info(bot, user_id, company, bank_details)
            return

        query = 'UPDATE companies SET note = ? WHERE id = ?'
        new_value = message.text.strip()
        old_value = company.get('note', '')

        edit_company(user_id, company['id'], old_value, new_value, parameter, query)

    # Обработчики для банковских реквизитов
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_bik')
    def handle_editing_company_bik(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        bank_details = db.get_company_bank_details(company['id'])
        parameter = 'bik'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            show_company_info(bot, user_id, company, bank_details)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ БИК не может быть пустым. Введите БИК:")
            return

        # Проверяем, есть ли уже банковские реквизиты
        if bank_details:
            query = 'UPDATE company_bank_details SET bik = ? WHERE company_id = ?'
        else:
            query = 'INSERT INTO company_bank_details (bik, company_id) VALUES (?, ?)'

        new_value = message.text.strip()
        old_value = bank_details.get('bik', '') if bank_details else ''

        edit_company_bank_detail(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_payment_account')
    def handle_editing_company_payment_account(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        bank_details = db.get_company_bank_details(company['id'])
        parameter = 'payment_account'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            show_company_info(bot, user_id, company, bank_details)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Расчетный счет не может быть пустым. Введите расчетный счет:")
            return

        if bank_details:
            query = 'UPDATE company_bank_details SET payment_account = ? WHERE company_id = ?'
        else:
            query = 'INSERT INTO company_bank_details (payment_account, company_id) VALUES (?, ?)'

        new_value = message.text.strip()
        old_value = bank_details.get('payment_account', '') if bank_details else ''

        edit_company_bank_detail(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_correspondent_account')
    def handle_editing_company_correspondent_account(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        bank_details = db.get_company_bank_details(company['id'])
        parameter = 'correspondent_account'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            show_company_info(bot, user_id, company, bank_details)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Корреспондентский счет не может быть пустым. Введите корреспондентский счет:")
            return

        if bank_details:
            query = 'UPDATE company_bank_details SET correspondent_account = ? WHERE company_id = ?'
        else:
            query = 'INSERT INTO company_bank_details (correspondent_account, company_id) VALUES (?, ?)'

        new_value = message.text.strip()
        old_value = bank_details.get('correspondent_account', '') if bank_details else ''

        edit_company_bank_detail(user_id, company['id'], old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'settings_editing_company_okpo')
    def handle_editing_company_okpo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        company = db.get_company_by_id(user_data[user_id]['company_id'])
        if not company:
            bot.send_message(user_id, "❌ Компания не найдена")
            return

        bank_details = db.get_company_bank_details(company['id'])
        parameter = 'okpo'

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_edit_action')
            show_company_info(bot, user_id, company, bank_details)
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ ОКПО не может быть пустым. Введите ОКПО:")
            return

        if bank_details:
            query = 'UPDATE company_bank_details SET okpo = ? WHERE company_id = ?'
        else:
            query = 'INSERT INTO company_bank_details (okpo, company_id) VALUES (?, ?)'

        new_value = message.text.strip()
        old_value = bank_details.get('okpo', '') if bank_details else ''

        edit_company_bank_detail(user_id, company['id'], old_value, new_value, parameter, query)

    def edit_company(user_id, company_id, old_value, new_value, parameter, query):
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None
        user = db.get_user_by_telegram_id(user_id)

        if role == 'admin':
            values = [new_value, company_id]
            success = db.execute_query(query, values)

            if success:
                bot.send_message(user_id, "✅ Данные компании успешно обновлены!")
                company = db.get_company_by_id(company_id)
                bank_details = db.get_company_bank_details(company_id)
                show_company_info(bot, user_id, company, bank_details)
            else:
                bot.send_message(user_id, "❌ Ошибка при обновлении данных компании.")
        else:
            # Создаем уникальный ID запроса
            import time
            request_id = f"{company_id}_{parameter}_{user_id}_{int(time.time())}"

            # Сохраняем данные запроса
            edit_requests[request_id] = {
                'company_id': company_id,
                'field': parameter,
                'new_value': new_value,
                'editor_id': user_id,
                'query': query
            }

            admins = db.get_all_admins()
            for admin in admins:
                bot.send_message(
                    admin['telegram_id'],
                    f"""
    📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ ДАННЫХ КОМПАНИИ**

    👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
    🆔 **Telegram ID:** {user_id}
    🏢 **Роль:** {role_names.get(user['role'])}

    📋 **Изменяемое поле:** {company_fields_display.get(parameter, parameter)}
    📄 **Старое значение:** {company_type_map.get(old_value, old_value)}
    🔄 **Новое значение:** {company_type_map.get(new_value, new_value)}

    ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

    Для подтверждения или отклонения изменения используйте кнопки ниже.
                    """,
                    reply_markup=get_id_request_approve_reject_company_edit_keyboard(request_id)
                )
            bot.send_message(
                user_id,
                '🕐 **Данные отправлены главному администратору на проверку**\n'
                '**Вам придет уведомление о результате проверки**',
                reply_markup=get_main_menu(role)
            )
            add_pending_moderation('company-edit', company_id)
            set_user_state(user_id, '')
    def edit_company_bank_detail(user_id, company_id, old_value, new_value, parameter, query):
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None
        user = db.get_user_by_telegram_id(user_id)

        if role == 'admin':
            values = [new_value, company_id]
            success = db.execute_query(query, values)

            if success:
                bot.send_message(user_id, "✅ Банковские реквизиты успешно обновлены!")
                company = db.get_company_by_id(company_id)
                bank_details = db.get_company_bank_details(company_id)
                show_company_info(bot, user_id, company, bank_details)
            else:
                bot.send_message(user_id, "❌ Ошибка при обновлении банковских реквизитов.")
        else:
            # Создаем уникальный ID запроса
            import time
            request_id = f"{company_id}_{parameter}_{user_id}_{int(time.time())}"

            # Сохраняем данные запроса
            edit_requests[request_id] = {
                'company_id': company_id,
                'field': parameter,
                'new_value': new_value,
                'editor_id': user_id,
                'query': query
            }

            admins = db.get_all_admins()
            for admin in admins:
                bot.send_message(
                    admin['telegram_id'],
                    f"""
    📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ БАНКОВСКИХ РЕКВИЗИТОВ**

    👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
    🆔 **Telegram ID:** {user_id}
    🏢 **Роль:** {role_names.get(user['role'])}

    📋 **Изменяемое поле:** {company_fields_display.get(parameter)}
    📄 **Старое значение:** {old_value}
    🔄 **Новое значение:** {new_value}

    ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

    Для подтверждения или отклонения изменения используйте кнопки ниже.
                    """,
                    reply_markup=get_id_request_approve_reject_company_edit_keyboard(request_id)
                )
            bot.send_message(
                user_id,
                '🕐 **Данные отправлены главному администратору на проверку**\n'
                '**Вам придет уведомление о результате проверки**',
                reply_markup=get_main_menu(role)
            )
            add_pending_moderation('company-edit', company_id)
            set_user_state(user_id, '')