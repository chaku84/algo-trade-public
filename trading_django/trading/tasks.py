# tasks.py in one of your Django apps
import os
import time
import traceback
from celery import shared_task
from datetime import datetime
import pytz

# from trading.manager import TradingManager
# from yourapp.models import Trade

trading_manager = None
logged_into_telegram = False
telegram_login_in_progress = False


@shared_task
def login_into_telegram():
    global trading_manager, logged_into_telegram
    # Your logic to login into Telegram
    print("login_into_telegram")
    # time.sleep(5)
    telegram_login_in_progress = True
    from trading.telegram_manager import TradingManager
    trading_manager = TradingManager()
    try:
        trading_manager.login_into_telegram()
    except Exception as e:
        traceback.print_exc()
        time.sleep(10)
        # login_into_telegram()
        return
    telegram_login_in_progress = False
    logged_into_telegram = True

@shared_task(priority=3)
def process_telegram_messages():
    # time.sleep(120) # Buffer for kite login 
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    # if now.hour < 9 or now.hour >= 16:
    #     if now.minute % 15 == 0:
    #         print("Skipping process_telegram_messages as market is closed!")
    #     return
    global trading_manager, logged_into_telegram
    # Your logic to get messages from Telegram and store in the database
    print("process_telegram_messages")
    # time.sleep(5)
    # from trading.telegram_manager import TradingManager
    # if trading_manager is None:
    #     trading_manager = TradingManager()
    # if not logged_into_telegram and not telegram_login_in_progress:
    #     login_into_telegram()
    # trading_manager.process_telegram_messages_and_presist()

@shared_task
def parse_and_filter_trades():
    # Your logic to parse messages and filter trades
    print("parse_and_filter_trades")

@shared_task(priority=1)
def execute_trades():
    # time.sleep(60) # Buffer for kite login
    # Your logic to execute trades based on entry and exit conditions
    print("execute_trades")
    # from trading.kite_manager import KiteManager
    # KiteManager().execute_trades()
    from trading.dhan_manager import DhanManager
    DhanManager().execute_trades()

@shared_task(priority=2)
def update_kite_ticks():
    # Your logic to execute trades based on entry and exit conditions
    print("update_kite_ticks")
    # from trading.kite_tick_updater import KiteTickUpdater
    # KiteTickUpdater().start_ws_connection()
    from trading.dhan_tick_updater import DhanTickUpdater
    DhanTickUpdater().start_ws_connection()




def update_trading_manager_obj():
    # if trading_manager is None:
        # from trading.manager import TradingManager
    trading_manager = TradingManager()
