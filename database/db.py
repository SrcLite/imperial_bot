import sqlite3
import logging
import json
import os

logger = logging.getLogger(__name__)
class Database:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def execute_query(self, query, params=()):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor
        except Exception as e:
            logger.error(f"Database error: {e}")
            return None

    def fetch_one(self, query, params=()):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Ошибка получения одной записи: {e}")
            return None

    def fetch_all(self, query, params=()):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                results = cursor.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Ошибка получения всех записей: {e}")
            return None

    # ДЛЯ ПОЛЬЗОВАТЕЛЕЙ

    def create_user(self, telegram_id, first_name, username, role="executor"):
        query = """
                   INSERT OR IGNORE INTO users (telegram_id, first_name, username, role, status)
                   VALUES (?, ?, ?, ?, 'pending')
               """
        return self.execute_query(query, (telegram_id, first_name, username, role))

    def get_user_by_telegram_id(self, telegram_id):
        return self.fetch_one('select * from users where telegram_id = ?', (telegram_id,))

    def update_user_status(self, telegram_id, status):
        query = "update users set status = ? where telegram_id=?"
        return self.execute_query(query, (status, telegram_id))

    def user_exists(self, telegram_id):
        user = self.get_user_by_telegram_id(telegram_id)
        return user is not None

    def update_user(self, telegram_id, **kwargs):
        if not kwargs:
            return None

        set_clause = ",".join([f'{key} = ?' for key in kwargs.keys()])
        query = f"update users set {set_clause} where telegram_id=?"
        params = list(kwargs.values()) + [telegram_id]

        return self.execute_query(query, params)

    def get_company_id_by_user_id(self,user_id):
        return self.fetch_one("select company_id from users where telegram_id=?",(user_id,))

    def get_company_by_id(self, company_id):
        return self.fetch_one('select * from companies where id = ?', (company_id,))

    def get_company_by_user_id(self, user_id):
        return self.fetch_one('select * from companies where id = (select company_id from users where telegram_id = ?)', (user_id,))
    def get_companies_names(self):
        return self.fetch_all('select name from companies')

    def get_company_bank_details(self, company_id):
        return self.fetch_one('select * from company_bank_details where company_id = ?', (company_id,))

    def get_all_admins(self):
        return self.fetch_all("select * from users where role = 'admin' and status = 'active'")

    def get_user_role(self, user_id):
        return self.fetch_one("select role from users where telegram_id=?", (user_id,))

    def get_username(self, user_id):
        return self.fetch_one("select username from users where telegram_id = ?",(user_id,))

    def get_pending_users(self):
        query = """
               select *
               from users 
               where status = 'pending'
               order by created_at"""
        return self.fetch_all(query)

    def approve_user(self, user_id, approved_by):
        query = "UPDATE users SET status = 'active', approved_by = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_query(query, (approved_by, user_id))

    # ДЛЯ КОМПАНИЙ

    def create_company(self, company_data):
        query = """
            INSERT INTO companies (
                name, company_type, inn, kpp, ogrn, management_name,
                address,contact_phone, contact_email, note, status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        params = (
            company_data['name'],
            company_data['company_type'],
            company_data.get('inn'),
            company_data.get('kpp', 'Не указан'),
            company_data.get('ogrn'),
            company_data['management_name'],
            company_data.get('address'),
            company_data.get('contact_phone'),
            company_data.get('contact_email'),
            company_data.get('note'),
            company_data.get('status', 'pending'),
            company_data.get('created_by')
        )
        cursor = self.execute_query(query, params)
        if cursor:
            return cursor.lastrowid  # Возвращаем ID созданной записи
        return None

    def edit_company(self, company_data):
        query = """update companies set contact_phone = ?, contact_email = ?, note = ?, created_by = ? where id = ?"""
        params = (
            company_data['contact_phone'],
            company_data['contact_email'],
            company_data['note'],
            company_data['created_by'],
            company_data['id']
        )
        return self.execute_query(query, params)


    def add_bank_details(self, company_data):
        query = """
                insert into company_bank_details 
                (company_id, bik, payment_account, correspondent_account, okpo)
                values (?,?,?,?,?)""",
        params = (
            company_data['company_id'],
            company_data.get('bik'),
            company_data.get('payment_account'),
            company_data.get('correspondent_account'),
            company_data.get('okpo')
        )
        return self.execute_query(query, params)

    def get_approved_companies(self):
        return self.fetch_all("select * from companies where status='approved'")

    def get_company_id_by_name(self, company_name):
        return self.fetch_one("select company_id from companies where company_id = ?", (company_name,))

    def get_approved_company_by_inn(self, inn):
        return self.fetch_all("select * from companies where inn = ? and status = 'approved'", (inn,))

    def get_approved_one_company_by_inn(self, inn):
        return self.fetch_one("select * from companies where inn = ? and status = 'approved'", (inn,))

    def update_company(self, company_name, **kwargs):
        if not kwargs:
            return 'Не указан'
        set_clause = ",".join([f"{key}=?" for key in kwargs.keys()])
        query = f"update companies set {set_clause}, updated_at = CURRENT_TIMESTAMP where name = ?"
        params = list(kwargs.values()) + [company_name]
        return self.execute_query(query, params)

    def get_pending_companies(self):
        query = """
                select *
                from companies
                where status = 'pending'"""
        return self.fetch_all(query)

    def approve_company(self, company_id):
        query = "UPDATE companies SET status = 'approved' WHERE id = ?"
        return self.execute_query(query, (company_id,))

    def get_rates(self):
        return self.fetch_all('select * from rates')

    # ДЛЯ ДОКУМЕНТОВ

    def add_company_document(self, company_id, document_type, file_path):
        """Добавляет документ компании в базу данных"""
        query = """
            INSERT INTO company_documents (company_id, document_type, file_path, uploaded_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """
        return self.execute_query(query, (company_id, document_type, file_path))

    def add_user_document(self, user_id, document_type, file_path):
        """Добавить документ пользователя"""
        try:
            file_name = os.path.basename(file_path)
            query = """
                   INSERT INTO user_documents (user_id, document_type, file_path, file_name)
                   VALUES (?, ?, ?, ?)
               """
            return self.execute_query(query, (user_id, document_type, file_path, file_name))
        except Exception as e:
            logger.error(f"Ошибка добавления документа: {e}")
            return None

    def get_user_documents(self, user_id):
        """Получить документы пользователя"""
        return self.fetch_all("SELECT * FROM user_documents WHERE user_id = ?", (user_id,))

    # ДЛЯ УВЕДОМЛЕНИЙ

    def create_admin_notification(self, user_id, notification_type, message):
        """Создать уведомление для администратора"""
        query = """
              INSERT INTO admin_notifications (user_id, notification_type, message)
              VALUES (?, ?, ?)
          """
        return self.execute_query(query, (user_id, notification_type, message))

    # ДЛЯ АНОМАЛИЙ

    def update_anomaly_percentage(self, percentage):
        self.execute_query(
            "UPDATE anomaly_settings SET anomaly_percentage = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (percentage,)
        )

    def get_anomaly_settings(self):
        return self.fetch_one("SELECT * FROM anomaly_settings LIMIT 1")

    # В database/db.py добавьте:

    def check_response_anomalies(self, application_id):
        """Проверяет аномалии в ответах на заявку"""
        query = """
            SELECT 
                ar.id as response_id,
                ar.executor_id,
                ar.payment_options,
                u.first_name || ' ' || u.last_name as executor_name,
                c.name as company_name,
                a.desired_budget
            FROM application_responses ar
            JOIN users u ON ar.executor_id = u.telegram_id
            LEFT JOIN companies c ON u.company_id = c.id
            JOIN applications a ON ar.application_id = a.id
            WHERE ar.application_id = ? 
                AND ar.status IN ('counter_offer', 'accepted_budget')
                AND a.desired_budget > 0
        """
        responses = self.fetch_all(query, (application_id,))

        if not responses:
            return []

        # Получаем настройки аномалий
        settings = self.get_anomaly_settings()
        percentage = settings.get('anomaly_percentage', 30.0)

        anomalies = []
        for response in responses:
            try:
                payment_options = json.loads(response['payment_options']) if response['payment_options'] else {}
                desired_budget = float(response['desired_budget'])

                for payment_type, amount in payment_options.items():
                    try:
                        amount_float = float(amount)
                        if desired_budget > 0:
                            deviation = abs(amount_float - desired_budget) / desired_budget * 100
                            if deviation > percentage:
                                anomalies.append({
                                    'response_id': response['response_id'],
                                    'executor_id': response['executor_id'],
                                    'executor_name': response['executor_name'],
                                    'company_name': response.get('company_name', ''),
                                    'payment_type': payment_type,
                                    'amount': amount_float,
                                    'deviation': deviation,
                                    'is_below': amount_float < desired_budget
                                })
                    except (ValueError, TypeError):
                        continue
            except (json.JSONDecodeError, TypeError):
                continue

        return anomalies

    def get_rating(self, user_id):
        return self.fetch_one('select current_rating from user_ratings where user_id = ?', (user_id,))