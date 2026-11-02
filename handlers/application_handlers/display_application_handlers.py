from datetime import datetime
import ast
from utils.dicts import VEHICLE_TYPE_REVERSE_MAPPING, CARGO_TYPE_REVERSE_MAPPING


def format_application_for_executor(application, points, creator_info=None, company_info=None):
    """Форматирует заявку для отображения перевозчикам"""

    # Разделяем точки на погрузку и выгрузку
    loading_points = [p for p in points if p['point_type'] == 'loading']
    unloading_points = [p for p in points if p['point_type'] == 'unloading']

    # Базовые данные
    app_id = application['id']
    app_type = application['application_type']

    # Для предпросмотра берем ПЕРВУЮ точку погрузки и ПОСЛЕДНЮЮ точку выгрузки
    first_loading_city = "Не указано"
    last_unloading_city = "Не указано"
    first_loading_datetime = None
    last_unloading_datetime = None

    if loading_points and len(loading_points) > 0:
        first_point = loading_points[0]
        first_loading_city = first_point.get('city', 'Не указано')
        first_loading_datetime = first_point.get('point_datetime')

    if unloading_points and len(unloading_points) > 0:
        last_point = unloading_points[-1]
        last_unloading_city = last_point.get('city', 'Не указано')
        last_unloading_datetime = last_point.get('point_datetime')

    # Вес и объем груза
    cargo_weight = float(application.get('weight', 0))
    cargo_volume = float(application.get('volume', 0))

    # Форматируем даты первой погрузки и последней выгрузки
    loading_date = format_datetime(first_loading_datetime) if first_loading_datetime else "Не указана"
    unloading_date = format_datetime(last_unloading_datetime) if last_unloading_datetime else "Не указана"

    # Убираем время, если оно 00:00
    if loading_date.endswith(' 00:00'):
        loading_date = loading_date.replace(' 00:00', '')
    if unloading_date.endswith(' 00:00'):
        unloading_date = unloading_date.replace(' 00:00', '')

    # Тип заявки и цена
    type_icon = "📦" if app_type == 'fixed' else "🏷️"
    type_text = "СТАНДАРТНАЯ" if app_type == 'fixed' else "ЗАПРОС СТАВОК"

    # Обрабатываем payment_options
    payment_options_text = ""
    if app_type == 'fixed':
        payment_options = application.get('payment_options')
        if payment_options:
            try:
                if isinstance(payment_options, str):
                    payment_options = ast.literal_eval(payment_options)

                payments = []
                if payment_options.get('nds'):
                    payments.append(f"• С НДС: {float(payment_options['nds']):,.0f} ₽")
                if payment_options.get('ip'):
                    payments.append(f"• Без НДС: {float(payment_options['ip']):,.0f} ₽")
                if payment_options.get('self-employed'):
                    payments.append(f"• Самозанятый: {float(payment_options['self-employed']):,.0f} ₽")
                if payment_options.get('cash'):
                    payments.append(f"• Наличные: {float(payment_options['cash']):,.0f} ₽")

                if payments:
                    payment_options_text = "\n".join(payments)
            except Exception as e:
                print(f"Ошибка парсинга payment_options: {e}")
                fixed_price = float(application.get('fixed_price', 0))
                payment_options_text = f"{fixed_price:,.0f} ₽".replace(',', ' ')
        else:
            fixed_price = float(application.get('fixed_price', 0))
            payment_options_text = f"{fixed_price:,.0f} ₽".replace(',', ' ')

        price_display = f"💰 **ВАРИАНТЫ ОПЛАТЫ:**\n{payment_options_text}"
    else:
        desired_budget = float(application.get('desired_budget', 0))
        price_display = f"💰 **БЮДЖЕТ:** {desired_budget:,.0f} ₽".replace(',', ' ')

    # Тип кузова
    vehicle_type = application.get('vehicle_type', 'Не указан')
    vehicle_type_display = VEHICLE_TYPE_REVERSE_MAPPING.get(vehicle_type, vehicle_type)

    # Информация о создателе заявки
    company_name = "Не указана"
    ati_code = "Не указан"
    urgent_app = ''

    if company_info and 'name' in company_info:
        company_name = company_info['name']

    if creator_info:
        if 'ati_code' in creator_info and creator_info['ati_code']:
            ati_code = creator_info['ati_code']
        elif 'ati_code_display' in creator_info and creator_info['ati_code_display']:
            ati_code = creator_info['ati_code_display']

    if application.get('status') == 'urgent':
        urgent_app = '🚨 **СРОЧНАЯ ЗАЯВКА** 🚨'

    # Формируем информацию о маршруте
    route_info = f"{first_loading_city} → {last_unloading_city}"

    # Добавляем информацию о количестве точек в маршруте
    points_info = ""
    if len(loading_points) > 1 or len(unloading_points) > 1:
        points_info = f"\n📍 Маршрут: {len(loading_points)} погрузок → {len(unloading_points)} выгрузок"

    # Добавляем информацию о сроке оплаты
    payment_deadline_text = ""
    payment_deadline = application.get('payment_deadline')
    if payment_deadline:
        try:
            if isinstance(payment_deadline, str):
                # Пробуем разные форматы даты
                for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S']:
                    try:
                        deadline_date = datetime.strptime(payment_deadline, fmt)
                        payment_deadline_text = f"\n📅 **Оплата до:** {deadline_date.strftime('%d.%m.%Y')}"
                        break
                    except:
                        continue
                else:
                    payment_deadline_text = f"\n📅 **Оплата до:** {payment_deadline}"
            else:
                payment_deadline_text = f"\n📅 **Оплата до:** {payment_deadline.strftime('%d.%m.%Y')}"
        except:
            payment_deadline_text = f"\n📅 **Оплата до:** {payment_deadline}"

    # Форматируем по шаблону
    formatted_text = f"""
📦 ЗАЯВКА #{app_id}
{urgent_app}
🏢 Компания: {company_name}
👤 ATI: {ati_code}
📍 {route_info}  
🚛 Требуемый транспорт: {vehicle_type_display} 
📅 {loading_date} → 📅 {unloading_date}
{points_info}
{price_display}
{payment_deadline_text}

{type_icon} {type_text}
""".strip()

    return formatted_text


def format_datetime(dt_value):
    """Форматирует дату-время в читаемый формат"""
    if not dt_value:
        return "Не указана"

    try:
        if isinstance(dt_value, str):
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%d.%m.%Y %H:%M',
                '%Y-%m-%d',
                '%d.%m.%Y'
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(dt_value, fmt)
                    if dt.hour == 0 and dt.minute == 0:
                        return dt.strftime('%d.%m.%Y')
                    else:
                        return dt.strftime('%d.%m.%Y %H:%M')
                except:
                    continue
            return dt_value
        elif isinstance(dt_value, datetime):
            if dt_value.hour == 0 and dt_value.minute == 0:
                return dt_value.strftime('%d.%m.%Y')
            else:
                return dt_value.strftime('%d.%m.%Y %H:%M')
        else:
            return str(dt_value)
    except:
        return "Не указана"