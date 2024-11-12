import logging
import re
from datetime import datetime, timedelta, timezone
from subprocess import Popen, PIPE
import subprocess
import signal
import redis
import json
import time

# from tips.market_guide import Telegram
# from trading.models import TelegramMessage, TelegramTrade
from django_celery_beat.models import PeriodicTask, IntervalSchedule
# from django.db.models import Q



class SchedulerManager(object):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # self.telegram = Telegram.get_instance()
        # self.telegram = None

    def schedule_task(self, payload):
        try:
            interval, _ = IntervalSchedule.objects.get_or_create(every=payload['interval_in_seconds'],
                                                                 period=IntervalSchedule.SECONDS)
            PeriodicTask.objects.create(
                interval=interval,
                start_time=payload['start_time'],
                name=payload['task_schedule_name'],
                task=payload['task_path']
                # task = "trading.tasks.process_telegram_messages",
                # args=json.dumps(["arg1", "arg2"])
                # one_off=True
            )
        except Exception as e:
            self.logger.error("ERROR: {}".format(str(e)))
            return False
        return True

    def get_scheduled_tasks(self, name):
        task_list = []
        try:
            if name is None or name == '' or name == 'all':
                tasks = PeriodicTask.objects.all()
                task_list = [{
                    'id': task.id,
                    'name': task.name,
                    'task': task.task,
                    'interval': str(task.interval),
                    'start_time': task.start_time,
                } for task in tasks]
            else:
                task = PeriodicTask.objects.get(name=name)
                task_list = [{
                    'id': task.id,
                    'name': task.name,
                    'task': task.task,
                    'interval': str(task.interval),
                    'start_time': task.start_time,
                }]
        except Exception as e:
            self.logger.error("ERROR: {}".format(str(e)))
            return {'success': False, 'message': 'Error: {}'.format(str(e)), 'data': []}
        return {'success': True, 'message': 'Success', 'data': task_list}

    def delete_scheduled_task(self, task_name):
        try:
            task = PeriodicTask.objects.get(name=task_name)
            task.delete()
            return {'sucess': True, 'message': f'Task with name "{task_name}" deleted successfully.'}
        except PeriodicTask.DoesNotExist:
            return {'success': False, 'message': f'Error: Task with name "{task_name}" does not exist.'}
        except Exception as e:
            self.logger.error("Error: {}".format(str(e)))
            return {'success': False, 'message': f'Error: {str(e)}'}
        return {'success': False, 'message': f'Error: '}

    def start_celery_worker(self):
        # Run Celery worker command in the background
        command = "celery -A trading_django worker -l info >> celery_worker.log 2>&1 &"

        # Using subprocess.Popen
        process = Popen(command, shell=True)
        return {'status': 'success'}

    def start_celery_beat(self):
        # Run Celery beat command in the background
        command = "celery -A trading_django beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler >> celery_beat.log 2>&1 &"
        process = Popen(command, shell=True)
        return {'status': 'success'}

    def kill_celery_worker(self):
        # Kill Celery worker process
        command = "ps aux | grep 'celery -A trading_django worker -l info' | awk '{print $2}' | xargs kill -9"

        # Run the command in the background without waiting
        Popen(command, shell=True, stdout=PIPE, stderr=PIPE, close_fds=True,
                         start_new_session=True)

    def kill_celery_beat(self):
        # Kill Celery beat process
        Popen(['pkill', '-f', 'celery -A trading_django beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler'])
        return {'status': 'success'}

    def kill_chromedriver_process(self):
        command = "lsof -t -i:9222 | awk '{print $1}' | xargs sudo kill -9"
        process = Popen(command, shell=True, stdout=PIPE, stderr=PIPE, close_fds=True)
        stdout, stderr = process.communicate()

        if stderr:
            self.logger.error("Error:", stderr.decode())
        else:
            self.logger.info("Process killed successfully.")

        command = "ps aux | grep chromedriver | awk '{print $2}' | xargs kill -9"
        process = Popen(command, shell=True, stdout=PIPE, stderr=PIPE, close_fds=True)
        stdout, stderr = process.communicate()

        if stderr:
            self.logger.error("Error:", stderr.decode())
        else:
            self.logger.info("Process killed successfully.")

        # command = "lsof -t -i:9223 | awk '{print $1}' | xargs sudo kill -9"

        # # Run the command in the background without waiting
        # Popen(command, shell=True, stdout=PIPE, stderr=PIPE, close_fds=True,
        #                  start_new_session=True)



        # command = "sudo lsof -t -i:9222| awk '{print $1}' | xargs kill -9"
        # Popen(command, shell=True, stdout=PIPE, stderr=PIPE, close_fds=True,
        #                  start_new_session=True)

    def flush_redis(self):
        # Flush Redis using redis-py
        r = redis.StrictRedis(host='localhost', port=6379, db=0)
        # r.flushall()
        # key_to_keep = 'tick_map_data'
        #
        # # Get all keys matching a pattern
        all_keys = r.keys('*')
        #
        # # Delete all keys except the one you want to keep
        for key in all_keys:
            if key.decode('utf-8') != 'last_running_pair':
                r.delete(key)

        # for key in all_keys:
        #     r.delete(key)

        return {'status': 'success'}

    def reschedule_task(self):
        self.kill_celery_worker()
        time.sleep(1)
        self.kill_celery_beat()
        self.flush_redis()
        self.kill_chromedriver_process()
        time.sleep(5)
        # self.kill_chromedriver_process()
        # time.sleep(15)
        task_list = self.get_scheduled_tasks(name='all')['data']
        for task in task_list:
            if task["id"] != 1:
                self.delete_scheduled_task(task["name"])
        self.start_celery_beat()
        time.sleep(1)
        self.start_celery_worker()
        time.sleep(1)
        utc_now = datetime.now(timezone.utc)

        # Format the datetime to the desired format
        formatted_datetime = utc_now.strftime('%Y-%m-%dT%H:%M:%SZ')
        for task in task_list:
            if task["id"] != 1 and task["interval"] is not None:
                print(task)
                self.logger.info(task["interval"])
                if type(task["interval"]) == int:
                    interval = task['interval']
                else:
                    task['interval'] = '%s$86400' % task['interval']
                    interval = int(re.findall(r'\d+', task["interval"])[0])
                payload = {
                    "interval_in_seconds": interval,
                    "task_schedule_name": task["name"],
                    "task_path": task["task"],
                    "start_time": formatted_datetime
                }
                self.schedule_task(payload)


        return True

