import threading
import time
from datetime import datetime, timedelta
import schedule

from handlers.application_handlers.application_restart import restart_expired_applications


class ApplicationScheduler:

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.running = False
        self.thread = None

    def start(self):
        """Запускает планировщик в отдельном потоке"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon = True)
        self.thread.start()
        print("📅 Планировщик заявок запущен")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _run_scheduler(self):
        schedule.every(1).hours.do(self.check_expired_application)

        print("📅 Задачи планировщика зарегистрированы")

        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)
            except Exception as e:
                print(f'❌ Ошибка в планировщике: {e}')
                time.sleep(300)

    def check_expired_application(self):
        try:
            print("⏰ Активация планировщика...")
            print("⏰ Проверяем просроченные заявки...")
            restart_expired_applications(self.bot, self.db)
        except Exception as e:
            print(f"❌ Ошибка при проверке заявок: {e}")

    # # def send_daily_report(self):
    #     try:
    #         logger.info("📊 Отправка ежедневного отчета...")
    #         # Здесь можно добавить отправку ежедневного отчета
    #         pass
    #     except Exception as e:
    #         logger.error(f"❌ Ошибка при отправке отчета: {e}")

_scheduler_instance = None

def init_scheduler(bot, db):
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ApplicationScheduler(bot, db)
        _scheduler_instance.start()
    return _scheduler_instance

def get_scheduler():
    return _scheduler_instance