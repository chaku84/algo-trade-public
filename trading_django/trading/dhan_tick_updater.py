#!/usr/bin/env python3
from dhanhq import dhanhq, marketfeed

import csv
from datetime import datetime, timedelta
import calendar
import math
import bisect
import time
import json
import traceback
import logging
import asyncio

import threading
import pytz

from threading import Thread
import os

from trading.scheduler_manager import SchedulerManager
from trading.helpers import get_ist_datetime, get_nearest_tens

from trading.models import TelegramMessage, TelegramTrade, Funds
from django.db.models import Q
from trading.strategies.rolling_redis_queue import RedisMap


class DhanTickUpdater(object):
    __instance = None

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.redis_map = RedisMap()
        self.client_id = "1101185196"
        api_token = None
        retrial_count = 5
        while not api_token and retrial_count > 0:
            redis_value = self.redis_map.get('dhan_api_token')
            api_token = redis_value.get('value') if redis_value is not None else None
            if api_token is not None:
                break
            self.logger.info("Waiting for dhan_manager to update dhan_api_token")
            time.sleep(60)
            retrial_count -= 1
        if not api_token:
            tokens_file_path = 'dhan_token.txt'
            with open(tokens_file_path, 'r') as token_file:
                api_token = token_file.read()
        self.access_token = api_token
        self.dhan = dhanhq("1101185196", self.access_token)
        # self.kite_manager = KiteManager()
        # login = self.kite_manager.login
        # access_token = login.access_token
        # request_token = login.request_token
        # self.telegram = None
        self.stop_event = threading.Event()
        self.loop = asyncio.get_event_loop()

    def start_ws_connection(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ws_thread = Thread(target=self.start_ws_connection_util)
        ws_thread.start()

    def start_ws_connection_util(self):
        # while True:
        nifty_trading_symbol = 'BANKNIFTY 28 SEP 47600 CALL'
        nifty_option_security_id_map = {}
        nifty_price_list = set([])
        bank_nifty_option_security_id_map = {}
        bank_nifty_price_list = set([])
        finnifty_option_security_id_map = {}
        finnifty_price_list = set([])
        nifty_nearest_expiry = ''
        bank_nifty_nearest_expiry = ''
        finnifty_nearest_expiry = ''
        min_nifty_expiry_diff = 10 ** 17
        min_bank_nifty_expiry_diff = 10 ** 17
        min_finnifty_expiry_diff = 10 ** 17
        nifty_50_security_id = 0
        bank_nifty_security_id = 0
        finnifty_security_id = 0
        security_id_to_trading_symbol_map = {}
        with open('/home/ec2-user/services/algo-trade/api-scrip-master.csv', mode='r') as file:
            csvFile = csv.reader(file)
            for lines in csvFile:
                if lines[3] == 'OPTIDX' and lines[12] == 'W':
                    weekly_timestamp = datetime.fromisoformat(lines[8].split(' ')[0].replace('/', '-')).timestamp()
                    timestamp_diff = weekly_timestamp - datetime.now().timestamp()
                    if lines[5].find('NIFTY') == 0:
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        nifty_option_security_id_map[lines[7]] = lines[2]
                        nifty_price_list.add(math.trunc(float(lines[9])))
                        if timestamp_diff > 0 and timestamp_diff < min_nifty_expiry_diff:
                            min_nifty_expiry_diff = timestamp_diff
                            nifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                    if lines[5].find('BANKNIFTY') == 0:
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        bank_nifty_option_security_id_map[lines[7]] = lines[2]
                        bank_nifty_price_list.add(math.trunc(float(lines[9])))
                        if timestamp_diff > 0 and timestamp_diff < min_bank_nifty_expiry_diff:
                            min_bank_nifty_expiry_diff = timestamp_diff
                            bank_nifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                    if lines[5].find('FINNIFTY') == 0:
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        finnifty_option_security_id_map[lines[7]] = lines[2]
                        finnifty_price_list.add(math.trunc(float(lines[9])))
                        if timestamp_diff > 0 and timestamp_diff < min_finnifty_expiry_diff:
                            min_finnifty_expiry_diff = timestamp_diff
                            finnifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                if lines[3] == 'INDEX':
                    if lines[7] == 'Nifty 50':
                        nifty_50_security_id = lines[2]
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                    if lines[7] == 'Nifty Bank':
                        bank_nifty_security_id = lines[2]
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                    if lines[7] == 'Fin Nifty':
                        finnifty_security_id = lines[2]
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
        nifty_price_list = sorted(list(nifty_price_list))
        bank_nifty_price_list = sorted(list(bank_nifty_price_list))
        finnifty_price_list = sorted(list(finnifty_price_list))
        now = datetime.now()
        from_date = datetime(now.year, now.month, now.day) - timedelta(days=7)
        to_date = now
        from_date = from_date.strftime('%Y-%m-%d')
        to_date = to_date.strftime('%Y-%m-%d')
        # symbol,exchange_segment,instrument_type
        nifty_historical_data = self.dhan.historical_daily_data(symbol='NIFTY', exchange_segment='IDX_I', instrument_type='INDEX', expiry_code=0, from_date=from_date,to_date=to_date)
        bank_nifty_historical_data = self.dhan.historical_daily_data(symbol='BANKNIFTY', exchange_segment='IDX_I', instrument_type='INDEX', expiry_code=0, from_date=from_date,to_date=to_date)
        finnifty_historical_data = self.dhan.historical_daily_data(symbol='FINNIFTY', exchange_segment='IDX_I', instrument_type='INDEX', expiry_code=0, from_date=from_date,to_date=to_date)

        last_day_nifty_price = nifty_historical_data['data']['close'][-1]
        last_day_bank_nifty_price = bank_nifty_historical_data['data']['close'][-1]
        last_day_finnifty_price = finnifty_historical_data['data']['close'][-1]

        instrument_subscription_list = [(marketfeed.IDX, nifty_50_security_id), (marketfeed.IDX, bank_nifty_security_id), (marketfeed.IDX, finnifty_security_id)]
        nearest_nifty_price_from_list = nifty_price_list[bisect.bisect_left(nifty_price_list, last_day_nifty_price)]
        nearest_bank_nifty_price_from_list = bank_nifty_price_list[
            bisect.bisect_left(bank_nifty_price_list, last_day_bank_nifty_price)]
        nearest_finnifty_price_from_list = finnifty_price_list[
            bisect.bisect_left(finnifty_price_list, last_day_finnifty_price)]

        inst_needed_nifty_price_list = [nearest_nifty_price_from_list]
        inst_needed_bank_nifty_price_list = [nearest_bank_nifty_price_from_list]
        inst_needed_finnifty_price_list = [nearest_finnifty_price_from_list]
        option_types = ['CALL', 'PUT']

        for i in range(7):
            inst_needed_nifty_price_list.append(nearest_nifty_price_from_list - (i + 1) * 50)
            inst_needed_nifty_price_list.append(nearest_nifty_price_from_list + (i + 1) * 50)

            inst_needed_bank_nifty_price_list.append(nearest_bank_nifty_price_from_list - (i + 1) * 100)
            inst_needed_bank_nifty_price_list.append(nearest_bank_nifty_price_from_list + (i + 1) * 100)

            inst_needed_finnifty_price_list.append(nearest_finnifty_price_from_list - (i + 1) * 50)
            inst_needed_finnifty_price_list.append(nearest_finnifty_price_from_list + (i + 1) * 50)

        for curr_strike_price in inst_needed_nifty_price_list:
            for option_type in option_types:
                if option_type == 'CALL' and curr_strike_price < nearest_nifty_price_from_list:
                    continue
                if option_type == 'PUT' and curr_strike_price > nearest_nifty_price_from_list:
                    continue
                inst_name = 'NIFTY %s %s %s' %(nifty_nearest_expiry, curr_strike_price, option_type)
                security_id = nifty_option_security_id_map[inst_name]
                # instrument_subscription_list.append((marketfeed.NSE_FNO, security_id))
        
        inst_name_list = []
        for curr_strike_price in inst_needed_bank_nifty_price_list:
            for option_type in option_types:
                # if option_type == 'CALL' and curr_strike_price < nearest_bank_nifty_price_from_list:
                #     continue
                # if option_type == 'PUT' and curr_strike_price > nearest_bank_nifty_price_from_list:
                #     continue
                inst_name = 'BANKNIFTY %s %s %s' %(bank_nifty_nearest_expiry, curr_strike_price, option_type)
                security_id = bank_nifty_option_security_id_map[inst_name]
                instrument_subscription_list.append((marketfeed.NSE_FNO, security_id))
                inst_name_list.append(inst_name)
                # inst_token = get_inst_token('BANKNIFTY', self.get_complete_date(bank_nifty_nearest_expiry),
                #                             curr_strike_price, option_type)
                # instrument_subscription_list.append(inst_token)

        print(instrument_subscription_list)
        print(inst_name_list)

        instrument_subscription_list = instrument_subscription_list[0:99]

        subscription_code = marketfeed.Ticker

        # stop_event = threading.Event()
        redis_map = self.redis_map

        async def on_message(instance, message):
            # Callback to receive ticks.
            # print(ticks)
            # while True:
            # self.logger.info(message)
            timestamp = get_ist_datetime(datetime.utcnow())
            ticks = {}
            if 'type' in message and message['type'] == 'Ticker Data' and 'security_id' in message:
                ticks[message['security_id']] = message
                if ticks[message['security_id']] is None:
                    ticks[message['security_id']] = {}
                if str(message['security_id']) in security_id_to_trading_symbol_map:
                    ticks[message['security_id']]['trading_symbol'] = security_id_to_trading_symbol_map[str(message['security_id'])]

            # time.sleep(1)
            # tick_map = redis_map.get('dhan_tick_data')
            # print(json.dumps(tick_map, default=str))
            # kws.prev_tick_map = tick_map
            redis_map.set('dhan_tick_data', ticks)

            # Update tick data every hour and then wait if market is closed
            IST = pytz.timezone('Asia/Kolkata')
            current_time = datetime.utcnow()
            current_time = current_time + timedelta(hours=5, minutes=30)
            market_closed_today = current_time.weekday() >= 5  # Check if it's Saturday or Sunday
            market_open_time = datetime(current_time.year, current_time.month, current_time.day, 8, 0)
            market_close_time = datetime(current_time.year, current_time.month, current_time.day, 15, 30)
            if market_closed_today or current_time < market_open_time or current_time > market_close_time:
                self.logger.info("Market is closed. Sleeping for 1 hour.")
                time.sleep(60 * 60)
                return

        async def on_connect(instance):
            print("Connected to websocket")

        async def on_close(ws, code, reason):
            # On connection close stop the main loop
            # Reconnection will not happen after executing `ws.stop()`
            print(f"WebSocket closed with code {code}: {reason}")
            print("Restarting webSocket connection")
            # time.sleep(1)
            self.stop_event.set()

        print("Subscription code :", subscription_code)

        # feed = marketfeed.DhanFeed(self.client_id,
        #     self.access_token,
        #     instrument_subscription_list,
        #     subscription_code,
        #     on_connect=on_connect,
        #     on_message=on_message,
        #     on_close=on_close)

        # self.loop.run_until_complete(feed.connect())

        # while not self.stop_event.is_set():
        #     # feed.connect()
        #     feed.run_forever()

        #     # Wait for the stop event to be set before reconnecting
        #     self.stop_event.wait()
        #     self.stop_event.clear()

        #     # Add a delay before reconnecting
        #     time.sleep(1)

        # # Wait for the stop event to be set before reconnecting
        # await self.async_wait_for_stop_event()
        # self.stop_event.clear()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the event loop and call the DhanFeed constructor
        try:
            loop.run_until_complete(self.start_dhan_feed(loop, on_connect, on_message, on_close, instrument_subscription_list, subscription_code))
        finally:
            loop.close()

    async def start_dhan_feed(self, loop, on_connect, on_message, on_close, instrument_subscription_list, subscription_code):
        feed = marketfeed.DhanFeed(
            client_id=self.client_id,
            access_token=self.access_token,
            instruments=instrument_subscription_list,
            subscription_code=subscription_code,
            on_connect=on_connect,
            on_message=on_message,
            on_close=on_close
        )
        await feed.connect()



    async def async_wait_for_stop_event(self):
        while not self.stop_event.is_set():
            await asyncio.sleep(0.1)




# KiteTickUpdater().start_ws_connection()
