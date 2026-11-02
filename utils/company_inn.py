from dadata import Dadata
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Инициализация (получите токен на dadata.ru)
DADATA_API_KEY = "ваш_api_ключ"
DADATA_SECRET_KEY = "ваш_секретный_ключ"


def get_company_by_inn(inn):
    """Получение данных компании по ИНН через DaData"""
    try:
        dadata = Dadata(DADATA_API_KEY, DADATA_SECRET_KEY)

        # Делаем запрос
        result = dadata.find_by_id("party", inn)

        if result:
            company_data = result[0]
            return format_company_info(company_data)
        else:
            return None

    except Exception as e:
        print(f'❌ Ошибка DaData: {e}')
        return None


def format_company_info(company_data):
    """Форматирование информации о компании"""
    data = company_data.get('data', {})

    info = f"""
🏢 **Название:** {company_data.get('value', 'Не указано')}
📊 **Полное название:** {data.get('name', {}).get('full_with_opf', 'Не указано')}
📄 **ИНН:** {data.get('inn', 'Не указано')}
📄 **КПП:** {data.get('kpp', 'Не указано')}
📄 **ОГРН:** {data.get('ogrn', 'Не указано')}

📍 **Адрес:** {data.get('address', {}).get('value', 'Не указано')}

👨‍💼 **Руководитель:** {data.get('management', {}).get('name', 'Не указано')}
📝 **Должность:** {data.get('management', {}).get('post', 'Не указано')}

💰 **Уставной капитал:** {data.get('capital', {}).get('value', 'Не указано')} руб.
🗓️ **Дата регистрации:** {data.get('ogrn_date', 'Не указано')}

✅ **Статус:** {data.get('state', {}).get('status', 'Не указано')}
    """

    return info.strip()