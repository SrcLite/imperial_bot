import glob
import os.path
import re
from datetime import datetime
from PIL import Image, ImageOps
import io
from telebot.types import InputMediaPhoto, ReplyKeyboardRemove
from handlers.admin_handlers.pending_moderations_handlers import add_pending_moderation
from handlers.registration_handlers.registration_user_handlers import get_user_state, set_user_state
from keyboards.admin_keyboards import get_back_keyboard, get_role_keyboard, get_approve_reject_edit_keyboard, \
    get_approve_reject_delete_photos_keyboard
from keyboards.main_menus import get_main_menu
from keyboards.profile_keyboards import get_profile_editing_keyboard, get_edit_photo_keyboard, get_edit_data_keyboard
from utils.dicts import user_fields_display
from utils.email_sender import send_email_notification, enhanced_send_email_notification

role_names = {
    'admin': '👑 Администратор',
    'logist': '📊 Логист',
    'executor': '🚛 Перевозчик',
    'external_admin': '👑 Администратор',
    'external_logist': '📊 Логист',
    'external_executor': '🚛 Перевозчик'
}


def register_profile_handlers(bot, db):
    @bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
    def handler_profile(message):
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
        profile_text = generate_profile_info(user_id, db)
        bot.send_message(chat_id,
                         profile_text,
                         reply_markup=get_profile_editing_keyboard(),
                         )
        set_user_state(user_id, 'waiting_for_edit_user_action')

    def generate_profile_info(user_id, db):
        user = db.get_user_by_telegram_id(user_id)
        company_result = db.get_company_id_by_user_id(user_id)
        company_id = company_result['company_id'] if company_result else None
        company = db.get_company_by_id(company_id) if company_id else None
        company_name = company["name"] if company and 'name' in company else 'Не указана'
        return f"""
        👤 **ВАШ ПРОФИЛЬ**

        📋 **Основная информация:**
        • **👤 ФИО:** {user.get('last_name', '')} {user.get('first_name', '')} {user.get('patronymic', '')}
        • **💼 Должность:** {role_names.get(user['role'], user['role'])}
        • **🏢 Компания:** {company_name}

        📞 **Контакты:**
        • **📞 Телефон:** {user.get('phone', 'Не указан')}
        • **📧 Email:** {user.get('email', 'Не указан')}
        • **🆔 Telegram:** @{user.get('username', 'Не указан')}

        📄 **Документы:**
        • **🎂 Дата рождения:** {user.get('birth_date', 'Не указана')}
        • **📘 Паспорт:** {user.get('passport_series', '')} {user.get('passport_number', '')}
        • **📅 Дата выдачи:** {user.get('passport_issue_date', 'Не указана')}
        • **📍 Адрес регистрации:** {user.get('registration_address', 'Не указан')}

        🔢 **Дополнительно:**
        • **Код АТИ:** {user.get('ati_code', 'Не указан')}
        • **Дата регистрации:** {user.get('created_at', 'Не указана')}
        """

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_user_action')
    def handle_edit_user_action(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_role = db.get_user_role(user_id)
        role = user_role['role'] if user_role else None
        if message.text == '✏️ Редактировать данные':
            set_user_state(user_id, 'waiting_for_edit_user_data')
            bot.send_message(chat_id, 'Выберите, что хотите отредактировать', reply_markup=get_edit_data_keyboard())
        elif message.text == '📷 Показать мои фото':
            set_user_state(user_id, 'waiting_for_edit_user_photos')
            send_photo(bot, chat_id, user_id)
        elif message.text == '🕹 Главное меню':
            set_user_state(user_id, '')
            bot.send_message(chat_id, 'Выберите действие:', reply_markup=get_main_menu(role))


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
                bot.send_message(chat_id, "❌ В папке нет фотографий", reply_markup = get_edit_photo_keyboard())
                set_user_state(chat_id, 'waiting_for_user_photos_action')
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
            bot.send_message(chat_id, "Выберите действие из меню:", reply_markup=get_edit_photo_keyboard())
            set_user_state(user_id, 'waiting_for_user_photos_action')

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

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_user_photos_action')
    def handle_user_photos_action(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None

        if message.text == '🔄 Добавить фотографии':
            set_user_state(user_id, 'waiting_for_edit_user_photos')
            bot.send_message(chat_id, "Пожалуйста, отправьте фото документов:\n"
                                      "• 1 страница паспорта (с фото и данными)\n"
                                      "• Страница с пропиской\n\n",
                             reply_markup=get_back_keyboard())
        elif message.text == "📁 Удалить все фото":
            if role == 'admin':
                # Админы могут удалять сразу
                set_user_state(user_id, 'waiting_for_delete_user_photos')
                delete_all_photos(user_id, chat_id)
            else:
                # Обычные пользователи отправляют заявку на удаление
                send_delete_photos_request(bot, db, user_id, chat_id)
        elif message.text == "⬅️ Назад в профиль":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, generate_profile_info(user_id, db), reply_markup=get_profile_editing_keyboard())

    def send_delete_photos_request(bot, db, user_id, chat_id):
        """Отправляет заявку на удаление фото администраторам"""
        user = db.get_user_by_telegram_id(user_id)
        admins = db.get_all_admins()

        for admin in admins:
            bot.send_message(
                admin['telegram_id'],
                f"""
                📝 **ЗАЯВКА НА УДАЛЕНИЕ ФОТОГРАФИЙ**

                👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
                🆔 **Telegram ID:** {user_id}
                🏢 **Роль:** {role_names.get(user['role'])}

                ❗️ **Запросил удаление всех своих фотографий.**

                ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

                Для подтверждения или отклонения используйте кнопки ниже.
                """,
                reply_markup=get_approve_reject_delete_photos_keyboard(user_id)
            )

        bot.send_message(
            chat_id,
            '🕐 **Запрос на удаление всех фотографий отправлен администратору на проверку.**\n'
            '**Вам придет уведомление о результате проверки.**',
            reply_markup=get_edit_photo_keyboard()
        )
        set_user_state(user_id, 'waiting_for_user_photos_action')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_user_photos')
    def handle_edit_user_photos(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Проверяем, есть ли фото в папке
        folder_path = f"data/documents/users/{user_id}"

        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)

        # Получаем список существующих фото
        existing_photos = glob.glob(os.path.join(folder_path, "*.jpg")) + glob.glob(
            os.path.join(folder_path, "*.jpeg")) + glob.glob(os.path.join(folder_path, "*.png"))

        if not existing_photos:
            # Если в папке нет фото, предлагаем добавить
            bot.send_message(
                chat_id,
                "📷 В вашей папке нет фотографий паспорта.\n\n"
                "Пожалуйста, отправьте фото документов:\n"
                "• 1 страница паспорта (с фото и данными)\n"
                "• Страница с пропиской\n\n"
                "Вы можете отправить одно или несколько фото.",
                reply_markup=get_edit_photo_keyboard()
            )
            return

        # Показываем текущие фото и предлагаем действия
        send_photo(bot, chat_id, user_id)

    @bot.message_handler(content_types=['photo', 'text'],
                         func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_user_photos')
    def handle_new_photos(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        folder_path = f"data/documents/users/{user_id}"

        if message.text == '⬅️ Назад':
            bot.send_message(chat_id, 'Выберите действие:', reply_markup = get_edit_photo_keyboard())

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

                # Получаем оригинальный размер файла
                original_size = len(downloaded_file) / 1024  # в KB

                # Сжимаем фото
                compressed_data = compress_image(downloaded_file, max_width=800, quality=20)

                if compressed_data is None:
                    bot.send_message(chat_id, "❌ Ошибка при обработке фото")
                    return

                # Генерируем уникальное имя файла
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"passport_photo_{timestamp}.jpg"

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

                # Проверяем количество фото после добавления
                updated_photos = glob.glob(os.path.join(folder_path, "*.jpg")) + glob.glob(
                    os.path.join(folder_path, "*.jpeg")) + glob.glob(os.path.join(folder_path, "*.png"))

                if len(updated_photos) >= 2:
                    bot.send_message(
                        chat_id,
                        "✅ У вас уже есть 2 фотографии паспорта. Вы можете просмотреть их или добавить новые.",
                        reply_markup=get_edit_photo_keyboard()
                    )
                else:
                    bot.send_message(
                        chat_id,
                        "📷 Вы можете добавить еще одну фотографию или просмотреть текущие.",
                        reply_markup=get_edit_photo_keyboard()
                    )

            except Exception as e:
                bot.send_message(chat_id, f"❌ Ошибка при сохранении фото: {str(e)}")
                print(f"Ошибка при сохранении фото: {e}")

    def delete_all_photos(user_id, chat_id):
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

        bot.send_message(
            chat_id,
            f"🗑️ Удалено {deleted_count} фотографий.\n\n"
            "Теперь вы можете добавить новые фото документов.",
            reply_markup=get_edit_photo_keyboard()
        )
        set_user_state(user_id, 'waiting_for_user_photos_action')

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_edit_user_data')
    def handle_editing_logist_field_selection(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, generate_profile_info(user_id, db), reply_markup=get_profile_editing_keyboard())

        if message.text == "👤 Редактировать имя":
            bot.send_message(
                chat_id,
                f"Текущее имя: {user['first_name']}\nВведите новое имя:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_first_name')

        elif message.text == "👤 Редактировать фамилию":
            bot.send_message(
                chat_id,
                f"Текущая фамилия: {user.get('last_name', 'Не указана')}\nВведите новую фамилию:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_last_name')

        elif message.text == "👤 Редактировать отчество":
            bot.send_message(
                chat_id,
                f"Текущее отчество: {user.get('patronymic', 'Не указано')}\nВведите новое отчество:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_patronymic')

        elif message.text == "💼 Редактировать должность":
            bot.send_message(
                chat_id,
                f"Текущая должность: {role_names.get(user.get('role', 'Не указана'))}\nВыберите новую должность:",
                reply_markup=get_role_keyboard()
            )
            set_user_state(user_id, 'editing_user_role')

        elif message.text == "📞 Редактировать телефон":
            bot.send_message(
                chat_id,
                f"Текущий телефон: {user.get('phone', 'Не указан')}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_phone')

        elif message.text == "📧 Редактировать email":
            bot.send_message(
                chat_id,
                f"Текущий email: {user.get('email', 'Не указан')}\nВведите новый email:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_email')

        elif message.text == "🎂 Редактировать дату рождения":
            bot.send_message(
                chat_id,
                f"Текущая дата рождения: {user.get('birth_date', 'Не указана')}\nВведите новую дату рождения (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_birth_date')

        elif message.text == "📘 Редактировать серию паспорта":
            bot.send_message(
                chat_id,
                f"Текущая серия паспорта: {user.get('passport_series', 'Не указана')}\nВведите новую серию паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_passport_series')

        elif message.text == "📘 Редактировать номер паспорта":
            bot.send_message(
                chat_id,
                f"Текущий номер паспорта: {user.get('passport_number', 'Не указан')}\nВведите новый номер паспорта:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_passport_number')

        elif message.text == "📅 Редактировать дату выдачи паспорта":
            bot.send_message(
                chat_id,
                f"Текущая дата выдачи паспорта: {user.get('passport_issue_date', 'Не указана')}\nВведите новую дату выдачи паспорта (ДД.ММ.ГГГГ):",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_passport_issue_date')

        elif message.text == "📍 Редактировать адрес регистрации":
            bot.send_message(
                chat_id,
                f"Текущий адрес регистрации: {user.get('registration_address', 'Не указан')}\nВведите новый адрес регистрации:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_registration_address')

        elif message.text == "🔢 Редактировать код АТИ":
            bot.send_message(
                chat_id,
                f"Текущий код АТИ: {user.get('ati_code', 'Не указан')}\nВведите новый код АТИ:",
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'editing_user_ati_code')

    def edit_user(user_id, old_value, new_value, parameter, query):
        user_info = db.get_user_role(user_id)
        role = user_info['role'] if user_info else None
        user = db.get_user_by_telegram_id(user_id)
        values = []
        values.append(new_value)
        values.append(user_id)
        if role == 'admin':
            success = db.execute_query(query, values)

            if success:
                bot.send_message(user_id, "✅ Данные успешно обновлены!")
            else:
                bot.send_message(user_id, "❌ Ошибка при обновлении данных.")
        else:
            email_subject = f'Заявка на изменение данных'
            email_message = f"""
                           Пользователь {user.get('first_name', '')} {user.get('last_name', '')} сделал запрос на изменение данных с {old_value} на {new_value}.
                           Откройте чат с Телеграм-ботом, чтобы принять или отклонить запрос
                           """
            admins = db.get_all_admins()
            for admin in admins:
                bot.send_message(
                    admin['telegram_id'],
                    f"""📝 **ЗАЯВКА НА ИЗМЕНЕНИЕ ДАННЫХ**

                  👤 **Пользователь:** {user.get('first_name', '')} {user.get('last_name', '')}
                  🆔 **Telegram ID:** {user_id}
                  🏢 **Роль:** {role_names.get(user['role'])}
    
                  📋 **Изменяемое поле:** {user_fields_display.get(parameter)}
                  📄 **Старое значение:** {old_value}
                  🔄 **Новое значение:** {new_value}
    
                  ⏰ **Время запроса:** {datetime.now().strftime('%d.%m.%Y %H:%M')}
    
                  Для подтверждения или отклонения изменения используйте панель администратора.
                      """,
                    reply_markup=get_approve_reject_edit_keyboard(user_id, new_value, parameter, user_id)
                )
                admin_email = admin.get('email')
                if not admin_email or not isinstance(admin_email, str) or not admin_email.strip():
                    print(f"Пропускаем администратора с некорректным email: {admin}")
                    continue

                # Убираем пробелы
                if not admin_email or not isinstance(admin_email, str) or not admin_email.strip():
                    print(f"Пропускаем администратора с некорректным email: {admin}")
                    continue

                try:
                    enhanced_send_email_notification(email_subject, email_message, admin['email'])
                except Exception as e:
                    print(f"Ошибка при отправке email администратору {admin_email}: {e}")
                    # Продолжаем отправку остальным администраторам
                    continue

            add_pending_moderation('user_edit', user_id)
            bot.send_message(
                user_id,
                '🕐**Данные отправлены главному администратору на проверку**\n'
                '  **Вам придет уведомление о результате проверки**',
                reply_markup=get_main_menu(role)
            )
            set_user_state(user_id, '')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_first_name")
    def handle_editing_user_first_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'first_name'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        if not message.text.strip() or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "❌ Имя должно содержать минимум 2 символа. Введите имя:")
            return

        query = 'UPDATE users SET first_name = ? WHERE telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['first_name']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_last_name")
    def handle_editing_user_last_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'last_name'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Фамилия не может быть пустой. Введите фамилию:")
            return

        query = 'Update users set last_name=? where telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['last_name']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_patronymic")
    def handle_editing_user_patronymic(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'patronymic'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        patronymic = message.text.strip()
        if not patronymic:
            bot.send_message(chat_id, "❌ Отчество не может быть пустым. Введите отчество или пропустите:")
            return

        query = 'Update users set patronymic=? where telegram_id = ?'
        new_value = patronymic
        old_value = user['patronymic']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_birth_date")
    def handle_editing_user_birth_date(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'birth_date'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        try:
            birth_date = datetime.strptime(message.text, '%d.%m.%Y')
            if birth_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата рождения не может быть в будущем. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        query = 'Update users set birth_date=? where telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['birth_date']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_passport_series")
    def handle_editing_user_passport_series(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'passport_series'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 4:
            bot.send_message(chat_id, "❌ Серия паспорта должна состоять из 4 цифр. Попробуйте еще раз:")
            return

        query = 'Update users set passport_series=? where telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['passport_series']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_passport_number")
    def handle_editing_user_passport_number(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'passport_number'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        if not message.text.strip() or not message.text.isdigit() or len(message.text) != 6:
            bot.send_message(chat_id, "❌ Номер паспорта должен состоять из 6 цифр. Попробуйте еще раз:")
            return

        query = 'Update users set passport_number=? where telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['passport_number']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == "editing_user_passport_issue_date")
    def handle_editing_user_passport_issue_date(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'passport_issue_date'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        try:
            issue_date = datetime.strptime(message.text, '%d.%m.%Y')
            if issue_date > datetime.now():
                bot.send_message(chat_id, "❌ Дата выдачи не может быть в будущем. Попробуйте еще раз:")
                return
        except ValueError:
            bot.send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ. Попробуйте еще раз:")
            return

        query = 'Update users set passport_issue_date=? where telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['passport_issue_date']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == "editing_user_registration_address")
    def handle_editing_user_registration_address(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'registration_address'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        if not message.text.strip():
            bot.send_message(chat_id, "❌ Адрес регистрации не может быть пустым. Введите адрес:")
            return

        query = 'Update users set registration_address=? where telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['registration_address']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_ati_code")
    def handle_editing_user_ati_code(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'ati_code'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        ati_code = message.text.strip()
        if not ati_code.isdigit():
            bot.send_message(chat_id, "❌ Код АТИ должен содержать только цифры. Попробуйте еще раз:")
            return

        query = 'Update users set ati_code=? where telegram_id = ?'
        new_value = ati_code
        old_value = user['ati_code']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_role")
    def handle_editing_user_role(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'role'
        user = db.get_user_by_telegram_id(user_id)
        user_role = db.get_user_role(user_id)
        role = user_role['role'] if user_role else None
        new_value = ''

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        if role == 'admin' or role == 'logis' or role == 'executor':
            if message.text == '👑 Администратор':
                new_value = 'admin'
            elif message.text == '📊 Логист':
                new_value = 'logist'
            elif message.text == '🚛 Перевозчик':
                new_value = 'executor'
            else:
                bot.send_message(
                    chat_id,
                    '❌ Выберите роль из предложенных в меню:',
                    reply_markup=get_role_keyboard()
                )
                return
        elif role == 'external_admin' or role == 'external_logist' or role == 'external_executor':
            if message.text == '👑 Администратор':
                new_value = 'external_admin'
            elif message.text == '📊 Логист':
                new_value = 'external_logist'
            elif message.text == '🚛 Перевозчик':
                new_value = 'external_executor'
            else:
                bot.send_message(
                    chat_id,
                    '❌ Выберите роль из предложенных в меню:',
                    reply_markup=get_role_keyboard()
                )
                return

        query = 'Update users set role=? where telegram_id = ?'
        old_value = user['role']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_phone")
    def handle_editing_user_phone(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'phone'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        phone = re.sub(r'[^\d+]', '', message.text)
        if not ((phone.startswith('+7') and len(phone) == 12) or (phone.startswith('8') and len(phone) == 11)):
            bot.send_message(
                chat_id,
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX или 8XXXXXXXXXX. Попробуйте еще раз:"
            )
            return

        query = 'Update users set phone=? where telegram_id = ?'
        new_value = message.text.strip()
        old_value = user['phone']

        edit_user(user_id, old_value, new_value, parameter, query)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == "editing_user_email")
    def handle_editing_user_email(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        parameter = 'email'
        user = db.get_user_by_telegram_id(user_id)

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_edit_user_action')
            bot.send_message(chat_id, "Выберите, что хотите редактировать:",
                             reply_markup=get_profile_editing_keyboard())
            return

        email = message.text.strip()

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            bot.send_message(chat_id, "❌ Неверный формат email. Попробуйте еще раз:")
            return

        query = 'Update users set email=? where telegram_id = ?'
        new_value = email
        old_value = user['email']

        edit_user(user_id, old_value, new_value, parameter, query)