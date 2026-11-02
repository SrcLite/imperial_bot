import requests
import sys


def test_bitrix_connection(webhook_url):
    """Тестирует подключение к Битрикс24"""

    # Добавляем слеш в конце если нужно
    if not webhook_url.endswith('/'):
        webhook_url += '/'

    print(f"🔄 Тестируем подключение к: {webhook_url}")

    # Метод 1: app.info (базовый метод)
    url1 = f"{webhook_url}app.info"
    print(f"1. Тестируем метод app.info: {url1}")

    try:
        response1 = requests.post(url1, timeout=10)
        print(f"   Код ответа: {response1.status_code}")
        print(f"   Ответ: {response1.text[:200]}")

        if response1.status_code == 200:
            data = response1.json()
            if 'result' in data:
                print(f"✅ Успешно! Приложение: {data['result'].get('name', 'Неизвестно')}")
                return True
            else:
                print(f"❌ Ошибка в ответе: {data}")
        else:
            print(f"❌ HTTP ошибка: {response1.status_code}")

    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")

    # Метод 2: crm.currency.list (простой метод CRM)
    print("\n2. Тестируем метод crm.currency.list")
    url2 = f"{webhook_url}crm.currency.list"

    try:
        response2 = requests.post(url2, timeout=10)
        print(f"   Код ответа: {response2.status_code}")
        print(f"   Ответ: {response2.text[:200]}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    # Метод 3: Проверка без .json в URL
    print("\n3. Тестируем без .json в URL")
    url3 = webhook_url.rstrip('/') + "/app.info"
    print(f"   URL: {url3}")

    try:
        response3 = requests.post(url3, timeout=10)
        print(f"   Код ответа: {response3.status_code}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    return False


def check_webhook_format(webhook_url):
    """Проверяет формат вебхука"""
    print("\n🔍 Анализ URL вебхука:")

    # Проверяем наличие обязательных частей
    required_parts = ['bitrix24', 'rest']
    for part in required_parts:
        if part not in webhook_url:
            print(f"❌ В URL отсутствует '{part}'")

    # Разбиваем URL на части
    parts = webhook_url.split('/')
    print(f"   Части URL: {parts}")

    # Проверяем структуру
    if len(parts) < 7:
        print(f"❌ URL слишком короткий: {len(parts)} частей")

    # Проверяем наличие кода вебхука (обычно после 'rest/')
    rest_index = -1
    for i, part in enumerate(parts):
        if part == 'rest':
            rest_index = i
            break

    if rest_index != -1 and rest_index + 2 < len(parts):
        webhook_code = parts[rest_index + 2]
        print(f"   Код вебхука: {webhook_code}")
        print(f"   Длина кода: {len(webhook_code)} символов")

    return True


if __name__ == "__main__":
    # Введите ваш URL вебхука
    if len(sys.argv) > 1:
        webhook_url = sys.argv[1]
    else:
        webhook_url = input("Введите URL вебхука Битрикс24: ").strip()

    print("=" * 60)
    check_webhook_format(webhook_url)
    print("=" * 60)
    test_bitrix_connection(webhook_url)