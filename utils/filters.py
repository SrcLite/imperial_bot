import json
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from utils.dicts import VEHICLE_TYPE_MAPPING, CARGO_CATEGORY_MAPPING, CARGO_TYPE_MAPPING, VEHICLE_TYPE_REVERSE_MAPPING, \
    CARGO_CATEGORY_REVERSE_MAPPING, CARGO_TYPE_REVERSE_MAPPING

# Доступные фильтры
AVAILABLE_FILTERS = {
    'cargo_type': '📦 Тип груза',
    'cargo_category': '📊 Категория груза',
    'vehicle_type': '🚛 Тип транспорта',
    'capacity_range': '⚖️ Грузоподъемность',
    'volume_range': '📏 Объем кузова',
    'price_range': '💰 Диапазон цен',
    'distance_range': '📍 Расстояние',
    'loading_date': '📅 Дата погрузки',
    'loading_city': '🏙️ Город погрузки',
    'unloading_city': '🏙️ Город выгрузки',
    'application_type': '📝 Тип заявки',
}


class ExecutorFilters:
    """Класс для управления фильтрами перевозчика"""

    def __init__(self, db, executor_id):
        self.db = db
        self.executor_id = executor_id
        self.filters = self.load_filters()

    def load_filters(self):
        """Загружает фильтры из БД и конвертирует значения"""
        result = self.db.fetch_one(
            "SELECT filters FROM executor_filters WHERE executor_id = ?",
            (self.executor_id,)
        )

        if result and result.get('filters'):
            try:
                filters = json.loads(result['filters'])
                # Конвертируем отображаемые значения обратно в ключи при загрузке
                return self.convert_display_to_keys(filters)
            except Exception as e:
                print(f"❌ Ошибка загрузки фильтров: {e}")
                return self.get_default_filters()

        return self.get_default_filters()

    def save_filters(self):
        """Сохраняет фильтры в БД с правильной обработкой числовых значений"""
        # Преобразуем числовые значения в правильные типы
        filters_to_save = self.filters.copy()

        # Обрабатываем числовые поля
        numeric_fields = ['capacity_min', 'capacity_max', 'volume_min', 'volume_max',
                          'price_min', 'price_max', 'distance_max']

        for field in numeric_fields:
            if field in filters_to_save and filters_to_save[field] is not None:
                try:
                    # Преобразуем в float, если это строка
                    if isinstance(filters_to_save[field], str):
                        filters_to_save[field] = float(filters_to_save[field])
                    # Округляем до 2 знаков после запятой
                    if isinstance(filters_to_save[field], (int, float)):
                        filters_to_save[field] = round(float(filters_to_save[field]), 2)
                except (ValueError, TypeError):
                    filters_to_save[field] = None

        # Удаляем пустые строки из списков городов
        for field in ['loading_city', 'unloading_city']:
            if field in filters_to_save and isinstance(filters_to_save[field], list):
                filters_to_save[field] = [city.strip() for city in filters_to_save[field] if city and str(city).strip()]

        filters_json = json.dumps(filters_to_save, ensure_ascii=False)

        # Проверяем, существует ли запись
        existing = self.db.fetch_one(
            "SELECT id FROM executor_filters WHERE executor_id = ?",
            (self.executor_id,)
        )

        if existing:
            self.db.execute_query(
                "UPDATE executor_filters SET filters = ?, updated_at = datetime('now') WHERE executor_id = ?",
                (filters_json, self.executor_id)
            )
        else:
            self.db.execute_query(
                "INSERT INTO executor_filters (executor_id, filters) VALUES (?, ?)",
                (self.executor_id, filters_json)
            )

    def convert_display_to_keys(self, filters):
        """Конвертирует отображаемые значения обратно в ключи"""
        converted = filters.copy()

        # Конвертируем cargo_type
        if 'cargo_type' in converted and isinstance(converted['cargo_type'], list):
            new_cargo_types = []
            for item in converted['cargo_type']:
                if item in CARGO_TYPE_REVERSE_MAPPING.values():
                    # Это отображаемое значение, ищем ключ
                    key = CARGO_TYPE_MAPPING.get(item)
                    if key:
                        new_cargo_types.append(key)
                else:
                    # Это уже ключ
                    new_cargo_types.append(item)
            converted['cargo_type'] = new_cargo_types

        # Конвертируем cargo_category
        if 'cargo_category' in converted and isinstance(converted['cargo_category'], list):
            new_categories = []
            for item in converted['cargo_category']:
                if item in CARGO_CATEGORY_REVERSE_MAPPING.values():
                    key = CARGO_CATEGORY_MAPPING.get(item)
                    if key:
                        new_categories.append(key)
                else:
                    new_categories.append(item)
            converted['cargo_category'] = new_categories

        # Конвертируем vehicle_type
        if 'vehicle_type' in converted and isinstance(converted['vehicle_type'], list):
            new_vehicles = []
            for item in converted['vehicle_type']:
                if item in VEHICLE_TYPE_REVERSE_MAPPING.values():
                    key = VEHICLE_TYPE_MAPPING.get(item)
                    if key:
                        new_vehicles.append(key)
                else:
                    new_vehicles.append(item)
            converted['vehicle_type'] = new_vehicles

        return converted

    def get_filter_display(self, filter_name, value):
        """Возвращает читаемое представление фильтра на русском"""

        # Обработка диапазонных фильтров (они состоят из двух полей)
        if filter_name in ['capacity_range', 'volume_range', 'price_range']:
            min_key = filter_name.replace('_range', '_min')
            max_key = filter_name.replace('_range', '_max')
            min_val = self.filters.get(min_key)
            max_val = self.filters.get(max_key)

            # Проверяем оба значения
            if min_val is None and max_val is None:
                return "❌ Не установлен"

            if filter_name == 'capacity_range':
                if min_val is not None and max_val is not None:
                    if min_val == max_val:
                        return f"{min_val} т"
                    else:
                        return f"{min_val}-{max_val} т"
                elif min_val is not None:
                    return f"от {min_val} т"
                elif max_val is not None:
                    return f"до {max_val} т"

            elif filter_name == 'volume_range':
                if min_val is not None and max_val is not None:
                    if min_val == max_val:
                        return f"{min_val} м³"
                    else:
                        return f"{min_val}-{max_val} м³"
                elif min_val is not None:
                    return f"от {min_val} м³"
                elif max_val is not None:
                    return f"до {max_val} м³"

            elif filter_name == 'price_range':
                if min_val is not None and max_val is not None:
                    if min_val == max_val:
                        min_f = f"{int(min_val):,}".replace(',', ' ')
                        return f"{min_f} ₽"
                    else:
                        min_f = f"{int(min_val):,}".replace(',', ' ')
                        max_f = f"{int(max_val):,}".replace(',', ' ')
                        return f"{min_f}-{max_f} ₽"
                elif min_val is not None:
                    min_f = f"{int(min_val):,}".replace(',', ' ')
                    return f"от {min_f} ₽"
                elif max_val is not None:
                    max_f = f"{int(max_val):,}".replace(',', ' ')
                    return f"до {max_f} ₽"

        # Обработка даты погрузки (тоже два поля)
        elif filter_name == 'loading_date':
            date_from = self.filters.get('loading_date_from')
            date_to = self.filters.get('loading_date_to')

            if date_from is None and date_to is None:
                return "❌ Не установлен"

            try:
                if date_from and date_to:
                    if date_from == date_to:
                        date_obj = datetime.strptime(date_from, '%Y-%m-%d')
                        return date_obj.strftime('%d.%m.%Y')
                    else:
                        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                        return f"{date_from_obj.strftime('%d.%m')}-{date_to_obj.strftime('%d.%m.%Y')}"
                elif date_from:
                    date_obj = datetime.strptime(date_from, '%Y-%m-%d')
                    return f"с {date_obj.strftime('%d.%m.%Y')}"
                elif date_to:
                    date_obj = datetime.strptime(date_to, '%Y-%m-%d')
                    return f"до {date_obj.strftime('%d.%m.%Y')}"
            except:
                if date_from and date_to:
                    return f"{date_from} - {date_to}"
                elif date_from:
                    return f"с {date_from}"
                elif date_to:
                    return f"до {date_to}"

        # Обработка списковых фильтров
        elif isinstance(value, list):
            if not value:  # Пустой список
                return "❌ Не установлен"

            if filter_name == 'cargo_type':
                display_values = []
                for v in value:
                    if v in CARGO_TYPE_REVERSE_MAPPING:
                        display_values.append(CARGO_TYPE_REVERSE_MAPPING[v])
                    elif v in CARGO_TYPE_MAPPING:
                        display_values.append(v)
                    else:
                        display_values.append(v)

                result = ", ".join(display_values)
                return result[:30] + "..." if len(result) > 30 else result

            elif filter_name == 'cargo_category':
                display_values = []
                for v in value:
                    if v in CARGO_CATEGORY_REVERSE_MAPPING:
                        display_values.append(CARGO_CATEGORY_REVERSE_MAPPING[v])
                    elif v in CARGO_CATEGORY_MAPPING:
                        display_values.append(v)
                    else:
                        display_values.append(v)

                result = ", ".join(display_values)
                return result[:30] + "..." if len(result) > 30 else result

            elif filter_name == 'vehicle_type':
                display_values = []
                for v in value:
                    if v in VEHICLE_TYPE_REVERSE_MAPPING:
                        display_values.append(VEHICLE_TYPE_REVERSE_MAPPING[v])
                    elif v in VEHICLE_TYPE_MAPPING:
                        display_values.append(v)
                    else:
                        display_values.append(v)

                result = ", ".join(display_values)
                return result[:30] + "..." if len(result) > 30 else result

            elif filter_name == 'application_type':
                display_map = {'fixed': '📦 Фиксированная', 'auction': '🏷️ Аукцион'}
                display_values = [display_map.get(v, v) for v in value]
                result = ", ".join(display_values)
                return result[:30] + "..." if len(result) > 30 else result

            elif filter_name in ['loading_city', 'unloading_city']:
                result = ", ".join(value)
                return result[:30] + "..." if len(result) > 30 else result

            # Для других списков
            result = ", ".join(str(v) for v in value)
            return result[:30] + "..." if len(result) > 30 else result

        # Обработка отдельных числовых значений
        elif isinstance(value, (int, float)):
            if filter_name in ['capacity_min', 'capacity_max']:
                return f"{value} т"
            elif filter_name in ['volume_min', 'volume_max']:
                return f"{value} м³"
            elif filter_name in ['price_min', 'price_max']:
                return f"{int(value):,} ₽".replace(',', ' ')
            elif filter_name == 'distance_max':
                return f"{value} км"
            else:
                return str(value)

        # Обработка строковых значений
        elif isinstance(value, str):
            if filter_name in ['loading_date_from', 'loading_date_to']:
                try:
                    date_obj = datetime.strptime(value, '%Y-%m-%d')
                    return date_obj.strftime('%d.%m.%Y')
                except:
                    return value
            else:
                return value[:30] + "..." if len(value) > 30 else value

        # Обработка булевых значений
        elif isinstance(value, bool):
            if filter_name == 'show_active_only':
                return "✅ Да" if value else "❌ Нет"
            elif filter_name == 'show_without_response':
                return "✅ Да" if value else "❌ Нет"
            else:
                return "✅ Да" if value else "❌ Нет"

        # Для None значений
        elif value is None:
            return "❌ Не установлен"

        # По умолчанию
        return str(value) if value else "❌ Не установлен"

    def get_default_filters(self):
        """Возвращает фильтры по умолчанию"""
        return {
            'cargo_type': [],
            'cargo_category': [],
            'vehicle_type': [],
            'capacity_min': None,
            'capacity_max': None,
            'volume_min': None,
            'volume_max': None,
            'price_min': None,
            'price_max': None,
            'distance_max': None,
            'loading_date_from': None,
            'loading_date_to': None,
            'loading_city': [],
            'unloading_city': [],
            'application_type': [],  # 'fixed', 'auction'
            'show_active_only': True,
            'show_without_response': False
        }

    def reset_filters(self):
        """Сбрасывает фильтры к значениям по умолчанию"""
        self.filters = self.get_default_filters()
        self.save_filters()

    def update_filter(self, filter_name, value):
        """Обновляет конкретный фильтр с обработкой числовых значений"""
        if filter_name in self.filters:
            # Специальная обработка для числовых значений
            if filter_name in ['capacity_min', 'capacity_max', 'volume_min', 'volume_max',
                               'price_min', 'price_max', 'distance_max']:
                if value is not None:
                    try:
                        # Преобразуем строку в число
                        if isinstance(value, str):
                            value = float(value) if value.strip() != '' else None
                        # Округляем до 2 знаков
                        if value is not None:
                            value = round(float(value), 2)
                    except (ValueError, TypeError):
                        value = None

            self.filters[filter_name] = value
            self.save_filters()


def apply_filters_to_query(base_query, filters, executor_id=None):
    """
    Применяет фильтры к SQL-запросу с учетом новой структуры таблиц
    """
    query = base_query
    params = []
    conditions = []

    # ОБЯЗАТЕЛЬНОЕ условие: только активные заявки
    conditions.append("a.status = 'active'")

    # Исключаем заявки, от которых пользователь отказался (статус rejected)
    if executor_id:
        conditions.append("""
            NOT EXISTS (
                SELECT 1 FROM application_responses ar 
                WHERE ar.application_id = a.id 
                AND ar.executor_id = ? 
                AND ar.status = 'rejected'
            )
        """)
        params.append(executor_id)

    # Фильтр по типу груза
    if filters.get('cargo_type') and len(filters['cargo_type']) > 0:
        placeholders = ', '.join(['?' for _ in filters['cargo_type']])
        conditions.append(f"(a.cargo_type IN ({placeholders}) OR a.cargo_custom_type IN ({placeholders}))")
        params.extend(filters['cargo_type'])
        params.extend(filters['cargo_type'])

    # Фильтр по категории груза
    if filters.get('cargo_category') and len(filters['cargo_category']) > 0:
        placeholders = ', '.join(['?' for _ in filters['cargo_category']])
        conditions.append(f"(a.cargo_category IN ({placeholders}) OR a.cargo_custom_category IN ({placeholders}))")
        params.extend(filters['cargo_category'])
        params.extend(filters['cargo_category'])

    # Фильтр по типу транспорта
    if filters.get('vehicle_type') and len(filters['vehicle_type']) > 0:
        placeholders = ', '.join(['?' for _ in filters['vehicle_type']])
        conditions.append(f"a.vehicle_type IN ({placeholders})")
        params.extend(filters['vehicle_type'])

    # Фильтр по грузоподъемности (используем вес груза)
    if filters.get('capacity_min'):
        conditions.append("a.weight >= ?")
        params.append(float(filters['capacity_min']))

    if filters.get('capacity_max'):
        conditions.append("a.weight <= ?")
        params.append(float(filters['capacity_max']))

    # Фильтр по объему
    if filters.get('volume_min'):
        conditions.append("a.volume >= ?")
        params.append(float(filters['volume_min']))

    if filters.get('volume_max'):
        conditions.append("a.volume <= ?")
        params.append(float(filters['volume_max']))

    # Фильтр по цене
    if filters.get('price_min'):
        price_min = float(filters['price_min'])
        conditions.append("""
            (a.application_type = 'fixed' AND (
                COALESCE(json_extract(a.payment_options, '$.nds'), 0) >= ? OR
                COALESCE(json_extract(a.payment_options, '$.ip'), 0) >= ? OR
                COALESCE(json_extract(a.payment_options, '$.self-employed'), 0) >= ? OR
                COALESCE(json_extract(a.payment_options, '$.cash'), 0) >= ?
            )) OR 
            (a.application_type = 'auction' AND COALESCE(a.desired_budget, 0) >= ?)
        """)
        for _ in range(4):
            params.append(price_min)
        params.append(price_min)

    if filters.get('price_max'):
        price_max = float(filters['price_max'])
        conditions.append("""
            (a.application_type = 'fixed' AND (
                COALESCE(json_extract(a.payment_options, '$.nds'), 0) <= ? OR
                COALESCE(json_extract(a.payment_options, '$.ip'), 0) <= ? OR
                COALESCE(json_extract(a.payment_options, '$.self-employed'), 0) <= ? OR
                COALESCE(json_extract(a.payment_options, '$.cash'), 0) <= ?
            )) OR 
            (a.application_type = 'auction' AND COALESCE(a.desired_budget, 0) <= ?)
        """)
        for _ in range(4):
            params.append(price_max)
        params.append(price_max)

    # Фильтр по дате погрузки (используем application_points)
    if filters.get('loading_date_from') or filters.get('loading_date_to'):
        date_conditions = []

        if filters.get('loading_date_from'):
            date_conditions.append("DATE(ap.point_datetime) >= DATE(?)")
            params.append(filters['loading_date_from'])

        if filters.get('loading_date_to'):
            date_conditions.append("DATE(ap.point_datetime) <= DATE(?)")
            params.append(filters['loading_date_to'])

        date_condition_str = " AND ".join(date_conditions) if date_conditions else "1=1"

        conditions.append(f"""
            EXISTS (
                SELECT 1 FROM application_points ap 
                WHERE ap.application_id = a.id 
                AND ap.point_type = 'loading'
                AND {date_condition_str}
            )
        """)

    # Фильтр по городам - улучшенный вариант с использованием application_points
    if filters.get('loading_city') and len(filters['loading_city']) > 0:
        city_conditions = []
        for city in filters['loading_city']:
            # Поиск без учета регистра и пробелов
            city_conditions.append(f"LOWER(TRIM(ap.city)) LIKE LOWER(TRIM(?))")
            params.append(f"%{city}%")

        placeholders = ' OR '.join(city_conditions)
        subquery = f"""
            EXISTS (
                SELECT 1 FROM application_points ap 
                WHERE ap.application_id = a.id 
                AND ap.point_type = 'loading' 
                AND ({placeholders})
            )
        """
        conditions.append(subquery)

    if filters.get('unloading_city') and len(filters['unloading_city']) > 0:
        city_conditions = []
        for city in filters['unloading_city']:
            city_conditions.append(f"LOWER(TRIM(ap.city)) LIKE LOWER(TRIM(?))")
            params.append(f"%{city}%")

        placeholders = ' OR '.join(city_conditions)
        subquery = f"""
            EXISTS (
                SELECT 1 FROM application_points ap 
                WHERE ap.application_id = a.id 
                AND ap.point_type = 'unloading' 
                AND ({placeholders})
            )
        """
        conditions.append(subquery)

    # Фильтр по типу заявки
    if filters.get('application_type') and len(filters['application_type']) > 0:
        placeholders = ', '.join(['?' for _ in filters['application_type']])
        conditions.append(f"a.application_type IN ({placeholders})")
        params.extend(filters['application_type'])

    # Фильтр "без моего отклика"
    if filters.get('show_without_response') and executor_id:
        conditions.append("""
            NOT EXISTS (
                SELECT 1 FROM application_responses ar 
                WHERE ar.application_id = a.id 
                AND ar.executor_id = ?
            )
        """)
        params.append(executor_id)

    # Добавляем условия к запросу
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    return query, params


def get_filtered_applications(db, executor_id, filters, limit=20, offset=0):
    """
    Получает отфильтрованные заявки с учетом новой структуры таблиц
    """
    base_query = """
        SELECT DISTINCT a.*, 
               u.first_name, u.last_name, u.ati_code,
               COUNT(DISTINCT ar.id) as response_count,
               EXISTS(
                   SELECT 1 FROM application_responses ar2 
                   WHERE ar2.application_id = a.id 
                   AND ar2.executor_id = ?
               ) as has_my_response,
               -- Получаем минимальную дату погрузки (первая точка погрузки)
               (
                   SELECT MIN(point_datetime) 
                   FROM application_points 
                   WHERE application_id = a.id AND point_type = 'loading'
               ) as first_loading_datetime,
               -- Получаем максимальную дату выгрузки (последняя точка выгрузки)
               (
                   SELECT MAX(point_datetime) 
                   FROM application_points 
                   WHERE application_id = a.id AND point_type = 'unloading'
               ) as last_unloading_datetime,
               -- Получаем список городов погрузки (исправлено: убран DISTINCT внутри GROUP_CONCAT)
               (
                   SELECT GROUP_CONCAT(city, ' → ') 
                   FROM (
                       SELECT DISTINCT city 
                       FROM application_points 
                       WHERE application_id = a.id AND point_type = 'loading'
                       ORDER BY point_order
                   )
               ) as loading_cities,
               -- Получаем список городов выгрузки (исправлено: убран DISTINCT внутри GROUP_CONCAT)
               (
                   SELECT GROUP_CONCAT(city, ' → ') 
                   FROM (
                       SELECT DISTINCT city 
                       FROM application_points 
                       WHERE application_id = a.id AND point_type = 'unloading'
                       ORDER BY point_order
                   )
               ) as unloading_cities
        FROM applications a
        JOIN users u ON a.created_by = u.telegram_id
        LEFT JOIN application_responses ar ON a.id = ar.application_id
    """

    # Добавляем параметр executor_id в начало
    all_params = [executor_id]

    # Применяем фильтры
    filtered_query, filter_params = apply_filters_to_query(
        base_query, filters, executor_id
    )
    all_params.extend(filter_params)

    # Добавляем группировку и сортировку
    full_query = filtered_query + """
        GROUP BY a.id
        ORDER BY a.created_at DESC
        LIMIT ? OFFSET ?
    """

    all_params.extend([limit, offset])

    print(f"📋 SQL запрос с фильтрами: {full_query}")
    print(f"📋 Параметры: {all_params}")

    applications = db.fetch_all(full_query, tuple(all_params))

    return applications


def get_filter_stats(db, executor_id, filters):
    """
    Получает статистику по фильтрам
    """
    base_query = """
        SELECT COUNT(DISTINCT a.id) as total
        FROM applications a
    """

    filtered_query, params = apply_filters_to_query(
        base_query, filters, executor_id
    )

    result = db.fetch_one(filtered_query, tuple(params))
    return result['total'] if result else 0