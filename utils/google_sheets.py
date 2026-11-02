import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


class GoogleSheetsManager:
    """Менеджер для работы с Google Sheets"""

    def __init__(self, credentials_path: Optional[Union[str, Path]] = None):
        """
        Инициализация подключения к Google Sheets

        Args:
            credentials_path (str|Path|None): Путь к файлу с учетными данными
        """
        # Обрабатываем путь к файлу учетных данных
        if credentials_path is None:
            # Определяем базовую директорию проекта
            base_dir = Path(__file__).parent.parent
            self.credentials_path = base_dir / 'data' / 'credentials' / 'google_credentials.json'
        elif isinstance(credentials_path, str):
            # Преобразуем строку в Path объект
            self.credentials_path = Path(credentials_path)
        else:
            # Уже Path объект
            self.credentials_path = credentials_path

        self.client = None
        self.spreadsheet = None
        self.worksheet = None

    def connect(self) -> bool:
        """Подключение к Google Sheets API"""
        try:
            # Проверяем существование файла
            if not self.credentials_path.exists():
                raise FileNotFoundError(
                    f"Файл с учетными данными не найден: {self.credentials_path}\n"
                    f"Пожалуйста, разместите файл google_credentials.json по указанному пути"
                )

            # Определяем область доступа
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            # Преобразуем Path в строку для совместимости
            credentials_path_str = str(self.credentials_path)

            # Загружаем учетные данные
            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                credentials_path_str, scope
            )

            # Создаем клиент
            self.client = gspread.authorize(credentials)

            print(f"✅ Успешно подключились к Google Sheets API")
            return True

        except FileNotFoundError as e:
            print(f"❌ Файл учетных данных не найден: {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка чтения JSON файла: {e}")
            return False
        except Exception as e:
            print(f"❌ Ошибка подключения к Google Sheets API: {type(e).__name__}: {e}")
            return False

    def open_spreadsheet(self, spreadsheet_url_or_id: str) -> bool:
        """
        Открытие таблицы по URL или ID

        Args:
            spreadsheet_url_or_id (str): URL или ID таблицы
        """
        try:
            if self.client is None:
                if not self.connect():
                    return False

            # Открываем таблицу
            self.spreadsheet = self.client.open_by_url(spreadsheet_url_or_id)

            print(f"✅ Успешно открыли таблицу: {self.spreadsheet.title}")
            return True

        except gspread.exceptions.SpreadsheetNotFound:
            print(f"❌ Таблица не найдена: {spreadsheet_url_or_id}")
            print("Убедитесь, что:")
            print("1. URL таблицы правильный")
            print("2. Сервисный аккаунт имеет доступ к таблице")
            return False
        except Exception as e:
            print(f"❌ Ошибка открытия таблицы: {type(e).__name__}: {e}")
            return False

    def get_or_create_worksheet(self, worksheet_name: str, rows: int = 1000, cols: int = 20) -> bool:
        """
        Получение или создание листа

        Args:
            worksheet_name (str): Название листа
            rows (int): Количество строк при создании
            cols (int): Количество столбцов при создании
        """
        try:
            # Пытаемся получить существующий лист
            try:
                self.worksheet = self.spreadsheet.worksheet(worksheet_name)
                print(f"✅ Лист '{worksheet_name}' найден")

                # Проверяем, есть ли заголовки
                existing_headers = self.worksheet.row_values(1)
                if not existing_headers or len(existing_headers) < 14:
                    # Если заголовков нет или их мало, создаем заново
                    self._init_worksheet_headers()
                    self.format_headers()

            except gspread.exceptions.WorksheetNotFound:
                # Создаем новый лист
                self.worksheet = self.spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=rows,
                    cols=cols
                )
                print(f"✅ Создан новый лист: '{worksheet_name}'")
                # Заполняем заголовки
                self._init_worksheet_headers()
                self.format_headers()

            return True

        except Exception as e:
            print(f"❌ Ошибка работы с листом: {type(e).__name__}: {e}")
            return False
    def _init_worksheet_headers(self):
        """Инициализация заголовков таблицы"""
        if self.worksheet:
            headers = [
                'ID заявки',
                'Тип заявки',
                'ID логиста',
                'Телефон логиста',
                'ID перевозчика',
                'Имя перевозчика',
                'Компания перевозчика',
                'ИНН компании',
                'Тип ответа',
                'Ставка с НДС',
                'Ставка без НДС (ИП)',
                'Ставка самозанятый',
                'Ставка наличные',
                'Дата ответа'
            ]

            # Записываем заголовки в первую строку
            self.worksheet.insert_row(headers, 1)
            print(f"✅ Заголовки добавлены в лист")

    def add_application_response(self, application_data: dict, response_data: dict) -> bool:
        """
        Добавление информации о предложении перевозчика

        Args:
            application_data (dict): Данные заявки
            response_data (dict): Данные ответа перевозчика
        """
        try:
            # Получаем все данные из таблицы
            all_data = self.worksheet.get_all_values()

            # Проверяем, есть ли уже эта запись (по ID заявки и ID перевозчика)
            for i, row in enumerate(all_data[1:], start=2):  # Пропускаем заголовки
                if len(row) > 4:
                    if (row[0] == str(application_data.get('id', '')) and  # ID заявки
                            row[4] == str(response_data.get('executor_id', ''))):  # ID перевозчика
                        # Обновляем существующую запись
                        self._update_existing_row(i, application_data, response_data)
                        return True

            # Если запись не найдена, добавляем новую
            self._add_new_row(application_data, response_data)
            return True

        except Exception as e:
            print(f"Ошибка добавления данных в таблицу: {type(e).__name__}: {e}")
            return False

    def _add_new_row(self, application_data: dict, response_data: dict):
        """Добавление новой строки"""
        # Парсим payment_options
        payment_options = {}
        try:
            if response_data.get('payment_options'):
                if isinstance(response_data['payment_options'], str):
                    payment_options = json.loads(response_data['payment_options'])
                else:
                    payment_options = response_data['payment_options']
        except:
            payment_options = {}

        # Подготавливаем данные для строки
        row_data = [
            application_data.get('id', ''),  # ID заявки
            'Аукцион' if application_data.get('application_type') == 'auction' else 'Фиксированная',  # Тип заявки
            application_data.get('created_by', ''),  # ID логиста
            application_data.get('logist_phone', ''),  # Телефон логиста
            response_data.get('executor_id', ''),  # ID перевозчика
            response_data.get('executor_name', ''),  # Имя перевозчика
            response_data.get('company_name', ''),  # Компания перевозчика
            response_data.get('company_inn', ''),  # ИНН компании
            response_data.get('response_type', ''),  # Тип ответа
            payment_options.get('nds', ''),  # Ставка с НДС
            payment_options.get('ip', ''),  # Ставка без НДС
            payment_options.get('self-employed', ''),  # Ставка самозанятый
            payment_options.get('cash', ''),  # Ставка наличные
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Дата ответа
        ]

        # Добавляем строку
        self.worksheet.append_row(row_data)
        print(f"✅ Добавлена новая строка для заявки #{application_data.get('id', '')}")
        return True

    def _update_existing_row(self, row_num: int, application_data: dict, response_data: dict):
        """Обновление существующей строки"""
        # Обновляем только изменяемые поля
        updates = {
            9: response_data.get('response_type', ''),  # Тип ответа (колонка I)
            13: datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Дата обновления (колонка M)
        }

        # Обновляем ставки
        payment_options = {}
        try:
            if response_data.get('payment_options'):
                if isinstance(response_data['payment_options'], str):
                    payment_options = json.loads(response_data['payment_options'])
                else:
                    payment_options = response_data['payment_options']
        except:
            payment_options = {}

        updates[10] = payment_options.get('nds', '')  # Ставка с НДС (колонка J)
        updates[11] = payment_options.get('ip', '')  # Ставка без НДС (колонка K)
        updates[12] = payment_options.get('self-employed', '')  # Ставка самозанятый (колонка L)
        updates[13] = payment_options.get('cash', '')  # Ставка наличные (колонка M)

        # Применяем обновления
        for col, value in updates.items():
            self.worksheet.update_cell(row_num, col, value)

        print(f"✅ Обновлена строка {row_num} для заявки #{application_data.get('id', '')}")

    def update_application_status(self, application_id: int, status: str, selected_executor: dict = None) -> bool:
        """
        Обновление статуса заявки в Google Sheets (упрощенная версия)

        Args:
            application_id (int): ID заявки
            status (str): Новый статус
            selected_executor (dict): Данные выбранного перевозчика
        """
        try:
            # Эта функция оставлена для совместимости, но в упрощенной версии
            # мы не храним статус в таблице
            print(f"ℹ️ Обновление статуса для заявки #{application_id}: {status}")

            # Если нужен статус, можно добавить колонку в заголовки
            # и обновлять соответствующие строки

            return True

        except Exception as e:
            print(f"Ошибка обновления статуса заявки: {type(e).__name__}: {e}")
            return False

    def export_all_applications(self, db) -> int:
        """
        Экспорт всех заявок и предложений в таблицу

        Args:
            db: Объект базы данных
        """
        try:
            print("🔄 Начинаем экспорт всех данных в Google Таблицу...")

            # Получаем все аукционные заявки
            applications = db.fetch_all("""
                SELECT a.*, 
                       u.phone as logist_phone
                FROM applications a
                JOIN users u ON a.created_by = u.telegram_id
                WHERE a.application_type = 'auction'
                ORDER BY a.created_at DESC
            """)

            if not applications:
                print("ℹ️ Нет аукционных заявок для экспорта")
                return 0

            print(f"📋 Найдено аукционных заявок: {len(applications)}")

            total_exported = 0

            for app in applications:
                try:
                    # Получаем все ответы на заявку
                    responses = db.fetch_all("""
                        SELECT ar.*, 
                               u.first_name as executor_first_name,
                               u.last_name as executor_last_name,
                               c.name as company_name,
                               c.inn as company_inn
                        FROM application_responses ar
                        JOIN users u ON ar.executor_id = u.telegram_id
                        LEFT JOIN companies c ON u.company_id = c.id
                        WHERE ar.application_id = ? 
                            AND ar.status IN ('counter_offer', 'accepted_budget', 'selected')
                        ORDER BY ar.created_at DESC
                    """, (app['id'],))

                    if not responses:
                        print(f"ℹ️ Для заявки #{app['id']} нет ответов перевозчиков")
                        continue

                    print(f"📊 Заявка #{app['id']}: найдено {len(responses)} ответов")

                    for response in responses:
                        # Подготавливаем данные для экспорта
                        application_data = {
                            'id': app['id'],
                            'application_type': app['application_type'],
                            'created_by': app['created_by'],
                            'logist_phone': app.get('logist_phone', '')
                        }

                        response_data = {
                            'response_id': response['id'],
                            'executor_id': response['executor_id'],
                            'executor_name': f"{response.get('executor_first_name', '')} {response.get('executor_last_name', '')}".strip(),
                            'company_name': response.get('company_name', ''),
                            'company_inn': response.get('company_inn', ''),
                            'response_type': response['status'],
                            'payment_options': response['payment_options']
                        }

                        # Добавляем в таблицу
                        if self.add_application_response(application_data, response_data):
                            total_exported += 1

                        # Небольшая задержка чтобы не превысить лимиты API
                        import time
                        time.sleep(0.1)

                    print(f"✅ Заявка #{app['id']} экспортирована")

                except Exception as e:
                    print(f"⚠️ Ошибка при экспорте заявки #{app.get('id', 'N/A')}: {type(e).__name__}: {e}")
                    continue

            print(f"✅ Экспорт завершен. Экспортировано записей: {total_exported}")
            return total_exported

        except Exception as e:
            print(f"❌ Ошибка при экспорте данных: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def format_headers(self):
        """Форматирование шапки таблицы"""
        try:
            # Форматируем заголовки (жирный шрифт, заливка)
            cell_range = f"A1:N1"  # От A1 до N1

            # Устанавливаем жирный шрифт
            self.worksheet.format(cell_range, {
                "textFormat": {"bold": True},
                "backgroundColor": {
                    "red": 0.8, "green": 0.9, "blue": 1.0  # Светло-синий фон
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })

            # Устанавливаем ширину столбцов
            self.worksheet.set_basic_filter(1, 1, 1, len(self.worksheet.get_all_values()[0]))

            print(f"✅ Шапка таблицы отформатирована")
            return True

        except Exception as e:
            print(f"❌ Ошибка форматирования шапки: {type(e).__name__}: {e}")
            return False


# Создаем глобальный экземпляр менеджера
google_sheets_manager: Optional[GoogleSheetsManager] = None


def init_google_sheets(spreadsheet_url: str, worksheet_name: str = 'Ставки перевозчиков',
                       credentials_path: Optional[Union[str, Path]] = None) -> bool:
    """
    Инициализация Google Sheets

    Args:
        spreadsheet_url (str): URL таблицы
        worksheet_name (str): Название листа
        credentials_path (str|Path|None): Путь к файлу учетных данных
    """
    global google_sheets_manager

    try:
        if credentials_path:
            google_sheets_manager = GoogleSheetsManager(credentials_path)
        else:
            google_sheets_manager = GoogleSheetsManager()

        print(f"🔄 Инициализация Google Sheets...")
        print(f"   URL таблицы: {spreadsheet_url}")
        print(f"   Лист: {worksheet_name}")
        print(f"   Путь к учетным данным: {google_sheets_manager.credentials_path}")

        if google_sheets_manager.connect():
            if google_sheets_manager.open_spreadsheet(spreadsheet_url):
                if google_sheets_manager.get_or_create_worksheet(worksheet_name):
                    print("✅ Google Sheets успешно инициализирован")
                    return True

        print("❌ Ошибка инициализации Google Sheets")
        return False

    except Exception as e:
        print(f"❌ Ошибка при инициализации Google Sheets: {type(e).__name__}: {e}")
        return False


def migrate_existing_sheet():
    """Миграция существующей таблицы с данными"""
    manager = get_google_sheets_manager()
    if not manager:
        return False

    try:
        # Получаем все данные
        all_data = manager.worksheet.get_all_values()

        # Если первая строка не содержит заголовков
        if all_data and not all_data[0][0].startswith('ID'):
            print("⚠️ Обнаружены данные без заголовков. Добавляем заголовки...")

            # Добавляем новую строку с заголовками в начало
            headers = [
                'ID заявки', 'Тип заявки', 'ID логиста', 'Телефон логиста',
                'ID перевозчика', 'Имя перевозчика', 'Компания перевозчика',
                'ИНН компании', 'Тип ответа', 'Ставка с НДС',
                'Ставка без НДС (ИП)', 'Ставка самозанятый', 'Ставка наличные', 'Дата ответа'
            ]

            # Вставляем заголовки в первую строку, сдвигая существующие данные вниз
            manager.worksheet.insert_row(headers, 1)
            manager.format_headers()

            print(f"✅ Заголовки добавлены, данные сдвинуты")
            return True

    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        return False

def get_google_sheets_manager() -> Optional[GoogleSheetsManager]:
    """Получение экземпляра менеджера Google Sheets"""
    return google_sheets_manager