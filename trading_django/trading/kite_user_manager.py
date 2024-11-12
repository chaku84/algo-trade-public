import logging
import re
import math
import pytz

from threading import Thread
from kiteconnect import KiteConnect, KiteTicker
import requests
import pyotp
import json
import os
import time
from kiteconnect.exceptions import TokenException
import calendar
import math
from datetime import datetime, timedelta
import talib
import traceback
import numpy as np
import bisect
import asyncio
import websockets
from strategies.login import Login
from strategies.instruments import Instruments
from trading.scheduler_manager import SchedulerManager
from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.strategies.user_entry_with_strategy import UserEntryWithStrategy
from trading.strategies.instant_user_entry import InstantUserEntry
from trading.strategies.user_exit_with_strategy import UserExitWithStrategy
from trading.strategies.instant_user_exit import InstantUserExit
from trading.authentication import validate_jwt_token
from trading.strategies.rolling_redis_queue import RedisMap
# from strategies.common import get_price, get_nearest_expiry
# from asgiref.sync import async_to_sync


from trading.models import TelegramMessage, TelegramTrade, UserTrade
from django.db.models import Q


def singleton(cls):
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance

@singleton
class KiteUserManager(object):
    __instance = None

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.login = Login()
        self.kite = None
        self.is_ws_open = False
        self.retry_ws_creation_count = 0
        # inst_obj = Instruments(kite)
        # login = self.login
        self.login.login()
        kite = self.login.kite
        self.inst_obj = Instruments(kite)
        self.inst_obj.load_instruments()
        self.inst_obj.update_tokens_and_expiry()
        print("Recreating kitemanager instance")
        # self.telegram = None

    def get_inst_details(self):
        if self.inst_obj is None:
            return {'success': False, 'message': 'Error', 'data': {}}
        data = {}
        try:
            nifty_price_list = self.inst_obj.nifty_price_list
            bank_nifty_price_list = self.inst_obj.bank_nifty_price_list
            nifty_expiry_list = self.inst_obj.nifty_expiry_list
            bank_nifty_expiry_list = self.inst_obj.bank_nifty_expiry_list
            data = {'NIFTY': {'prices': list(nifty_price_list), 'expiry': list(nifty_expiry_list)},
                    'BANKNIFTY': {'prices': list(bank_nifty_price_list), 'expiry': list(bank_nifty_expiry_list)}}
        except Exception as e:
            self.logger.error("ERROR: {}".format(str(e)))
            return {'success': False, 'message': 'Error: {}'.format(str(e)), 'data': []}
        return {'success': True, 'message': 'Success', 'data': data}

    def generate_token(self, date_month_str, strike_price, option_type):
        # Map abbreviated month names to their numeric values
        month_mapping = {
            'JAN': '1',
            'FEB': '2',
            'MAR': '3',
            'APR': '4',
            'MAY': '5',
            'JUN': '6',
            'JUL': '7',
            'AUG': '8',
            'SEP': '9',
            'OCT': '10',
            'NOV': '11',
            'DEC': '12',
        }

        # Append 0 as prefix for 1JULY case
        if not '0' <= date_month_str[1] <= '9':
            date_month_str = '0' + date_month_str

        # Extract components from the date and month string
        print("date_month_str: {}".format(date_month_str))
        day = date_month_str[:2]
        month_abbrev = date_month_str[2:5]

        # Use the current year
        current_year = datetime.now().strftime('%y')

        # Map the abbreviated month to its numeric value
        month = month_mapping.get(month_abbrev.upper())
        if not month:
            raise ValueError("Invalid month abbreviation")

        # Create the token
        token = f'NIFTY{current_year}{month}{day}{strike_price}{option_type}'
        return token

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
            if 'last_price' in tick and tick['instrument_token'] in prev_tick_map:
                high_price = prev_tick_map[tick['instrument_token']].get('high', 0)
                high_price = max(tick['last_price'], high_price)
                tick['high'] = high_price
            else:
                tick['high'] = 0
            tick_map[tick['instrument_token']] = tick
        return tick_map

    def execute_trades(self):
        redis_map = RedisMap()
        # ws_thread = Thread(target=self.start_websocket_server_thread, args=(redis_map,))
        trade_thread = Thread(target=self.execute_trades_util, args=(redis_map,))
        # ws_thread.start()
        trade_thread.start()

    def execute_trades_util(self, redis_map):
        login = self.login
        kite = login.kite

        inst_obj = self.inst_obj

        nifty_option_inst_token_map = inst_obj.nifty_option_inst_token_map
        bank_nifty_option_inst_token_map = inst_obj.bank_nifty_option_inst_token_map
        nifty_50_inst_token = inst_obj.nifty_50_inst_token

        inst_token_to_trading_symbol_map = inst_obj.inst_token_to_trading_symbol_map

        # redis_map = RedisMap()
        
        tick_map_data = redis_map.get('tick_map_data')
        # print(json.dumps(tick_map_data, default=str))

        # instrument_subscription_list = list(tick_map_data.keys())
        # print(instrument_subscription_list)

        # print(instruments[0])
        def get_trading_symbol(placed_trade, tick_map):
            expiry = placed_trade.expiry.replace(' ', '')
            trade_name = placed_trade.index_name.replace(' ', '')
            inst_token_key = "%s-%s-%s-%s" % (
                placed_trade.index_name.replace(' ', ''),
                self.get_complete_date(expiry), placed_trade.index_strike_price, placed_trade.option_type)
            inst_token = nifty_50_inst_token
            if trade_name == 'NIFTY':
                inst_token = nifty_option_inst_token_map[inst_token_key]
            elif trade_name == 'BANKNIFTY':
                inst_token = bank_nifty_option_inst_token_map[inst_token_key]
            # if inst_token not in instrument_subscription_list:
            #     raise ValueError("Unexpected Instrument Token")
                # instrument_subscription_list.append(inst_token)
                # print(instrument_subscription_list)
            if inst_token in tick_map:
                last_price = tick_map[inst_token]['last_price']
            else:
                last_price = -1
            trading_symbol = inst_token_to_trading_symbol_map[inst_token]
            return last_price, trading_symbol, inst_token

        # normal_entry_obj = NormalEntry()
        # discounted_entry_obj = DiscountedEntry()
        user_entry_with_strategy_obj = UserEntryWithStrategy()
        instant_user_entry_obj = InstantUserEntry()

        entry_obj_map = {
            'INSTANT_USER': instant_user_entry_obj,
            'USER_WITH_STRATEGY': user_entry_with_strategy_obj
        }

        # normal_exit_obj = NormalExit(entry_obj=normal_entry_obj)
        # discounted_exit_obj = DiscountedExit(entry_obj=discounted_entry_obj)
        user_exit_with_strategy_obj = UserExitWithStrategy(entry_obj=user_entry_with_strategy_obj)
        instant_user_exit_obj = InstantUserExit(entry_obj=instant_user_entry_obj)

        exit_obj_map = {
            'INSTANT_USER': instant_user_exit_obj,
            'USER_WITH_STRATEGY': user_exit_with_strategy_obj
        }

        while True:
            IST = pytz.timezone('Asia/Kolkata')
            current_time = datetime.utcnow()
            current_time = current_time + timedelta(hours=5, minutes=30)
            market_closed_today = current_time.weekday() >= 5  # Check if it's Saturday or Sunday
            market_open_time = datetime(current_time.year, current_time.month, current_time.day, 8, 0)
            market_close_time = datetime(current_time.year, current_time.month, current_time.day, 15, 30)
            if market_closed_today or current_time < market_open_time or current_time > market_close_time:
                self.logger.info("Market is closed. Sleeping for 1 hour.")
                time.sleep(60 * 60)
                continue
            timestamp = get_ist_datetime(datetime.utcnow())
            # Callback to receive ticks.
            # print(ticks)
            # while True:
            tick_map = redis_map.get('tick_map_data')
            if not tick_map:
                self.logger.info("No Tick Data Found. Waiting for updater to update data.")
                time.sleep(1)
                continue
            # kws.prev_tick_map = tick_map

            # Get today's date
            today_date = datetime.now().date()
            # Create a datetime object for today at 12:01 AM
            start_of_today = datetime.combine(today_date, datetime.min.time())
            
            if timestamp.second % 5 == 0:
                matched_objects = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today) &
                    (Q(metadata__icontains='EXIT_AT_CMP') | Q(metadata__icontains='CANCEL'))
                )
                for curr_trade in matched_objects:
                    try:
                        if 'NOT_PLACED' in curr_trade.order_status:
                            curr_trade.order_status = 'CANCELLED'
                            curr_trade.save()
                        elif curr_trade.order_status == 'ORDER_ENTRY_PLACED':
                            trigger_id = curr_trade.order_id
                            kite.delete_gtt(trigger_id)
                            curr_trade.order_status = 'CANCELLED'
                            curr_trade.save()
                        elif 'ORDER_EXIT_GTT_PLACED' in curr_trade.order_status:
                            last_price, trading_symbol, inst_token = get_trading_symbol(curr_trade, tick_map)
                            exit_obj_map.get(curr_trade.entry_type).cancel_gtt_and_all_orders(
                                kite, curr_trade, trading_symbol, last_price)
                    except Exception as e:
                        traceback.print_exc()
                        print("Exception while cancelling trade")

            entry_placed_trades = TelegramTrade.objects.filter(
                Q(created_at_time__gte=start_of_today) & Q(order_status='ORDER_ENTRY_PLACED')
            )

            if timestamp.second % 5 == 0:
                for placed_trade in entry_placed_trades:
                    try:
                        last_price, trading_symbol, inst_token = get_trading_symbol(placed_trade, tick_map)
                        entry_obj_map.get(placed_trade.entry_type).check_if_order_is_executed(kite, placed_trade,
                                                                                              trading_symbol,
                                                                                              last_price)

                        if placed_trade.order_status == 'ORDER_ENTRY_EXECUTED':
                            # last_price, trading_symbol, inst_token = get_trading_symbol(placed_trade, tick_map)
                            # if inst_token not in instrument_subscription_list:
                            #     raise ValueError("Unexpected Instrument Token")
                            exit_obj_map.get(placed_trade.entry_type).place_exit_gtt_orders(kite, placed_trade,
                                                                                            trading_symbol,
                                                                                            last_price)
                    except Exception as e:
                        traceback.print_exc()
                        print("Exception in place_exit_gtt_orders")

            exit_gtt_placed_trades = TelegramTrade.objects.filter(
                Q(created_at_time__gte=start_of_today) &
                (Q(order_status__startswith='ORDER_EXIT_GTT_PLACED') | Q(order_status__contains='TARGET_HIT'))
            )

            if timestamp.second % 8 == 0:
                for placed_trade in exit_gtt_placed_trades:
                    try:
                        last_price, trading_symbol, inst_token = get_trading_symbol(placed_trade, tick_map)
                        # if inst_token not in instrument_subscription_list:
                        #     raise ValueError("Unexpected Instrument Token")
                        exit_obj_map.get(placed_trade.entry_type).update_targets_status_and_trail_stop_loss(
                            kite, placed_trade, trading_symbol, last_price)
                    except Exception as e:
                        traceback.print_exc()
                        print("Exception in update_targets_status_and_trail_stop_loss")
                        
            if timestamp.second % 15 == 0:
                exit_gtt_placed_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today) &
                    Q(order_status__startswith='ORDER_EXIT_GTT_PLACED')
                )
                for placed_trade in exit_gtt_placed_trades:
                    try:
                        last_price, trading_symbol, inst_token = get_trading_symbol(placed_trade, tick_map)
                        # if inst_token not in instrument_subscription_list:
                        #     raise ValueError("Unexpected Instrument Token")
                        exit_obj_map.get(placed_trade.entry_type).cancel_gtt_and_all_orders_below_range(
                            kite, placed_trade, trading_symbol, last_price)
                    except Exception as e:
                        traceback.print_exc()
                        print("Exception in cancel_gtt_and_all_orders_below_range")

            # for trade in existing_trades:
            if timestamp.second % 5 == 0:
                # print("Ticks: {}".format(ticks))
                print("inside process_on_tick")
                # print(kite.margins())
                # kite = self.kite
                existing_trades = TelegramTrade.objects.filter(created_at_time__gte=start_of_today)
                # print(json.dumps(existing_trades))
                for trade in existing_trades:
                    try:
                        expiry = trade.expiry.replace(' ', '')
                        trade_name = trade.index_name.replace(' ', '')
                        # trading_symbol = self.generate_token(expiry, trade.index_strike_price,
                        #                                      trade.option_type)
                        inst_token_key = "%s-%s-%s-%s" % (
                            trade.index_name.replace(' ', ''),
                            self.get_complete_date(expiry), trade.index_strike_price, trade.option_type)
                        inst_token = nifty_50_inst_token
                        if trade_name == 'NIFTY':
                            inst_token = nifty_option_inst_token_map[inst_token_key]
                        elif trade_name == 'BANKNIFTY':
                            inst_token = bank_nifty_option_inst_token_map[inst_token_key]
                        print("inst_token: %s" % inst_token)
                        # if inst_token not in instrument_subscription_list:
                        #     # raise ValueError("Instrument Token not subscribed!")
                        #     raise ValueError("Unexpected Instrument Token")

                        trading_symbol = inst_token_to_trading_symbol_map[inst_token]
                        tick_last_price = tick_map[inst_token]['last_price']

                        if trade.order_status == 'NOT_PLACED':
                            # entry_start_price | entry_end_price | exit_first_target_price |
                            # exit_second_target_price | exit_third_target_price | exit_stop_loss_price |
                            curr_entry_obj = entry_obj_map.get(trade.entry_type)
                            # if curr_entry_obj.risk > 0:
                            #     curr_entry_obj.check_entry_criteria_and_update_metadata_and_status(kite,
                            #                                                                        tick_last_price,
                            #                                                                        trade,
                            #                                                                        inst_token,
                            #                                                                        timestamp, tick_map)

                        if trade.order_status == 'NOT_PLACED_ENTRY_ALLOWED':
                            entry_obj_map.get(trade.entry_type).process_prices_and_quantities(trade)

                        if trade.order_status == 'NOT_PLACED_PRICES_PROCESSED':
                            curr_entry_obj = entry_obj_map.get(trade.entry_type)
                            curr_entry_obj.place_order(kite, trade, trading_symbol, tick_last_price)
                            curr_entry_obj.check_if_order_is_executed(kite, trade, trading_symbol, tick_last_price)
                    except Exception as e:
                        traceback.print_exc()
                        logging.info("Order placement failed: {}".format(str(e)))
            time.sleep(1)

# KiteManager().start_ws_connection()