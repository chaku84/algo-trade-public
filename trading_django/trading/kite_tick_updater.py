#!/usr/bin/env python3
import logging
import threading
import json
import pytz

from threading import Thread
from kiteconnect import KiteConnect, KiteTicker
import os
import time
from kiteconnect.exceptions import TokenException
from datetime import datetime, timedelta
# import talib
import traceback
import bisect
from trading.kite_manager import KiteManager
from trading.strategies.rolling_redis_queue import RedisMap
from trading.helpers import get_ist_datetime, get_nearest_tens


class KiteTickUpdater(object):
    __instance = None

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # self.kite_manager = KiteManager()
        # login = self.kite_manager.login
        # access_token = login.access_token
        # request_token = login.request_token
        # self.telegram = None

    def get_complete_date(self, date_month_str):
        month_mapping = { 'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'}
        # Append 0 as prefix for 1JULY case
        if not '0' <= date_month_str[1] <= '9':
            date_month_str = '0' + date_month_str

        day = date_month_str[:2]
        month_abbrev = date_month_str[2:5]

        # Use the current year
        current_year = datetime.now().year

        # Map the abbreviated month to its numeric value
        month = month_mapping.get(month_abbrev.upper())
        if not month:
            raise ValueError("Invalid month abbreviation")

        return f'{current_year}-{month}-{day}'
        
    def get_tick_map(self, ticks, prev_tick_map=None):
        tick_map = {}
        for tick in ticks:
            if 'last_price' in tick and prev_tick_map is not None and tick['instrument_token'] in prev_tick_map:
                high_price = prev_tick_map[tick['instrument_token']].get('high', 0)
                high_price = max(tick['last_price'], high_price)
                tick['high'] = high_price
                low_price = prev_tick_map[tick['instrument_token']].get('low', 999999)
                low_price = min(tick['last_price'], low_price)
                tick['low'] = low_price
            else:
                tick['high'] = 0
                tick['low'] = 999999
            tick_map[tick['instrument_token']] = tick
        return tick_map

    def start_ws_connection(self):
        ws_thread = Thread(target=self.start_ws_connection_util)
        ws_thread.start()

    def start_ws_connection_util(self):
        while True:
            self.kite_manager = KiteManager()
            login = self.kite_manager.login
            kite = login.kite
            access_token = login.access_token
            request_token = login.request_token
            inst_obj = self.kite_manager.inst_obj

            instruments = inst_obj.instruments
            risk_percent = inst_obj.risk_percent
            reward_percent = inst_obj.reward_percent
            max_allowed_lots = inst_obj.max_allowed_lots
            # NIFTY-2024-01-18-22000-CE
            # map_key = "%s-%s-%s-%s" % (
            #                 inst['name'], inst['expiry'].date().isoformat(), int(inst['strike']), inst['instrument_type'])
            nifty_option_inst_token_map = inst_obj.nifty_option_inst_token_map
            bank_nifty_option_inst_token_map = inst_obj.bank_nifty_option_inst_token_map
            mid_cap_nifty_option_inst_token_map = inst_obj.mid_cap_nifty_option_inst_token_map
            sensex_option_inst_token_map = inst_obj.sensex_option_inst_token_map
            nifty_price_list = inst_obj.nifty_price_list
            bank_nifty_price_list = inst_obj.bank_nifty_price_list
            mid_cap_nifty_price_list = inst_obj.mid_cap_nifty_price_list
            sensex_price_list = inst_obj.sensex_price_list
            nifty_nearest_expiry = inst_obj.nifty_nearest_expiry
            bank_nifty_nearest_expiry = inst_obj.bank_nifty_nearest_expiry
            mid_cap_nifty_nearest_expiry = inst_obj.mid_cap_nifty_nearest_expiry
            sensex_nearest_expiry = inst_obj.sensex_nearest_expiry
            min_nifty_expiry_diff = inst_obj.min_nifty_expiry_diff
            min_bank_nifty_expiry_diff = inst_obj.min_bank_nifty_expiry_diff
            min_mid_cap_nifty_expiry_diff = inst_obj.min_mid_cap_nifty_expiry_diff
            min_sensex_expiry_diff = inst_obj.min_sensex_expiry_diff
            nifty_50_inst_token = inst_obj.nifty_50_inst_token
            bank_nifty_inst_token = inst_obj.bank_nifty_inst_token
            mid_cap_nifty_inst_token = inst_obj.mid_cap_nifty_inst_token
            sensex_inst_token = inst_obj.sensex_inst_token
            nifty_expiry_list = inst_obj.nifty_expiry_list
            bank_nifty_expiry_list = inst_obj.bank_nifty_expiry_list
            mid_cap_nifty_expiry_list = inst_obj.mid_cap_nifty_expiry_list
            sensex_expiry_list = inst_obj.sensex_expiry_list

            inst_token_to_trading_symbol_map = inst_obj.inst_token_to_trading_symbol_map

            # print(nifty_option_inst_token_map)

            # nifty_nearest_expiry = '23AUG'

            # nifty_nearest_expiry = get_nearest_expiry(nifty_expiry_list, datetime.now())
            print(nifty_nearest_expiry)

            def get_inst_token(index_name, expiry, index_strike_price, option_type):
                inst_token_key = "%s-%s-%s-%s" % (
                    index_name,
                    expiry, index_strike_price, option_type)
                inst_token = None
                if index_name == 'NIFTY':
                    inst_token = nifty_option_inst_token_map[inst_token_key]
                elif index_name == 'BANKNIFTY':
                    inst_token = bank_nifty_option_inst_token_map[inst_token_key]
                elif index_name == 'MIDCPNIFTY':
                    inst_token = mid_cap_nifty_option_inst_token_map[inst_token_key]
                elif index_name == 'SENSEX':
                    inst_token = sensex_option_inst_token_map[inst_token_key]
                return inst_token

            print(instruments[0])
            now = datetime.now()
            day_cnt = 1
            while day_cnt <= 6:
                try:
                    from_date = datetime(now.year, now.month, now.day, 15, 25)
                    to_date = datetime(now.year, now.month, now.day, 15, 30)
                    from_date = from_date - timedelta(days=day_cnt)
                    to_date = to_date - timedelta(days=day_cnt)

                    nifty_historical_data = kite.historical_data(nifty_50_inst_token, from_date, to_date, "minute", False)
                    last_day_nifty_price = nifty_historical_data[len(nifty_historical_data) - 1]['close']

                    bank_nifty_historical_data = kite.historical_data(bank_nifty_inst_token, from_date, to_date, "minute",
                                                                      False)
                    last_day_bank_nifty_price = bank_nifty_historical_data[len(bank_nifty_historical_data) - 1]['close']

                    mid_cap_nifty_historical_data = kite.historical_data(mid_cap_nifty_inst_token, from_date, to_date, "minute",
                                                                      False)
                    last_day_mid_cap_nifty_price = mid_cap_nifty_historical_data[len(mid_cap_nifty_historical_data) - 1]['close']

                    sensex_historical_data = kite.historical_data(sensex_inst_token, from_date, to_date, "minute",
                                                                      False)
                    last_day_sensex_price = sensex_historical_data[len(sensex_historical_data) - 1]['close']
                    break
                except Exception as e:
                    day_cnt += 1
                    if day_cnt == 7:
                        raise e

            instrument_subscription_list = [nifty_50_inst_token, bank_nifty_inst_token, mid_cap_nifty_inst_token, sensex_inst_token]
            nearest_nifty_price_from_list = nifty_price_list[bisect.bisect_left(nifty_price_list, last_day_nifty_price)]
            nearest_bank_nifty_price_from_list = bank_nifty_price_list[
                bisect.bisect_left(bank_nifty_price_list, last_day_bank_nifty_price)]
            nearest_mid_cap_nifty_price_from_list = mid_cap_nifty_price_list[
                bisect.bisect_left(mid_cap_nifty_price_list, last_day_mid_cap_nifty_price)]
            nearest_sensex_price_from_list = sensex_price_list[
                bisect.bisect_left(sensex_price_list, last_day_sensex_price)]

            inst_needed_nifty_price_list = [nearest_nifty_price_from_list]
            inst_needed_bank_nifty_price_list = [nearest_bank_nifty_price_from_list]
            inst_needed_mid_cap_nifty_price_list = [nearest_mid_cap_nifty_price_from_list]
            inst_needed_sensex_price_list = [nearest_sensex_price_from_list]
            option_types = ['CE', 'PE']

            for i in range(10):
                inst_needed_nifty_price_list.append(nearest_nifty_price_from_list - (i + 1) * 50)
                inst_needed_nifty_price_list.append(nearest_nifty_price_from_list + (i + 1) * 50)

                inst_needed_bank_nifty_price_list.append(nearest_bank_nifty_price_from_list - (i + 1) * 100)
                inst_needed_bank_nifty_price_list.append(nearest_bank_nifty_price_from_list + (i + 1) * 100)

                inst_needed_mid_cap_nifty_price_list.append(nearest_mid_cap_nifty_price_from_list - (i + 1) * 25)
                inst_needed_mid_cap_nifty_price_list.append(nearest_mid_cap_nifty_price_from_list + (i + 1) * 25)

                inst_needed_sensex_price_list.append(nearest_sensex_price_from_list - (i + 1) * 100)
                inst_needed_sensex_price_list.append(nearest_sensex_price_from_list + (i + 1) * 100)

            for curr_strike_price in inst_needed_nifty_price_list:
                for option_type in option_types:
                    for nifty_expiry_index in range(min(len(nifty_expiry_list), 2)):
                        nifty_expiry_date = datetime.fromtimestamp(nifty_expiry_list[nifty_expiry_index])
                        year = nifty_expiry_date.year
                        month = nifty_expiry_date.month
                        day = nifty_expiry_date.day
                        inst_token = get_inst_token('NIFTY', f'{year}-{month:02d}-{day:02d}',
                                                    curr_strike_price, option_type)
                        instrument_subscription_list.append(inst_token)

            for curr_strike_price in inst_needed_bank_nifty_price_list:
                for option_type in option_types:
                    for bank_nifty_expiry_index in range(min(len(bank_nifty_expiry_list), 2)):
                        bank_nifty_expiry_date = datetime.fromtimestamp(bank_nifty_expiry_list[bank_nifty_expiry_index])
                        year = bank_nifty_expiry_date.year
                        month = bank_nifty_expiry_date.month
                        day = bank_nifty_expiry_date.day
                        inst_token = get_inst_token('BANKNIFTY', f'{year}-{month:02d}-{day:02d}',
                                                    curr_strike_price, option_type)
                        instrument_subscription_list.append(inst_token)
                    # inst_token = get_inst_token('BANKNIFTY', self.get_complete_date(bank_nifty_nearest_expiry),
                    #                             curr_strike_price, option_type)
                    # instrument_subscription_list.append(inst_token)

            for curr_strike_price in inst_needed_mid_cap_nifty_price_list:
                for option_type in option_types:
                    for mid_cap_nifty_expiry_index in range(min(len(mid_cap_nifty_expiry_list), 2)):
                        mid_cap_nifty_expiry_date = datetime.fromtimestamp(mid_cap_nifty_expiry_list[mid_cap_nifty_expiry_index])
                        year = mid_cap_nifty_expiry_date.year
                        month = mid_cap_nifty_expiry_date.month
                        day = mid_cap_nifty_expiry_date.day
                        inst_token = get_inst_token('MIDCPNIFTY', f'{year}-{month:02d}-{day:02d}',
                                                    curr_strike_price, option_type)
                        instrument_subscription_list.append(inst_token)

            for curr_strike_price in inst_needed_sensex_price_list:
                for option_type in option_types:
                    for sensex_expiry_index in range(min(len(sensex_expiry_list), 2)):
                        sensex_expiry_date = datetime.fromtimestamp(sensex_expiry_list[sensex_expiry_index])
                        year = sensex_expiry_date.year
                        month = sensex_expiry_date.month
                        day = sensex_expiry_date.day
                        inst_token = get_inst_token('SENSEX', f'{year}-{month:02d}-{day:02d}',
                                                    curr_strike_price, option_type)
                        instrument_subscription_list.append(inst_token)
            
            print(instrument_subscription_list)

            inst_token_to_trading_symbol_map = inst_obj.inst_token_to_trading_symbol_map
            kws = KiteTicker("2s3d6ngrn9fa5bsf", access_token)

            stop_event = threading.Event()
            redis_map = RedisMap()

            def on_ticks(ws, ticks):
                # Callback to receive ticks.
                # print(ticks)
                # while True:
                timestamp = get_ist_datetime(datetime.utcnow())
                for curr_tick in ticks:
                    if 'instrument_token' in curr_tick and curr_tick['instrument_token'] in inst_token_to_trading_symbol_map:
                        curr_tick['trading_symbol'] = inst_token_to_trading_symbol_map[curr_tick['instrument_token']]
                    if 'exchange_timestamp' in curr_tick:
                        # curr_tick['exchange_timestamp'] = timestamp
                        timestamp = get_ist_datetime(curr_tick['exchange_timestamp'])

                # time.sleep(1)
                tick_map = self.get_tick_map(ticks, redis_map.get('tick_map_data'))
                # print(json.dumps(tick_map, default=str))
                # kws.prev_tick_map = tick_map
                redis_map.set('tick_map_data', tick_map)

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

            def on_connect(ws, response):
                ws.subscribe(instrument_subscription_list)

                ws.set_mode(ws.MODE_LTP, instrument_subscription_list)
                ws.set_mode(ws.MODE_FULL, [nifty_50_inst_token])

            def on_close(ws, code, reason):
                # On connection close stop the main loop
                # Reconnection will not happen after executing `ws.stop()`
                try:
                    ws.stop()
                except Exception:
                    pass
                print(f"WebSocket closed with code {code}: {reason}")
                print("Restarting webSocket connection")
                # time.sleep(1)
                stop_event.set()

            kws.on_ticks = on_ticks
            kws.on_connect = on_connect
            kws.on_close = on_close
            kws.connect(threaded=True)

            stop_event.wait()
            # kws.disconnect()



# KiteTickUpdater().start_ws_connection()