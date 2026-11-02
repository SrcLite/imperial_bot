import requests
import json
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Bitrix24Client:
    def __init__(self, webhook_url):
        """
        Инициализация клиента Битрикс24 с исправлениями

        Args:
            webhook_url (str): URL вебхука
        """
        # Убедимся, что URL заканшем на /
        if not webhook_url.endswith('/'):
            webhook_url = webhook_url + '/'

        self.webhook_url = webhook_url
        self.session = requests.Session()

        # Более универсальные заголовки
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'TelegramBot/1.0'
        })

        # Настройка таймаутов
        self.timeout = 30

        print(f"Инициализирован клиент для: {self.webhook_url}")

    def _make_request(self, method, params=None):
        """
        Отправляет запрос к API Битрикс24

        Args:
            method (str): Метод API (например: crm.deal.add)
            params (dict): Параметры запроса

        Returns:
            dict or list or None: Ответ от API
        """
        # Убираем .json если уже есть
        if method.endswith('.json'):
            method = method.replace('.json', '')

        # Формируем URL
        url = f"{self.webhook_url}{method}"

        print(f"Запрос к {url}")
        print(f"Параметры: {json.dumps(params, ensure_ascii=False)[:200]}...")

        try:
            # Отправляем запрос
            response = self.session.post(
                url,
                json=params or {},
                timeout=self.timeout,
                verify=True  # Включаем проверку SSL
            )

            print(f"Статус ответа: {response.status_code}")
            print(f"Заголовки: {dict(response.headers)}")

            # Если ответ не 200
            if response.status_code != 200:
                print(f"HTTP ошибка {response.status_code}: {response.text[:200]}")
                return None

            # Пытаемся распарсить JSON
            try:
                result = response.json()
                print(f"Ответ JSON: {json.dumps(result, ensure_ascii=False)[:200]}...")

                # Проверяем структуру ответа
                if isinstance(result, dict):
                    if 'error' in result:
                        error_msg = result.get('error_description', result['error'])
                        print(f"Ошибка API: {error_msg}")
                        return None
                    elif 'result' in result:
                        return result['result']
                    else:
                        # Если нет поля result, возвращаем весь ответ
                        print(f"Нет поля 'result' в ответе. Возвращаю весь ответ")
                        return result
                else:
                    # Если ответ не словарь (например, список)
                    return result

            except json.JSONDecodeError as e:
                print(f"Ошибка парсинга JSON: {e}")
                print(f"Сырой ответ: {response.text[:500]}")
                return None

        except requests.exceptions.Timeout:
            print(f"Таймаут запроса к {method}")
            return None
        except requests.exceptions.SSLError as e:
            print(f"SSL ошибка: {e}")
            # Пробуем без проверки SSL (для тестирования)
            try:
                response = self.session.post(
                    url,
                    json=params or {},
                    timeout=self.timeout,
                    verify=False  # Отключаем проверку SSL
                )
                print(f"Повторный запрос без SSL проверки: {response.status_code}")
                return response.json().get('result') if response.status_code == 200 else None
            except:
                return None
        except Exception as e:
            print(f"Неожиданная ошибка: {type(e).__name__}: {str(e)}")
            return None

    def test_connection(self):
        """
        Тестирует соединение с Битрикс24

        Returns:
            bool: True если соединение успешно
        """
        print("Тестируем подключение к Битрикс24...")

        # Пробуем несколько методов
        test_methods = [
            'app.info',  # Базовый метод
            'crm.currency.list',  # Метод CRM
            'user.current',  # Метод пользователя
        ]

        for method in test_methods:
            print(f"Пробуем метод: {method}")
            result = self._make_request(method)

            if result is not None:
                print(f"✅ Метод {method} успешно выполнен")

                if method == 'app.info':
                    print(f"   Приложение: {result.get('name', 'Неизвестно')}")
                    print(f"   Версия: {result.get('version', 'Неизвестно')}")

                # Если хотя бы один метод работает, считаем подключение успешным
                return True

        print("❌ Не удалось подключиться ни по одному из методов")
        return False

    def simple_test(self):
        """Простой тест с подробным выводом"""
        print("\n" + "=" * 60)
        print("🔧 ПРОСТОЙ ТЕСТ ПОДКЛЮЧЕНИЯ К БИТРИКС24")
        print("=" * 60)

        # Тест 1: app.info
        print("\n1. Тестируем app.info:")
        result1 = self._make_request('app.info')
        if result1:
            print(f"   ✅ Успешно!")
            print(f"   • Приложение: {result1.get('name', 'Неизвестно')}")
            print(f"   • Версия: {result1.get('version', 'Неизвестно')}")
            print(f"   • Scope: {result1.get('scope', 'Неизвестно')}")
        else:
            print(f"   ❌ Не удалось")

        # Тест 2: crm.currency.list
        print("\n2. Тестируем crm.currency.list:")
        result2 = self._make_request('crm.currency.list')
        if result2:
            print(f"   ✅ Успешно! Найдено {len(result2)} валют")
            for currency in result2[:3]:  # Показываем первые 3
                print(f"   • {currency.get('CURRENCY')}: {currency.get('FULL_NAME')}")
        else:
            print(f"   ❌ Не удалось")

        # Тест 3: crm.deal.fields (проверка прав на CRM)
        print("\n3. Тестируем crm.deal.fields:")
        result3 = self._make_request('crm.deal.fields')
        if result3:
            print(f"   ✅ Успешно! Доступно {len(result3)} полей")
            # Проверяем доступность пользовательских полей
            custom_fields = [k for k in result3.keys() if k.startswith('UF_CRM')]
            print(f"   • Найдено {len(custom_fields)} пользовательских полей")
            for field in custom_fields[:5]:
                print(f"   • {field}: {result3[field].get('listLabel', 'Нет описания')}")
        else:
            print(f"   ⚠️ Нет прав на CRM или метод недоступен")

        print("\n" + "=" * 60)

        # Общий вывод
        if result1 or result2 or result3:
            print("✅ Подключение к Битрикс24 РАБОТАЕТ")
            return True
        else:
            print("❌ Не удалось подключиться к Битрикс24")
            return False

    def create_deal(self, application_data, creator_info=None):
        try:
            # Подготавливаем данные для сделки
            deal_data = self._prepare_deal_data(application_data, creator_info)

            # Логируем данные перед отправкой
            print(f"Данные для создания сделки: {json.dumps(deal_data, ensure_ascii=False, indent=2)}")

            # Проверяем существование полей
            self._check_fields_availability()

            # Создаем сделку
            result = self._make_request('crm.deal.add', {
                'fields': deal_data
            })

            if result:
                deal_id = result
                print(f"✅ Создана сделка в Битрикс24: ID={deal_id}")

                # Логируем все поля созданной сделки для проверки
                deal_info = self.get_deal_info(deal_id)
                if deal_info:
                    print(f"Поля созданной сделки: {json.dumps(deal_info, ensure_ascii=False, indent=2)}")

                # Добавляем комментарий с деталями
                self._add_deal_comment(deal_id, application_data)

                # Обновляем описание в сделке (вдруг комментарий не сохранился)
                self._update_deal_description(deal_id, application_data, creator_info)

                return deal_id

            return None

        except Exception as e:
            print(f"❌ Ошибка создания сделки в Битрикс24: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def _check_fields_availability(self):
        """Проверяет доступность полей для сделки"""
        try:
            fields = self._make_request('crm.deal.fields')
            if fields:
                print(f"Доступно {len(fields)} полей для сделки")
                # Логируем пользовательские поля
                uf_fields = {k: v for k, v in fields.items() if k.startswith('UF_CRM')}
                print(f"Доступные пользовательские поля: {list(uf_fields.keys())}")
        except Exception as e:
            print(f"Не удалось проверить доступность полей: {e}")

    def _prepare_deal_data(self, application_data, creator_info):
        # Формируем название сделки
        title = f"Заявка #{application_data.get('id', 'N/A')} - Грузоперевозка"

        # Если есть города, добавляем их в название
        loading_cities = application_data.get('loading_cities', [])
        unloading_cities = application_data.get('unloading_cities', [])

        if loading_cities and unloading_cities:
            title = f"Заявка #{application_data.get('id', 'N/A')}: {loading_cities[0]} → {unloading_cities[0]}"

        # Определяем тип заявки
        app_type = application_data.get('type', 'fixed')

        stage_id = "NEW"  # По умолчанию для новой сделки
        category_id = 0  # Основная воронка

        # Попробуйте получить список доступных стадий
        try:
            stages = self._make_request('crm.dealcategory.stage.list', {
                'id': category_id
            })
            if stages and len(stages) > 0:
                stage_id = stages[0]['STATUS_ID']  # Берем первую доступную стадию
        except Exception as e:
            print(f"Не удалось получить стадии воронки: {e}")

        # Определяем цену
        price = 0
        price = application_data.get('price')

        # Преобразуем в число если это строка
        if isinstance(price, str):
            try:
                price = float(price.replace(' ', '').replace(',', '.'))
            except:
                price = 0

        # Базовые данные сделки - используем стандартные поля
        deal_data = {
            'TITLE': title,
            'STAGE_ID': stage_id,
            'CATEGORY_ID': category_id,
            'OPPORTUNITY': price,
            'CURRENCY_ID': 'RUB',
            'COMMENTS': self._create_simple_description(application_data, creator_info),  # Без HTML
            'SOURCE_ID': 'SELF',
            'SOURCE_DESCRIPTION': 'Заявка из Telegram-бота',
            'ASSIGNED_BY_ID': 1,
            'IS_NEW': 'Y',

            'UF_CRM_1765444245': str(application_data.get('id', '')),  # ID заявки
            'UF_CRM_1765444260': application_data.get('type', 'fixed'),
            # 'UF_CRM_1765444269': str(application_data.get('weight', 0)),
            # 'UF_CRM_1765444299': str(application_data.get('volume', 0)),
            # 'UF_CRM_1765444346': application_data.get('cargo_type', 'Не указан'),
        }

        # Данные о маршруте
        if loading_cities:
            deal_data['UF_CRM_1765445462'] = ', '.join(loading_cities[:3])  # Ограничиваем количество
        if unloading_cities:
            deal_data['UF_CRM_1765445482'] = ', '.join(unloading_cities[:3])

        # Данные о транспорте
        # deal_data.update({
        #     'UF_CRM_1765444436': application_data.get('vehicle_type_display',
        #                                               application_data.get('vehicle_type', 'Не указан')),
        # })

        # Даты
        loading_date = application_data.get('loading_date')
        unloading_date = application_data.get('unloading_date')
        if loading_date:
            deal_data['UF_CRM_1765444469'] = loading_date
        if unloading_date:
            deal_data['UF_CRM_1765444480'] = unloading_date

        # Если есть контакт, привязываем его
        if creator_info:
            contact_id = self._find_or_create_contact(creator_info)
            if contact_id:
                deal_data['CONTACT_ID'] = contact_id

            # Добавляем контактную информацию
            deal_data.update({
                'UF_CRM_1765446737': creator_info.get('phone', 'Не указан'),
                'UF_CRM_1765446701': creator_info.get('email', 'Не указан'),
            })
        return deal_data

    def _create_simple_description(self, application_data, creator_info):
        """Создает простое описание без HTML"""
        lines = []
        lines.append(f"ИНФОРМАЦИЯ О ЗАЯВКЕ")
        lines.append(f"ID заявки: #{application_data.get('id', 'N/A')}")
        lines.append(
            f"Тип заявки: {'Стандартная' if application_data.get('type') == 'fixed' else 'Аукцион'}")
        lines.append(f"Вес: {application_data.get('weight', 0)}")
        lines.append(f"Объем: {application_data.get('volume', 0)}")

        if creator_info:
            lines.append(f"\nКОНТАКТНАЯ ИНФОРМАЦИЯ")
            lines.append(f"Контактное лицо: {creator_info.get('first_name', '')} {creator_info.get('last_name', '')}")
            lines.append(f"Телефон: {creator_info.get('phone', 'Не указан')}")
            lines.append(f"Email: {creator_info.get('email', 'Не указан')}")

        return "\n".join(lines)

    def _create_deal_description(self, application_data, creator_info):
        description_parts = []

        # Основная информация
        description_parts.append("<b>📋 ИНФОРМАЦИЯ О ЗАЯВКЕ</b>")
        description_parts.append(f"ID заявки: #{application_data.get('id', 'N/A')}")

        # Тип заявки
        app_type = application_data.get('application_type', 'fixed')
        description_parts.append(f"Тип заявки: {'📦 Стандартная' if app_type == 'fixed' else '🏷️ Аукцион'}")

        # Маршрут
        loading_cities = application_data.get('loading_cities', [])
        unloading_cities = application_data.get('unloading_cities', [])

        if loading_cities:
            description_parts.append(f"Города погрузки: {', '.join(loading_cities)}")
        if unloading_cities:
            description_parts.append(f"Города выгрузки: {', '.join(unloading_cities)}")

        # Параметры груза
        description_parts.append("\n<b>📦 ХАРАКТЕРИСТИКИ ГРУЗА</b>")
        description_parts.append(f"Вес: {application_data.get('weight', 0)} кг")
        description_parts.append(f"Объем: {application_data.get('volume', 0)} м³")
        description_parts.append(f"Тип груза: {application_data.get('cargo_type', 'Не указан')}")
        description_parts.append(f"Категория груза: {application_data.get('cargo_category', 'Не указана')}")

        # Транспорт
        description_parts.append("\n<b>🚛 ТРЕБОВАНИЯ К ТРАНСПОРТУ</b>")
        description_parts.append(
            f"Тип кузова: {application_data.get('vehicle_type_display', application_data.get('vehicle_type', 'Не указан'))}")
        description_parts.append(
            f"Грузоподъемность: {application_data.get('capacity_min', 0)} - {application_data.get('capacity_max', 0)} т")
        description_parts.append(
            f"Объем кузова: {application_data.get('volume_min', 0)} - {application_data.get('volume_max', 0)} м³")

        # Сроки
        description_parts.append("\n<b>⏰ СРОКИ</b>")
        loading_date = application_data.get('loading_date')
        unloading_date = application_data.get('unloading_date')

        if loading_date:
            description_parts.append(f"Дата погрузки: {loading_date}")
        if unloading_date:
            description_parts.append(f"Дата выгрузки: {unloading_date}")

        # Финансы
        description_parts.append("\n<b>💰 ФИНАНСОВАЯ ИНФОРМАЦИЯ</b>")
        if app_type == 'fixed':
            price = application_data.get('min_price', 0) or application_data.get('fixed_price', 0)
            description_parts.append(f"Цена: {price:,.0f} руб.")
        else:
            description_parts.append(f"Желаемый бюджет: {application_data.get('desired_budget', 0):,.0f} руб.")

        # Контактная информация
        if creator_info:
            description_parts.append("\n<b>👤 КОНТАКТНАЯ ИНФОРМАЦИЯ</b>")
            description_parts.append(
                f"Контактное лицо: {creator_info.get('first_name', '')} {creator_info.get('last_name', '')}")
            description_parts.append(f"Телефон: {creator_info.get('phone', 'Не указан')}")
            description_parts.append(f"Email: {creator_info.get('email', 'Не указан')}")
            if creator_info.get('company_name'):
                description_parts.append(f"Компания: {creator_info.get('company_name')}")

        # Дополнительные примечания
        notes = application_data.get('notes')
        if notes:
            description_parts.append("\n<b>📝 ПРИМЕЧАНИЯ</b>")
            description_parts.append(notes)

        # Добавляем время создания
        created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        description_parts.append(f"\n<i>Заявка создана: {created_at}</i>")

        return "<br>".join(description_parts)

    def _update_deal_description(self, deal_id, application_data, creator_info):
        """Обновляет описание сделки после создания"""
        try:
            description = self._create_simple_description(application_data, creator_info)
            self._make_request('crm.deal.update', {
                'id': deal_id,
                'fields': {
                    'COMMENTS': description
                }
            })
        except Exception as e:
            print(f"Не удалось обновить описание сделки: {e}")

    def _find_or_create_contact(self, creator_info):
        try:
            # Сначала пытаемся найти контакт по email
            email = creator_info.get('email')
            if email:
                result = self._make_request('crm.contact.list', {
                    'filter': {'EMAIL': email},
                    'select': ['ID']
                })

                if result and len(result) > 0:
                    return result[0]['ID']

            # Если не нашли по email, ищем по телефону
            phone = creator_info.get('phone')
            if phone:
                result = self._make_request('crm.contact.list', {
                    'filter': {'PHONE': phone},
                    'select': ['ID']
                })

                if result and len(result) > 0:
                    return result[0]['ID']

            # Если контакт не найден, создаем новый
            contact_data = {
                'NAME': creator_info.get('first_name', ''),
                'LAST_NAME': creator_info.get('last_name', ''),
                'EMAIL': [{'VALUE': email, 'VALUE_TYPE': 'WORK'}] if email else [],
                'PHONE': [{'VALUE': phone, 'VALUE_TYPE': 'WORK'}] if phone else [],
            }

            # Добавляем компанию, если есть
            company_name = creator_info.get('company_name')
            if company_name:
                company_id = self._find_or_create_company(company_name, creator_info)
                if company_id:
                    contact_data['COMPANY_ID'] = company_id

            result = self._make_request('crm.contact.add', {
                'fields': contact_data
            })

            return result

        except Exception as e:
            print(f"❌ Ошибка поиска/создания контакта: {e}")
            return None

    def _find_or_create_company(self, company_name, creator_info):
        """
        Ищет или создает компанию в Битрикс24

        Args:
            company_name (str): Название компании
            creator_info (dict): Дополнительная информация

        Returns:
            int: ID компании или None
        """
        try:
            # Ищем компанию по названию
            result = self._make_request('crm.company.list', {
                'filter': {'TITLE': company_name},
                'select': ['ID']
            })

            if result and len(result) > 0:
                return result[0]['ID']

            # Создаем новую компанию
            company_data = {
                'TITLE': company_name,
            }

            # Добавляем ИНН, если есть
            company_inn = creator_info.get('company_inn')
            if company_inn:
                company_data['UF_CRM_INN'] = company_inn

            result = self._make_request('crm.company.add', {
                'fields': company_data
            })

            return result

        except Exception as e:
            print(f"❌ Ошибка поиска/создания компании: {e}")
            return None

    def _add_deal_comment(self, deal_id, application_data):
        """
        Добавляет комментарий к сделке с деталями заявки

        Args:
            deal_id (int): ID сделки
            application_data (dict): Данные заявки
        """
        try:
            comment_text = f"✅ Заявка #{application_data.get('id', 'N/A')} успешно создана в Telegram-боте\n"
            comment_text += f"Тип: {'Стандартная' if application_data.get('type') == 'fixed' else 'Аукцион'}\n"

            self._make_request('crm.timeline.comment.add', {
                'fields': {
                    'ENTITY_ID': deal_id,
                    'ENTITY_TYPE': 'deal',
                    'COMMENT': comment_text,
                    'AUTHOR_ID': 1  # ID пользователя, от имени которого добавляется комментарий
                }
            })

        except Exception as e:
            print(f"❌ Ошибка добавления комментария к сделке: {e}")

    def update_deal_status(self, deal_id, new_status, comment=None):
        try:
            fields = {'STAGE_ID': new_status}

            if comment:
                fields['COMMENTS'] = comment

            result = self._make_request('crm.deal.update', {
                'id': deal_id,
                'fields': fields
            })

            return result is not None

        except Exception as e:
            print(f"❌ Ошибка обновления статуса сделки: {e}")
            return False

    def get_deal_info(self, deal_id):
        try:
            return self._make_request('crm.deal.get', {'id': deal_id})
        except Exception as e:
            print(f"❌ Ошибка получения информации о сделке: {e}")
            return None


