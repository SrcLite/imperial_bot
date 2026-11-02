from utils.google_sheets import get_google_sheets_manager
from config.google_sheets_config import is_google_sheets_enabled


def export_response_to_google_sheets(db, application_id, response_id, executor_id, response_type, payment_options):
    """
    Экспорт предложения перевозчика в Google Sheets

    Args:
        db: Объект базы данных
        application_id (int): ID заявки
        response_id (int): ID ответа
        executor_id (int): ID перевозчика
        response_type (str): Тип ответа
        payment_options (dict): Варианты оплаты
    """
    if not is_google_sheets_enabled():
        return

    try:
        manager = get_google_sheets_manager()
        if not manager:
            print("Google Sheets менеджер не инициализирован")
            return

        # Получаем данные заявки
        application = db.fetch_one("""
            SELECT a.*,
                   u.phone as logist_phone
            FROM applications a
            JOIN users u ON a.created_by = u.telegram_id
            WHERE a.id = ?
        """, (application_id,))

        if not application:
            print(f"Заявка {application_id} не найдена")
            return

        # Получаем данные перевозчика
        executor = db.fetch_one("""
            SELECT u.*, c.name as company_name, c.inn as company_inn
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.id
            WHERE u.telegram_id = ?
        """, (executor_id,))

        if not executor:
            print(f"Перевозчик {executor_id} не найден")
            return

        # Подготавливаем данные для экспорта (только нужные поля)
        application_data = {
            'id': application['id'],
            'application_type': application['application_type'],
            'created_by': application['created_by'],
            'logist_phone': application.get('logist_phone', '')
        }

        response_data = {
            'response_id': response_id,
            'executor_id': executor_id,
            'executor_name': f"{executor.get('first_name', '')} {executor.get('last_name', '')}".strip(),
            'company_name': executor.get('company_name', ''),
            'company_inn': executor.get('company_inn', ''),
            'response_type': response_type,
            'payment_options': payment_options
        }

        # Добавляем в Google Sheets
        success = manager.add_application_response(application_data, response_data)

        if success:
            print(f"Данные предложения {response_id} успешно экспортированы в Google Sheets")
        else:
            print(f"Ошибка экспорта предложения {response_id} в Google Sheets")

    except Exception as e:
        print(f"Ошибка при экспорте в Google Sheets: {e}")

def export_application_responses_to_google_sheets(db, application_id):
    """
    Экспорт всех предложений по заявке в Google Sheets

    Args:
        db: Объект базы данных
        application_id (int): ID заявки
    """
    if not is_google_sheets_enabled():
        return

    try:
        # Получаем все ответы по заявке
        responses = db.fetch_all("""
            SELECT ar.id as response_id, ar.executor_id, ar.status as response_type, ar.payment_options
            FROM application_responses ar
            WHERE ar.application_id = ?
                AND ar.status IN ('counter_offer', 'accepted_budget', 'selected')
        """, (application_id,))

        for response in responses:
            # Экспортируем каждый ответ
            export_response_to_google_sheets(
                db=db,
                application_id=application_id,
                response_id=response['response_id'],
                executor_id=response['executor_id'],
                response_type=response['response_type'],
                payment_options=response['payment_options']
            )

    except Exception as e:
        print(f"Ошибка при экспорте всех ответов в Google Sheets: {e}")

def update_application_status_in_sheets(db, application_id, status, selected_executor_id=None):
    """
    Обновление статуса заявки в Google Sheets

    Args:
        db: Объект базы данных
        application_id (int): ID заявки
        status (str): Новый статус
        selected_executor_id (int): ID выбранного перевозчика (опционально)
    """
    if not is_google_sheets_enabled():
        return

    try:
        manager = get_google_sheets_manager()
        if not manager:
            return

        selected_executor = None
        if selected_executor_id:
            # Получаем данные выбранного перевозчика
            executor = db.fetch_one("""
                SELECT u.*, c.name as company_name
                FROM users u
                LEFT JOIN companies c ON u.company_id = c.id
                WHERE u.telegram_id = ?
            """, (selected_executor_id,))

            if executor:
                selected_executor = {
                    'executor_id': selected_executor_id,
                    'executor_name': f"{executor.get('first_name', '')} {executor.get('last_name', '')}".strip()
                }

        # Обновляем статус в Google Sheets
        success = manager.update_application_status(application_id, status, selected_executor)

        if success:
            print(f"Статус заявки {application_id} обновлен в Google Sheets")
        else:
            print(f"Ошибка обновления статуса заявки {application_id} в Google Sheets")

    except Exception as e:
        print(f"Ошибка при обновлении статуса в Google Sheets: {e}")