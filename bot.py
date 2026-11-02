import telebot
from telebot import types
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from config.config import config
from connect_bitrix.bitrix24 import Bitrix24Client
from database.db import Database
import threading
import time

from handlers.admin_handlers.admin_rates_handlers import register_admin_rates_handlers
from handlers.main_handlers.rates_handlers import register_rates_handlers
from handlers.main_handlers.subscription_handlers import register_subscription_handlers
from utils.subscription_notifier import SubscriptionNotifier
from handlers.admin_handlers.logist_accepted_application_handlers import register_logist_accepted_applications_handlers
from handlers.application_handlers.admin_applications_handlers import register_admin_applications_handlers
from handlers.application_handlers.display_application_handlers import format_application_for_executor
from handlers.application_handlers.logist_completion_handlers import register_logist_completion_handlers
from handlers.application_handlers.urgent_applications_handlers import register_urgent_applications_handlers
from handlers.main_handlers.executor_filter_handlers import register_executor_filter_handlers, \
    register_filter_text_handlers
from handlers.main_handlers.rating_handlers import register_rating_handlers
from handlers.admin_handlers.admin_anomaly_handler import register_admin_anomaly_handlers
from handlers.admin_handlers.admin_manage_executor_handlers import register_executor_admin_handlers
from handlers.admin_handlers.admin_manage_external_handlers import register_external_user_admin_handlers
from handlers.admin_handlers.google_sheets_commands import register_google_sheets_handlers
from handlers.application_handlers.active_applications_handlers import register_active_application_handlers
from handlers.application_handlers.assigned_executor_applications import \
    register_assigned_executor_applications_handlers
from handlers.application_handlers.creation_application_handlers import register_application_handlers
from handlers.application_handlers.executor_application_handlers import register_executor_application_handlers, \
    format_detailed_application, get_cargo_info
from handlers.application_handlers.logist_application_bid_handlers import register_logist_application_bid_handlers
from handlers.main_handlers.common import handle_start, handle_start_registration, handle_registration_confirmation
from handlers.admin_handlers.main_admin_handlers import register_main_admin_handler
from handlers.main_handlers.profile_handlers import register_profile_handlers
from handlers.main_handlers.settings_rating_handlers import register_settings_rating_handlers
from handlers.main_handlers.statistics_handlers import register_statistics_handlers
from handlers.registration_handlers.registration_company_handlers import register_company_handlers
from handlers.registration_handlers.registration_user_handlers import register_user_handlers, set_user_state, \
    get_user_state
from handlers.admin_handlers.admin_moderation_handlers import register_admin_moderation_handlers
from handlers.admin_handlers.admin_manage_logists_handlers import register_logists_admin_handlers
from handlers.main_handlers.settings_company_handlers import register_settings_company_handlers
from handlers.main_handlers.settings_handlers import register_settings_handlers
from keyboards.main_menus import get_start_menu
from utils.scheduler import init_scheduler
from handlers.application_handlers.application_restart import (
    restart_expired_applications
)

bot = telebot.TeleBot(config.BOT_TOKEN)
db = Database(config.DATABASE_PATH)
demo_view_data = {}

# Словарь для хранения ID последних сообщений пользователей
last_messages = {}


# Функция для отправки или редактирования сообщения
def send_or_edit_message(chat_id, user_id, text, reply_markup=None, parse_mode=None):
    """Отправляет новое сообщение или редактирует последнее, если оно существует"""
    if user_id in last_messages:
        try:
            # Пробуем отредактировать существующее сообщение
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=last_messages[user_id],
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return last_messages[user_id]
        except Exception as e:
            # Если не удалось отредактировать (сообщение слишком старое или удалено), удаляем старый ID
            if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                del last_messages[user_id]
            pass

    # Отправляем новое сообщение
    msg = bot.send_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    last_messages[user_id] = msg.message_id
    return msg.message_id


# Сначала общие обработчики
@bot.message_handler(commands=['start'])
def start_command(message):
    set_user_state(message.from_user.id, '')
    # Очищаем сохраненное сообщение при старте
    if message.from_user.id in last_messages:
        del last_messages[message.from_user.id]
    handle_start(bot, message, db)


@bot.message_handler(commands=['help'])
def help_command(message):
    set_user_state(message.from_user.id, '')
    if message.from_user.id in last_messages:
        del last_messages[message.from_user.id]


register_user_handlers(bot, db)
register_company_handlers(bot, db)
register_admin_moderation_handlers(bot, db)
register_logists_admin_handlers(bot, db)
register_executor_admin_handlers(bot, db)
register_main_admin_handler(bot, db)
register_external_user_admin_handlers(bot, db)
register_profile_handlers(bot, db)
register_settings_handlers(bot, db)
register_settings_company_handlers(bot, db)
register_application_handlers(bot, db)
register_executor_application_handlers(bot, db)
register_active_application_handlers(bot, db)
register_assigned_executor_applications_handlers(bot, db)
register_logist_application_bid_handlers(bot, db)
register_admin_anomaly_handlers(bot, db)
register_google_sheets_handlers(bot, db)
register_statistics_handlers(bot, db)
register_logist_accepted_applications_handlers(bot, db)
register_rating_handlers(bot, db)
register_logist_completion_handlers(bot, db)
register_admin_applications_handlers(bot, db)
register_settings_rating_handlers(bot, db)
register_urgent_applications_handlers(bot, db)
register_executor_filter_handlers(bot, db)
register_filter_text_handlers(bot, db)
register_subscription_handlers(bot, db)
register_rates_handlers(bot, db)
register_admin_rates_handlers(bot, db)

scheduler = init_scheduler(bot, db)
try:
    restart_expired_applications(bot, db)
except Exception as e:
    print(f"❌ Ошибка при стартовой проверке заявок: {e}")


def run_subscription_checker(bot, db):
    notifier = SubscriptionNotifier(db, bot)

    while True:
        try:
            notifier.check_expiring_subscriptions()
        except Exception as e:
            print(f"Ошибка при проверке подписок: {e}")
        time.sleep(24 * 60 * 60)


threading.Thread(target=run_subscription_checker, args=(bot, db), daemon=True).start()


@bot.message_handler(func=lambda message: message.text == "🤖 Посмотреть, как работает бот")
def show_demo_applications(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Очищаем предыдущее сообщение пользователя
    if user_id in last_messages:
        try:
            bot.delete_message(chat_id, last_messages[user_id])
        except:
            pass
        del last_messages[user_id]

    user = db.get_user_by_telegram_id(user_id)
    if user and user.get('status') == 'active':
        from keyboards.main_menus import get_main_menu
        send_or_edit_message(chat_id, user_id, "Вы уже зарегистрированы!", reply_markup=get_main_menu(user.get('role')))
        return

    # Получаем активные заявки
    applications = db.fetch_all("""
        SELECT a.*, u.first_name, u.last_name, u.ati_code, u.phone as logist_phone
        FROM applications a
        JOIN users u ON a.created_by = u.telegram_id
        WHERE a.status = 'active'
        ORDER BY a.created_at DESC
        LIMIT 20
    """)

    if not applications:
        send_or_edit_message(chat_id, user_id, "Активных заявок пока нет. Попробуйте позже.", reply_markup=get_start_menu())
    else:
        send_or_edit_message(
            chat_id,
            user_id,
            "Вот как выглядят новые заявки для перевозчиков:\n\n"
            "Нажмите «Подробно», чтобы увидеть полную информацию по заявке",
            reply_markup=types.ReplyKeyboardRemove()
        )


    # Сохраняем заявки в кэш
    demo_view_data[user_id] = {
        'applications': applications,
        'current_index': 0
    }

    # Отправляем первую заявку
    send_demo_application_page(chat_id, user_id, 0)


def send_demo_application_page(chat_id, user_id, index):
    if user_id not in demo_view_data:
        return

    apps = demo_view_data[user_id]['applications']
    if index < 0 or index >= len(apps):
        return

    demo_view_data[user_id]['current_index'] = index
    app = apps[index]

    # Получаем точки маршрута
    points = db.fetch_all(
        "SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order",
        (app['id'],)
    )

    creator_info = {
        'ati_code': app.get('ati_code', 'Не указан'),
        'first_name': app.get('first_name', ''),
        'last_name': app.get('last_name', '')
    }
    company_info = {'name': 'Логистическая компания'}

    text = format_application_for_executor(app, points, creator_info, company_info)

    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []

    if index > 0:
        buttons.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"demo_prev_{index}"))
    if index < len(apps) - 1:
        buttons.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"demo_next_{index}"))

    if buttons:
        keyboard.row(*buttons)

    keyboard.row(InlineKeyboardButton("📋 Подробно", callback_data=f"demo_view_{app['id']}"))

    # Счетчик
    counter = f"📌 Заявка {index + 1} из {len(apps)}"

    send_or_edit_message(
        chat_id,
        user_id,
        f"*{counter}*\n\n" + text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('demo_prev_') or call.data.startswith('demo_next_'))
def handle_demo_navigation(call):
    user_id = call.from_user.id
    if user_id not in demo_view_data:
        bot.answer_callback_query(call.id, "Сессия истекла")
        return

    direction = call.data.split('_')[1]
    current_index = int(call.data.split('_')[2])
    apps_count = len(demo_view_data[user_id]['applications'])

    new_index = current_index - 1 if direction == 'prev' else current_index + 1

    if new_index < 0 or new_index >= apps_count:
        bot.answer_callback_query(call.id)
        return

    # Просто обновляем страницу через нашу функцию
    send_demo_application_page(call.message.chat.id, user_id, new_index)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('demo_view_'))
def handle_demo_view_detail(call):
    user_id = call.from_user.id
    app_id = int(call.data.split('_')[2])

    application = db.fetch_one(
        "SELECT a.*, u.phone as logist_phone, u.email as logist_email FROM applications a JOIN users u ON a.created_by = u.telegram_id WHERE a.id = ?",
        (app_id,))
    if not application:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return

    cargo_info = get_cargo_info(application)

    # Получаем контактные данные логиста
    logist_info = db.fetch_one(
        "SELECT * FROM users WHERE telegram_id = ?",
        (application['created_by'],)
    )

    points = db.fetch_all("SELECT * FROM application_points WHERE application_id = ? ORDER BY point_order", (app_id,))
    loading_points = [p for p in points if p['point_type'] == 'loading']
    unloading_points = [p for p in points if p['point_type'] == 'unloading']

    detailed_text = format_detailed_application(db, application, loading_points, unloading_points, cargo_info,
                                                logist_info)

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("◀️ Назад к списку", callback_data=f"demo_back_to_list"))

    # Сохраняем, что мы сейчас в детальном просмотре
    if user_id not in demo_view_data:
        demo_view_data[user_id] = {}
    demo_view_data[user_id]['in_detail'] = True

    send_or_edit_message(
        call.message.chat.id,
        user_id,
        detailed_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == 'demo_back_to_list')
def handle_demo_back_to_list(call):
    user_id = call.from_user.id
    if user_id not in demo_view_data:
        return

    current_index = demo_view_data[user_id].get('current_index', 0)
    demo_view_data[user_id]['in_detail'] = False

    send_demo_application_page(call.message.chat.id, user_id, current_index)
    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda message: message.text == "🖊 Начать регистрацию")
def start_registration_command(message):
    user_id = message.from_user.id
    # Очищаем предыдущее сообщение
    if user_id in last_messages:
        try:
            bot.delete_message(message.chat.id, last_messages[user_id])
        except:
            pass
        del last_messages[user_id]
    handle_start_registration(bot, message, db)


# Регистрируем обработчик подтверждения начала регистрации
@bot.message_handler(
    func=lambda message: get_user_state(message.from_user.id) == 'waiting_for_registration_confirmation')
def registration_confirmation_command(message):
    user_id = message.from_user.id
    # Очищаем предыдущее сообщение
    if user_id in last_messages:
        try:
            bot.delete_message(message.chat.id, last_messages[user_id])
        except:
            pass
        del last_messages[user_id]
    handle_registration_confirmation(bot, message, db)


# Также нужно добавить обработчик отмены регистрации в процессе
@bot.message_handler(func=lambda message: get_user_state(message.from_user.id) in [
    'waiting_for_full_name', 'waiting_for_phone', 'waiting_for_email',
    'waiting_for_role', 'waiting_for_company_name', 'waiting_for_company_inn',
    'waiting_for_tax_system', 'waiting_for_terms_confirmation'
] and message.text == "❌ Отмена")
def cancel_registration_command(message):
    user_id = message.from_user.id
    set_user_state(user_id, '')

    # Очищаем предыдущее сообщение
    if user_id in last_messages:
        try:
            bot.delete_message(message.chat.id, last_messages[user_id])
        except:
            pass
        del last_messages[user_id]

    send_or_edit_message(
        message.chat.id,
        user_id,
        "❌ Регистрация отменена.\n\n"
        "Вы можете начать регистрацию в любое время, нажав «🖊 Начать регистрацию»",
        reply_markup=get_start_menu()
    )


@bot.message_handler(func=lambda message: True)
def block_unregistered(message):
    user_id = message.from_user.id
    user = db.get_user_by_telegram_id(user_id)

    # Разрешаем только этим командам работать гостям
    allowed_texts = [
        "/start",
        "🤖 Посмотреть, как работает бот",
        "🖊 Начать регистрацию"
    ]

    if user and user.get('status') == 'active':
        return  # Зарегистрирован — пропускаем

    if message.text in allowed_texts:
        return  # Разрешённые команды

    # Всё остальное — блокируем
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🖊 Начать регистрацию"))

    send_or_edit_message(
        message.chat.id,
        user_id,
        "Эта функция доступна только после регистрации\n\n"
        "Пройдите регистрацию, чтобы получить полный доступ",
        reply_markup=keyboard
    )


if __name__ == "__main__":
    print("🚀 Бот запущен и готов к работе с несколькими пользователями!")
    bot.infinity_polling()