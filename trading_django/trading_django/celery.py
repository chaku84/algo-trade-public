from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab
# from settings import INSTALLED_APPS
# from trading.tasks import process_telegram_messages
from trading.tasks import process_telegram_messages

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trading_django.settings')

# import django
# django.setup()

app = Celery('trading_django')

app.config_from_object('django.conf:settings', namespace='CELERY')

# app.autodiscover_tasks()
# from trading import tasks
# app.autodiscover_tasks(lambda: INSTALLED_APPS)
active_tasks = app.control.inspect().active()

# Revoke all active tasks
if active_tasks:
    for worker, tasks in active_tasks.items():
        for task in tasks:
            app.control.revoke(task['id'], terminate=True)


# app.conf.beat_schedule = {
#     'trading_workers': {
#         'task': 'process_telegram_messages',  # the name of the Celery task to run
#         'schedule': crontab(hour=17, minute=30, day_of_week='mon-sun'),
#     },
# }
