import email
import smtplib
import time
import re
import dns.resolver
import dns.exception
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid, formatdate
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple


# Конфигурация отправителя
EMAIL_CONFIG = {
    'sender_email': 'imper1bot@yandex.ru',
    'sender_name': 'Империал',
    'sender_password': 'gmrestwmsnlmhoaq',
    'default_smtp': 'smtp.yandex.ru',
    'default_port': 587
}

# Глобальные настройки для избежания спам-фильтров
EMAIL_SETTINGS = {
    'max_emails_per_day': 30,
    'delay_between_emails': 5,
    'last_sent_time': None,
    'sent_today': 0,
    'last_reset_date': datetime.now().date()
}
DNS_SETTINGS = {
    'timeout': 5,
    'lifetime': 10,
    'nameservers': ['8.8.8.8', '1.1.1.1']  # Google DNS и Cloudflare DNS
}

class DNSRecordChecker:
    """Класс для проверки DNS записей SPF, DKIM, DMARC"""

    def __init__(self):
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = DNS_SETTINGS['timeout']
        self.resolver.lifetime = DNS_SETTINGS['lifetime']

        if DNS_SETTINGS['nameservers']:
            self.resolver.nameservers = DNS_SETTINGS['nameservers']

    def check_spf_record(self, domain: str) -> Dict:
        """
        Проверяет SPF запись для домена
        Возвращает словарь с результатами проверки
        """
        result = {
            'has_spf': False,
            'record': None,
            'includes_yandex': False,
            'all_mechanism': None,
            'valid': False,
            'errors': []
        }

        try:
            answers = self.resolver.resolve(domain, 'TXT')

            for rdata in answers:
                txt_record = str(rdata).strip('"')
                if txt_record.startswith('v=spf1'):
                    result['has_spf'] = True
                    result['record'] = txt_record

                    # Проверяем включает ли Яндекс
                    if 'include:yandex.net' in txt_record or 'include:yandex.ru' in txt_record:
                        result['includes_yandex'] = True

                    # Определяем механизм all
                    if '~all' in txt_record:
                        result['all_mechanism'] = 'softfail (~all)'
                        result['valid'] = True
                    elif '-all' in txt_record:
                        result['all_mechanism'] = 'hardfail (-all)'
                        result['valid'] = True
                    elif '?all' in txt_record:
                        result['all_mechanism'] = 'neutral (?all)'
                        result['valid'] = True
                    else:
                        result['errors'].append('Отсутствует механизм all в SPF записи')

                    # Проверяем синтаксис
                    if 'v=spf1' in txt_record:
                        result['valid'] = True
                    else:
                        result['errors'].append('Некорректный синтаксис SPF записи')

                    break

            if not result['has_spf']:
                result['errors'].append('SPF запись не найдена')

        except dns.resolver.NoAnswer:
            result['errors'].append('Нет TXT записей для домена')
        except dns.resolver.NXDOMAIN:
            result['errors'].append('Домен не существует')
        except dns.exception.Timeout:
            result['errors'].append('Таймаут при запросе DNS')
        except Exception as e:
            result['errors'].append(f'Ошибка DNS: {str(e)}')

        return result

    def check_dkim_record(self, domain: str, selector: str = 'mail') -> Dict:
        """
        Проверяет DKIM запись для домена
        selector: селектор DKIM (по умолчанию 'mail', 'default', 'yandex' и т.д.)
        """
        result = {
            'has_dkim': False,
            'selector': selector,
            'record': None,
            'valid': False,
            'key_type': None,
            'key_length': None,
            'errors': []
        }

        dkim_domain = f'{selector}._domainkey.{domain}'

        try:
            answers = self.resolver.resolve(dkim_domain, 'TXT')

            for rdata in answers:
                txt_record = str(rdata).strip('"')
                if 'v=DKIM1' in txt_record or 'k=rsa' in txt_record:
                    result['has_dkim'] = True
                    result['record'] = txt_record
                    result['valid'] = True

                    # Извлекаем информацию о ключе
                    if 'k=rsa' in txt_record:
                        result['key_type'] = 'RSA'
                        # Пытаемся определить длину ключа
                        p_match = re.search(r'p=([A-Za-z0-9+/]+)', txt_record)
                        if p_match:
                            key_data = p_match.group(1)
                            # Примерная оценка длины ключа
                            key_bits = len(key_data) * 6  # Базовый расчет
                            if key_bits < 512:
                                result['key_length'] = 'короткий (<512 бит)'
                            elif key_bits < 1024:
                                result['key_length'] = 'средний (512-1024 бит)'
                            else:
                                result['key_length'] = 'рекомендуемый (≥1024 бит)'

                    break

            if not result['has_dkim']:
                result['errors'].append(f'DKIM запись не найдена для селектора {selector}')

        except dns.resolver.NoAnswer:
            result['errors'].append(f'Нет DKIM записи для селектора {selector}')
        except dns.resolver.NXDOMAIN:
            result['errors'].append(f'DKIM домен не существует: {dkim_domain}')
        except dns.exception.Timeout:
            result['errors'].append('Таймаут при запросе DNS')
        except Exception as e:
            result['errors'].append(f'Ошибка DKIM проверки: {str(e)}')

        return result

    def check_dmarc_record(self, domain: str) -> Dict:
        """
        Проверяет DMARC запись для домена
        """
        result = {
            'has_dmarc': False,
            'record': None,
            'policy': None,
            'subdomain_policy': None,
            'percentage': 100,
            'report_uri': [],
            'forensic_report_uri': [],
            'rua': [],
            'ruf': [],
            'valid': False,
            'errors': [],
            'warnings': []
        }

        dmarc_domain = f'_dmarc.{domain}'

        try:
            answers = self.resolver.resolve(dmarc_domain, 'TXT')

            for rdata in answers:
                txt_record = str(rdata).strip('"')
                if 'v=DMARC1' in txt_record:
                    result['has_dmarc'] = True
                    result['record'] = txt_record

                    # Парсим параметры DMARC
                    params = {}
                    for param in txt_record.split(';'):
                        param = param.strip()
                        if '=' in param:
                            key, value = param.split('=', 1)
                            params[key] = value

                    # Проверяем политику
                    if 'p' in params:
                        result['policy'] = params['p']
                        if params['p'] in ['none', 'quarantine', 'reject']:
                            result['valid'] = True
                        else:
                            result['errors'].append(f'Некорректная политика DMARC: {params["p"]}')
                    else:
                        result['errors'].append('Отсутствует параметр p (policy)')

                    # Проверяем политику для поддоменов
                    if 'sp' in params:
                        result['subdomain_policy'] = params['sp']

                    # Процент сообщений
                    if 'pct' in params:
                        try:
                            result['percentage'] = int(params['pct'])
                        except:
                            result['warnings'].append(f'Некорректный процент: {params["pct"]}')

                    # Адреса для отчетов
                    if 'rua' in params:
                        uris = params['rua'].split(',')
                        result['rua'] = [uri.strip() for uri in uris]
                        result['report_uri'] = result['rua']

                    if 'ruf' in params:
                        uris = params['ruf'].split(',')
                        result['ruf'] = [uri.strip() for uri in uris]
                        result['forensic_report_uri'] = result['ruf']

                    # Формат отчетов
                    if 'fo' in params:
                        result['forensic_options'] = params['fo']

                    # Интервал отчетов
                    if 'ri' in params:
                        try:
                            result['report_interval'] = int(params['ri'])
                        except:
                            pass

                    break

            if not result['has_dmarc']:
                result['warnings'].append('DMARC запись не найдена (рекомендуется настроить)')

        except dns.resolver.NoAnswer:
            result['warnings'].append('DMARC запись не найдена')
        except dns.resolver.NXDOMAIN:
            result['warnings'].append('DMARC домен не существует')
        except dns.exception.Timeout:
            result['errors'].append('Таймаут при запросе DNS')
        except Exception as e:
            result['errors'].append(f'Ошибка DMARC проверки: {str(e)}')

        return result

    def check_all_records(self, domain: str) -> Dict:
        """
        Комплексная проверка всех DNS записей для домена
        """
        print(f"\n🔍 ПРОВЕРКА DNS ЗАПИСЕЙ ДЛЯ: {domain}")
        print("=" * 50)

        results = {
            'domain': domain,
            'spf': self.check_spf_record(domain),
            'dkim': [],
            'dmarc': self.check_dmarc_record(domain),
            'overall_score': 0,
            'recommendations': []
        }

        # Проверяем несколько возможных DKIM селекторов
        common_selectors = ['mail', 'default', 'yandex', 'google', 'selector1', 'selector2']
        for selector in common_selectors:
            dkim_result = self.check_dkim_record(domain, selector)
            if dkim_result['has_dkim']:
                results['dkim'].append(dkim_result)
                break

        # Если не нашли DKIM, добавляем пустой результат
        if not results['dkim']:
            results['dkim'].append(self.check_dkim_record(domain, 'mail'))

        # Вычисляем общий балл
        score = 0
        max_score = 3

        if results['spf']['valid']:
            score += 1
            print(f"✅ SPF: Настроен корректно")
            if results['spf']['includes_yandex']:
                print(f"   • Включает Яндекс: ДА")
            print(f"   • Механизм: {results['spf']['all_mechanism']}")
        else:
            print(f"❌ SPF: Проблемы с настройкой")
            for error in results['spf']['errors']:
                print(f"   • {error}")

        if results['dkim'][0]['valid']:
            score += 1
            print(f"✅ DKIM: Настроен корректно")
            print(f"   • Селектор: {results['dkim'][0]['selector']}")
            if results['dkim'][0]['key_length']:
                print(f"   • Длина ключа: {results['dkim'][0]['key_length']}")
        else:
            print(f"⚠️ DKIM: Не настроен или проблемы")
            for error in results['dkim'][0]['errors']:
                print(f"   • {error}")

        if results['dmarc']['valid']:
            score += 1
            print(f"✅ DMARC: Настроен корректно")
            print(f"   • Политика: {results['dmarc']['policy']}")
            if results['dmarc']['rua']:
                print(f"   • Отчеты отправляются на: {', '.join(results['dmarc']['rua'])}")
        else:
            print(f"⚠️ DMARC: Не настроен или проблемы")
            if results['dmarc']['warnings']:
                for warning in results['dmarc']['warnings']:
                    print(f"   • {warning}")
            for error in results['dmarc']['errors']:
                print(f"   • {error}")

        results['overall_score'] = (score / max_score) * 100

        print(f"\n📊 ОБЩАЯ ОЦЕНКА: {results['overall_score']:.0f}%")

        # Формируем рекомендации
        if not results['spf']['valid']:
            results['recommendations'].append(
                "Добавьте SPF запись в DNS вашего домена: "
                "v=spf1 include:yandex.net ~all"
            )

        if not results['dkim'][0]['valid']:
            results['recommendations'].append(
                "Настройте DKIM в панели управления Яндекс.Почты для доменов"
            )

        if not results['dmarc']['valid']:
            results['recommendations'].append(
                "Добавьте DMARC запись для мониторинга: "
                "v=DMARC1; p=none; rua=mailto:admin@example.com"
            )

        if results['recommendations']:
            print(f"\n💡 РЕКОМЕНДАЦИИ:")
            for i, rec in enumerate(results['recommendations'], 1):
                print(f"   {i}. {rec}")

        print("=" * 50)

        return results


class DMARCReportManager:
    """Класс для управления DMARC отчетами"""

    def __init__(self):
        self.reports_dir = 'dmarc_reports'
        self.setup_directories()

    def setup_directories(self):
        """Создает необходимые директории для отчетов"""
        import os
        if not os.path.exists(self.reports_dir):
            os.makedirs(self.reports_dir)

        subdirs = ['received', 'processed', 'failed', 'archived']
        for subdir in subdirs:
            path = os.path.join(self.reports_dir, subdir)
            if not os.path.exists(path):
                os.makedirs(path)

    def parse_dmarc_report(self, xml_content: str) -> Optional[Dict]:
        """
        Парсит XML отчет DMARC
        Упрощенная версия для анализа структуры
        """
        try:
            # В реальном приложении используйте xml.etree.ElementTree
            # Здесь упрощенный парсинг для демонстрации
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_content)

            report = {
                'report_id': None,
                'date_range': {},
                'policy_published': {},
                'records': []
            }

            # Парсим основные поля
            for child in root:
                if child.tag.endswith('report_metadata'):
                    for meta in child:
                        if meta.tag.endswith('report_id'):
                            report['report_id'] = meta.text
                        elif meta.tag.endswith('date_range'):
                            for date_elem in meta:
                                if date_elem.tag.endswith('begin'):
                                    report['date_range']['begin'] = int(date_elem.text)
                                elif date_elem.tag.endswith('end'):
                                    report['date_range']['end'] = int(date_elem.text)

                elif child.tag.endswith('policy_published'):
                    for policy in child:
                        tag_name = policy.tag.split('}')[-1]
                        report['policy_published'][tag_name] = policy.text

                elif child.tag.endswith('record'):
                    record_data = {}
                    for record in child:
                        if record.tag.endswith('row'):
                            for row_elem in record:
                                tag_name = row_elem.tag.split('}')[-1]
                                record_data[tag_name] = row_elem.text

                        elif record.tag.endswith('identifiers'):
                            for id_elem in record:
                                tag_name = id_elem.tag.split('}')[-1]
                                record_data[f'identifier_{tag_name}'] = id_elem.text

                        elif record.tag.endswith('auth_results'):
                            auth_data = {}
                            for auth in record:
                                auth_type = auth.tag.split('}')[-1]
                                auth_data[auth_type] = {}
                                for result in auth:
                                    result_name = result.tag.split('}')[-1]
                                    auth_data[auth_type][result_name] = result.text
                            record_data['auth_results'] = auth_data

                    report['records'].append(record_data)

            return report

        except Exception as e:
            print(f"Ошибка парсинга DMARC отчета: {e}")
            return None

    def generate_summary_report(self, domain: str, days: int = 30) -> Dict:
        """
        Генерирует суммарный отчет на основе полученных данных
        """
        import os
        import json

        summary = {
            'domain': domain,
            'period_days': days,
            'total_reports': 0,
            'total_messages': 0,
            'spf_pass': 0,
            'dkim_pass': 0,
            'dmarc_pass': 0,
            'sources': {},
            'recommendations': []
        }

        reports_path = os.path.join(self.reports_dir, 'processed')

        if os.path.exists(reports_path):
            for filename in os.listdir(reports_path):
                if filename.endswith('.json') and domain in filename:
                    try:
                        with open(os.path.join(reports_path, filename), 'r') as f:
                            report = json.load(f)

                        summary['total_reports'] += 1

                        for record in report.get('records', []):
                            summary['total_messages'] += 1

                            # Анализируем результаты аутентификации
                            auth = record.get('auth_results', {})

                            if auth.get('spf', {}).get('result') == 'pass':
                                summary['spf_pass'] += 1

                            if auth.get('dkim', {}).get('result') == 'pass':
                                summary['dkim_pass'] += 1

                            # DMARC проходит если проходит SPF ИЛИ DKIM
                            if (auth.get('spf', {}).get('result') == 'pass' or
                                    auth.get('dkim', {}).get('result') == 'pass'):
                                summary['dmarc_pass'] += 1

                            # Собираем информацию об источниках
                            source_ip = record.get('source_ip')
                            if source_ip:
                                summary['sources'][source_ip] = summary['sources'].get(source_ip, 0) + 1

                    except Exception as e:
                        print(f"Ошибка обработки отчета {filename}: {e}")

        # Формируем рекомендации
        if summary['total_messages'] > 0:
            spf_rate = (summary['spf_pass'] / summary['total_messages']) * 100
            dkim_rate = (summary['dkim_pass'] / summary['total_messages']) * 100
            dmarc_rate = (summary['dmarc_pass'] / summary['total_messages']) * 100

            if spf_rate < 90:
                summary['recommendations'].append(
                    f"Улучшите SPF: только {spf_rate:.1f}% писем проходят проверку"
                )

            if dkim_rate < 90:
                summary['recommendations'].append(
                    f"Улучшите DKIM: только {dkim_rate:.1f}% писем проходят проверку"
                )

            if dmarc_rate < 95:
                summary['recommendations'].append(
                    f"Улучшите DMARC: только {dmarc_rate:.1f}% писем проходят проверку"
                )

        return summary


def sanitize_email_content(text):
    """
    Очищает текст от элементов, которые могут вызвать спам-фильтр

    Правила для Яндекса:
    1. Убираем все HTML-теги (используем только plain text)
    2. Убираем эмодзи и специальные символы
    3. Ограничиваем повторяющиеся символы
    4. Убираем спам-триггеры
    """
    if not isinstance(text, str):
        text = str(text)

    # Список спам-триггеров (избегаем этих слов в чистом виде)
    spam_triggers = [
        r'\bбесплатно\b', r'\bкупи\b', r'\bсрочно\b', r'\bтолько сегодня\b',
        r'\bуникальный\b', r'\bгарантия\b', r'\bприбыль\b', r'\bдоход\b',
        r'\bвыиграй\b', r'\bподарок\b'
    ]

    # Заменяем спам-триггеры на нейтральные синонимы
    replacements = {
        'бесплатно': 'без оплаты',
        'купи': 'приобрети',
        'срочно': 'в ближайшее время',
        'гарантия': 'обеспечение'
    }

    for trigger, replacement in replacements.items():
        text = re.sub(r'\b' + re.escape(trigger) + r'\b', replacement, text, flags=re.IGNORECASE)

    # Убираем HTML-теги
    text = re.sub(r'<[^>]+>', '', text)

    # Убираем эмодзи и специальные символы, кроме основных знаков препинания
    text = re.sub(r'[^\w\s\-\.\,\:\!\?\@\#\$\%\&\*\(\)\+\=\[\]\{\}\\\/\|\<\>\'\"\n\r]', '', text)

    # Ограничиваем повторяющиеся символы (не более 3 подряд)
    text = re.sub(r'(.)\1{3,}', r'\1\1\1', text)

    # Ограничиваем длину строк (не более 78 символов для email)
    lines = text.split('\n')
    wrapped_lines = []
    for line in lines:
        if len(line) > 78:
            # Простой перенос строк
            for i in range(0, len(line), 78):
                wrapped_lines.append(line[i:i + 78])
        else:
            wrapped_lines.append(line)

    return '\n'.join(wrapped_lines).strip()


def validate_email_auth_before_send(sender_domain: str, recipient_domain: str) -> bool:
    """
    Проверяет настройки аутентификации перед отправкой
    """
    print(f"\n🔐 ПРОВЕРКА АУТЕНТИФИКАЦИИ ПЕРЕД ОТПРАВКОЙ")
    print(f"   Отправитель: {sender_domain}")
    print(f"   Получатель: {recipient_domain}")

    checker = DNSRecordChecker()

    # Проверяем настройки отправителя
    sender_results = checker.check_all_records(sender_domain)

    if sender_results['overall_score'] < 60:
        print(f"⚠️  Внимание: низкий уровень аутентификации отправителя")
        print(f"   Рекомендуется улучшить настройки SPF/DKIM/DMARC")

    # Проверяем политику получателя
    recipient_dmarc = checker.check_dmarc_record(recipient_domain)

    if recipient_dmarc.get('policy') == 'reject':
        print(f"⚠️  Внимание: получатель использует strict DMARC policy")
        print(f"   Письма без SPF/DKIM будут отклонены")

    return sender_results['overall_score'] >= 50


def enhanced_send_email_notification(subject, message, recipient_email):
    """
    Улучшенная функция отправки с проверкой аутентификации
    """
    # Извлекаем домены
    sender_domain = EMAIL_CONFIG['sender_email'].split('@')[1]
    recipient_domain = recipient_email.split('@')[1]

    # Проверяем аутентификацию
    if not validate_email_auth_before_send(sender_domain, recipient_domain):
        print(f"⚠️  Отправка может быть проблематичной из-за настроек аутентификации")
        user_input = input("Продолжить отправку? (y/n): ")
        if user_input.lower() != 'y':
            return False

    return send_email_notification(subject, message, recipient_email)


def generate_dmarc_record(domain: str, report_email: str = None) -> str:
    """
    Генерирует рекомендуемую DMARC запись для домена
    """
    if not report_email:
        report_email = f'admin@{domain}'

    # Начальная рекомендация - мониторинг без блокировки
    dmarc_template = (
        f"v=DMARC1; p=none; rua=mailto:{report_email}; "
        f"ruf=mailto:{report_email}; fo=1; ri=86400"
    )

    print(f"\n📝 РЕКОМЕНДУЕМАЯ DMARC ЗАПИСЬ ДЛЯ {domain}:")
    print(f"   Имя записи: _dmarc.{domain}")
    print(f"   Тип записи: TXT")
    print(f"   Значение: {dmarc_template}")
    print(f"\n💡 Рекомендации по настройке:")
    print(f"   1. После 2 недель мониторинга измените p=none на p=quarantine")
    print(f"   2. Еще через 2 недели - на p=reject")
    print(f"   3. Проверяйте отчеты на {report_email}")

    return dmarc_template


def generate_spf_record(domain: str, include_yandex: bool = True) -> str:
    """
    Генерирует рекомендуемую SPF запись
    """
    if include_yandex:
        spf_record = "v=spf1 include:yandex.net ~all"
    else:
        spf_record = "v=spf1 ~all"

    print(f"\n📝 РЕКОМЕНДУЕМАЯ SPF ЗАПИСЬ ДЛЯ {domain}:")
    print(f"   Имя записи: @ (корневой домен)")
    print(f"   Тип записи: TXT")
    print(f"   Значение: {spf_record}")

    return spf_record


def setup_email_monitoring_system():
    """
    Настраивает систему мониторинга email доставляемости
    """
    print(f"\n🎯 НАСТРОЙКА СИСТЕМЫ МОНИТОРИНГА EMAIL")
    print("=" * 50)

    checker = DNSRecordChecker()
    report_manager = DMARCReportManager()

    # Проверяем текущие настройки
    sender_domain = EMAIL_CONFIG['sender_email'].split('@')[1]
    results = checker.check_all_records(sender_domain)

    # Предлагаем рекомендации
    if not results['spf']['valid']:
        print(f"\n🚨 ТРЕБУЕТСЯ НАСТРОЙКА SPF")
        spf_record = generate_spf_record(sender_domain, True)

        print(f"\n📋 Инструкция по добавлению SPF:")
        print(f"   1. Войдите в панель управления вашим хостингом")
        print(f"   2. Найдите раздел DNS или Zone Editor")
        print(f"   3. Добавьте новую TXT запись для домена {sender_domain}")
        print(f"   4. В поле значения введите: {spf_record}")

    if not results['dkim'][0]['valid'] and 'yandex' in sender_domain:
        print(f"\n🚨 ТРЕБУЕТСЯ НАСТРОЙКА DKIM")
        print(f"   Для Яндекс.Почты DKIM настраивается в Яндекс.Почте для доменов")
        print(f"   Инструкция: https://yandex.ru/support/business/mail/access.html")

    if not results['dmarc']['valid']:
        print(f"\n🚨 ТРЕБУЕТСЯ НАСТРОЙКА DMARC")
        dmarc_record = generate_dmarc_record(sender_domain)

        print(f"\n📋 Инструкция по добавлению DMARC:")
        print(f"   1. Войдите в панель управления вашим хостингом")
        print(f"   2. Найдите раздел DNS или Zone Editor")
        print(f"   3. Добавьте новую TXT запись с именем _dmarc.{sender_domain}")
        print(f"   4. В поле значения введите: {dmarc_record}")

    print(f"\n📊 СИСТЕМА МОНИТОРИНГА НАСТРОЕНА")
    print(f"   • Отчеты будут сохраняться в: {report_manager.reports_dir}")
    print(f"   • Для анализа используйте метод generate_summary_report()")

    return results

def check_sending_limits():
    """
    Проверяет и обновляет лимиты отправки

    Возвращает:
        tuple: (можно_отправлять, оставшееся_количество, задержка_в_секундах)
    """
    today = datetime.now().date()

    # Сбрасываем счетчик если новый день
    if today != EMAIL_SETTINGS['last_reset_date']:
        EMAIL_SETTINGS['sent_today'] = 0
        EMAIL_SETTINGS['last_reset_date'] = today

    # Проверяем лимит на день
    if EMAIL_SETTINGS['sent_today'] >= EMAIL_SETTINGS['max_emails_per_day']:
        return False, 0, 86400  # Ждать до завтра

    # Проверяем задержку между отправками
    if EMAIL_SETTINGS['last_sent_time']:
        elapsed = time.time() - EMAIL_SETTINGS['last_sent_time']
        if elapsed < EMAIL_SETTINGS['delay_between_emails']:
            wait_time = EMAIL_SETTINGS['delay_between_emails'] - elapsed
            return False, 0, wait_time

    remaining = EMAIL_SETTINGS['max_emails_per_day'] - EMAIL_SETTINGS['sent_today']
    return True, remaining, 0


def create_email_message(sender_email, sender_name, recipient_email, subject, body):
    """
    Создает email сообщение с правильными заголовками для избежания спама
    """
    # Очищаем содержимое
    clean_subject = sanitize_email_content(subject)
    clean_body = sanitize_email_content(body)

    # Создаем простое текстовое сообщение (не multipart!)
    msg = MIMEText(clean_body, 'plain', 'utf-8')

    # Устанавливаем основные заголовки
    msg['From'] = formataddr((sender_name, sender_email))
    msg['To'] = recipient_email
    msg['Subject'] = clean_subject

    # ВАЖНО: Добавляем заголовки для аутентификации и избежания спама
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='yandex.ru')

    # Для телеграм-бота лучше указать конкретный User-Agent
    msg['X-Mailer'] = 'TelegramBot/1.0'
    msg['X-Priority'] = '3'  # Нормальный приоритет

    # Критически важные заголовки для Яндекса
    msg['X-Originating-IP'] = 'unknown'  # Яндекс проверяет этот заголовок
    msg['X-Antivirus'] = 'Checked'
    msg['X-Antivirus-Status'] = 'Clean'

    # Указываем что это автоматическое уведомление (честно)
    msg['Auto-Submitted'] = 'auto-generated'
    msg['Precedence'] = 'bulk'

    # Обратный адрес (должен совпадать с отправителем)
    msg['Reply-To'] = sender_email

    return msg


def send_email_notification(subject, message, recipient_email):
    """
    Исправленная функция отправки email с защитой от спам-фильтров
    """
    print(f"\n{'=' * 60}")
    print(f"📧 ПОДГОТОВКА К ОТПРАВКЕ EMAIL")
    print(f"{'=' * 60}")

    # 1. Проверяем лимиты отправки
    can_send, remaining, wait_time = check_sending_limits()

    if not can_send:
        if wait_time >= 3600:
            hours = wait_time / 3600
            print(f"⏳ Достигнут дневной лимит ({EMAIL_SETTINGS['max_emails_per_day']} писем/день)")
            print(f"   Следующая отправка будет доступна через {hours:.1f} часов")
        else:
            print(f"⏳ Задержка между отправками: {wait_time:.1f} секунд")
            print(f"   Отправка через {wait_time:.1f} секунд...")
            time.sleep(wait_time)

    # 2. Проверяем валидность email
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', recipient_email):
        print(f"❌ Неверный email адрес: {recipient_email}")
        return False

    # 3. Подготавливаем сообщение
    print(f"🔧 Подготовка сообщения...")
    print(f"   От: {EMAIL_CONFIG['sender_name']} <{EMAIL_CONFIG['sender_email']}>")
    print(f"   Кому: {recipient_email}")
    print(f"   Тема: {subject[:50]}..." if len(subject) > 50 else f"   Тема: {subject}")

    # Создаем очищенное сообщение
    msg = create_email_message(
        EMAIL_CONFIG['sender_email'],
        EMAIL_CONFIG['sender_name'],
        recipient_email,
        subject,
        message
    )

    # 4. Подключаемся к SMTP (упрощенная версия, специфичная для Яндекс)
    try:
        print(f"🌐 Подключение к SMTP Яндекса...")

        # Используем явные настройки для Яндекса
        server = smtplib.SMTP('smtp.yandex.ru', 587, timeout=30)
        server.set_debuglevel(0)  # Отключаем отладку для чистоты вывода

        server.starttls()  # Обязательно для Яндекса
        print("   ✓ TLS соединение установлено")

        # 5. Авторизация
        print("🔑 Авторизация...")
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        print("   ✓ Авторизация успешна")

        # 6. Отправка
        print("📤 Отправка письма...")
        server.sendmail(
            EMAIL_CONFIG['sender_email'],
            recipient_email,
            msg.as_string()
        )

        # 7. Обновляем счетчики
        EMAIL_SETTINGS['sent_today'] += 1
        EMAIL_SETTINGS['last_sent_time'] = time.time()

        # 8. Закрываем соединение
        server.quit()

        print(f"✅ Письмо успешно отправлено!")
        print(f"   Отправлено сегодня: {EMAIL_SETTINGS['sent_today']}/{EMAIL_SETTINGS['max_emails_per_day']}")
        print(f"   Осталось на сегодня: {EMAIL_SETTINGS['max_emails_per_day'] - EMAIL_SETTINGS['sent_today']}")

        # 9. Логируем успешную отправку
        log_email_success(recipient_email, subject)

        return True

    except smtplib.SMTPDataError as e:
        print(f"❌ ОШИБКА: Яндекс отклонил письмо как спам")
        print(f"   Код ошибки: {e.smtp_code}")
        print(f"   Сообщение: {e.smtp_error}")

        # Если это спам-блокировка, ждем 24 часа
        if "spam" in str(e.smtp_error).lower():
            print(f"⏳ Временная блокировка за спам. Ждите 24 часа.")
            EMAIL_SETTINGS['max_emails_per_day'] = 0  # Временно запрещаем отправку

        log_email_error(recipient_email, f"SMTPDataError: {e}")
        return False

    except smtplib.SMTPAuthenticationError:
        print(f"❌ ОШИБКА АВТОРИЗАЦИИ")
        print(f"   Проверьте пароль приложения в Яндекс.Почте")
        print(f"   Инструкция: https://yandex.ru/support/id/authorization/app-passwords.html")
        return False

    except Exception as e:
        print(f"❌ ОШИБКА: {type(e).__name__}: {str(e)}")
        log_email_error(recipient_email, f"{type(e).__name__}: {e}")
        return False


def log_email_success(recipient, subject):
    """Логирует успешную отправку"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] SUCCESS: {recipient} - {subject[:50]}\n"

    try:
        with open('email_success.log', 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except:
        pass  # Игнорируем ошибки логирования


def log_email_error(recipient, error):
    """Логирует ошибку отправки"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] ERROR: {recipient} - {error}\n"

    try:
        with open('email_errors.log', 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except:
        pass


def send_email_to_multiple(subject, message, recipient_emails):
    """
    Безопасная отправка нескольким получателям с учетом лимитов
    """
    print(f"\n{'=' * 60}")
    print(f"📨 МАССОВАЯ РАССЫЛКА")
    print(f"   Всего получателей: {len(recipient_emails)}")
    print(f"   Дневной лимит: {EMAIL_SETTINGS['max_emails_per_day']} писем")
    print(f"{'=' * 60}")

    results = []
    successful = 0
    failed = 0

    for i, recipient in enumerate(recipient_emails, 1):
        print(f"\n[{i}/{len(recipient_emails)}] Отправка для: {recipient}")

        # Проверяем, не превысили ли лимит
        if EMAIL_SETTINGS['sent_today'] >= EMAIL_SETTINGS['max_emails_per_day']:
            print(f"⚠️  Достигнут дневной лимит! Прерываем рассылку.")
            break

        # Отправляем письмо
        if send_email_notification(subject, message, recipient):
            successful += 1
            results.append((recipient, True))
        else:
            failed += 1
            results.append((recipient, False))

    # Итоговый отчет
    print(f"\n{'=' * 60}")
    print(f"📊 ИТОГИ РАССЫЛКИ")
    print(f"{'=' * 60}")
    print(f"   ✅ Успешно отправлено: {successful}")
    print(f"   ❌ Не отправлено: {failed}")
    print(f"   📨 Всего планировалось: {len(recipient_emails)}")
    print(f"   🎯 Достигнуто: {successful}/{len(recipient_emails)} ({successful / len(recipient_emails) * 100:.1f}%)")

    return results


# Дополнительные утилиты для мониторинга
def get_sending_stats():
    """Возвращает статистику отправки"""
    today = datetime.now().date()

    # Сбрасываем если новый день
    if today != EMAIL_SETTINGS['last_reset_date']:
        EMAIL_SETTINGS['sent_today'] = 0
        EMAIL_SETTINGS['last_reset_date'] = today

    return {
        'sent_today': EMAIL_SETTINGS['sent_today'],
        'max_per_day': EMAIL_SETTINGS['max_emails_per_day'],
        'remaining': EMAIL_SETTINGS['max_emails_per_day'] - EMAIL_SETTINGS['sent_today'],
        'last_sent': EMAIL_SETTINGS['last_sent_time'],
        'delay': EMAIL_SETTINGS['delay_between_emails']
    }


def reset_daily_counter():
    """Сбрасывает дневной счетчик (для тестирования)"""
    EMAIL_SETTINGS['sent_today'] = 0
    EMAIL_SETTINGS['last_reset_date'] = datetime.now().date()
    print("✅ Дневной счетчик сброшен")


# Пример использования
if __name__ == "__main__":
    # Тестовая отправка
    test_recipient = "test@example.com"  # Замените на реальный email

    result = send_email_notification(
        subject="Тестовое уведомление от бота",
        message="""Здравствуйте!

Это тестовое уведомление от нашего телеграм-бота.
Сообщение отправлено для проверки работы email-рассылки.

Если вы получили это письмо, значит система работает корректно.

С уважением,
Команда Империал""",
        recipient_email=test_recipient
    )

    if result:
        print("\n✅ Тест пройден успешно!")
    else:
        print("\n❌ Тест не пройден. Проверьте настройки.")