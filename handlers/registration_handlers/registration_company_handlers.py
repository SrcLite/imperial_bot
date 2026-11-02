import glob
import logging
import os
import io
import time
from PIL import Image
from datetime import datetime
from collections import defaultdict
from telebot.types import ReplyKeyboardRemove

from handlers.admin_handlers.pending_moderations_handlers import add_pending_moderation
from keyboards.admin_keyboards import get_approve_reject_company_keyboard
from keyboards.registration_company_keyboards import *
from handlers.registration_handlers.registration_user_handlers import user_states
from keyboards.registration_user_keyboards import get_company_selection_keyboard
from utils.email_sender import send_email_notification

company_temp_data = {}
processed_media_groups = defaultdict(bool)

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


def register_company_handlers(bot, db):
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_reg')
    def handle_company_reg(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        bot.send_message(
            chat_id,
            'Переходим к регистрации компании.\n'
            'Выберите тип компании:',
            reply_markup=get_company_type_keyboard()
        )
        set_user_state(user_id, 'waiting_for_company_type')

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_type')
    def handle_company_type(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            # Возврат к выбору компании
            approved_companies = db.fetch_all(
                "SELECT * FROM companies WHERE status = 'approved' ORDER BY name"
            )
            companies_text = "🏢 **Выберите вашу компанию из списка:**\n\n"
            for company in approved_companies:
                companies_text += f"{company['name']}\n"

            bot.send_message(
                chat_id,
                companies_text,
                reply_markup=get_company_selection_keyboard(approved_companies)
            )
            set_user_state(user_id, 'waiting_for_company_selection')
            return

        company_type = message.text[2:] if message.text.startswith("🏢 ") or message.text.startswith(
            "👤 ") or message.text.startswith("💼 ") else message.text

        if company_type not in ['Юридическое лицо', 'Индивидуальный предприниматель', 'Самозанятый']:
            bot.send_message(chat_id, 'Пожалуйста, выберите тип компании из предложенных вариантов.')
            return

        # Сохраняем тип компании
        type_map = {
            'Юридическое лицо': 'legal',
            'Индивидуальный предприниматель': 'individual',
            'Самозанятый': 'self_employed'
        }
        if user_id not in company_temp_data:
            company_temp_data[user_id] = {}

        company_temp_data[user_id]['company_type'] = type_map[company_type]

        set_user_state(user_id, 'waiting_for_company_name')
        bot.send_message(
            chat_id,
            'Введите название компании:',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_name')
    def handle_company_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '🏦 Выберите тип компании:',
                reply_markup=get_company_type_keyboard()
            )
            set_user_state(user_id, 'waiting_for_company_type')
            return

        if not message.text.strip():
            bot.send_message(chat_id, 'Название компании не может быть пустым. Введите название:')
            return

        company_temp_data[user_id]['name'] = message.text.strip()
        set_user_state(user_id, 'waiting_for_company_reg_inn')
        bot.send_message(
            chat_id,
            '🏦**Введите ИНН компании**:',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_reg_inn')
    def handle_company_inn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '🏦 Введите название компании:',
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_company_name')
            return

        inn = message.text.strip()
        if not inn.isdigit():
            bot.send_message(chat_id, 'ИНН должен содержать только цифры. Введите ИНН:')
            return

        company_type = company_temp_data[user_id].get('company_type')
        if company_type == 'legal' and len(inn) != 10:
            bot.send_message(chat_id, 'ИНН юридического лица должен содержать 10 цифр. Введите ИНН:')
            return
        elif company_type in ['individual', 'self_employed'] and len(inn) != 12:
            bot.send_message(chat_id,
                             'ИНН индивидуального предпринимателя/самозанятого должен содержать 12 цифр. Введите ИНН:')
            return

        company_temp_data[user_id]['inn'] = inn

        # Для юридических лиц запрашиваем КПП, для остальных - пропускаем
        if company_type == 'legal':
            set_user_state(user_id, 'waiting_for_company_kpp')
            bot.send_message(
                chat_id,
                '🏦**Введите КПП компании**(9 цифр):',
                reply_markup=get_back_keyboard()
            )
        else:
            set_user_state(user_id, 'waiting_for_company_management_name')
            bot.send_message(
                chat_id,
                'Введите ФИО директора:',
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_kpp')
    def handle_company_kpp(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '🏦**Введите ИНН компании**:',
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_company_reg_inn')
            return
        company_temp_data[user_id]['kpp'] = 'Не указан'
        kpp = message.text.strip()
        if not kpp.isdigit() or len(kpp) != 9:
            bot.send_message(chat_id, 'КПП должен содержать 9 цифр. Введите КПП:')
            return

        company_temp_data[user_id]['kpp'] = kpp
        set_user_state(user_id, 'waiting_for_company_management_name')
        bot.send_message(
            chat_id,
            '🏦 Введите ФИО директора:',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_management_name')
    def handle_company_management_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            company_type = company_temp_data[user_id].get('company_type')
            if company_type == 'legal':
                bot.send_message(
                    chat_id,
                    '🏦**Введите КПП компании**(9 цифр):',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_company_kpp')
            else:
                bot.send_message(
                    chat_id,
                    '🏦**Введите ИНН компании**:',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_company_reg_inn')
            return

        if not message.text.strip():
            bot.send_message(chat_id, 'Фамилия не может быть пустой. Введите фамилию директора:')
            return

        company_temp_data[user_id]['management_name'] = message.text.strip()
        set_user_state(user_id, 'waiting_for_company_ogrn')
        bot.send_message(
            chat_id,
            '🏦**Введите ОГРН/ОГРНИП**:',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_ogrn')
    def handle_company_ogrn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                'Введите ФИО директора:',
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_company_management_name')
            return

        ogrn = message.text.strip()
        if not ogrn.isdigit():
            bot.send_message(chat_id, 'ОГРН должен содержать только цифры. Введите ОГРН:')
            return

        company_type = company_temp_data[user_id].get('company_type')
        if company_type == 'legal' and len(ogrn) != 13:
            bot.send_message(chat_id, 'ОГРН юридического лица должен содержать 13 цифр. Введите ОГРН:')
            return
        elif company_type == 'individual' and len(ogrn) != 15:
            bot.send_message(chat_id, 'ОГРНИП должен содержать 15 цифр. Введите ОГРНИП:')
            return

        company_temp_data[user_id]['ogrn'] = ogrn
        set_user_state(user_id, 'waiting_for_company_legal_address')
        bot.send_message(
            chat_id,
            'Введите юридический адрес:',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_legal_address')
    def handle_company_legal_address(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                'Введите ОГРН/ОГРНИП:',
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_company_ogrn')
            return

        if not message.text.strip():
            bot.send_message(chat_id, 'Адрес не может быть пустым. Введите юридический адрес:')
            return

        company_temp_data[user_id]['address'] = message.text.strip()
        set_user_state(user_id, 'waiting_for_company_tax_system')
        set_user_state(user_id, 'waiting_for_company_contact_phone')
        bot.send_message(
            chat_id,
            'Введите контактный телефон компании:',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_tax_system')
    def handle_company_tax_system(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                'Введите юридический адрес:',
                reply_markup=get_back_keyboard()
            )
            set_user_state(user_id, 'waiting_for_company_legal_address')
            return

        company_type = company_temp_data[user_id].get('company_type')

        # Проверяем доступные системы налогообложения для данного типа компании
        available_tax_systems = get_available_tax_systems(company_type)

        if message.text not in available_tax_systems:
            bot.send_message(
                chat_id,
                f'❌ Пожалуйста, выберите систему налогообложения из предложенных вариантов для {company_type}.'
            )
            return

        # Сохраняем выбранную систему налогообложения
        tax_system_map = {
            'ОСНО': 'osn',
            'УСН': 'usn',
            'ЕСХН': 'eshn',
            'ПСН': 'psn',
            'НПД': 'npd',
            'АУСН': 'ausn'
        }

        company_temp_data[user_id]['tax_system'] = tax_system_map[message.text]
        set_user_state(user_id, 'waiting_for_company_contact_phone')
        bot.send_message(
            chat_id,
            'Введите контактный телефон компании:',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_contact_phone', 'waiting_for_company_partial_contact_phone'])
    def handle_company_contact_phone(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        if user_id not in company_temp_data:
            company_temp_data[user_id] = {}
        user = db.get_user_by_telegram_id(user_id)
        company = db.get_company_by_id(user['company_id'])
        if company:
            company_temp_data[user_id] = company

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'waiting_for_company_legal_address')
            bot.send_message(
                chat_id,
                'Введите юридический адрес:',
                reply_markup=get_back_keyboard()
            )
            return
        # Простая валидация телефона
        phone = message.text.strip()
        if len(phone) < 10:
            bot.send_message(chat_id, 'Номер телефона слишком короткий. Введите корректный номер:')
            return

        company_temp_data[user_id]['contact_phone'] = phone
        if get_user_state(user_id) == 'waiting_for_company_partial_contact_phone':
            set_user_state(user_id, 'waiting_for_company_partial_contact_email')
            bot.send_message(
                chat_id,
                'Введите email компании:',
                reply_markup=get_back_keyboard()
            )
        else:
            set_user_state(user_id, 'waiting_for_company_contact_email')
            bot.send_message(
                chat_id,
                'Введите email компании:',
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_contact_email', 'waiting_for_company_partial_contact_email'])
    def handle_company_contact_email(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            if get_user_state(user_id) == 'waiting_for_company_partial_contact_email':
                bot.send_message(
                    chat_id,
                    'Введите контактный телефон компании:',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_company_partial_contact_phone')
                return
            else:
                bot.send_message(
                    chat_id,
                    'Введите контактный телефон компании:',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_company_contact_phone')
                return

        email = message.text.strip()
        if '@' not in email or '.' not in email:
            bot.send_message(chat_id, 'Введите корректный email адрес:')
            return

        company_temp_data[user_id]['contact_email'] = email
        if get_user_state(user_id) == 'waiting_for_company_partial_contact_email':
            set_user_state(user_id, 'waiting_for_company_partial_bik')
        else:
            set_user_state(user_id, 'waiting_for_company_bik')
        bot.send_message(
            chat_id,
            '🏦 **Введите БИК банка** (9 цифр):',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_bik', 'waiting_for_company_partial_bik'])
    def handle_company_bik(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            if get_user_state(user_id) == 'waiting_for_company_partial_bik':
                set_user_state(user_id, 'waiting_for_company_partial_contact_email')
            else:
                set_user_state(user_id, 'waiting_for_company_contact_email')
            bot.send_message(
                chat_id,
                'Введите email компании:',
                reply_markup=get_back_keyboard()
            )
            return

        bik = message.text.strip()
        if not (bik.isdigit() and len(bik) == 9):
            bot.send_message(chat_id, '❌ БИК должен содержать 9 цифр. Введите БИК:')
            return

        company_temp_data[user_id]['bik'] = bik
        if get_user_state(user_id) == 'waiting_for_company_partial_bik':
            set_user_state(user_id, 'waiting_for_company_partial_payment_account')
        else:
            set_user_state(user_id, 'waiting_for_company_payment_account')
        bot.send_message(
            chat_id,
            '🏦 **Введите расчетный счет** (20 цифр):',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_payment_account', 'waiting_for_company_partial_payment_account'])
    def handle_company_payment_account(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            if get_user_state(user_id) == 'waiting_for_company_partial_payment_account':
                set_user_state(user_id, 'waiting_for_company_partial_bik')
            else:
                set_user_state(user_id, 'waiting_for_company_bik')
            bot.send_message(
                chat_id,
                'Введите БИК банка:',
                reply_markup=get_back_keyboard()
            )
            return

        payment_account = message.text.strip()
        if not (payment_account.isdigit() and len(payment_account) == 20):
            bot.send_message(chat_id, '❌ Расчетный счет должен содержать 20 цифр. Введите расчетный счет:')
            return

        company_temp_data[user_id]['payment_account'] = payment_account
        if get_user_state(user_id) == 'waiting_for_company_partial_payment_account':
            set_user_state(user_id, 'waiting_for_company_partial_correspondent_account')
        else:
            set_user_state(user_id, 'waiting_for_company_correspondent_account')
        bot.send_message(
            chat_id,
            '🏦 **Введите корреспондентский счет** (20 цифр):',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_correspondent_account', 'waiting_for_company_partial_correspondent_account'])
    def handle_company_correspondent_account(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                'Введите расчетный счет:',
                reply_markup=get_back_keyboard()
            )
            if get_user_state(user_id) == 'waiting_for_company_partial_correspondent_account':
                set_user_state(user_id, 'waiting_for_company_partial_payment_account')
            else:
                set_user_state(user_id, 'waiting_for_company_payment_account')
            return

        correspondent_account = message.text.strip()
        if not (correspondent_account.isdigit() and len(correspondent_account) == 20):
            bot.send_message(chat_id,
                             '❌ Корреспондентский счет должен содержать 20 цифр. Введите корреспондентский счет:')
            return

        company_temp_data[user_id]['correspondent_account'] = correspondent_account
        if get_user_state(user_id) == 'waiting_for_company_partial_correspondent_account':
            set_user_state(user_id, 'waiting_for_company_partial_okpo')
        else:
            set_user_state(user_id, 'waiting_for_company_okpo')
        bot.send_message(
            chat_id,
            '🏦 **Введите код ОКПО** (8 или 10 цифр, можно пропустить):',
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_okpo', 'waiting_for_company_partial_okpo'])
    def handle_company_okpo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '🏦 **Введите корреспондентский счет** (20 цифр):',
                reply_markup=get_back_keyboard()
            )
            if get_user_state(user_id) == 'waiting_for_company_partial_okpo':
                set_user_state(user_id, 'waiting_for_company_partial_correspondent_account')
            else:
                set_user_state(user_id, 'waiting_for_company_correspondent_account')
            return

        if message.text == "⏭️ Пропустить":
            company_temp_data[user_id]['okpo'] = 'Не указан'
        else:
            okpo = message.text.strip()
            if not (okpo.isdigit() and len(okpo) in [8, 10]):
                bot.send_message(chat_id,
                                 '❌ Код ОКПО должен содержать 8 или 10 цифр. Попробуйте еще раз или пропустите:')
                return
            company_temp_data[user_id]['okpo'] = okpo


        if get_user_state(user_id) == 'waiting_for_company_partial_okpo':
            set_user_state(user_id, 'waiting_for_company_partial_note')
        else:
            set_user_state(user_id, 'waiting_for_company_note')
        bot.send_message(
            chat_id,
            'Введите примечание (необязательно, можно пропустить):',
            reply_markup=get_skip_back_keyboard()
        )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_note', 'waiting_for_company_partial_note'])
    def handle_company_note(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            bot.send_message(
                chat_id,
                '🏦 **Введите код ОКПО** (8 или 10 цифр, можно пропустить):',
                reply_markup=get_back_keyboard()
            )
            if get_user_state(user_id) == 'waiting_for_company_partial_note':
                set_user_state(user_id, 'waiting_for_company_partial_okpo')
            else:
                set_user_state(user_id, 'waiting_for_company_okpo')
            return

        if message.text == "⏭️ Пропустить":
            company_temp_data[user_id]['note'] = 'Не указан'
        else:
            company_temp_data[user_id]['note'] = message.text.strip()

        if get_user_state(user_id) == 'waiting_for_company_partial_note':
            set_user_state(user_id, 'waiting_for_company_documents_upload')
        else:
            set_user_state(user_id, 'waiting_for_company_documents_upload')
        bot.send_message(
            chat_id,
            "📎 **Загрузка документов компании**\n\n"
            "Прикрепите фото следующих документов:\n"
            "• Свидетельство о регистрации (ОГРН)\n"
            "• Свидетельство о постановке на налоговый учет (ИНН)\n"
            "• Устав компании (первая страница)\n\n"
            "Нажмите '📎 Загрузить документы', чтобы продолжить.",
            reply_markup=get_documents_upload_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(
            message.from_user.id) in ['waiting_for_company_documents_upload',
                                      'waiting_for_editing_company_documents_upload', 'waiting_for_company_partial_documents_upload'] and message.text)
    def handle_company_documents_text(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            if get_user_state(user_id) == 'waiting_for_editing_company_documents_upload':
                show_company_summary(bot, user_id, chat_id)
                set_user_state(user_id, 'waiting_for_company_confirmation')
            elif get_user_state(user_id) == 'waiting_for_company_partial_documents_upload':
                bot.send_message(
                    chat_id,
                    'Введите примечание (необязательно, можно пропустить):',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_company_partial_note')
            else:
                bot.send_message(
                    chat_id,
                    'Введите примечание (необязательно, можно пропустить):',
                    reply_markup=get_back_keyboard()
                )
                set_user_state(user_id, 'waiting_for_company_note')
        elif message.text == "📎 Загрузить документы":
            if get_user_state(user_id) == 'waiting_for_editing_company_documents_upload':
                set_user_state(user_id, 'waiting_for_editing_company_ogrn_photo')
            elif get_user_state(user_id) == 'waiting_for_company_partial_documents_upload':
                set_user_state(user_id, 'waiting_for_company_partial_ogrn_photo')
                bot.send_message(
                    chat_id,
                    "📎 **Шаг 1 из 3: Загрузите фото свидетельства о регистрации (ОГРН)**\n\n"
                    "Пожалуйста, прикрепите ОДНУ фотографию свидетельства ОГРН.",
                    reply_markup=get_back_keyboard()
                )
            else:
                set_user_state(user_id, 'waiting_for_company_ogrn_photo')
            bot.send_message(
                chat_id,
                "📎 **Шаг 1 из 3: Загрузите фото свидетельства о регистрации (ОГРН)**\n\n"
                "Пожалуйста, прикрепите ОДНУ фотографию свидетельства ОГРН.",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(
        content_types=['photo'],
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_ogrn_photo',
                                                                      'waiting_for_editing_company_ogrn_photo',
                                                                      'waiting_for_company_partial_ogrn_photo'])
    def handle_company_ogrn_photo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        print('Обработка фото свидетельства ОГРН')

        # Инициализируем структуры данных если их нет
        if user_id not in company_temp_data:
            company_temp_data[user_id] = {}

        if 'company_documents' not in company_temp_data[user_id]:
            company_temp_data[user_id]['company_documents'] = {
                'ogrn_certificate': None,
                'inn_certificate': None,
                'charter': None
            }

        # Сохраняем file_id для свидетельства ОГРН
        if message.photo:
            file_id = message.photo[-1].file_id

            # Сохраняем в отложенные документы
            if 'pending_documents' not in company_temp_data[user_id]:
                company_temp_data[user_id]['pending_documents'] = []

            company_temp_data[user_id]['pending_documents'].append({
                'file_id': file_id,
                'type': 'company_ogrn'
            })
            company_temp_data[user_id]['company_documents']['ogrn_certificate'] = True

            # Переходим к следующему шагу
            if get_user_state(user_id) == 'waiting_for_editing_company_ogrn_photo':
                set_user_state(user_id, 'waiting_for_editing_company_inn_photo')
                bot.send_message(
                    chat_id,
                    "✅ **Свидетельство ОГРН сохранено!**\n\n"
                    "📎 **Шаг 2 из 3: Загрузите фото свидетельства о постановке на налоговый учет (ИНН)**\n\n"
                    "Пожалуйста, прикрепите ОДНУ фотографию свидетельства ИНН.",
                    reply_markup=ReplyKeyboardRemove()
                )
            elif get_user_state(user_id) == 'waiting_for_company_partial_ogrn_photo':
                set_user_state(user_id, 'waiting_for_company_partial_inn_photo')
                bot.send_message(
                    chat_id,
                    "✅ **Свидетельство ОГРН сохранено!**\n\n"
                    "📎 **Шаг 2 из 3: Загрузите фото свидетельства о постановке на налоговый учет (ИНН)**\n\n"
                    "Пожалуйста, прикрепите ОДНУ фотографию свидетельства ИНН.",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                set_user_state(user_id, 'waiting_for_company_inn_photo')
                bot.send_message(
                    chat_id,
                    "✅ **Свидетельство ОГРН сохранено!**\n\n"
                    "📎 **Шаг 2 из 3: Загрузите фото свидетельства о постановке на налоговый учет (ИНН)**\n\n"
                    "Пожалуйста, прикрепите ОДНУ фотографию свидетельства ИНН.",
                    reply_markup=ReplyKeyboardRemove()
                )
        else:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, отправьте фотографию свидетельства ОГРН.",
                reply_markup=ReplyKeyboardRemove()
            )

    # Шаг 2: Загрузка фото свидетельства ИНН
    @bot.message_handler(
        content_types=['photo'],
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_inn_photo', 'waiting_for_company_partial_inn_photo', 'waiting_for_editing_company_inn_photo'])
    def handle_company_inn_photo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        print('Обработка фото свидетельства ИНН')

        # Сохраняем file_id для свидетельства ИНН
        if message.photo:
            file_id = message.photo[-1].file_id

            # Сохраняем в отложенные документы
            if 'pending_documents' not in company_temp_data[user_id]:
                company_temp_data[user_id]['pending_documents'] = []

            company_temp_data[user_id]['pending_documents'].append({
                'file_id': file_id,
                'type': 'company_inn'
            })
            company_temp_data[user_id]['company_documents']['inn_certificate'] = True

            # Переходим к следующему шагу
            if get_user_state(user_id) == 'waiting_for_editing_company_inn_photo':
                set_user_state(user_id, 'waiting_for_editing_company_charter_photo')
                bot.send_message(
                    chat_id,
                    "✅ **Свидетельство ИНН сохранено!**\n\n"
                    "📎 **Шаг 3 из 3: Загрузите фото устава компании (первая страница)**\n\n"
                    "Пожалуйста, прикрепите ОДНУ фотографию первой страницы устава компании.",
                    reply_markup=ReplyKeyboardRemove()
                )
            elif get_user_state(user_id) == 'waiting_for_company_partial_inn_photo':
                set_user_state(user_id, 'waiting_for_company_partial_charter_photo')
                bot.send_message(
                    chat_id,
                    "✅ **Свидетельство ИНН сохранено!**\n\n"
                    "📎 **Шаг 3 из 3: Загрузите фото устава компании (первая страница)**\n\n"
                    "Пожалуйста, прикрепите ОДНУ фотографию первой страницы устава компании.",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                set_user_state(user_id, 'waiting_for_company_charter_photo')
                bot.send_message(
                    chat_id,
                    "✅ **Свидетельство ИНН сохранено!**\n\n"
                    "📎 **Шаг 3 из 3: Загрузите фото устава компании (первая страница)**\n\n"
                    "Пожалуйста, прикрепите ОДНУ фотографию первой страницы устава компании.",
                    reply_markup=ReplyKeyboardRemove()
                )
        else:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, отправьте фотографию свидетельства ИНН.",
                reply_markup=ReplyKeyboardRemove()
            )

    # Шаг 3: Загрузка фото устава компании
    @bot.message_handler(
        content_types=['photo'],
        func=lambda message: get_user_state(message.from_user.id) in ['waiting_for_company_charter_photo', 'waiting_for_company_partial_charter_photo', "waiting_for_editing_company_charter_photo"])
    def handle_company_charter_photo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        print('Обработка фото устава компании')

        # Сохраняем file_id для устава
        if message.photo:
            file_id = message.photo[-1].file_id

            # Сохраняем в отложенные документы
            if 'pending_documents' not in company_temp_data[user_id]:
                company_temp_data[user_id]['pending_documents'] = []

            company_temp_data[user_id]['pending_documents'].append({
                'file_id': file_id,
                'type': 'company_charter'
            })
            company_temp_data[user_id]['company_documents']['charter'] = True

            # Все документы загружены, переходим к сводке
            bot.send_message(
                chat_id,
                "✅ **Все документы компании успешно загружены!**\n\n"
                "Переходим к проверке данных...",
                reply_markup=ReplyKeyboardRemove()
            )
            show_company_summary(bot, user_id, chat_id)
        else:
            bot.send_message(
                chat_id,
                "❌ Пожалуйста, отправьте фотографию устава компании.",
                reply_markup=ReplyKeyboardRemove()
            )

    # Обработчики кнопки "Назад" для каждого этапа
    @bot.message_handler(
        func=lambda message: get_user_state(
            message.from_user.id) in ['waiting_for_company_ogrn_photo',
                                      'waiting_for_editing_company_ogrn_photo'] and message.text == "⬅️ Назад")
    def handle_back_from_ogrn_photo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if get_user_state(user_id) == 'waiting_for_editing_company_ogrn_photo':
            set_user_state(user_id, 'waiting_for_company_confirmation')
            show_company_summary(bot, user_id, chat_id)
        else:
            # Возвращаемся к выбору загрузки документов
            set_user_state(user_id, 'waiting_for_company_documents_upload')
            bot.send_message(
                chat_id,
                "📎 **Загрузка документов компании**\n\n"
                "Прикрепите фото следующих документов:\n"
                "• Свидетельство о регистрации (ОГРН)\n"
                "• Свидетельство о постановке на налоговый учет (ИНН)\n"
                "• Устав компании (первая страница)\n\n"
                "Нажмите '📎 Загрузить документы', чтобы продолжить.",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(
        func=lambda message: get_user_state(
            message.from_user.id) in ['waiting_for_company_inn_photo',
                                      'waiting_for_editing_company_inn_photo'] and message.text == "⬅️ Назад")
    def handle_back_from_inn_photo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Возвращаемся к загрузке ОГРН
        if get_user_state(user_id) == 'waiting_for_editing_company_inn_photo':
            set_user_state(user_id, 'waiting_for_editing_company_ogrn_photo')
        else:
            set_user_state(user_id, 'waiting_for_company_ogrn_photo')
        bot.send_message(
            chat_id,
            "📎 **Шаг 1 из 3: Загрузите фото свидетельства о регистрации (ОГРН)**\n\n"
            "Пожалуйста, прикрепите ОДНУ фотографию свидетельства ОГРН.",
            reply_markup=get_back_keyboard()
        )

    @bot.message_handler(
        func=lambda message: get_user_state(
            message.from_user.id) in ['waiting_for_company_charter_photo',
                                      'waiting_for_editing_company_charter_photo'] and message.text == "⬅️ Назад")
    def handle_back_from_charter_photo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Возвращаемся к загрузке ИНН
        if get_user_state(user_id) == 'waiting_for_editing_company_charter_photo':
            set_user_state(user_id, 'waiting_for_editing_company_inn_photo')
        else:
            set_user_state(user_id, 'waiting_for_company_inn_photo')
        bot.send_message(
            chat_id,
            "✅ **Свидетельство ОГРН сохранено!**\n\n"
            "📎 **Шаг 2 из 3: Загрузите фото свидетельства о постановке на налоговый учет (ИНН)**\n\n"
            "Пожалуйста, прикрепите ОДНУ фотографию свидетельства ИНН.",
            reply_markup=get_back_keyboard()
        )

    # Добавляем новую функцию для создания клавиатуры загрузки документов
    def get_documents_upload_keyboard():
        from telebot.types import ReplyKeyboardMarkup, KeyboardButton

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row(KeyboardButton("📎 Загрузить документы"))
        keyboard.row(KeyboardButton("⬅️ Назад"))

        return keyboard

    def show_next_document_prompt(bot, user_id, chat_id):
        """Показывает запрос на следующий документ"""
        documents = company_temp_data[user_id]['company_documents']

        if documents['ogrn_certificate'] is None:
            bot.send_message(
                chat_id,
                "✅ Свидетельство ОГРН сохранено.\n\n"
                "Теперь отправьте фото свидетельства ИНН:",
                reply_markup=get_back_keyboard()
            )
        elif documents['inn_certificate'] is None:
            bot.send_message(
                chat_id,
                "✅ Свидетельство ИНН сохранено.\n\n"
                "Теперь отправьте фото устава компании (первая страница):",
                reply_markup=get_back_keyboard()
            )
        elif documents['charter'] is None:
            bot.send_message(
                chat_id,
                "✅ Устав компании сохранен.\n\n"
                "Ожидаем загрузку предыдущих документов...",
                reply_markup=get_back_keyboard()
            )
        else:
            # Все документы загружены
            bot.send_message(
                chat_id,
                "✅ Все документы компании успешно сохранены!\n\n"
                "Переходим к проверке данных...",
                reply_markup=ReplyKeyboardRemove()
            )
            show_company_summary(bot, user_id, chat_id)

    def cleanup_old_media_groups():
        """Очистка старых записей о media_group (старше 5 минут)"""
        current_time = time.time()
        # Создаем копию ключей для безопасного удаления
        keys_to_remove = [key for key, timestamp in processed_media_groups.items()
                          if current_time - timestamp > 300]  # 5 минут

        for key in keys_to_remove:
            del processed_media_groups[key]
        if keys_to_remove:
            print(f"Очищено {len(keys_to_remove)} старых media_group записей")

    def delete_company_documents(company_id):
        """Удаляет все документы компании из файловой системы и БД"""
        try:
            folder_path = f"data/documents/companies/{company_id}"

            # Удаляем файлы из папки
            if os.path.exists(folder_path):
                deleted_files = []
                for filename in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            deleted_files.append(filename)
                            print(f"Удален файл: {filename}")
                    except Exception as e:
                        print(f"Ошибка при удалении файла {filename}: {e}")

                # Удаляем записи из БД
                db.execute_query("DELETE FROM company_documents WHERE company_id = ?", (company_id,))

                print(f"Удалено {len(deleted_files)} файлов для компании {company_id}")
                return True

            return False

        except Exception as e:
            print(f"Ошибка при удалении документов компании {company_id}: {e}")
            return False

    def save_pending_company_documents(bot, user_id, company_id):
        """Сохраняет отложенные документы компании после создания компании в БД"""
        if user_id not in company_temp_data or 'pending_documents' not in company_temp_data[user_id]:
            return True

        pending_docs = company_temp_data[user_id]['pending_documents']
        success_count = 0

        for doc in pending_docs:
            try:
                success = save_and_compress_company_photos(
                    bot,
                    doc['file_id'],
                    doc['type'],
                    company_id
                )
                if success:
                    success_count += 1
            except Exception as e:
                logging.error(f"Ошибка при сохранении отложенного документа: {e}")

        # Удаляем обработанные документы
        del company_temp_data[user_id]['pending_documents']

        return success_count == len(pending_docs)

    def save_and_compress_company_photos(bot, file_ids, document_types, company_id):
        """Сохранение и сжатие фото документов компании с привязкой к company_id"""
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

                # Создаем папку для документов компании
                company_folder = f"data/documents/companies/{company_id}"
                os.makedirs(company_folder, exist_ok=True)

                # Генерируем уникальное имя файла для сжатого изображения
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")  # Добавим микросекунды для уникальности
                filename = f"{doc_type}_{timestamp}_compressed.jpg"
                compressed_path = os.path.join(company_folder, filename)

                # Сжимаем фото и сохраняем сразу в сжатом виде
                success = compress_and_save_image(downloaded_file, compressed_path)

                if success:
                    # Сохраняем информацию о документе компании с привязкой к company_id
                    db.add_company_document(company_id, doc_type, compressed_path)
                    results.append(True)
                    print(f"Сохранен документ: {doc_type} -> {filename}")
                else:
                    results.append(False)

            except Exception as e:
                logging.error(f"Ошибка при сохранении документа компании {i} ({doc_type}): {e}")
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
            return True

        except Exception as e:
            logging.error(f"Ошибка при сжатии изображения: {e}")
            return False

    def show_company_summary(bot, user_id, chat_id):
        """Показывает сводку данных компании с возможностью редактирования"""

        data = company_temp_data[user_id]

        company_type_map = {
            'legal': 'Юридическое лицо',
            'individual': 'Индивидуальный предприниматель',
            'self_employed': 'Самозанятый'
        }

        tax_system_display_map = {
            'osn': 'ОСНО',
            'usn': 'УСН',
            'eshn': 'ЕСХН',
            'psn': 'ПСН',
            'npd': 'НПД',
            'ausn': 'АУСН'
        }

        # Добавляем банковские реквизиты в сводку
        bank_details_text = ""
        if 'bik' in data:
            bank_details_text = f"""
    🏦 **Банковские реквизиты:**
    **БИК:** {data.get('bik')}
    **Расчетный счет:** {data.get('payment_account')}
    **Корреспондентский счет:** {data.get('correspondent_account')}
    **ОКПО:** {data.get('okpo', 'Не указан')}
    """

        # Добавляем информацию о документах
        documents_text = ""
        company_documents = data.get('company_documents', {})
        if (company_documents.get('ogrn_certificate') and
                company_documents.get('inn_certificate') and
                company_documents.get('charter')):
            documents_text = "\n📎 **Документы:** все документы загружены"
        elif (company_documents.get('ogrn_certificate') or
              company_documents.get('inn_certificate') or
              company_documents.get('charter')):
            documents_text = "\n📎 **Документы:** частично загружены"
        else:
            documents_text = "\n📎 **Документы:** не загружены"

        summary_text = f"""
    📋 **Проверьте введенные данные:**

    🏢 **Данные компании:**
    **Название:** {data['name']}
    **Тип:** {company_type_map.get(data['company_type'], data['company_type'])}
    **ИНН:** {data.get('inn', 'Не указан')}
    **КПП:** {data.get('kpp', 'Не указан')}
    **ОГРН:** {data.get('ogrn', 'Не указан')}

    👤 **Руководитель:** {data.get('management_name', 'Не указан')}
   

    📍 **Юридический адрес:** {data.get('address', 'Не указан')}
    📞 **Контактный телефон:** {data.get('contact_phone', 'Не указан')}
    📧 **Email:** {data.get('contact_email', 'Не указан')}
    {bank_details_text}
    📝 **Примечание:** {data.get('note', 'Не указано')}
    {documents_text}

    Если все данные верны, нажмите "✅ Подтвердить регистрацию".
    Если нужно что-то изменить, выберите поле для редактирования.
            """

        # Создаем клавиатуру для редактирования
        keyboard = get_edit_company_keyboard(data.get('company_type'))

        set_user_state(user_id, 'waiting_for_company_confirmation')
        bot.send_message(
            chat_id,
            summary_text,
            reply_markup=keyboard,
        )


    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_company_confirmation')
    def handle_company_confirmation(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "✅ Подтвердить регистрацию":
            complete_company_registration(bot, db, user_id, chat_id)

        # Обработка кнопок редактирования
        elif message.text == "✏️ Редактировать название":
            set_user_state(user_id, 'editing_company_name')
            bot.send_message(
                chat_id,
                f"Текущее название: {company_temp_data[user_id]['name']}\nВведите новое название:",
                reply_markup=get_back_keyboard()
            )

        elif message.text == "✏️ Редактировать ИНН":
            set_user_state(user_id, 'editing_company_inn')
            bot.send_message(
                chat_id,
                f"Текущий ИНН: {company_temp_data[user_id]['inn']}\nВведите новый ИНН:",
                reply_markup=get_back_keyboard()
            )

        elif message.text == "✏️ Редактировать КПП":
            set_user_state(user_id, 'editing_company_kpp')
            bot.send_message(
                chat_id,
                f"Текущий КПП: {company_temp_data[user_id].get('kpp', 'Не указан')}\nВведите новый КПП:",
                reply_markup=get_back_keyboard()
            )

        elif message.text == "✏️ Редактировать ФИО директора":
            set_user_state(user_id, 'editing_company_management_name')
            bot.send_message(
                chat_id,
                f"Текущая фамилия директора: {company_temp_data[user_id]['management_name']}\nВведите новую фамилию:",
                reply_markup=get_back_keyboard()
            )

        elif message.text == "✏️ Редактировать ОГРН":
            set_user_state(user_id, 'editing_company_ogrn')
            bot.send_message(
                chat_id,
                f"Текущий ОГРН: {company_temp_data[user_id]['ogrn']}\nВведите новый ОГРН:",
                reply_markup=get_back_keyboard()
            )

        elif message.text == "✏️ Редактировать адрес":
            set_user_state(user_id, 'editing_company_address')
            bot.send_message(
                chat_id,
                f"Текущий адрес: {company_temp_data[user_id]['address']}\nВведите новый адрес:",
                reply_markup=get_back_keyboard()
            )

        elif message.text == "✏️ Редактировать контакты":
            set_user_state(user_id, 'editing_company_contacts')
            bot.send_message(
                chat_id,
                f"Текущие контакты:\nТелефон: {company_temp_data[user_id]['contact_phone']}\nEmail: {company_temp_data[user_id]['contact_email']}\nВыберите что редактировать:",
                reply_markup=get_edit_contacts_keyboard()
            )

        elif message.text == "✏️ Редактировать банковские реквизиты":
            set_user_state(user_id, 'editing_company_bank')
            bot.send_message(
                chat_id,
                "Выберите банковский реквизит для редактирования:",
                reply_markup=get_edit_bank_keyboard()
            )

        elif message.text == "📎 Редактировать документы":

            company_id = None
            if user_id in company_temp_data and 'id' in company_temp_data[user_id]:
                company_id = company_temp_data[user_id]['id']

            # Если компания уже создана (редактирование существующей), удаляем старые документы
            if company_id:
                delete_company_documents(company_id)

            # Очищаем старые отложенные документы перед началом редактирования
            if user_id in company_temp_data and 'pending_documents' in company_temp_data[user_id]:
                del company_temp_data[user_id]['pending_documents']

            # Сбрасываем флаги загруженных документов
            if 'company_documents' in company_temp_data[user_id]:
                company_temp_data[user_id]['company_documents'] = {
                    'ogrn_certificate': None,
                    'inn_certificate': None,
                    'charter': None
                }

            set_user_state(user_id, 'waiting_for_editing_company_documents_upload')
            bot.send_message(
                chat_id,
                "📎 **Загрузка документов компании**\n\n"
                "Прикрепите фото следующих документов:\n"
                "• Свидетельство о регистрации (ОГРН)\n"
                "• Свидетельство о постановке на налоговый учет (ИНН)\n"
                "• Устав компании (первая страница)\n\n"
                "Нажмите '📎 Загрузить документы', чтобы продолжить.",
                reply_markup=get_documents_upload_keyboard()
            )

        elif message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            set_user_state(user_id, 'waiting_for_company_confirmation')

    # Обработчики редактирования полей
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_name')
    def handle_editing_company_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, 'Название компании не может быть пустым. Введите название:')
            return

        company_temp_data[user_id]['name'] = message.text.strip()
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_inn')
    def handle_editing_company_inn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return

        inn = message.text.strip()
        if not inn.isdigit():
            bot.send_message(chat_id, 'ИНН должен содержать только цифры. Введите ИНН:')
            return

        company_type = company_temp_data[user_id].get('company_type')
        if company_type == 'legal' and len(inn) != 10:
            bot.send_message(chat_id, 'ИНН юридического лица должен содержать 10 цифр. Введите ИНН:')
            return
        elif company_type in ['individual', 'self_employed'] and len(inn) != 12:
            bot.send_message(chat_id,
                             'ИНН индивидуального предпринимателя/самозанятого должен содержать 12 цифр. Введите ИНН:')
            return

        company_temp_data[user_id]['inn'] = inn
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_kpp')
    def handle_editing_company_kpp(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return

        kpp = message.text.strip()
        if not kpp.isdigit() or len(kpp) != 9:
            bot.send_message(chat_id, 'КПП должен содержать 9 цифр. Введите КПП:')
            return

        company_temp_data[user_id]['kpp'] = kpp
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(
        func=lambda message: get_user_state(message.from_user.id) == 'editing_company_management_name')
    def handle_editing_company_management_name(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, 'Фамилия не может быть пустой. Введите фамилию директора:')
            return

        company_temp_data[user_id]['management_name'] = message.text.strip()
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_address')
    def handle_editing_company_address(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return

        if not message.text.strip():
            bot.send_message(chat_id, 'Адрес не может быть пустым. Введите юридический адрес:')
            return

        company_temp_data[user_id]['address'] = message.text.strip()
        show_company_summary(bot, user_id, chat_id)

    # Обработчики для редактирования контактов
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_contacts')
    def handle_editing_company_contacts(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return
        elif message.text == "📞 Редактировать телефон":
            set_user_state(user_id, 'editing_company_phone')
            bot.send_message(
                chat_id,
                f"Текущий телефон: {company_temp_data[user_id]['contact_phone']}\nВведите новый телефон:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "📧 Редактировать email":
            set_user_state(user_id, 'editing_company_email')
            bot.send_message(
                chat_id,
                f"Текущий email: {company_temp_data[user_id]['contact_email']}\nВведите новый email:",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_phone')
    def handle_editing_company_phone(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_company_contacts')
            bot.send_message(
                chat_id,
                "Выберите контакт для редактирования:",
                reply_markup=get_edit_contacts_keyboard()
            )
            return

        phone = message.text.strip()
        if len(phone) < 10:
            bot.send_message(chat_id, 'Номер телефона слишком короткий. Введите корректный номер:')
            return

        company_temp_data[user_id]['contact_phone'] = phone
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_ogrn')
    def handle_editing_company_ogrn(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return

        ogrn = message.text.strip()
        if not ogrn.isdigit():
            bot.send_message(chat_id, 'ОГРН должен содержать только цифры. Введите ОГРН:')
            return

        company_type = company_temp_data[user_id].get('company_type')
        if company_type == 'legal' and len(ogrn) != 13:
            bot.send_message(chat_id, 'ОГРН юридического лица должен содержать 13 цифр. Введите ОГРН:')
            return
        elif company_type == 'individual' and len(ogrn) != 15:
            bot.send_message(chat_id, 'ОГРНИП должен содержать 15 цифр. Введите ОГРНИП:')
            return

        company_temp_data[user_id]['ogrn'] = ogrn
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_email')
    def handle_editing_company_email(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            set_user_state(user_id, 'editing_company_contacts')
            bot.send_message(
                chat_id,
                "Выберите контакт для редактирования:",
                reply_markup=get_edit_contacts_keyboard()
            )
            return

        email = message.text.strip()
        if '@' not in email or '.' not in email:
            bot.send_message(chat_id, 'Введите корректный email адрес:')
            return

        company_temp_data[user_id]['contact_email'] = email
        show_company_summary(bot, user_id, chat_id)

    # Обработчики для редактирования банковских реквизитов
    @bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'editing_company_bank')
    def handle_editing_company_bank(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)
            return
        elif message.text == "🏦 Редактировать БИК":
            set_user_state(user_id, 'editing_company_bik')
            bot.send_message(
                chat_id,
                f"Текущий БИК: {company_temp_data[user_id]['bik']}\nВведите новый БИК:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "🏦 Редактировать расчетный счет":
            set_user_state(user_id, 'editing_company_payment_account')
            bot.send_message(
                chat_id,
                f"Текущий расчетный счет: {company_temp_data[user_id]['payment_account']}\nВведите новый расчетный счет:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "🏦 Редактировать корр. счет":
            set_user_state(user_id, 'editing_company_correspondent_account')
            bot.send_message(
                chat_id,
                f"Текущий корреспондентский счет: {company_temp_data[user_id]['correspondent_account']}\nВведите новый корреспондентский счет:",
                reply_markup=get_back_keyboard()
            )
        elif message.text == "🏦 Редактировать ОКПО":
            set_user_state(user_id, 'editing_company_okpo')
            bot.send_message(
                chat_id,
                f"Текущий ОКПО: {company_temp_data[user_id].get('okpo', 'Не указан')}\nВведите новый ОКПО:",
                reply_markup=get_back_keyboard()
            )

    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'editing_company_bik' and message.text)
    def handle_editing_company_bik(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == '⬅️ Назад':
            show_company_summary(bot, user_id, chat_id)
            return

        bik = message.text.strip()
        if not (bik.isdigit() and len(bik) == 9):
            bot.send_message(chat_id, '❌ БИК должен содержать 9 цифр. Введите БИК:')
            return

        company_temp_data[user_id]['bik'] = bik
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'editing_company_payment_account' and message.text)
    def handle_editing_company_payment_account(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == '⬅️ Назад':
            show_company_summary(bot, user_id, chat_id)
            return

        payment_account = message.text.strip()
        if not (payment_account.isdigit() and len(payment_account) == 20):
            bot.send_message(chat_id, '❌ Расчетный счет должен содержать 20 цифр. Введите расчетный счет:')
            return

        company_temp_data[user_id]['payment_account'] = payment_account
        show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'editing_company_correspondent_account' and message.text)
    def handle_editing_company_correspondent_account(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == '⬅️ Назад':
            show_company_summary(bot, user_id, chat_id)
            return

        correspondent_account = message.text.strip()
        if not (correspondent_account.isdigit() and len(correspondent_account) == 20):
            bot.send_message(chat_id, '❌ Корреспондентский счет должен содержать 20 цифр. Введите расчетный счет:')
            return

        company_temp_data[user_id]['correspondent_account'] = correspondent_account
        show_company_summary(bot, user_id, chat_id)


    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'editing_company_okpo' and message.text)
    def handle_editing_company_okpo(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        if message.text == '⬅️ Назад':
            show_company_summary(bot, user_id, chat_id)
            return
        okpo = message.text.strip()
        if not (okpo.isdigit() and len(okpo) in [8, 10]):
            bot.send_message(chat_id,
                             '❌ Код ОКПО должен содержать 8 или 10 цифр. Попробуйте еще раз или пропустите:')
            return
        company_temp_data[user_id]['okpo'] = okpo

        show_company_summary(bot, user_id, chat_id)


    @bot.message_handler(func=lambda message: get_user_state(
        message.from_user.id) == 'waiting_for_editing_company_documents_upload' and message.text)
    def handle_editing_company_documents_text(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.text == "⬅️ Назад":
            show_company_summary(bot, user_id, chat_id)

    @bot.message_handler(content_types=['photo'], func=lambda message: get_user_state(
        message.from_user.id) == 'waiting_for_editing_company_documents_upload')
    def handle_editing_company_documents(message):
        """Обработка фото документов компании с защитой от множественных срабатываний"""

        # Проверяем media_group_id для групповых отправок фото
        media_group_id = message.media_group_id

        if media_group_id:
            # Если эта группа медиа уже обрабатывалась - пропускаем
            if processed_media_groups[media_group_id]:
                print(f"Пропускаем повторную обработку media_group: {media_group_id}")
                return

            # Помечаем группу как обработанную
            processed_media_groups[media_group_id] = True
            print(f"Обрабатываем media_group: {media_group_id}")

        print('Запущен обработчик фото документов компании')
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Получаем текущие данные пользователя
        if user_id not in company_temp_data:
            company_temp_data[user_id] = {}

        if 'company_documents' not in company_temp_data[user_id]:
            company_temp_data[user_id]['company_documents'] = {
                'ogrn_certificate': None,
                'inn_certificate': None,
                'charter': None
            }

        if 'id' in company_temp_data[user_id]:
            company_id = company_temp_data[user_id]['id']
            delete_company_documents(company_id)

        # Очищаем старые записи media_group (старше 5 минут)
        cleanup_old_media_groups()

        # Обрабатываем фото
        if message.photo:
            photos_count = len(message.photo)
            photos_count = len(message.photo)
            print(f"Получено фото документов компании: {photos_count} шт.")

            if photos_count >= 3:
                # Пользователь отправил все три фото сразу
                file_id_ogrn = message.photo[-3].file_id  # Первое фото
                file_id_inn = message.photo[-2].file_id  # Второе фото
                file_id_charter = message.photo[-1].file_id  # Третье фото

                # Сохраняем все три фото за один вызов
                # Временно сохраняем file_ids для последующего сохранения после создания компании
                if 'pending_documents' not in company_temp_data[user_id]:
                    company_temp_data[user_id]['pending_documents'] = []

                company_temp_data[user_id]['pending_documents'].extend([
                    {'file_id': file_id_ogrn, 'type': 'company_ogrn'},
                    {'file_id': file_id_inn, 'type': 'company_inn'},
                    {'file_id': file_id_charter, 'type': 'company_charter'}
                ])

                company_temp_data[user_id]['company_documents']['ogrn_certificate'] = True
                company_temp_data[user_id]['company_documents']['inn_certificate'] = True
                company_temp_data[user_id]['company_documents']['charter'] = True

                bot.send_message(
                    chat_id,
                    "✅ Все документы компании получены и будут сохранены после регистрации!\n\n"
                    "Переходим к проверке данных...",
                    reply_markup=ReplyKeyboardRemove()
                )
                # Показываем сводку с документами
                show_company_summary(bot, user_id, chat_id)

            else:
                # Пользователь отправил одно или два фото
                file_id = message.photo[-1].file_id

                # Определяем, какое фото еще не загружено
                documents = company_temp_data[user_id]['company_documents']

                if documents['ogrn_certificate'] is None:
                    # Сохраняем file_id для последующего сохранения
                    if 'pending_documents' not in company_temp_data[user_id]:
                        company_temp_data[user_id]['pending_documents'] = []
                    company_temp_data[user_id]['pending_documents'].append({
                        'file_id': file_id,
                        'type': 'company_ogrn'
                    })
                    company_temp_data[user_id]['company_documents']['ogrn_certificate'] = True
                    show_next_document_prompt(bot, user_id, chat_id)

                elif documents['inn_certificate'] is None:
                    if 'pending_documents' not in company_temp_data[user_id]:
                        company_temp_data[user_id]['pending_documents'] = []
                    company_temp_data[user_id]['pending_documents'].append({
                        'file_id': file_id,
                        'type': 'company_inn'
                    })
                    company_temp_data[user_id]['company_documents']['inn_certificate'] = True
                    show_next_document_prompt(bot, user_id, chat_id)

                elif documents['charter'] is None:
                    if 'pending_documents' not in company_temp_data[user_id]:
                        company_temp_data[user_id]['pending_documents'] = []
                    company_temp_data[user_id]['pending_documents'].append({
                        'file_id': file_id,
                        'type': 'company_charter'
                    })
                    company_temp_data[user_id]['company_documents']['charter'] = True
                    show_next_document_prompt(bot, user_id, chat_id)
                else:
                    # Все документы уже загружены
                    bot.send_message(
                        chat_id,
                        "✅ Все документы уже получены. Переходим к проверке данных...",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    show_company_summary(bot, user_id, chat_id)

    def complete_company_registration(bot, db, user_id, chat_id):
        """Завершение регистрации компании и сохранение всех данных"""
        try:
            company_data = company_temp_data[user_id].copy()
            company_data['status'] = 'pending'
            company_data['created_by'] = user_id
            company = ''
            print()

            company = db.get_company_by_id(company_temp_data[user_id].get('id', None))
            if company:
                print('Компания уже есть в базе данных, обновляем запись')
                print(company_data)
                success = db.edit_company(company_data)
                company_info = db.get_company_by_id(company_temp_data[user_id]['id'])
                company_id = company_info['id']
            else:
                print('Компании нет в БД, создаем новую запись')
                print(company_data)
                company_id = db.create_company(company_data)

            success = db.execute_query(
                """INSERT INTO company_bank_details 
                (company_id, bik, payment_account, correspondent_account, okpo) 
                VALUES (?, ?, ?, ?, ?)""",
                (
                    company_id,
                    company_temp_data[user_id]['bik'],
                    company_temp_data[user_id]['payment_account'],
                    company_temp_data[user_id]['correspondent_account'],
                    company_temp_data[user_id].get('okpo')
                ))

            if not success:
                print("Не удалось сохранить банковские реквизиты")

            # Сохраняем отложенные документы компании
            documents_saved = True
            if 'pending_documents' in company_temp_data[user_id]:
                documents_saved = save_pending_company_documents(bot, user_id, company_id)

            # Отправляем данные админам ТОЛЬКО после сохранения документов
            send_company_to_admins(bot, db, company_id)

            # Очищаем временные данные
            if user_id in company_temp_data:
                del company_temp_data[user_id]

            set_user_state(user_id, '')
            if documents_saved:
                bot.send_message(
                    chat_id,
                    "✅ Компания успешно зарегистрирована и отправлена на модерацию!\n\nВсе документы сохранены.\n\nПосле проверки администратором вы получите уведомление.",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                bot.send_message(
                    chat_id,
                    "✅ Компания успешно зарегистрирована и отправлена на модерацию!\n\n⚠️ Некоторые документы не удалось сохранить.\n\nПосле проверки администратором вы получите уведомление.",
                    reply_markup=ReplyKeyboardRemove()
                )

        except Exception as e:
            print(f"Ошибка при регистрации компании: {e}")
            bot.send_message(
                chat_id,
                '❌ Произошла ошибка при регистрации компании. Пожалуйста, попробуйте позже.'
            )
    def send_company_to_admins(bot, db, company_id):
        try:
            company = db.get_company_by_id(company_id)
            if not company:
                return

            admins = db.get_all_admins()

            if not admins:
                print("Не найдены администраторы для отправки заявки")
                return

            bank_details = db.fetch_one('select * from company_bank_details where company_id = ?', (company_id,))

            # Получаем документы компании
            company_documents = db.fetch_all(
                "SELECT * FROM company_documents WHERE company_id = ? ORDER BY document_type",
                (company_id,)
            )

            bank_details_text = ""
            if bank_details:
                bank_details_text = f"""
    🏦 **Банковские реквизиты:**
    **БИК:** {bank_details.get('bik', 'Не указан')}
    **Расчетный счет:** {bank_details.get('payment_account', 'Не указан')}
    **Корреспондентский счет:** {bank_details.get('correspondent_account', 'Не указан')}
    **ОКПО:** {bank_details.get('okpo', 'Не указан')}
    """

            message_text = format_company_moderation_message(company, bank_details_text)

            email_subject = "👤 Модерация новой компании"
            email_message = f"""🆕 **НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ КОМПАНИИ**

    **Данные компании:**
    • Название: {company.get('name', 'Не указано')}
    • Тип: {company_type_map.get(company.get('company_type'), company.get('company_type', 'Не указан'))}
    • ИНН: {company.get('inn', 'Не указан')}
    • КПП: {company.get('kpp', 'Не указан')}
    • ОГРН: {company.get('ogrn', 'Не указан')}

    **Руководитель:**
    • ФИО: {company.get('management_name', '')}

    **Юридический адрес:** {company.get('address', 'Не указан')}
    **Телефон:** {company.get('contact_phone', 'Не указан')}
    **Email:** {company.get('contact_email', 'Не указан')}

    {bank_details_text if bank_details else ''}

    В чате с ботом вы найдете фотографии документов.
    Откройте чат с Телеграм-ботом, чтобы принять или отклонить регистрацию.
    """

            for admin in admins:
                try:
                    # Отправляем email уведомление
                    send_email_notification(email_subject, email_message, admin.get('email'))
                    send_company_documents_photos_single(bot, admin.get('telegram_id'), company_id)

                    # Отправляем текстовое сообщение с данными компании
                    bot.send_message(
                        admin.get('telegram_id'),
                        message_text,
                        reply_markup=get_approve_reject_company_keyboard(company_id),
                    )

                    # Отправляем фотографии документов, если они есть
                    # Добавляем в очередь модерации
                    add_pending_moderation('company_registration', company_id)

                except Exception as e:
                    print(f"Ошибка при отправке сообщения администратору {admin.get('telegram_id', 'Unknown')}: {e}")

        except Exception as e:
            print(f"Ошибка при отправке заявки администраторам: {e}")

    def send_company_documents_photos_single(bot, chat_id, company_id, max_photos=10):
        """Отправляет все документы компании одной медиагруппой"""
        from telebot.types import InputMediaPhoto

        folder_path = f"data/documents/companies/{company_id}"

        try:
            if not os.path.exists(folder_path):
                bot.send_message(chat_id, "❌ Папка с документами компании не найдена")
                return False

            # Ищем все файлы документов
            photo_extensions = ('*.jpg', '*.jpeg', '*.png')
            all_documents = []

            for extension in photo_extensions:
                all_documents.extend(glob.glob(os.path.join(folder_path, extension)))

            if not all_documents:
                bot.send_message(chat_id, "❌ Нет документов для отправки")
                return False

            # Сортируем документы
            all_documents.sort()
            documents_to_send = all_documents[:max_photos]

            # Сопоставляем типы документов
            document_types_map = {
                'company_ogrn': '📄 ОГРН',
                'company_inn': '📄 ИНН',
                'company_charter': '📄 Устав'
            }

            # Читаем все файлы
            media_group = []
            photo_data = []

            for doc_path in documents_to_send:
                try:
                    with open(doc_path, 'rb') as photo_file:
                        photo_data.append(photo_file.read())
                except Exception as e:
                    print(f"Ошибка при чтении файла {doc_path}: {e}")
                    continue

            # Создаем медиагруппу с подписями
            for i, data in enumerate(photo_data):
                doc_path = documents_to_send[i]
                filename = os.path.basename(doc_path)

                # Определяем тип документа
                doc_type = '📄 Документ'
                for key, value in document_types_map.items():
                    if key in filename.lower():
                        doc_type = value
                        break

                if i == 0:
                    media_group.append(
                        InputMediaPhoto(
                            data,
                            caption=f"{doc_type}\n📁 Документы компании ({len(documents_to_send)} шт.)"
                        )
                    )
                else:
                    media_group.append(
                        InputMediaPhoto(
                            data,
                            caption=doc_type
                        )
                    )

            if media_group:
                bot.send_media_group(chat_id, media_group)
            else:
                bot.send_message(chat_id, "❌ Не удалось загрузить документы")
                return False

            # Сообщение о количестве документов
            total_documents = len(all_documents)
            if total_documents > max_photos:
                bot.send_message(
                    chat_id,
                    f"📋 Показано {max_photos} из {total_documents} документов\n"
                    f"Остальные документы не поместились в одну группу"
                )

            return True

        except Exception as e:
            error_msg = f"❌ Ошибка при отправке документов компании: {str(e)}"
            bot.send_message(chat_id, error_msg)
            print(f"Ошибка при отправке документов компании {company_id}: {e}")
            return False

    def format_company_moderation_message(company, bank_details_text):

        return f"""
        🆕 **НОВАЯ ЗАЯВКА НА РЕГИСТРАЦИЮ КОМПАНИИ**

        🏢 **Данные компании:**
        • Название: {company['name']}
        • Тип: {company_type_map.get(company['company_type'], company['company_type'])}
        • ИНН: {company.get('inn', 'Не указан')}
        • КПП: {company.get('kpp', 'Не указан')}
        • ОГРН: {company.get('ogrn', 'Не указан')}

        👤 **Руководитель:**
        • ФИО: {company.get('management_name', '')}

        📍 **Юридический адрес:** {company.get('address', 'Не указан')}
        📞 **Телефон:** {company.get('contact_phone', 'Не указан')}
        📧 **Email:** {company.get('contact_email', 'Не указан')}
        {bank_details_text}
        ⏰ **Дата подачи заявки:** {company.get('created_at', 'Не указана')}

        Выберите действие:
        """

    # Обработчик отмены регистрации компании
    @bot.message_handler(func=lambda message: message.text == '❌ Отмена регистрации компании')
    def handle_company_registration_cancel(message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        if user_id in company_temp_data:
            del company_temp_data[user_id]

        set_user_state(user_id, '')
        bot.send_message(
            chat_id,
            'Регистрация компании отменена.',
            reply_markup=ReplyKeyboardRemove()
        )

    def get_user_state(user_id):
        """Получить состояние пользователя"""
        return user_states.get(user_id, '')

    def set_user_state(user_id, state):
        """Установить состояние пользователя"""
        user_states[user_id] = state
        print(f"Пользователь {user_id}: новое состояние = {state}")

    def get_available_tax_systems(company_type):
        """Возвращает доступные системы налогообложения для типа компании"""
        if company_type == 'legal':
            return ['ОСНО', 'УСН', 'ЕСХН', 'АУСН']
        elif company_type == 'individual':
            return ['ОСНО', 'УСН', 'ЕСХН', 'ПСН', 'АУСН', 'НПД']
        elif company_type == 'self_employed':
            return ['НПД']
        else:
            return []

    def get_tax_system_keyboard(company_type):
        """Создает клавиатуру для выбора системы налогообложения в зависимости от типа компании"""
        from telebot.types import ReplyKeyboardMarkup, KeyboardButton

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

        available_systems = get_available_tax_systems(company_type)

        for system in available_systems:
            keyboard.add(KeyboardButton(system))

        keyboard.add(KeyboardButton('⬅️ Назад'))

        return keyboard


