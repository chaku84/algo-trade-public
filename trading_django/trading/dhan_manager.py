from dhanhq import dhanhq
from threading import Thread
import csv
from datetime import datetime, timedelta
import calendar
import math
import bisect
import time
import json
import traceback
import logging
import re
import math
import pytz
import websockets
import requests

from trading.scheduler_manager import SchedulerManager
from trading.dhan_web_manager import DhanWebManager
from trading.helpers import get_ist_datetime, get_nearest_tens

from trading.models import TelegramMessage, TelegramTrade, Funds
from django.db.models import Q
from trading.strategies.rolling_redis_queue import RedisMap


def singleton(cls):
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance

@singleton
class DhanManager(object):
    __instance = None

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.redis_map = RedisMap()
        self.dhan_web_manager = DhanWebManager()
        self.gmail_service = self.dhan_web_manager.gmail_service
        api_token = self.reset_secrets_before_market_opening()
        if not api_token:
            self.dhan_web_manager.driver.quit()
            self.reset_secrets_before_market_opening()
        if not api_token:
            tokens_file_path = 'dhan_token.txt'
            with open(tokens_file_path, 'r') as token_file:
                api_token = token_file.read()
            self.redis_map.set('dhan_api_token', {'value': api_token})
        self.dhan = dhanhq("1101185196", api_token)
        admin_fund = Funds.objects.filter(
                    Q(user_login__email='chandan5284ssb@gmail.com')
                ).first()
        self.risk = (admin_fund.investment_amount_per_year * admin_fund.risk_percentage) / 100
        self.fund = admin_fund.investment_amount_per_year
        self.gmail_queue = []
        self.aws_hostname = self.gmail_service.get_aws_hostname()

    def reset_secrets_before_market_opening(self):
        try:
            print("started reset_secrets_before_market_opening")
            self.dhan_web_manager.create_driver_instance()
            self.dhan_web_manager.login()
            api_token = self.dhan_web_manager.reset_api_token()
            self.redis_map.set('dhan_api_token', {'value': api_token})
            self.dhan_web_manager.reset_password()
            self.dhan_web_manager.login()
            self.dhan_web_manager.reset_pin()
            self.dhan_web_manager.login()
            print("completed reset_secrets_before_market_opening")
            return api_token
        except Exception as e:
            traceback.print_exc()
            self.gmail_service.send_email('Found Exception while reset_secrets_before_market_opening', traceback.format_exc())
            self.logger.error("Found Exception while reset_secrets_before_market_opening: {}".format(str(e)))
            try:
                self.dhan_web_manager.clear_cache()
                self.dhan_web_manager.reset_password()
            except Exception:
                pass
        return None

    def execute_trades(self):
        redis_map = self.redis_map
        # ws_thread = Thread(target=self.start_websocket_server_thread, args=(redis_map,))
        trade_thread = Thread(target=self.execute_trades_util, args=(redis_map,))
        exit_thread = Thread(target=self.check_exit_criteria, args=(redis_map,))
        # ws_thread.start()
        trade_thread.start()
        exit_thread.start()

    def execute_trades_util(self, redis_map):
        IST = pytz.timezone('Asia/Kolkata')
        dhan = self.dhan
        risk_percent = 5
        reward_percent = 5
        max_allowed_lots = 1
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
        trading_symbol_to_security_id_map = {}
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        response = requests.get(url)
        if response.status_code == 200:
            with open('/home/ec2-user/services/algo-trade/api-scrip-master.csv', 'wb') as file:
                file.write(response.content)
            self.logger.info("CSV downloaded and saved successfully.")
        else:
            self.logger.info(f"Failed to download CSV. Status code: {response.status_code}")

        with open('/home/ec2-user/services/algo-trade/api-scrip-master.csv', mode='r') as file:
            csvFile = csv.reader(file)
            for lines in csvFile:
                if lines[3] == 'OPTIDX' and (lines[12] == 'W' or lines[12] == 'M'):
                    weekly_timestamp = datetime.fromisoformat(lines[8].split(' ')[0].replace('/', '-')).timestamp()
                    current_date = datetime.now(IST).date()
                    # Create a datetime object at the start of the day
                    start_of_day = datetime.combine(current_date, datetime.min.time()).timestamp()

                    timestamp_diff = weekly_timestamp - start_of_day
                    if lines[5].find('NIFTY') == 0:
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        trading_symbol_to_security_id_map[lines[7]] = lines[2]
                        nifty_option_security_id_map[lines[7]] = lines[2]
                        nifty_price_list.add(math.trunc(float(lines[9])))
                        if timestamp_diff >= 0 and timestamp_diff < min_nifty_expiry_diff:
                            min_nifty_expiry_diff = timestamp_diff
                            nifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                    if lines[5].find('BANKNIFTY') == 0:
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        trading_symbol_to_security_id_map[lines[7]] = lines[2]
                        bank_nifty_option_security_id_map[lines[7]] = lines[2]
                        bank_nifty_price_list.add(math.trunc(float(lines[9])))
                        if timestamp_diff >= 0 and timestamp_diff < min_bank_nifty_expiry_diff:
                            min_bank_nifty_expiry_diff = timestamp_diff
                            bank_nifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                    if lines[5].find('FINNIFTY') == 0:
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        trading_symbol_to_security_id_map[lines[7]] = lines[2]
                        finnifty_option_security_id_map[lines[7]] = lines[2]
                        finnifty_price_list.add(math.trunc(float(lines[9])))
                        if timestamp_diff >= 0 and timestamp_diff < min_finnifty_expiry_diff:
                            min_finnifty_expiry_diff = timestamp_diff
                            finnifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                if lines[3] == 'INDEX':
                    if lines[7] == 'Nifty 50':
                        nifty_50_security_id = lines[2]
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        trading_symbol_to_security_id_map[lines[7]] = lines[2]
                    if lines[7] == 'Nifty Bank':
                        bank_nifty_security_id = lines[2]
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        trading_symbol_to_security_id_map[lines[7]] = lines[2]
                    if lines[7] == 'Fin Nifty':
                        finnifty_security_id = lines[2]
                        security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        trading_symbol_to_security_id_map[lines[7]] = lines[2]
        # print(trading_symbol_to_security_id_map)
        # dhan_hedge_entry_obj = DhanHedgeEntry()

        # entry_obj_map = {
        #     'DHAN_HEDGE': dhan_hedge_entry_obj
        # }

        # dhan_hedge_exit_obj = DhanHedgeExit(entry_obj=dhan_hedge_entry_obj)

        # exit_obj_map = {
        #     'DHAN_HEDGE': dhan_hedge_exit_obj
        # }

        admin_fund = Funds.objects.filter(
                    Q(user_login__email='chandan5284ssb@gmail.com')
                ).first()

        self.logger.info(admin_fund.created_by)
        self.logger.info(admin_fund.investment_amount_per_year)
        self.logger.info(admin_fund.risk_percentage)

        kill_switch = False
        redis_map.set('pair_strategy_status', {'value': 'CLOSED'})

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
            tick_map = self.redis_map.get('dhan_tick_data')
            if not tick_map:
                self.logger.info("No Tick Data Found. Waiting for updater to update data.")
                time.sleep(1)
                continue
            # kws.prev_tick_map = tick_map

            # Get today's date
            today_date = datetime.now(IST).date()
            # Create a datetime object for today at 12:01 AM
            start_of_today = datetime.combine(today_date, datetime.min.time())

            if timestamp.hour < 9 or (timestamp.hour == 9 and timestamp.minute <= 15):
                # self.logger.info("Market is closed. Sleeping for 1 second.")
                time.sleep(1)
                continue

            if timestamp.hour == 15 and kill_switch:
                logging.info("Deactivating kill switch for sell hedge position.")
                dhan.kill_switch(status='DEACTIVATE')
                kill_switch = False

            # if timestamp.hour == 9 and timestamp.minute == 16 and timestamp.second <= 30:
            #     time.sleep(1)
            #     continue

            MINUTE_THRESHOLD = 16
            if timestamp.second == 59 and timestamp.hour == 9:
                # TODO: Move dhan hedge position to waiting state by exiting it until buy order is placed & executed
                existing_trades = TelegramTrade.objects.filter(
                    Q(entry_type='DHAN_HEDGE')
                    & (Q(order_status='ORDER_PLACED_DHAN') | Q(order_status='SL_TARGET_ORDER_PLACED_DHAN')))
                existing_scalper_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PUT_SCALPER'))
                if not existing_scalper_trades:
                    for trade in existing_trades:
                        metadata = trade.get_metadata_as_dict()
                        if not 'updated_order_status' in metadata or metadata['updated_order_status'] != 'CANCELLED_WAITING':
                            metadata['updated_order_status'] = 'CANCELLED_WAITING'
                            trade.set_metadata_from_dict(metadata)
                            trade.created_at_time = timestamp
                            trade.save()
                existing_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PUT_SCALPER'))

                existing_hedge_trades = TelegramTrade.objects.filter(
                    Q(entry_type='DHAN_HEDGE')
                    & (Q(order_status='ORDER_PLACED_DHAN') | Q(order_status='SL_TARGET_ORDER_PLACED_DHAN')))
                try:
                    if not existing_trades and not existing_hedge_trades:
                        banknifty_data = dhan.intraday_minute_data(bank_nifty_security_id, exchange_segment='IDX_I', instrument_type='INDEX')
                        if 'start_Time' in banknifty_data['data']:
                            data_length = len(banknifty_data['data']['start_Time'])
                            for i in range(data_length):
                                banknifty_data['data']['start_Time'][i] = dhan.convert_to_date_time(banknifty_data['data']['start_Time'][i])
                                if banknifty_data['data']['start_Time'][i].hour >= timestamp.hour and banknifty_data['data']['start_Time'][i].minute >= timestamp.minute and timestamp.minute >= MINUTE_THRESHOLD:
                                    logging.info("Checking for DHAN_PUT_SCALPER entry")
                                    low_price = banknifty_data['data']['low'][-1]
                                    high_price = banknifty_data['data']['high'][-1]
                                    open_price = banknifty_data['data']['open'][-1]
                                    close_price = banknifty_data['data']['close'][-1]
                                    logging.info("open_price: %s, close_price: %s" % (open_price, close_price))
                                    if i == data_length - 1:
                                        if timestamp.minute == banknifty_data['data']['start_Time'][i].minute:
                                            # doji_condition
                                            high_low_diff = (high_price - low_price) * 0.3
                                            doji_condition = False
                                            if open_price < low_price + high_low_diff and close_price < low_price + high_low_diff:
                                                doji_condition = True
                                            bullish_candle = False
                                            high_low_diff_max = (high_price - low_price)
                                            if open_price >= (low_price + (0.5 * high_low_diff_max)) and close_price >= (low_price + (0.5 * high_low_diff_max)):
                                                bullish_candle = True
                                            if bullish_candle and close_price < open_price:
                                                # Skip Scalper Trade on such days as market is bullish
                                                # Add dummy put scalper trade with last state to avoid re-entry
                                                # and update hedge trades to NOT_PLACED_DHAN
                                                telegram_trade = TelegramTrade()
                                                telegram_trade.index_name = 'BANKNIFTY'
                                                telegram_trade.index_strike_price = -1
                                                telegram_trade.option_type = 'PE'
                                                telegram_trade.expiry = bank_nifty_nearest_expiry
                                                telegram_trade.entry_start_price = -1
                                                telegram_trade.exit_first_target_price = -1
                                                telegram_trade.exit_stop_loss_price = -1
                                                telegram_trade.created_at_time = timestamp
                                                telegram_trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
                                                telegram_trade.quantity = -1
                                                metadata = {'strategy': 'DHAN_PUT_SCALPER', 'action_type': 'BUY'}
                                                telegram_trade.set_metadata_from_dict(metadata)
                                                telegram_trade.entry_type = 'DHAN_PUT_SCALPER'
                                                telegram_trade.save()
                                                redis_map.set('last_running_pair', {'value': 'RG'})
                                                break

                                            green_red_pair = False
                                            prev_open_price = banknifty_data['data']['open'][-2]
                                            prev_close_price = banknifty_data['data']['close'][-2]

                                            if prev_close_price > prev_open_price and close_price < open_price and close_price < prev_open_price:
                                                green_red_pair = True

                                            if close_price <= open_price or doji_condition:
                                                # strike_price = int((close_price + 50)/ 100) * 100
                                                strike_price = int((close_price)/ 100) * 100
                                                strike_price = (strike_price + 100)
                                                original_strike_price = strike_price
                                                expiry = bank_nifty_nearest_expiry
                                                option_type = 'PUT'
                                                trading_symbol = "%s %s %s %s" % (
                                                    'BANKNIFTY',
                                                    expiry, strike_price, option_type)
                                                security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
                                                premium_data = dhan.intraday_minute_data(security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
                                                last_min_premium_close_price = premium_data['data']['close'][-1]
                                                if last_min_premium_close_price < 100:
                                                    strike_price += 300
                                                elif last_min_premium_close_price < 200:
                                                    strike_price += 200
                                                elif last_min_premium_close_price < 250:
                                                    strike_price += 100
                                                if original_strike_price != strike_price:
                                                    expiry = bank_nifty_nearest_expiry
                                                    option_type = 'PUT'
                                                    trading_symbol = "%s %s %s %s" % (
                                                        'BANKNIFTY',
                                                        expiry, strike_price, option_type)
                                                    security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
                                                    premium_data = dhan.intraday_minute_data(security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
                                                    last_min_premium_close_price = premium_data['data']['close'][-1]
                                                fund = self.dhan.get_fund_limits()['data']['availabelBalance']
                                                fund = 20000
                                                quantity = (int(int(fund / last_min_premium_close_price) / 15) * 15)
                                                if quantity >= 75:
                                                    quantity = quantity - 60

                                                # Loop until the time is 59 seconds and 900ms (0.9 seconds)
                                                while True:
                                                    current_time = time.localtime()
                                                    milliseconds = int(time.time() * 1000) % 1000  # Get the milliseconds part
                                                    if (current_time.tm_sec == 59 and milliseconds >= 600) or current_time.tm_sec != 59:
                                                        logging.info("Reached %s seconds and %s ms!" % (current_time.tm_sec, milliseconds))
                                                        break
                                                    time.sleep(0.001)  # Sleep for 1ms to prevent busy waiting

                                                response = self.dhan.place_slice_order(security_id=security_id,
                                                    exchange_segment=dhan.NSE_FNO,
                                                    transaction_type=dhan.BUY,
                                                    quantity=quantity,
                                                    order_type=dhan.MARKET,
                                                    product_type=dhan.MARGIN,
                                                    price=0,
                                                    validity='DAY')
                                                order_id_list = [data['orderId'] for data in response['data']]

                                                time.sleep(2)
                                                try:
                                                    is_pending = False
                                                    try:
                                                        order_list = dhan.get_order_list()['data']
                                                        for order in order_list:
                                                            if order['orderId'] in order_id_list and order['orderStatus'] == 'PENDING':
                                                                is_pending = True
                                                                break
                                                    except Exception as e:
                                                        traceback.print_exc()
                                                        self.gmail_service.send_email(
                                                            'Dhan Put Scalper Order Status Check after 2 sec failed',
                                                            traceback.format_exc())
                                                        logging.info("Dhan Put Scalper Order Status Check after 2 sec failed: {}".format(str(e)))

                                                    if is_pending:
                                                        time.sleep(3)

                                                    logging.info("last_min_premium_close_price at 59th sec: %s" % last_min_premium_close_price)

                                                    premium_data = dhan.intraday_minute_data(security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
                                                    last_min_start_time = dhan.convert_to_date_time(premium_data['data']['start_Time'][-1])
                                                    second_last_min_start_time = dhan.convert_to_date_time(premium_data['data']['start_Time'][-2])
                                                    prev_min = timestamp.minute
                                                    if prev_min == second_last_min_start_time.minute:
                                                        last_min_premium_close_price = premium_data['data']['close'][-2]
                                                    elif prev_min == last_min_start_time.minute:
                                                        last_min_premium_close_price = premium_data['data']['close'][-1]
                                                    logging.info("last_min_premium_close_price after waiting 2 sec: %s" % last_min_premium_close_price)
                                                except Exception as e:
                                                    traceback.print_exc()
                                                    self.gmail_service.send_email(
                                                        'Dhan Put Scalper last_min_premium_close_price check after 2 sec failed',
                                                        traceback.format_exc())
                                                    logging.info("Dhan Put Scalper last_min_premium_close_price check after 2 sec failed: {}".format(str(e)))

                                                # for curr_order_id in order_id_list:
                                                #     curr_order = dhan.get_order_by_id(curr_order_id)
                                                #     curr_price = last_min_premium_close_price
                                                #     if curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], dict):
                                                #         if 'price' in curr_order['data'] and curr_order['data']['price'] is not None:
                                                #             curr_price = curr_order['data']['price']
                                                #     elif curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], list):
                                                #         if len(curr_order['data']) >= 1 and 'price' in curr_order['data'][0] and curr_order['data'][0]['price'] is not None:
                                                #             curr_price = curr_order['data'][0]['price']
                                                #     curr_price = round(curr_price, 1)
                                                #     last_min_premium_close_price = max(last_min_premium_close_price, curr_price)
                                                last_min_premium_close_price = round(last_min_premium_close_price, 1)
                                                telegram_trade = TelegramTrade()
                                                telegram_trade.index_name = 'BANKNIFTY'
                                                telegram_trade.index_strike_price = strike_price
                                                telegram_trade.option_type = 'PE'
                                                telegram_trade.expiry = bank_nifty_nearest_expiry
                                                telegram_trade.entry_start_price = last_min_premium_close_price
                                                telegram_trade.exit_first_target_price = last_min_premium_close_price + round((last_min_premium_close_price * 100) / 100, 1)
                                                logging.info("exit_first_target_price: %s" % telegram_trade.exit_first_target_price)
                                                if original_strike_price != strike_price:
                                                    telegram_trade.exit_first_target_price = int(telegram_trade.exit_first_target_price)
                                                # if telegram_trade.exit_first_target_price - telegram_trade.entry_start_price >= 1.5 and \
                                                #     telegram_trade.exit_first_target_price - int(telegram_trade.exit_first_target_price) < 0.4:
                                                #     telegram_trade.exit_first_target_price = int(telegram_trade.exit_first_target_price)
                                                telegram_trade.exit_stop_loss_price = last_min_premium_close_price - round((last_min_premium_close_price * 10) / 100, 1)
                                                logging.info("exit_stop_loss_price: %s" % telegram_trade.exit_stop_loss_price)
                                                telegram_trade.created_at_time = timestamp
                                                telegram_trade.order_status = 'ORDER_PLACED_DHAN'
                                                telegram_trade.quantity = quantity
                                                metadata = {'strategy': 'DHAN_PUT_SCALPER', 'action_type': 'BUY'}
                                                metadata['order_id_list'] = order_id_list
                                                metadata['original_strike_price'] = original_strike_price
                                                telegram_trade.set_metadata_from_dict(metadata)
                                                telegram_trade.entry_type = 'DHAN_PUT_SCALPER'
                                                telegram_trade.save()
                                                # time.sleep(10)

                                                sl_response = self.dhan.place_slice_order(security_id=security_id,
                                                    exchange_segment=dhan.NSE_FNO,
                                                    transaction_type=dhan.SELL,
                                                    quantity=quantity,
                                                    order_type=dhan.SL,
                                                    product_type=dhan.MARGIN,
                                                    trigger_price=telegram_trade.exit_stop_loss_price,
                                                    price=telegram_trade.exit_stop_loss_price-0.05,
                                                    validity='DAY')
                                                sl_order_id_list = [data['orderId'] for data in sl_response['data']]
                                                metadata['sl_order_id_list'] = sl_order_id_list
                                                metadata['target_order_id_list'] = []

                                                # target_response = self.dhan.place_slice_order(security_id=security_id,
                                                #     exchange_segment=dhan.NSE_FNO,
                                                #     transaction_type=dhan.SELL,
                                                #     quantity=quantity,
                                                #     order_type=dhan.LIMIT,
                                                #     product_type=dhan.MARGIN,
                                                #     price=telegram_trade.exit_first_target_price,
                                                #     validity='DAY')
                                                # target_order_id_list = [data['orderId'] for data in target_response['data']]
                                                # metadata['target_order_id_list'] = target_order_id_list
                                                
                                                metadata['security_id'] = security_id
                                                telegram_trade.set_metadata_from_dict(metadata)
                                                telegram_trade.save()


                                                redis_map.set('last_running_pair', {'value': 'GR'})
                                                
                                                time.sleep(2)
                                                
                                                order_list = dhan.get_order_list()['data']
                                                logging.info(order_list)
                                                self.gmail_queue.append({'subject': 'Dhan Order List', 'email_content': json.dumps(order_list)})
                                                # self.gmail_service.send_email('Dhan Order List', json.dumps(order_list))
                except Exception as e:
                    traceback.print_exc()
                    self.gmail_service.send_email(
                        'Dhan Put Scalper Order Placement failed',
                        traceback.format_exc())
                    logging.info("Dhan Put Scalper Order Placement failed: {}".format(str(e)))
            
            if timestamp.second >= 0:
                existing_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PUT_SCALPER')
                    & Q(order_status='ORDER_PLACED_DHAN'))
                
                for trade in existing_trades:
                    try:
                        created_at_time = trade.created_at_time
                        created_at_time_ist = get_ist_datetime(created_at_time)
                        time_diff = timestamp - created_at_time_ist
                        diff_in_minutes = time_diff.total_seconds() / 60
                        # print("created_at_time")
                        # print(created_at_time)
                        # print("diff_in_minutes:")
                        # print(diff_in_minutes)
                        metadata = trade.get_metadata_as_dict()

                        target_order_id_list = metadata.get('target_order_id_list', [])
                        sl_order_id_list = metadata.get('sl_order_id_list', [])
                        order_list = dhan.get_order_list()['data']
                        target_pending_id_list = []
                        sl_pending_id_list = []
                        no_pending = True
                        remaining_quantity = 0
                        trigerred_but_pending = False
                        for order in order_list:
                            if order['orderId'] in target_order_id_list and order['orderStatus'] == 'PENDING':
                                target_pending_id_list.append(order['orderId'])
                                remaining_quantity += order['quantity']
                                no_pending = False
                                
                            if order['orderId'] in sl_order_id_list and order['orderStatus'] == 'PENDING':
                                sl_pending_id_list.append(order['orderId'])
                                remaining_quantity += order['quantity']
                                no_pending = False
                                
                            if order['orderStatus'] == 'PENDING':
                                no_pending = False
                        
                        if remaining_quantity == 0 and not no_pending:
                            trigerred_but_pending = True
                        if no_pending:
                            redis_map.set('last_running_pair', {'value': 'GR'})
                            trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
                            trade.save()
                            # continue

                        security_id = metadata['security_id']

                        curr_tick_data = tick_map.get(str(security_id), {})
                        if 'LTP' in curr_tick_data:
                            ltp = float(curr_tick_data['LTP'])

                            ltt = curr_tick_data['LTT']
                            today_date = datetime.now(IST).date()
                            time_obj = datetime.strptime(ltt, "%H:%M:%S").time()
                            combined_datetime = datetime.combine(today_date, time_obj)

                            now = datetime.now(IST)
                            now = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
                            time_diff = now - combined_datetime
                            diff_in_seconds = abs(time_diff.total_seconds())

                            if diff_in_seconds >= 10:
                                min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
                                    instrument_type='OPTIDX')
                                ltp = min_data['data']['close'][-1]
                        else:
                            temp_min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
                                instrument_type='OPTIDX')
                            ltp = temp_min_data['data']['close'][-1]

                        prev_stop_loss = trade.exit_stop_loss_price
                        if trade.option_type == 'CE' and not no_pending:
                            updated_sl = trade.exit_stop_loss_price
                            if ltp > (trade.entry_start_price * 1):
                                updated_sl = trade.entry_start_price
                            if ltp >= (trade.entry_start_price * 1.01):
                                updated_sl = round(trade.entry_start_price * 1.005, 1)
                            if ltp >= (trade.entry_start_price * 1.02):
                                updated_sl = round(trade.entry_start_price * 1.01, 1)
                            if ltp >= (trade.entry_start_price * 1.03):
                                updated_sl = round(trade.entry_start_price * 1.02, 1)
                            if ltp >= (trade.entry_start_price * 1.04):
                                updated_sl = round(trade.entry_start_price * 1.03, 1)
                            if ltp >= (trade.entry_start_price * 1.05):
                                updated_sl = round(trade.entry_start_price * 1.03, 1)
                            if ltp >= (trade.entry_start_price * 1.07):
                                updated_sl = round(trade.entry_start_price * 1.04, 1)
                            if ltp >= (trade.entry_start_price * 1.10):
                                updated_sl = round(trade.entry_start_price * 1.05, 1)
                            if ltp >= (trade.entry_start_price * 1.15):
                                updated_sl = round(trade.entry_start_price * 1.05, 1)
                            if ltp >= (trade.entry_start_price * 1.5):
                                updated_sl = round(trade.entry_start_price * 1.2, 1)
                            if ltp >= (trade.entry_start_price * 1.7):
                                updated_sl = round(trade.entry_start_price * 1.4, 1)
                            if ltp >= (trade.entry_start_price * 1.9):
                                updated_sl = round(trade.entry_start_price * 1.6, 1)
                            if updated_sl >= trade.exit_stop_loss_price:
                                trade.exit_stop_loss_price = updated_sl

                        if trade.option_type == 'PE' and not no_pending:
                            # prev_stop_loss = trade.exit_stop_loss_price
                            updated_sl = trade.exit_stop_loss_price
                            if ltp > (trade.entry_start_price * 1):
                                updated_sl = trade.entry_start_price
                            if ltp >= (trade.entry_start_price * 1.01):
                                updated_sl = round(trade.entry_start_price * 1.005, 1)
                            if ltp >= (trade.entry_start_price * 1.02):
                                updated_sl = round(trade.entry_start_price * 1.01, 1)
                            if ltp >= (trade.entry_start_price * 1.03):
                                updated_sl = round(trade.entry_start_price * 1.02, 1)
                            if ltp >= (trade.entry_start_price * 1.04):
                                updated_sl = round(trade.entry_start_price * 1.03, 1)
                            if ltp >= (trade.entry_start_price * 1.05):
                                updated_sl = round(trade.entry_start_price * 1.03, 1)
                            if ltp >= (trade.entry_start_price * 1.07):
                                updated_sl = round(trade.entry_start_price * 1.04, 1)
                            if ltp >= (trade.entry_start_price * 1.10):
                                updated_sl = round(trade.entry_start_price * 1.05, 1)
                            if ltp >= (trade.entry_start_price * 1.15):
                                updated_sl = round(trade.entry_start_price * 1.05, 1)
                            if ltp >= (trade.entry_start_price * 1.5):
                                updated_sl = round(trade.entry_start_price * 1.2, 1)
                            if ltp >= (trade.entry_start_price * 1.7):
                                updated_sl = round(trade.entry_start_price * 1.4, 1)
                            if ltp >= (trade.entry_start_price * 1.9):
                                updated_sl = round(trade.entry_start_price * 1.6, 1)
                            if updated_sl >= trade.exit_stop_loss_price:
                                trade.exit_stop_loss_price = updated_sl

                        if prev_stop_loss != trade.exit_stop_loss_price and not no_pending:
                            logging.info("%s sl trailed to %s" % (trade.option_type, trade.exit_stop_loss_price))
                            email_message = "%s sl trailed to %s" % (trade.option_type, trade.exit_stop_loss_price)
                            self.gmail_queue.append({'subject': email_message, 'email_content': email_message})
                            # self.gmail_service.send_email(email_message, email_message)
                            trade.save()

                            sl_order_id_list = metadata['sl_order_id_list']
                            for order_id in sl_order_id_list:
                                try:
                                    sl_order = dhan.get_order_by_id(order_id)
                                    sl_order_data = sl_order['data']
                                    if isinstance(sl_order['data'], dict):
                                        sl_order_data = sl_order['data']
                                    else:
                                        sl_order_data = sl_order['data'][0]
                                    dhan.modify_order(order_id=order_id,
                                                      order_type=sl_order_data['orderType'],
                                                      leg_name="STOP_LOSS_LEG",
                                                      quantity=sl_order_data["quantity"],
                                                      price=trade.exit_stop_loss_price-0.05,
                                                      trigger_price=trade.exit_stop_loss_price,
                                                      disclosed_quantity=sl_order_data["disclosedQuantity"],
                                                      validity=sl_order_data["validity"])
                                except Exception as e:
                                    traceback.print_exc()
                                    self.gmail_service.send_email(
                                        'Dhan SL Order Modification Failed for trade.',
                                        traceback.format_exc())
                                    logging.info("Dhan SL Order Modification Failed for %s trade." % trade.option_type)

                        # print("ltp:")
                        # print(ltp)
                        DIFF_MIN_THRESHOLD = 300
                        if trade.option_type == 'CE':
                            DIFF_MIN_THRESHOLD = 300
                        CLOSE_COUNT_THRESHOLD = 1

                        # if ltp <= trade.exit_stop_loss_price or diff_in_minutes >= 2:
                        if (trigerred_but_pending and  ltp <= (0.95 * trade.exit_stop_loss_price)) or diff_in_minutes >= DIFF_MIN_THRESHOLD or no_pending:
                            trailing_map = metadata.get('trailing_map', {})
                            current_trailing_map_count = trailing_map.get(str(trade.exit_stop_loss_price), 0) + 1

                            if current_trailing_map_count < CLOSE_COUNT_THRESHOLD:
                                trailing_map[str(trade.exit_stop_loss_price)] = current_trailing_map_count
                                metadata['trailing_map'] = trailing_map
                                trade.set_metadata_from_dict(metadata)
                                trade.save()
                                continue
                            if not no_pending:
                                for sl_order_id in metadata['target_order_id_list']:
                                    dhan.cancel_order(sl_order_id)
                                for sl_order_id in metadata['sl_order_id_list']:
                                    dhan.cancel_order(sl_order_id)
                                time.sleep(0.5)
                                response = self.dhan.place_slice_order(security_id=security_id,
                                    exchange_segment=dhan.NSE_FNO,
                                    transaction_type=dhan.SELL,
                                    quantity=remaining_quantity,
                                    order_type=dhan.MARKET,
                                    product_type=dhan.MARGIN,
                                    price=0,
                                    validity='DAY')
                            metadata['sl_hit'] = True
                            trailing_map[str(trade.exit_stop_loss_price)] = current_trailing_map_count
                            metadata['trailing_map'] = trailing_map
                            trade.set_metadata_from_dict(metadata)
                            trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
                            trade.save()
                            redis_map.set('last_running_pair', {'value': 'RG'})

                            time.sleep(5)

                            sl_premium_close_price = trade.exit_stop_loss_price

                            if not no_pending:
                                order_id_list = [data['orderId'] for data in response['data']]
                                for curr_order_id in order_id_list:
                                    curr_order = dhan.get_order_by_id(curr_order_id)
                                    curr_price = sl_premium_close_price
                                    if curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], dict):
                                        if 'price' in curr_order['data'] and curr_order['data']['price'] is not None:
                                            curr_price = curr_order['data']['price']
                                    elif curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], list):
                                        if len(curr_order['data']) >= 1 and 'price' in curr_order['data'][0] and curr_order['data'][0]['price'] is not None:
                                            curr_price = curr_order['data'][0]['price']
                                    curr_price = round(curr_price, 1)
                                    sl_premium_close_price = min(sl_premium_close_price, curr_price)

                            sl_premium_close_price = round(sl_premium_close_price, 1)

                            if sl_premium_close_price <= 0:
                                sl_premium_close_price = ltp
                            
                            print("sl_premium_close_price %s" % sl_premium_close_price)

                            sl_percent = (sl_premium_close_price - trade.entry_start_price) * 100 / trade.entry_start_price

                            print("sl_percent: %s" % sl_percent)

                            metadata['sl_percent'] = sl_percent
                            trade.set_metadata_from_dict(metadata)
                            trade.save()

                            # Skip reverse trade for now
                            # if metadata['sl_hit']:
                            #     continue

                            if trade.option_type == 'CE':
                                continue

                            if sl_percent < -15 or sl_percent >= 0:
                                break

                            # Reverse Trade Section

                            # # Loop until the time is 59 seconds and 900ms (0.9 seconds)
                            # while True:
                            #     current_time = time.localtime()
                            #     milliseconds = int(time.time() * 1000) % 1000  # Get the milliseconds part
                            #     if (current_time.tm_sec == 59 and milliseconds >= 600) or current_time.tm_sec == 0:
                            #         logging.info(
                            #             "Reached %s seconds and %s ms!" % (current_time.tm_sec, milliseconds))
                            #         break
                            #     if current_time.tm_sec < 59:
                            #         time.sleep(1)
                            #     time.sleep(0.001)  # Sleep for 1ms to prevent busy waiting

                            original_strike_price = metadata['original_strike_price']

                            strike_price = original_strike_price - 100
                            expiry = bank_nifty_nearest_expiry
                            option_type = 'CALL'
                            trading_symbol = "%s %s %s %s" % (
                                'BANKNIFTY',
                                expiry, strike_price, option_type)
                            security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
                            premium_data = dhan.intraday_minute_data(security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
                            last_min_premium_close_price = premium_data['data']['close'][-1]
                            last_min_premium_low_price = premium_data['data']['low'][-1]
                            updated_strike_price = strike_price

                            if last_min_premium_close_price < 100:
                                updated_strike_price -= 300
                            elif last_min_premium_close_price < 200:
                                updated_strike_price -= 200
                            elif last_min_premium_close_price < 250:
                                updated_strike_price -= 100
                            if updated_strike_price != strike_price:
                                expiry = bank_nifty_nearest_expiry
                                option_type = 'CALL'
                                trading_symbol = "%s %s %s %s" % (
                                    'BANKNIFTY',
                                    expiry, updated_strike_price, option_type)
                                security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
                                premium_data = dhan.intraday_minute_data(security_id, exchange_segment=dhan.FNO,
                                                                         instrument_type='OPTIDX')
                                last_min_premium_close_price = premium_data['data']['close'][-1]
                                last_min_premium_low_price = premium_data['data']['low'][-1]

                            fund = self.dhan.get_fund_limits()['data']['availabelBalance']
                            fund = 20000
                            quantity = (int(int(fund / last_min_premium_close_price) / 15) * 15)
                            if quantity >= 75:
                                quantity = quantity - 60
                            response = self.dhan.place_slice_order(security_id=security_id,
                                exchange_segment=dhan.NSE_FNO,
                                transaction_type=dhan.BUY,
                                quantity=quantity,
                                order_type=dhan.MARKET,
                                product_type=dhan.MARGIN,
                                price=0,
                                validity='DAY')
                            order_id_list = [data['orderId'] for data in response['data']]
                            for curr_order_id in order_id_list:
                                curr_order = dhan.get_order_by_id(curr_order_id)
                                curr_price = last_min_premium_close_price
                                if curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], dict):
                                    if 'price' in curr_order['data'] and curr_order['data']['price'] is not None:
                                        curr_price = curr_order['data']['price']
                                elif curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], list):
                                    if len(curr_order['data']) >= 1 and 'price' in curr_order['data'][0] and curr_order['data'][0]['price'] is not None:
                                        curr_price = curr_order['data'][0]['price']
                                last_min_premium_close_price = max(last_min_premium_close_price, curr_price)

                            last_min_premium_close_price = round(last_min_premium_close_price, 1)
                            logging.info("CE last_min_premium_close_price: %s" % last_min_premium_close_price)
                            telegram_trade = TelegramTrade()
                            telegram_trade.index_name = 'BANKNIFTY'
                            telegram_trade.index_strike_price = strike_price
                            telegram_trade.option_type = 'CE'
                            telegram_trade.expiry = bank_nifty_nearest_expiry
                            telegram_trade.entry_start_price = last_min_premium_close_price
                            telegram_trade.exit_first_target_price = last_min_premium_close_price + round((last_min_premium_close_price * (abs(sl_percent) + 1)) / 100, 1)
                            telegram_trade.exit_first_target_price = int(telegram_trade.exit_first_target_price)
                            logging.info("CE exit_first_target_price: %s" % telegram_trade.exit_first_target_price)
                            telegram_trade.exit_stop_loss_price = last_min_premium_close_price - round((last_min_premium_close_price * (abs(sl_percent) + 1)) / 100, 1)
                            logging.info("CE exit_stop_loss_price: %s" % telegram_trade.exit_stop_loss_price)
                            telegram_trade.created_at_time = timestamp
                            telegram_trade.order_status = 'ORDER_PLACED_DHAN'
                            telegram_trade.quantity = quantity
                            metadata = {'strategy': 'DHAN_PUT_SCALPER', 'action_type': 'BUY'}
                            metadata['order_id_list'] = order_id_list
                            telegram_trade.set_metadata_from_dict(metadata)
                            telegram_trade.entry_type = 'DHAN_PUT_SCALPER'
                            telegram_trade.save()
                            # time.sleep(10)

                            sl_response = self.dhan.place_slice_order(security_id=security_id,
                                exchange_segment=dhan.NSE_FNO,
                                transaction_type=dhan.SELL,
                                quantity=quantity,
                                order_type=dhan.SL,
                                product_type=dhan.MARGIN,
                                trigger_price=telegram_trade.exit_stop_loss_price,
                                price=telegram_trade.exit_stop_loss_price-0.05,
                                validity='DAY')
                            sl_order_id_list = [data['orderId'] for data in sl_response['data']]
                            metadata['sl_order_id_list'] = sl_order_id_list
                            metadata['target_order_id_list'] = []

                            time.sleep(1)
                            is_pending = False
                            try:
                                order_list = dhan.get_order_list()['data']
                                self.gmail_queue.append({'subject': 'Dhan Order List', 'email_content': json.dumps(order_list)})
                                for order in order_list:
                                    if order['orderId'] in order_id_list and order['orderStatus'] == 'PENDING':
                                        is_pending = True
                                        break
                            except Exception as e:
                                traceback.print_exc()
                                self.gmail_service.send_email(
                                    'Dhan Call Scalper Order Status Check after 1 sec failed',
                                    traceback.format_exc())
                                logging.info("Dhan Call Scalper Order Status Check after 1 sec failed: {}".format(str(e)))

                            if is_pending:
                                logging.info("Dhan Call Scalper Order still pending. Waiting for 2 more seconds.")
                                time.sleep(2)

                            # target_response = self.dhan.place_slice_order(security_id=security_id,
                            #     exchange_segment=dhan.NSE_FNO,
                            #     transaction_type=dhan.SELL,
                            #     quantity=quantity,
                            #     order_type=dhan.LIMIT,
                            #     product_type=dhan.MARGIN,
                            #     price=telegram_trade.exit_first_target_price,
                            #     validity='DAY')
                            # target_order_id_list = [data['orderId'] for data in target_response['data']]
                            # metadata['target_order_id_list'] = target_order_id_list
                            metadata['security_id'] = security_id
                            telegram_trade.set_metadata_from_dict(metadata)
                            telegram_trade.save()
                            
                    except Exception as e:
                        traceback.print_exc()
                        self.gmail_service.send_email(
                            'Dhan Put/Call Scalper Order Status Check failed',
                            traceback.format_exc())
                        logging.info("Dhan Put/Call Scalper Order Status Check failed: {}".format(str(e)))

            
            if timestamp.second >= 0:
                existing_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PAIR_SCALPER')
                    & Q(order_status='ORDER_PLACED_DHAN'))
                
                for trade in existing_trades:
                    try:
                        created_at_time = trade.created_at_time
                        created_at_time_ist = get_ist_datetime(created_at_time)
                        time_diff = timestamp - created_at_time_ist
                        diff_in_minutes = time_diff.total_seconds() / 60
                        print("created_at_time")
                        print(created_at_time)
                        print("diff_in_minutes:")
                        print(diff_in_minutes)
                        metadata = trade.get_metadata_as_dict()

                        target_order_id_list = metadata.get('target_order_id_list', [])
                        order_list = dhan.get_order_list()['data']
                        target_pending_id_list = []
                        no_pending = True
                        remaining_quantity = 0
                        for order in order_list:
                            if order['orderId'] in target_order_id_list and order['orderStatus'] == 'PENDING':
                                target_pending_id_list.append(order['orderId'])
                                remaining_quantity += order['quantity']
                                no_pending = False
                        
                        if no_pending:
                            # redis_map.set('last_running_pair', {'value': 'GR'})
                            trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
                            trade.save()
                            continue

                        security_id = metadata['security_id']

                        curr_tick_data = tick_map.get(str(security_id), {})
                        if 'LTP' in curr_tick_data:
                            ltp = float(curr_tick_data['LTP'])

                            ltt = curr_tick_data['LTT']
                            today_date = datetime.now(IST).date()
                            time_obj = datetime.strptime(ltt, "%H:%M:%S").time()
                            combined_datetime = datetime.combine(today_date, time_obj)

                            now = datetime.now(IST)
                            now = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
                            time_diff = now - combined_datetime
                            diff_in_seconds = abs(time_diff.total_seconds())

                            if diff_in_seconds >= 10:
                                min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
                                    instrument_type='OPTIDX')
                                ltp = min_data['data']['close'][-1]
                        else:
                            temp_min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
                                instrument_type='OPTIDX')
                            ltp = temp_min_data['data']['close'][-1]
                        

                        print("ltp:")
                        print(ltp)
                        # if ltp <= trade.exit_stop_loss_price or diff_in_minutes >= 2:
                        if ltp <= trade.exit_stop_loss_price or diff_in_minutes >= 1:
                            for sl_order_id in metadata['target_order_id_list']:
                                dhan.cancel_order(sl_order_id)
                            time.sleep(0.1)
                            response = self.dhan.place_slice_order(security_id=security_id,
                                exchange_segment=dhan.NSE_FNO,
                                transaction_type=dhan.SELL,
                                quantity=remaining_quantity,
                                order_type=dhan.MARKET,
                                product_type=dhan.MARGIN,
                                price=0,
                                validity='DAY')
                            metadata['sl_hit'] = True
                            trade.set_metadata_from_dict(metadata)
                            trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
                            trade.save()

                            # time.sleep(2)

                            # Skip reverse trade for now
                            

                            sl_premium_close_price = ltp

                            order_id_list = [data['orderId'] for data in response['data']]
                            for curr_order_id in order_id_list:
                                curr_order = dhan.get_order_by_id(curr_order_id)
                                curr_price = sl_premium_close_price
                                if curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], dict):
                                    if 'price' in curr_order['data'] and curr_order['data']['price'] is not None:
                                        curr_price = curr_order['data']['price']
                                elif curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], list):
                                    if len(curr_order['data']) >= 1 and 'price' in curr_order['data'][0] and curr_order['data'][0]['price'] is not None:
                                        curr_price = curr_order['data'][0]['price']
                                curr_price = round(curr_price, 1)
                                sl_premium_close_price = min(sl_premium_close_price, curr_price)
                            
                            sl_premium_close_price = round(sl_premium_close_price, 1)

                            if sl_premium_close_price <= 0:
                                sl_premium_close_price = ltp
                            
                            print("sl_premium_close_price %s" % sl_premium_close_price)

                            sl_percent = (sl_premium_close_price - trade.entry_start_price) * 100 / trade.entry_start_price
                            print("sl_percent: %s" % sl_percent)

                            metadata['sl_percent'] = sl_percent
                            trade.set_metadata_from_dict(metadata)
                            trade.save()

                            if sl_percent < 0:
                                redis_value = redis_map.get('last_running_pair')
                                last_running_pair = redis_value.get('value') if redis_value is not None else 'GR'
                                if last_running_pair is None:
                                    last_running_pair = 'GR'
                                curr_running_pair = 'RG' if last_running_pair == 'GR' else 'GR'
                                redis_map.set('last_running_pair', {'value': curr_running_pair})

                            
                            
                    except Exception as e:
                        traceback.print_exc()
                        logging.info("Dhan Pair Scalper Order Status Check failed: {}".format(str(e)))


            if timestamp.second == 59:
                pair_scalper_exited_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PAIR_SCALPER')
                    & Q(order_status='ORDER_EXIT_EXECUTED_DHAN'))
                
                net_pnl_percent = 0
                total_trade_cnt = 0
                for trade in pair_scalper_exited_trades:
                    metadata = trade.get_metadata_as_dict()
                    if 'sl_percent' in metadata:
                        net_pnl_percent += metadata['sl_percent']
                    else:
                        net_pnl_percent += 1
                    total_trade_cnt += 1

                if net_pnl_percent <= -2 or total_trade_cnt >= 20 or timestamp.hour == 15 or net_pnl_percent >= 2:
                    redis_map.set('pair_strategy_status', {'value': 'CLOSED'})

            if timestamp.second == 59:
                put_scalper_placed_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PUT_SCALPER')
                    & Q(order_status='ORDER_PLACED_DHAN'))

                pair_scalper_placed_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PAIR_SCALPER')
                    & Q(order_status='ORDER_PLACED_DHAN'))

                put_scalper_exited_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PUT_SCALPER')
                    & Q(order_status='ORDER_EXIT_EXECUTED_DHAN'))

                redis_value = redis_map.get('pair_strategy_status')
                pair_strategy_status = redis_value.get('value') if redis_value is not None else 'OPEN'

                expiry_day = int(bank_nifty_nearest_expiry.split(' ')[0])
                expiry_month_str = bank_nifty_nearest_expiry.split(' ')[1].upper()
                expiry_month = {month[:3].upper(): index for index, month in enumerate(calendar.month_name) if month}[expiry_month_str]
                
                current_year = timestamp.year

                timestamp_date = datetime(current_year, timestamp.month, timestamp.day)
                expiry_date = datetime(current_year, expiry_month, expiry_day)
                day_diff = (expiry_date - timestamp_date).days

                if not put_scalper_placed_trades and put_scalper_exited_trades and not pair_scalper_placed_trades and pair_strategy_status != 'CLOSED' and day_diff >= 2:
                    redis_value = redis_map.get('last_running_pair')
                    last_running_pair = redis_value.get('value') if redis_value is not None else 'GR'
                    if last_running_pair is None:
                        last_running_pair = 'GR'
                    
                    redis_value = redis_map.get('pair_strategy_status')
                    if redis_value is None:
                        redis_map.set('pair_strategy_status', {'value': 'OPEN'})
                    
                    try:
                        banknifty_data = dhan.intraday_minute_data(bank_nifty_security_id, exchange_segment='IDX_I', instrument_type='INDEX')
                        if 'start_Time' in banknifty_data['data']:
                            data_length = len(banknifty_data['data']['start_Time'])
                            for i in range(data_length):
                                banknifty_data['data']['start_Time'][i] = dhan.convert_to_date_time(banknifty_data['data']['start_Time'][i])
                                if pair_strategy_status != 'CLOSED':
                                    if i == data_length - 1:
                                        logging.info("Checking for DHAN_PAIR_SCALPER entry")
                                        low_price = banknifty_data['data']['low'][-1]
                                        high_price = banknifty_data['data']['high'][-1]
                                        open_price = banknifty_data['data']['open'][-1]
                                        close_price = banknifty_data['data']['close'][-1]
                                        logging.info("open_price: %s, close_price: %s" % (open_price, close_price))
                                        if timestamp.minute == banknifty_data['data']['start_Time'][i].minute:
                                            green_red_pair = False
                                            prev_open_price = banknifty_data['data']['open'][-2]
                                            prev_close_price = banknifty_data['data']['close'][-2]
                                            logging.info("prev_open_price: %s, prev_close_price: %s" % (prev_open_price, prev_close_price))

                                            if prev_close_price > prev_open_price and close_price < open_price and close_price < prev_open_price and abs(prev_open_price - close_price) > 1:
                                                green_red_pair = True

                                            red_green_pair = False
                                            if prev_close_price < prev_open_price and close_price > open_price and prev_open_price < close_price and abs(close_price - prev_open_price) > 1:
                                                red_green_pair = True

                                            if (green_red_pair and last_running_pair == 'GR') or (red_green_pair and last_running_pair == 'RG'):
                                                option_type = 'PUT' if last_running_pair == 'GR' else 'CALL'
                                                strike_price = int((close_price)/ 100) * 100
                                                strike_price = (strike_price + 100) if option_type == 'PUT' else strike_price
                                                original_strike_price = strike_price
                                                expiry = bank_nifty_nearest_expiry
                                                
                                                trading_symbol = "%s %s %s %s" % (
                                                    'BANKNIFTY',
                                                    expiry, strike_price, option_type)
                                                security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
                                                premium_data = dhan.intraday_minute_data(security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
                                                last_min_premium_close_price = premium_data['data']['close'][-1]
                                                # if last_min_premium_close_price < 100:
                                                #     strike_price += 200
                                                # elif last_min_premium_close_price < 200:
                                                #     strike_price += 100
                                                if original_strike_price != strike_price:
                                                    expiry = bank_nifty_nearest_expiry
                                                    option_type = 'PUT' if last_running_pair == 'GR' else 'CALL'
                                                    trading_symbol = "%s %s %s %s" % (
                                                        'BANKNIFTY',
                                                        expiry, strike_price, option_type)
                                                    security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
                                                    premium_data = dhan.intraday_minute_data(security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
                                                    last_min_premium_close_price = premium_data['data']['close'][-1]
                                                fund = self.dhan.get_fund_limits()['data']['availabelBalance']
                                                fund = 20000
                                                quantity = (int(int(fund / last_min_premium_close_price) / 15) * 15)
                                                if quantity >= 75:
                                                    quantity = quantity - 15
                                                response = self.dhan.place_slice_order(security_id=security_id,
                                                    exchange_segment=dhan.NSE_FNO,
                                                    transaction_type=dhan.BUY,
                                                    quantity=quantity,
                                                    order_type=dhan.MARKET,
                                                    product_type=dhan.MARGIN,
                                                    price=0,
                                                    validity='DAY')
                                                order_id_list = [data['orderId'] for data in response['data']]

                                                time.sleep(5)

                                                for curr_order_id in order_id_list:
                                                    curr_order = dhan.get_order_by_id(curr_order_id)
                                                    curr_price = last_min_premium_close_price
                                                    if curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], dict):
                                                        if 'price' in curr_order['data'] and curr_order['data']['price'] is not None:
                                                            curr_price = curr_order['data']['price']
                                                    elif curr_order is not None and curr_order.get('status') == 'success' and isinstance(curr_order['data'], list):
                                                        if len(curr_order['data']) >= 1 and 'price' in curr_order['data'][0] and curr_order['data'][0]['price'] is not None:
                                                            curr_price = curr_order['data'][0]['price']
                                                    curr_price = round(curr_price, 1)
                                                    last_min_premium_close_price = max(last_min_premium_close_price, curr_price)
                                                last_min_premium_close_price = round(last_min_premium_close_price, 1)
                                                telegram_trade = TelegramTrade()
                                                telegram_trade.index_name = 'BANKNIFTY'
                                                telegram_trade.index_strike_price = strike_price
                                                telegram_trade.option_type = 'PE' if option_type == 'PUT' else 'CE'
                                                telegram_trade.expiry = bank_nifty_nearest_expiry
                                                telegram_trade.entry_start_price = last_min_premium_close_price
                                                telegram_trade.exit_first_target_price = last_min_premium_close_price + round(last_min_premium_close_price / 100, 1)
                                                if original_strike_price != strike_price:
                                                    telegram_trade.exit_first_target_price = int(telegram_trade.exit_first_target_price)
                                                # if telegram_trade.exit_first_target_price - telegram_trade.entry_start_price >= 1.5 and \
                                                #     telegram_trade.exit_first_target_price - int(telegram_trade.exit_first_target_price) < 0.4:
                                                #     telegram_trade.exit_first_target_price = int(telegram_trade.exit_first_target_price)
                                                telegram_trade.exit_stop_loss_price = last_min_premium_close_price - round((last_min_premium_close_price * 5) / 100, 1)
                                                telegram_trade.created_at_time = timestamp
                                                telegram_trade.order_status = 'ORDER_PLACED_DHAN'
                                                telegram_trade.quantity = quantity
                                                metadata = {'strategy': 'DHAN_PAIR_SCALPER', 'action_type': 'BUY'}
                                                metadata['order_id_list'] = order_id_list
                                                metadata['original_strike_price'] = original_strike_price
                                                telegram_trade.set_metadata_from_dict(metadata)
                                                telegram_trade.entry_type = 'DHAN_PAIR_SCALPER'
                                                # telegram_trade.save()
                                                # time.sleep(10)

                                                # sl_response = self.dhan.place_slice_order(security_id=security_id,
                                                #     exchange_segment=dhan.NSE_FNO,
                                                #     transaction_type=dhan.SELL,
                                                #     quantity=quantity,
                                                #     order_type=dhan.SL,
                                                #     product_type=dhan.MARGIN,
                                                #     trigger_price=telegram_trade.exit_stop_loss_price,
                                                #     price=telegram_trade.exit_stop_loss_price-1,
                                                #     validity='DAY')
                                                # sl_order_id_list = [data['orderId'] for data in sl_response['data']]
                                                # metadata['sl_order_id_list'] = sl_order_id_list

                                                target_response = self.dhan.place_slice_order(security_id=security_id,
                                                    exchange_segment=dhan.NSE_FNO,
                                                    transaction_type=dhan.SELL,
                                                    quantity=quantity,
                                                    order_type=dhan.LIMIT,
                                                    product_type=dhan.MARGIN,
                                                    price=telegram_trade.exit_first_target_price,
                                                    validity='DAY')
                                                target_order_id_list = [data['orderId'] for data in target_response['data']]
                                                metadata['target_order_id_list'] = target_order_id_list
                                                metadata['security_id'] = security_id
                                                metadata['last_running_pair'] = last_running_pair
                                                telegram_trade.set_metadata_from_dict(metadata)
                                                telegram_trade.save()
                                                
                                                time.sleep(5)
                    except Exception as e:
                        traceback.print_exc()
                        logging.info("Dhan Pair Scalper Order Placement failed: {}".format(str(e)))
                    

            # if timestamp.second == 59:
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_PUT_SCALPER')
            #         & Q(order_status='ORDER_PLACED_DHAN'))
            #     try:
            #         for existing_trade in existing_trades:
            #             metadata = existing_trade.get_metadata_as_dict()
            #             security_id = metadata['security_id']

            #             target_order_id_list = metadata.get('target_order_id_list', [])
            #             order_list = dhan.get_order_list()['data']
            #             target_pending_id_list = []
            #             no_pending = True
            #             remaining_quantity = 0
            #             for order in order_list:
            #                 if order['orderId'] in target_order_id_list and order['orderStatus'] == 'PENDING':
            #                     target_pending_id_list.append(order['orderId'])
            #                     remaining_quantity += order['quantity']
            #                     no_pending = False
                        
            #             if no_pending:
            #                 trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                 trade.save()
            #             else:
            #                 print("Checking Dhan Put Scalper Order Status based on 1 minute data")
            #                 min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
            #                     instrument_type='OPTIDX')
            #                 created_at_time = get_ist_datetime(existing_trade.created_at_time)
            #                 print("created_at_time")
            #                 print(created_at_time)
            #                 created_at_time = datetime(created_at_time.year, created_at_time.month, created_at_time.day, created_at_time.hour, created_at_time.minute + 1)
            #                 if 'start_Time' in min_data['data']:
            #                     data_length = len(min_data['data']['start_Time'])
            #                     for i in range(data_length):
            #                         min_data['data']['start_Time'][i] = dhan.convert_to_date_time(min_data['data']['start_Time'][i])
            #                         if min_data['data']['start_Time'][i] >= created_at_time:
            #                             low = min_data['data']['low'][i]
            #                             high = min_data['data']['high'][i]
            #                             if existing_trade.exit_stop_loss_price >= low or existing_trade.exit_first_target_price <= high:
            #                                 for sl_order_id in metadata['target_order_id_list']:
            #                                     dhan.cancel_order(sl_order_id)
            #                                 response = self.dhan.place_slice_order(security_id=security_id,
            #                                     exchange_segment=dhan.NSE_FNO,
            #                                     transaction_type=dhan.SELL,
            #                                     quantity=remaining_quantity,
            #                                     order_type=dhan.MARKET,
            #                                     product_type=dhan.MARGIN,
            #                                     price=0,
            #                                     validity='DAY')
            #                                 existing_trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                                 existing_trade.save()
            #                                 break


                                
            #             # if existing_trade.order_status == 'ORDER_PLACED_DHAN':
            #             #     sl_order_id_list = metadata.get('sl_order_id_list', [])
            #             #     target_order_id_list = metadata.get('target_order_id_list', [])

            #             #     sl_pending_id_list = []
            #             #     target_pending_id_list = []

            #             #     order_list = dhan.get_order_list()['data']
            #             #     no_pending = True
            #             #     remaining_quantity = 0
            #             #     for order in order_list:
            #             #         if order['orderId'] in sl_order_id_list and order['orderStatus'] == 'PENDING':
            #             #             sl_pending_id_list.append(order['orderId'])
            #             #             remaining_quantity += order['quantity']
            #             #         if order['orderId'] in target_order_id_list and order['orderStatus'] == 'PENDING':
            #             #             target_pending_id_list.append(order['orderId'])
            #             #             remaining_quantity += order['quantity']
            #             #         if order['orderStatus'] == 'PENDING':
            #             #             no_pending = False

            #             #     if len(sl_pending_id_list) == 0:
            #             #         for order_id in target_pending_id_list:
            #             #             dhan.cancel_order(order_id)
            #             #     elif len(target_pending_id_list) == 0:
            #             #         for order_id in sl_pending_id_list:
            #             #             dhan.cancel_order(order_id)
            #             #     elif len(sl_pending_id_list) != len(sl_order_id_list) or len(target_pending_id_list) != len(target_order_id_list):
            #             #         for order_id in sl_pending_id_list:
            #             #             dhan.cancel_order(order_id)
            #             #         for order_id in target_pending_id_list:
            #             #             dhan.cancel_order(order_id)
            #             #         time.sleep(1)
            #             #         response = self.dhan.place_slice_order(security_id=security_id,
            #             #             exchange_segment=dhan.NSE_FNO,
            #             #             transaction_type=dhan.SELL,
            #             #             quantity=remaining_quantity,
            #             #             order_type=dhan.MARKET,
            #             #             product_type=dhan.MARGIN,
            #             #             price=0,
            #             #             validity='DAY')
            #             #         time.sleep(5)

            #             #     order_list = dhan.get_order_list()['data']
            #             #     no_pending = True
            #             #     for order in order_list:
            #             #         if order['orderStatus'] == 'PENDING':
            #             #             no_pending = False

            #             #     if no_pending:
            #             #         existing_trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #             #         existing_trade.save()
            #     except Exception as e:
            #         traceback.print_exc()
            #         logging.info("Dhan Put Scalper Order Status Check based on 1 minute data failed: {}".format(str(e)))

            if timestamp.second == 59:
                existing_running_scalper_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PUT_SCALPER')
                    & Q(order_status='ORDER_PLACED_DHAN'))
                existing_scalper_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today)
                    & Q(entry_type='DHAN_PUT_SCALPER')
                    & Q(order_status='ORDER_EXIT_EXECUTED_DHAN'))
                try:
                    if existing_scalper_trades and not existing_running_scalper_trades:
                        cancelled_waiting_trades = TelegramTrade.objects.filter(
                            Q(entry_type='DHAN_HEDGE')
                            & ~Q(order_status='EXPIRED')
                            & Q(metadata__icontains='CANCELLED_WAITING'))

                        for trade in cancelled_waiting_trades:
                            trade.order_status = 'NOT_PLACED_DHAN'
                            # total_fund = self.dhan.get_fund_limits()['data']['sodLimit']
                            # trade.quantity = int(((trade.quantity * 1000000) / total_fund) / 15) * 15
                            metadata = trade.get_metadata_as_dict()
                            total_fund = self.dhan.get_fund_limits()['data']['sodLimit']
                            if 'quantity' in metadata:
                                trade.quantity = int(((metadata['quantity'] * 1000000) / total_fund) / 15) * 15
                            else:
                                trade.quantity = int(((trade.quantity * 1000000) / total_fund) / 15) * 15
                            del metadata['updated_order_status']
                            trade.set_metadata_from_dict(metadata)
                            if 'force_wait' not in metadata:
                                trade.save()
                except Exception as e:
                    traceback.print_exc()
                    logging.info("Dhan Put Scalper Switch to Hedge Position failed: {}".format(str(e)))


                        




            # if timestamp.second == 59:
            #     # print("Ticks: {}".format(ticks))
            #     if timestamp.second % 10 == 0:
            #         print("inside process_on_tick")
            #     # print(kite.margins())
            #     # kite = self.kite

            #     # TODO: Cancel all existing sell positions based on order_status
            #     cancelled_trades = TelegramTrade.objects.filter(
            #         Q(entry_type='DHAN_HEDGE')
            #         & ~Q(order_status='EXPIRED')
            #         & Q(metadata__icontains='CANCEL'))

            #     for trade in cancelled_trades:
            #         try:
            #             metadata = trade.get_metadata_as_dict()

            #             if (trade.order_status == 'ORDER_PLACED_DHAN' or trade.order_status == 'SL_TARGET_ORDER_PLACED_DHAN') and metadata['action_type'] == 'SELL':
            #                 sl_order_status = ''
            #                 if 'stop_loss_order_id' in metadata and len(metadata['stop_loss_order_id']) > 0:
            #                     stop_loss_order_id = metadata['stop_loss_order_id']
            #                     sl_order = dhan.get_order_by_id(stop_loss_order_id)
            #                     if isinstance(sl_order['data'], dict):
            #                         sl_order_status = sl_order['data']['orderStatus']
            #                     else:
            #                         sl_order_status = sl_order['data'][0]['orderStatus']
            #                     dhan.cancel_order(stop_loss_order_id)

            #                 target_order_status = ''
            #                 if 'target_order_id' in metadata:
            #                     target_order_id = metadata['target_order_id']
            #                     target_order = dhan.get_order_by_id(target_order_id)
            #                     if isinstance(target_order['data'], dict):
            #                         target_order_status = target_order['data']['orderStatus']
            #                     else:
            #                         target_order_status = target_order['data'][0]['orderStatus']
            #                     dhan.cancel_order(target_order_id)

            #                 expiry = trade.expiry
            #                 option_type = 'CALL' if trade.option_type == 'CE' else 'PUT'
            #                 trading_symbol = "%s %s %s %s" % (
            #                     trade.index_name.replace(' ', ''),
            #                     expiry, trade.index_strike_price, option_type)
            #                 security_id = None
            #                 trade_name = trade.index_name.replace(' ', '')
            #                 if trade_name == 'NIFTY':
            #                     security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                 elif trade_name == 'BANKNIFTY':
            #                     security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                 elif trade_name == 'FINNIFTY':
            #                     security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                 response = self.dhan.place_order(security_id=security_id,
            #                     exchange_segment=dhan.NSE_FNO,
            #                     transaction_type=dhan.BUY,
            #                     quantity=trade.quantity,
            #                     order_type=dhan.MARKET,
            #                     product_type=dhan.MARGIN,
            #                     price=0,
            #                     validity='DAY')
            #                 order_id = ''
            #                 if isinstance(response['data'], dict):
            #                     order_id = response['data']['orderId']
            #                 else:
            #                     order_id = response['data'][0]['orderId']
            #                 time.sleep(5)
            #                 order = dhan.get_order_by_id(order_id)
            #                 if isinstance(order['data'], dict):
            #                     order_status = order['data']['orderStatus']
            #                 else:
            #                     order_status = order['data'][0]['orderStatus']
            #                 retrial_cnt = 20
            #                 while order_status != 'TRADED' and retrial_cnt > 0:
            #                     print("Sell Hedge Trade Was not cancelled. Retrying %s" %(21-retrial_cnt))
            #                     response = self.dhan.place_order(security_id=security_id,
            #                         exchange_segment=dhan.NSE_FNO,
            #                         transaction_type=dhan.BUY,
            #                         quantity=trade.quantity,
            #                         order_type=dhan.MARKET,
            #                         product_type=dhan.MARGIN,
            #                         price=0,
            #                         validity='DAY')
            #                     if isinstance(response['data'], dict):
            #                         order_id = response['data']['orderId']
            #                     else:
            #                         order_id = response['data'][0]['orderId']
            #                     time.sleep(5)
            #                     order = dhan.get_order_by_id(order_id)
            #                     if isinstance(order['data'], dict):
            #                         order_status = order['data']['orderStatus']
            #                     else:
            #                         order_status = order['data'][0]['orderStatus']
            #                     # hedge_trade.quantity = (actual_lots_based_on_fund - 1 - (actual_lots_based_on_fund - retrial_cnt)) * lot_size
            #                     retrial_cnt -= 1
            #                 trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                 trade.save()

            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("Dhan Hedge Sell Cancellation failed: {}".format(str(e)))

            #     # Wait for exeution of Sell Exit
            #     time.sleep(5)

            #     for trade in cancelled_trades:
            #         try:
            #             metadata = trade.get_metadata_as_dict()
                        
            #             if metadata['action_type'] == 'BUY' and trade.order_status == 'ORDER_PLACED_DHAN':
            #                 buy_trade = trade
            #                 expiry = buy_trade.expiry
            #                 option_type = 'CALL' if buy_trade.option_type == 'CE' else 'PUT'
            #                 trading_symbol = "%s %s %s %s" % (
            #                     buy_trade.index_name.replace(' ', ''),
            #                     expiry, buy_trade.index_strike_price, option_type)
            #                 trade_name = buy_trade.index_name.replace(' ', '')
            #                 security_id = None
            #                 if trade_name == 'NIFTY':
            #                     security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                 elif trade_name == 'BANKNIFTY':
            #                     security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                 elif trade_name == 'FINNIFTY':
            #                     security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                 response = self.dhan.place_order(security_id=security_id,
            #                     exchange_segment=dhan.NSE_FNO,
            #                     transaction_type=dhan.SELL,
            #                     quantity=buy_trade.quantity,
            #                     order_type=dhan.MARKET,
            #                     product_type=dhan.MARGIN,
            #                     price=0,
            #                     validity='DAY')
            #                 time.sleep(5)
            #                 order = dhan.get_order_by_id(order_id)
            #                 if isinstance(order['data'], dict):
            #                     order_status = order['data']['orderStatus']
            #                 else:
            #                     order_status = order['data'][0]['orderStatus']
            #                 retrial_cnt = 20
            #                 while order_status != 'TRADED' and retrial_cnt > 0:
            #                     print("Buy Hedge Trade Was not cancelled. Retrying %s" %(21-retrial_cnt))
            #                     response = self.dhan.place_order(security_id=security_id,
            #                         exchange_segment=dhan.NSE_FNO,
            #                         transaction_type=dhan.SELL,
            #                         quantity=buy_trade.quantity,
            #                         order_type=dhan.MARKET,
            #                         product_type=dhan.MARGIN,
            #                         price=0,
            #                         validity='DAY')
            #                     if isinstance(response['data'], dict):
            #                         order_id = response['data']['orderId']
            #                     else:
            #                         order_id = response['data'][0]['orderId']
            #                     time.sleep(5)
            #                     order = dhan.get_order_by_id(order_id)
            #                     if isinstance(order['data'], dict):
            #                         order_status = order['data']['orderStatus']
            #                     else:
            #                         order_status = order['data'][0]['orderStatus']
            #                     # hedge_trade.quantity = (actual_lots_based_on_fund - 1 - (actual_lots_based_on_fund - retrial_cnt)) * lot_size
            #                     retrial_cnt -= 1
            #                 buy_trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                 buy_trade.save()

            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("Dhan Hedge Buy Cancellation failed: {}".format(str(e)))

            #     # Wait for 10 second after cancellation of trades for fresh entry
            #     time.sleep(5)

            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_HEDGE')
            #         & Q(order_status='NOT_PLACED_DHAN'))
            #     # print(json.dumps(existing_trades))
            #     for trade in existing_trades:
            #         try:
            #             expiry = trade.expiry
            #             trade_name = trade.index_name.replace(' ', '')
            #             if expiry == 'latest':
            #                 if trade_name == 'NIFTY':
            #                     expiry = nifty_nearest_expiry
            #                 elif trade_name == 'BANKNIFTY':
            #                     expiry = bank_nifty_nearest_expiry
            #                 elif trade_name == 'FINNIFTY':
            #                     expiry = finnifty_nearest_expiry
                            
            #             # trading_symbol = self.generate_token(expiry, trade.index_strike_price,
            #             #                                      trade.option_type)
            #             # BANKNIFTY 28 SEP 47600 CALL
            #             option_type = 'CALL' if trade.option_type == 'CE' else 'PUT'
            #             trading_symbol = "%s %s %s %s" % (
            #                 trade.index_name.replace(' ', ''),
            #                 expiry, trade.index_strike_price, option_type)
            #             security_id = nifty_50_security_id
            #             print(trading_symbol)
            #             if trade_name == 'NIFTY':
            #                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #             elif trade_name == 'BANKNIFTY':
            #                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #             elif trade_name == 'FINNIFTY':
            #                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #             # if inst_token not in instrument_subscription_list:
            #             #     # raise ValueError("Instrument Token not subscribed!")
            #             #     raise ValueError("Unexpected Instrument Token")
            #             if security_id is None:
            #                 self.logger.error("security_id not found for trade id: %s" % (trade.id))
            #                 continue
                        
            #             if security_id not in security_id_to_trading_symbol_map:
            #                 continue

            #             if trade.order_status == 'NOT_PLACED_DHAN':
            #                 trading_symbol = security_id_to_trading_symbol_map.get(security_id, None)
            #                 if trading_symbol is None:
            #                     continue
            #                 # tick_last_price = tick_map[security_id]['last_price']
            #                 # Search for last 4 set of trades or set of 2 hedge trades
            #                 metadata = trade.get_metadata_as_dict()
            #                 message_id = metadata['message_id']
            #                 existing_trades = TelegramTrade.objects.filter(
            #                     Q(created_at_time__gte=start_of_today)
            #                     & Q(order_status='NOT_PLACED_DHAN')
            #                     & Q(metadata__icontains=message_id)).order_by('-id')
            #                 temp_cnt = 0
            #                 temp_buy_cnt = 0
            #                 temp_sell_cnt = 0
            #                 hedge_trade_set_cnt = 0
            #                 for hedge_trade in existing_trades:
            #                     temp_cnt += 1
            #                     metadata = hedge_trade.get_metadata_as_dict()
            #                     if metadata['action_type'] == "SELL":
            #                         temp_sell_cnt += 1
            #                     if metadata['action_type'] == "BUY":
            #                         temp_buy_cnt += 1
            #                     if temp_cnt == 2 and temp_buy_cnt == 1 and temp_sell_cnt == 1:
            #                         hedge_trade_set_cnt = 2
            #                     if temp_cnt == 4 and temp_buy_cnt == 2 and temp_sell_cnt == 2:
            #                         hedge_trade_set_cnt = 4
            #                     if temp_cnt == 4:
            #                         break
                            
            #                 if hedge_trade_set_cnt > 0:
            #                     fund = self.dhan.get_fund_limits()['data']['availabelBalance']
            #                     temp_cnt = 0
            #                     for hedge_trade in existing_trades:
            #                         temp_cnt += 1
            #                         # Place Buy Order first for hedging
            #                         metadata = hedge_trade.get_metadata_as_dict()
            #                         if metadata['action_type'] == 'BUY':
            #                             option_type = 'CALL' if hedge_trade.option_type == 'CE' else 'PUT'
            #                             trading_symbol = "%s %s %s %s" % (
            #                                 hedge_trade.index_name.replace(' ', ''),
            #                                 expiry, hedge_trade.index_strike_price, option_type)
            #                             security_id = None
            #                             lot_size = 15
            #                             if trade_name == 'NIFTY':
            #                                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                                 lot_size = 50
            #                             elif trade_name == 'BANKNIFTY':
            #                                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                             elif trade_name == 'FINNIFTY':
            #                                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                                 lot_size = 25
            #                             expected_lots = hedge_trade.quantity / lot_size
            #                             actual_lots_based_on_fund = int(expected_lots * fund / 1000000)
            #                             response = self.dhan.place_order(security_id=security_id,
            #                                 exchange_segment=dhan.NSE_FNO,
            #                                 transaction_type=dhan.BUY,
            #                                 quantity=actual_lots_based_on_fund * lot_size,
            #                                 order_type=dhan.MARKET,
            #                                 product_type=dhan.MARGIN,
            #                                 price=0,
            #                                 validity='DAY')
            #                             time.sleep(10)
            #                             print(response)
            #                             if isinstance(response['data'], dict):
            #                                 hedge_trade.order_id = response['data']['orderId']
            #                             else:
            #                                 hedge_trade.order_id = response['data'][0]['orderId']
            #                             hedge_trade.quantity = actual_lots_based_on_fund * lot_size
            #                             hedge_trade.order_status = 'ORDER_PLACED_DHAN'
            #                             hedge_trade.save()
            #                         if temp_cnt == hedge_trade_set_cnt:
            #                             break

            #                     temp_cnt = 0

            #                     for hedge_trade in existing_trades:
            #                         temp_cnt += 1
            #                         # Place Buy Order first for hedging
            #                         metadata = hedge_trade.get_metadata_as_dict()
            #                         if metadata['action_type'] == 'SELL':
            #                             option_type = 'CALL' if hedge_trade.option_type == 'CE' else 'PUT'
            #                             trading_symbol = "%s %s %s %s" % (
            #                                 hedge_trade.index_name.replace(' ', ''),
            #                                 expiry, hedge_trade.index_strike_price, option_type)
            #                             security_id = None
            #                             lot_size = 15
            #                             if trade_name == 'NIFTY':
            #                                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                                 lot_size = 50
            #                             elif trade_name == 'BANKNIFTY':
            #                                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                             elif trade_name == 'FINNIFTY':
            #                                 security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                                 lot_size = 25
            #                             expected_lots = hedge_trade.quantity / lot_size
            #                             actual_lots_based_on_fund = int(expected_lots * fund / 1000000)
            #                             response = self.dhan.place_order(security_id=security_id,
            #                                 exchange_segment=dhan.NSE_FNO,
            #                                 transaction_type=dhan.SELL,
            #                                 quantity=actual_lots_based_on_fund * lot_size,
            #                                 order_type=dhan.MARKET,
            #                                 product_type=dhan.MARGIN,
            #                                 price=0,
            #                                 validity='DAY')
            #                             hedge_trade.quantity = actual_lots_based_on_fund * lot_size
            #                             retrial_cnt = actual_lots_based_on_fund

            #                             while response['status'] != 'success' and retrial_cnt > 0:
            #                                 response = self.dhan.place_order(security_id=security_id,
            #                                     exchange_segment=dhan.NSE_FNO,
            #                                     transaction_type=dhan.SELL,
            #                                     quantity=(actual_lots_based_on_fund - 1 - (actual_lots_based_on_fund - retrial_cnt)) * lot_size,
            #                                     order_type=dhan.MARKET,
            #                                     product_type=dhan.MARGIN,
            #                                     price=0,
            #                                     validity='DAY')
            #                                 hedge_trade.quantity = (actual_lots_based_on_fund - 1 - (actual_lots_based_on_fund - retrial_cnt)) * lot_size
            #                                 retrial_cnt -= 1
                                        
            #                             if isinstance(response['data'], dict):
            #                                 hedge_trade.order_id = response['data']['orderId']
            #                             else:
            #                                 hedge_trade.order_id = response['data'][0]['orderId']
            #                             time.sleep(5)
            #                             order = dhan.get_order_by_id(hedge_trade.order_id)
            #                             if isinstance(order['data'], dict):
            #                                 order_status = order['data']['orderStatus']
            #                             else:
            #                                 order_status = order['data'][0]['orderStatus']
            #                             retrial_cnt = actual_lots_based_on_fund
            #                             while order_status != 'TRADED' and retrial_cnt > 0:
            #                                 response = self.dhan.place_order(security_id=security_id,
            #                                     exchange_segment=dhan.NSE_FNO,
            #                                     transaction_type=dhan.SELL,
            #                                     quantity=(actual_lots_based_on_fund - 1 - (actual_lots_based_on_fund - retrial_cnt)) * lot_size,
            #                                     order_type=dhan.MARKET,
            #                                     product_type=dhan.MARGIN,
            #                                     price=0,
            #                                     validity='DAY')
            #                                 if isinstance(response['data'], dict):
            #                                     hedge_trade.order_id = response['data']['orderId']
            #                                 else:
            #                                     hedge_trade.order_id = response['data'][0]['orderId']
            #                                 time.sleep(5)
            #                                 order = dhan.get_order_by_id(hedge_trade.order_id)
            #                                 if isinstance(order['data'], dict):
            #                                     order_status = order['data']['orderStatus']
            #                                 else:
            #                                     order_status = order['data'][0]['orderStatus']
            #                                 hedge_trade.quantity = (actual_lots_based_on_fund - 1 - (actual_lots_based_on_fund - retrial_cnt)) * lot_size
            #                                 retrial_cnt -= 1
            #                             hedge_trade.order_status = 'ORDER_PLACED_DHAN'
            #                             hedge_trade.save()
            #                         if temp_cnt == hedge_trade_set_cnt:
            #                             break
            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("Order placement failed: {}".format(str(e)))
            #             # Rollback - Need to cancel all orders in case of any exception

            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(entry_type='DHAN_HEDGE')
            #         & Q(order_status='ORDER_PLACED_DHAN'))

            #     for trade in existing_trades:
            #         try:
            #             expiry = trade.expiry
            #             trade_name = trade.index_name.replace(' ', '')
            #             if expiry == 'latest':
            #                 if trade_name == 'NIFTY':
            #                     expiry = nifty_nearest_expiry
            #                 elif trade_name == 'BANKNIFTY':
            #                     expiry = bank_nifty_nearest_expiry
            #                 elif trade_name == 'FINNIFTY':
            #                     expiry = finnifty_nearest_expiry
            #             metadata = trade.get_metadata_as_dict()
            #             action_type = metadata['action_type']
            #             if 'stop_loss' in metadata and action_type == 'SELL':
            #                 stop_loss_order_id = ''
            #                 try:
            #                     stop_loss = metadata['stop_loss']
            #                     option_type = 'CALL' if trade.option_type == 'CE' else 'PUT'
            #                     trading_symbol = "%s %s %s %s" % (
            #                         trade.index_name.replace(' ', ''),
            #                         expiry, trade.index_strike_price, option_type)
            #                     security_id = None
            #                     lot_size = 15
            #                     if trade_name == 'NIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                         lot_size = 50
            #                     elif trade_name == 'BANKNIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                     elif trade_name == 'FINNIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                         lot_size = 25
            #                     exit_action_type = dhan.SELL if action_type == 'BUY' else dhan.BUY
            #                     response = self.dhan.place_order(security_id=security_id,
            #                         exchange_segment=dhan.NSE_FNO,
            #                         transaction_type=dhan.BUY,
            #                         quantity=trade.quantity,
            #                         order_type=dhan.SL,
            #                         product_type=dhan.MARGIN,
            #                         trigger_price=stop_loss,
            #                         price=round(min((stop_loss+1), stop_loss * 1.2), 1),
            #                         validity='DAY')
            #                     print(response)
            #                     if isinstance(response['data'], dict):
            #                         stop_loss_order_id = response['data']['orderId']
            #                     else:
            #                         stop_loss_order_id = response['data'][0]['orderId']
                                
            #                 except Exception as e:
            #                     traceback.print_exc()
            #                 metadata['stop_loss_order_id'] = stop_loss_order_id
            #                 trade.set_metadata_from_dict(metadata)
            #                 trade.order_status = 'SL_TARGET_ORDER_PLACED_DHAN'
            #                 trade.save()

            #             if 'targets' in metadata and action_type == 'SELL':
            #                 target_order_id = ''
            #                 try:
            #                     second_target = metadata['targets'][1]
            #                     option_type = 'CALL' if trade.option_type == 'CE' else 'PUT'
            #                     trading_symbol = "%s %s %s %s" % (
            #                         trade.index_name.replace(' ', ''),
            #                         expiry, trade.index_strike_price, option_type)
            #                     security_id = None
            #                     lot_size = 15
            #                     if trade_name == 'NIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                         lot_size = 50
            #                     elif trade_name == 'BANKNIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                     elif trade_name == 'FINNIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                         lot_size = 25
            #                     exit_action_type = dhan.SELL if action_type == 'BUY' else dhan.BUY
            #                     response = self.dhan.place_order(security_id=security_id,
            #                         exchange_segment=dhan.NSE_FNO,
            #                         transaction_type=dhan.BUY,
            #                         quantity=trade.quantity,
            #                         order_type=dhan.LIMIT,
            #                         product_type=dhan.MARGIN,
            #                         price=second_target,
            #                         validity='DAY')
            #                     if isinstance(response['data'], dict):
            #                         target_order_id = response['data']['orderId']
            #                     else:
            #                         target_order_id = response['data'][0]['orderId']
            #                 except Exception as e:
            #                     traceback.print_exc()
            #                 metadata['target_order_id'] = target_order_id
            #                 trade.set_metadata_from_dict(metadata)
            #                 trade.order_status = 'SL_TARGET_ORDER_PLACED_DHAN'
            #                 trade.save()


            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("SL/Target Update failed: {}".format(str(e)))
                
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(entry_type='DHAN_HEDGE')
            #         & Q(order_status='SL_TARGET_ORDER_PLACED_DHAN'))
                
            #     for trade in existing_trades:
            #         try:
            #             metadata = trade.get_metadata_as_dict()
            #             stop_loss_order_id = metadata['stop_loss_order_id']
            #             sl_order = dhan.get_order_by_id(stop_loss_order_id)
            #             # print(sl_order)
            #             if isinstance(sl_order['data'], dict):
            #                 sl_order_status = sl_order['data']['orderStatus']
            #             else:
            #                 sl_order_status = sl_order['data'][0]['orderStatus']

            #             target_order_status = ''
            #             if 'target_order_id' in metadata:
            #                 target_order_id = metadata['target_order_id']
            #                 target_order = dhan.get_order_by_id(target_order_id)
            #                 if isinstance(target_order['data'], dict):
            #                     target_order_status = target_order['data']['orderStatus']
            #                 else:
            #                     target_order_status = target_order['data'][0]['orderStatus']

            #             if sl_order_status == 'TRADED' and 'target_order_id' in metadata:
            #                 dhan.cancel_order(target_order_id)
                        
            #             if target_order_status == 'TRADED':
            #                 dhan.cancel_order(stop_loss_order_id)

            #             if sl_order_status == 'TRADED' or target_order_status == 'TRADED':
            #                 trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                 trade.save()
            #                 option_type = 'CALL' if trade.option_type == 'CE' else 'PUT'

            #                 buy_trade = TelegramTrade.objects.filter(
            #                     Q(entry_type='DHAN_HEDGE')
            #                     & Q(order_status='ORDER_PLACED_DHAN')
            #                     & Q(option_type=trade.option_type)
            #                     & Q(metadata__icontains='BUY')).order_by('-id').first()
                            
            #                 if buy_trade is not None:
            #                     expiry = buy_trade.expiry
            #                     option_type = 'CALL' if buy_trade.option_type == 'CE' else 'PUT'
            #                     trading_symbol = "%s %s %s %s" % (
            #                         buy_trade.index_name.replace(' ', ''),
            #                         expiry, buy_trade.index_strike_price, option_type)
            #                     security_id = None
            #                     if trade_name == 'NIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                     elif trade_name == 'BANKNIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                     elif trade_name == 'FINNIFTY':
            #                         security_id = trading_symbol_to_security_id_map.get(trading_symbol, None)
            #                     response = self.dhan.place_order(security_id=security_id,
            #                         exchange_segment=dhan.NSE_FNO,
            #                         transaction_type=dhan.SELL,
            #                         quantity=buy_trade.quantity,
            #                         order_type=dhan.MARKET,
            #                         product_type=dhan.MARGIN,
            #                         price=0,
            #                         validity='DAY')
            #                     buy_trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                     buy_trade.save()

            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("SL/Target Check Status failed: {}".format(str(e)))

            
            # if timestamp.hour == 14 and timestamp.minute >= 14 and timestamp.minute <= 30 and timestamp.second == 59:
            #     print("inside DHAN_EXPIRY_HEDGE_BUY Order Placement Sections")
            #     day = timestamp.day
            #     month = calendar.month_name[timestamp.month].upper()[:3]
            #     expiry_day = int(bank_nifty_nearest_expiry.split(' ')[0])
            #     expiry_month = bank_nifty_nearest_expiry.split(' ')[1]
            #     is_today_expiry = (day == expiry_day and month == expiry_month)
            #     # is_today_expiry = True
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(entry_type='DHAN_HEDGE')
            #         & (Q(order_status='ORDER_PLACED_DHAN') | Q(order_status='SL_TARGET_ORDER_PLACED_DHAN')))
            #     existing_scalper_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_EXPIRY_HEDGE_BUY'))
            #     if not existing_scalper_trades and is_today_expiry:
            #         for trade in existing_trades:
            #             metadata = trade.get_metadata_as_dict()
            #             if 'updated_order_status' not in metadata or metadata['updated_order_status'] != 'CANCELLED_WAITING_EXPIRY':
            #                 metadata['updated_order_status'] = 'CANCELLED_WAITING_EXPIRY'
            #                 trade.set_metadata_from_dict(metadata)
            #                 trade.created_at_time = timestamp
            #                 trade.save()
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_EXPIRY_HEDGE_BUY'))

            #     existing_hedge_trades = TelegramTrade.objects.filter(
            #         Q(entry_type='DHAN_HEDGE')
            #         & (Q(order_status='ORDER_PLACED_DHAN') | Q(order_status='SL_TARGET_ORDER_PLACED_DHAN')))
            #     if is_today_expiry and not existing_trades and not existing_hedge_trades:
            #         try:
            #             banknifty_data = dhan.intraday_minute_data(bank_nifty_security_id, exchange_segment='IDX_I', instrument_type='INDEX')
            #             low = banknifty_data['data']['low'][0]
            #             high = banknifty_data['data']['high'][0]
            #             close = banknifty_data['data']['close'][-1]
            #             for curr_low in banknifty_data['data']['low']:
            #                 low = min(low, curr_low)
            #             for curr_high in banknifty_data['data']['high']:
            #                 high = max(high, curr_high)
            #             if (high - low) >= high / 100:
            #                 mid_price = (high + low) / 2
            #                 strike_price = int((mid_price + 50)/ 100) * 100

            #                 possible_strike_price_list = [strike_price]

            #                 for temp in range(5):
            #                     possible_strike_price_list.append((strike_price + (100 * (temp+1))))
            #                     possible_strike_price_list.append((strike_price - (100 * (temp+1))))

            #                 expiry = bank_nifty_nearest_expiry
            #                 min_price_diff = 10000
            #                 min_price_diff2 = 10000
            #                 best_strike_price = strike_price
            #                 best_strike_price2 = strike_price
                            
            #                 for sp in possible_strike_price_list:
            #                     option_type = 'PUT'
            #                     put_trading_symbol = "%s %s %s %s" % (
            #                         'BANKNIFTY',
            #                         expiry, sp, option_type)
            #                     put_security_id = trading_symbol_to_security_id_map.get(put_trading_symbol, None)

            #                     call_option_type = 'CALL'
            #                     call_trading_symbol = "%s %s %s %s" % (
            #                         'BANKNIFTY',
            #                         expiry, sp, call_option_type)
            #                     call_security_id = trading_symbol_to_security_id_map.get(call_trading_symbol, None)

            #                     if call_security_id is None or put_security_id is None:
            #                         continue

            #                     call_tick_data = tick_map.get(str(call_security_id), {})
            #                     put_tick_data = tick_map.get(str(put_security_id), {})

            #                     if 'LTP' in call_tick_data and 'LTP' in put_tick_data:
            #                         call_ltp = float(call_tick_data['LTP'])

            #                         ltt = call_tick_data['LTT']
            #                         today_date = datetime.now(IST).date()
            #                         time_obj = datetime.strptime(ltt, "%H:%M:%S").time()
            #                         combined_datetime = datetime.combine(today_date, time_obj)

            #                         now = datetime.now(IST)
            #                         now = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
            #                         time_diff = now - combined_datetime
            #                         diff_in_seconds = abs(time_diff.total_seconds())

            #                         if diff_in_seconds >= 10:
            #                             min_data = dhan.intraday_minute_data(call_security_id, exchange_segment='NSE_FNO',
            #                                 instrument_type='OPTIDX')
            #                             call_ltp = min_data['data']['close'][-1]

                                    
            #                         put_ltp = float(put_tick_data['LTP'])

            #                         ltt = put_tick_data['LTT']
            #                         today_date = datetime.now(IST).date()
            #                         time_obj = datetime.strptime(ltt, "%H:%M:%S").time()
            #                         combined_datetime = datetime.combine(today_date, time_obj)

            #                         time_diff = get_ist_datetime(datetime.now()) - combined_datetime
            #                         diff_in_seconds = abs(time_diff.total_seconds())

            #                         if diff_in_seconds >= 10:
            #                             min_data = dhan.intraday_minute_data(put_security_id, exchange_segment='NSE_FNO',
            #                                 instrument_type='OPTIDX')
            #                             put_ltp = min_data['data']['close'][-1]

            #                         if (call_ltp <= 150 and put_ltp <= 150):
            #                             if call_ltp + put_ltp < min_price_diff:
            #                                 min_price_diff = call_ltp + put_ltp
            #                                 best_strike_price = sp
            #                         elif ((call_ltp < 150 and put_ltp > 150) or (call_ltp > 150 and put_ltp < 150)):
            #                             if abs(call_ltp - 150) + abs(put_ltp - 150) < min_price_diff2:
            #                                 min_price_diff2 = abs(call_ltp - 150) + abs(put_ltp - 150)
            #                                 best_strike_price2 = sp

            #                 if best_strike_price != strike_price:
            #                     strike_price = best_strike_price
            #                 else:
            #                     strike_price = best_strike_price2

            #                 expiry = bank_nifty_nearest_expiry

            #                 option_type = 'PUT'
            #                 put_trading_symbol = "%s %s %s %s" % (
            #                     'BANKNIFTY',
            #                     expiry, strike_price, option_type)
            #                 put_security_id = trading_symbol_to_security_id_map.get(put_trading_symbol, None)

            #                 call_option_type = 'CALL'
            #                 call_trading_symbol = "%s %s %s %s" % (
            #                     'BANKNIFTY',
            #                     expiry, strike_price, call_option_type)
            #                 call_security_id = trading_symbol_to_security_id_map.get(call_trading_symbol, None)

            #                 call_premium_data = dhan.intraday_minute_data(call_security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
            #                 last_min_premium_close_price_call = call_premium_data['data']['close'][-1]

            #                 put_premium_data = dhan.intraday_minute_data(put_security_id, exchange_segment=dhan.FNO, instrument_type='OPTIDX')
            #                 last_min_premium_close_price_put = put_premium_data['data']['close'][-1]

            #                 fund = self.dhan.get_fund_limits()['data']['availabelBalance']
            #                 fund = 20000 if fund >= 20000 else fund

            #                 call_fund = fund / 2
            #                 put_fund = fund / 2


            #                 call_quantity = (int(int(call_fund / last_min_premium_close_price_call) / 15) * 15)
            #                 put_quantity = (int(int(put_fund / last_min_premium_close_price_put) / 15) * 15)

            #                 call_response = self.dhan.place_slice_order(security_id=call_security_id,
            #                     exchange_segment=dhan.NSE_FNO,
            #                     transaction_type=dhan.BUY,
            #                     quantity=call_quantity,
            #                     order_type=dhan.MARKET,
            #                     product_type=dhan.MARGIN,
            #                     price=0,
            #                     validity='DAY')
            #                 order_id_list = [data['orderId'] for data in call_response['data']]
            #                 telegram_trade = TelegramTrade()
            #                 telegram_trade.index_name = 'BANKNIFTY'
            #                 telegram_trade.index_strike_price = strike_price
            #                 telegram_trade.option_type = 'CE'
            #                 telegram_trade.expiry = bank_nifty_nearest_expiry
            #                 telegram_trade.entry_start_price = last_min_premium_close_price_call
            #                 telegram_trade.exit_first_target_price = round(last_min_premium_close_price_call * 1.25, 1)
            #                 telegram_trade.exit_second_target_price = round(last_min_premium_close_price_call * 1.75, 1)
            #                 telegram_trade.exit_third_target_price = round(last_min_premium_close_price_call * 2.75, 1)
            #                 telegram_trade.exit_stop_loss_price = round(last_min_premium_close_price_call * 0.5, 1)
            #                 telegram_trade.created_at_time = timestamp
            #                 telegram_trade.order_status = 'ORDER_PLACED_DHAN_EXPIRY'
            #                 telegram_trade.quantity = call_quantity
            #                 metadata = {'strategy': 'DHAN_EXPIRY_HEDGE_BUY', 'action_type': 'BUY',
            #                 'targets': [last_min_premium_close_price_call,
            #                             last_min_premium_close_price_call * 1.25,
            #                             last_min_premium_close_price_call * 1.75,
            #                             last_min_premium_close_price_call * 2.75,
            #                             last_min_premium_close_price_call * 3.5]}
            #                 metadata['order_id_list'] = order_id_list
            #                 metadata['security_id'] = call_security_id
            #                 metadata['next_target_price'] = round(last_min_premium_close_price_call * 1.25, 1)
            #                 metadata['trailing_price'] = round(last_min_premium_close_price_call * 0.5, 1)
            #                 telegram_trade.set_metadata_from_dict(metadata)
            #                 telegram_trade.entry_type = 'DHAN_EXPIRY_HEDGE_BUY'

            #                 time.sleep(5)

            #                 sl_response = self.dhan.place_slice_order(security_id=call_security_id,
            #                     exchange_segment=dhan.NSE_FNO,
            #                     transaction_type=dhan.SELL,
            #                     quantity=call_quantity,
            #                     order_type=dhan.SL,
            #                     product_type=dhan.MARGIN,
            #                     trigger_price=telegram_trade.exit_stop_loss_price,
            #                     price=round(telegram_trade.exit_stop_loss_price * 0.99, 1),
            #                     validity='DAY')
            #                 sl_order_id_list = [data['orderId'] for data in sl_response['data']]
            #                 metadata['sl_order_id_list'] = sl_order_id_list
            #                 telegram_trade.set_metadata_from_dict(metadata)

            #                 telegram_trade.save()

            #                 put_response = self.dhan.place_slice_order(security_id=put_security_id,
            #                     exchange_segment=dhan.NSE_FNO,
            #                     transaction_type=dhan.BUY,
            #                     quantity=put_quantity,
            #                     order_type=dhan.MARKET,
            #                     product_type=dhan.MARGIN,
            #                     price=0,
            #                     validity='DAY')
            #                 order_id_list = [data['orderId'] for data in put_response['data']]
            #                 telegram_trade = TelegramTrade()
            #                 telegram_trade.index_name = 'BANKNIFTY'
            #                 telegram_trade.index_strike_price = strike_price
            #                 telegram_trade.option_type = 'PE'
            #                 telegram_trade.expiry = bank_nifty_nearest_expiry
            #                 telegram_trade.entry_start_price = last_min_premium_close_price_put
            #                 telegram_trade.exit_first_target_price = round(last_min_premium_close_price_put * 1.25, 1)
            #                 telegram_trade.exit_second_target_price = round(last_min_premium_close_price_put * 1.75, 1)
            #                 telegram_trade.exit_third_target_price = round(last_min_premium_close_price_put * 2.75, 1)
            #                 telegram_trade.exit_stop_loss_price = round(last_min_premium_close_price_put * 0.5, 1)
            #                 telegram_trade.created_at_time = timestamp
            #                 telegram_trade.order_status = 'ORDER_PLACED_DHAN_EXPIRY'
            #                 telegram_trade.quantity = put_quantity
            #                 metadata = {'strategy': 'DHAN_EXPIRY_HEDGE_BUY', 'action_type': 'BUY',
            #                 'targets': [last_min_premium_close_price_put,
            #                             last_min_premium_close_price_put * 1.25,
            #                             last_min_premium_close_price_put * 1.75,
            #                             last_min_premium_close_price_put * 2.75,
            #                             last_min_premium_close_price_put * 3.5]}
            #                 metadata['order_id_list'] = order_id_list
            #                 metadata['security_id'] = put_security_id
            #                 metadata['next_target_price'] = round(last_min_premium_close_price_put * 1.25, 1)
            #                 metadata['trailing_price'] = round(last_min_premium_close_price_put * 0.5, 1)
            #                 telegram_trade.set_metadata_from_dict(metadata)
            #                 telegram_trade.entry_type = 'DHAN_EXPIRY_HEDGE_BUY'

            #                 time.sleep(5)

            #                 sl_response = self.dhan.place_slice_order(security_id=put_security_id,
            #                     exchange_segment=dhan.NSE_FNO,
            #                     transaction_type=dhan.SELL,
            #                     quantity=put_quantity,
            #                     order_type=dhan.SL,
            #                     product_type=dhan.MARGIN,
            #                     trigger_price=telegram_trade.exit_stop_loss_price,
            #                     price=round(telegram_trade.exit_stop_loss_price * 0.99, 1),
            #                     validity='DAY')
            #                 sl_order_id_list = [data['orderId'] for data in sl_response['data']]
            #                 metadata['sl_order_id_list'] = sl_order_id_list

            #                 telegram_trade.set_metadata_from_dict(metadata)

            #                 telegram_trade.save()
            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("DHAN_EXPIRY_HEDGE_BUY Order Placement failed: {}".format(str(e)))


            # if timestamp.second >= 0:
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_EXPIRY_HEDGE_BUY')
            #         & Q(order_status='ORDER_PLACED_DHAN_EXPIRY'))
            #     for trade in existing_trades:
            #         try:
            #             metadata = trade.get_metadata_as_dict()
            #             entry_price = trade.entry_start_price
            #             next_target_price = metadata['next_target_price']
            #             trailing_price = metadata['trailing_price']
            #             security_id = metadata['security_id']
            #             curr_tick_data = tick_map.get(str(security_id), {})
            #             if 'LTP' in curr_tick_data:
            #                 ltp = float(curr_tick_data['LTP'])

            #                 ltt = curr_tick_data['LTT']
            #                 today_date = datetime.now(IST).date()
            #                 time_obj = datetime.strptime(ltt, "%H:%M:%S").time()
            #                 combined_datetime = datetime.combine(today_date, time_obj)

            #                 now = datetime.now(IST)
            #                 now = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
            #                 time_diff = now - combined_datetime
            #                 diff_in_seconds = abs(time_diff.total_seconds())

            #                 if diff_in_seconds >= 10:
            #                     min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
            #                         instrument_type='OPTIDX')
            #                     ltp = min_data['data']['close'][-1]
            #             else:
            #                 temp_min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
            #                     instrument_type='OPTIDX')
            #                 ltp = temp_min_data['data']['close'][-1]
            #             print("ltp:")
            #             print(ltp)
            #             if ltp >= next_target_price:
            #                 sl_order_id_list = metadata['sl_order_id_list']
            #                 for order_id in sl_order_id_list:
            #                     sl_order = dhan.get_order_by_id(order_id)
            #                     sl_order_data = sl_order['data']
            #                     if isinstance(sl_order['data'], dict):
            #                         sl_order_data = sl_order['data']
            #                     else:
            #                         sl_order_data = sl_order['data'][0]
                                
            #                     if trailing_price == round(entry_price * 0.9, 1):
            #                         dhan.modify_order(order_id=order_id,
            #                             order_type=sl_order_data['orderType'],
            #                             leg_name="",
            #                             quantity=sl_order_data["quantity"],
            #                             price=round(trailing_price * 0.99, 1),
            #                             trigger_price=trailing_price,
            #                             disclosed_quantity=sl_order_data["disclosedQuantity"],
            #                             validity=sl_order_data["validity"])
            #                 metadata['close_count_below_trailing_price'] = 0
            #                 trade.set_metadata_from_dict(metadata)
            #                 trade.save()

            #             if timestamp.second == 59:
            #                 close_count_below_trailing_price = metadata.get('close_count_below_trailing_price', 0)
            #                 if ltp < trailing_price:
            #                     close_count_below_trailing_price += 1
            #                     print("close_count_below_trailing_price: %s" % close_count_below_trailing_price)
            #                 if metadata.get('close_count_below_trailing_price', 0) != close_count_below_trailing_price:
            #                     metadata['close_count_below_trailing_price'] = close_count_below_trailing_price
            #                     if close_count_below_trailing_price >= 2:
            #                         metadata['updated_order_status'] = 'CANCELLED'
            #                     trade.set_metadata_from_dict(metadata)
            #                     trade.save()

            #                 min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
            #                     instrument_type='OPTIDX')
            #                 created_at_time = get_ist_datetime(trade.created_at_time)
            #                 # print("created_at_time")
            #                 # print(created_at_time)
            #                 created_at_time = datetime(created_at_time.year, created_at_time.month, created_at_time.day, created_at_time.hour, created_at_time.minute + 1)
            #                 if 'start_Time' in min_data['data']:
            #                     data_length = len(min_data['data']['start_Time'])
            #                     close_count_below_trailing_price = 0
            #                     for i in range(data_length):
            #                         min_data['data']['start_Time'][i] = dhan.convert_to_date_time(min_data['data']['start_Time'][i])
            #                         if min_data['data']['start_Time'][i] >= created_at_time:
            #                             close = min_data['data']['close'][i]
            #                             if close < trailing_price:
            #                                 close_count_below_trailing_price += 1
            #                                 print("close_count_below_trailing_price based on min data: %s" % close_count_below_trailing_price)

            #                     if close_count_below_trailing_price >= 2:
            #                         metadata['close_count_below_trailing_price'] = close_count_below_trailing_price
            #                         metadata['updated_order_status'] = 'CANCELLED'
            #                         trade.set_metadata_from_dict(metadata)
            #                         trade.save()


            #             if ltp >= round(entry_price * 3.5, 1):
            #                 next_target_price = round(entry_price * ((ltp / entry_price) + 1), 1)
            #                 trailing_price = round(next_target_price / 2, 1)
            #             elif ltp >= round(entry_price * 3.25, 1):
            #                 next_target_price = round(entry_price * 3.5, 1)
            #                 trailing_price = round(entry_price * 2.25, 1)
            #             elif ltp >= round(entry_price * 3, 1):
            #                 next_target_price = round(entry_price * 3.25, 1)
            #                 trailing_price = round(entry_price * 2, 1)
            #             elif ltp >= round(entry_price * 2.75, 1):
            #                 next_target_price = round(entry_price * 3.5, 1)
            #                 trailing_price = round(entry_price * 1.75, 1)
            #             elif ltp >= round(entry_price * 2.5, 1):
            #                 next_target_price = round(entry_price * 2.75, 1)
            #                 trailing_price = round(entry_price * 1.5, 1)
            #             elif ltp >= round(entry_price * 1.75, 1):
            #                 next_target_price = round(entry_price * 2.5, 1)
            #                 trailing_price = round(entry_price * 1.25, 1)
            #             elif ltp >= round(entry_price * 1.25, 1):
            #                 next_target_price = round(entry_price * 1.75, 1)
            #                 trailing_price = round(entry_price * 0.9, 1)
                        
            #             if next_target_price != metadata.get('next_target_price', 0) or trailing_price != metadata.get('trailing_price', 0):
            #                 metadata['next_target_price'] = next_target_price
            #                 metadata['trailing_price'] = trailing_price
            #                 trade.set_metadata_from_dict(metadata)
            #                 trade.save()
            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("DHAN_EXPIRY_HEDGE_BUY Target & Trailing Update failed: {}".format(str(e)))

            # if timestamp.second == 59:
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_EXPIRY_HEDGE_BUY')
            #         & Q(order_status='ORDER_PLACED_DHAN_EXPIRY'))
            #     for trade in existing_trades:
            #         try:
            #             metadata = trade.get_metadata_as_dict()
            #             entry_price = trade.entry_start_price
            #             next_target_price = metadata['next_target_price']
            #             trailing_price = metadata['trailing_price']
            #             security_id = metadata['security_id']
            #             if 'updated_order_status' in metadata and metadata['updated_order_status'] == 'CANCELLED':
            #                 print("inside DHAN_EXPIRY_HEDGE_BUY cancelled section")
            #                 sl_order_id_list = metadata['sl_order_id_list']
            #                 remaining_quantity = 0
            #                 for order_id in sl_order_id_list:
            #                     sl_order = dhan.get_order_by_id(order_id)
            #                     sl_order_data = sl_order['data']
            #                     if isinstance(sl_order['data'], dict):
            #                         sl_order_data = sl_order['data']
            #                     else:
            #                         sl_order_data = sl_order['data'][0]

            #                     if sl_order_data['orderStatus'] == 'PENDING' or sl_order_data['orderStatus'] == 'TRANSIT':
            #                         remaining_quantity += sl_order_data["quantity"]
            #                         dhan.cancel_order(order_id)
            #                         print("Cancelling order_id: %s" % order_id)
            #                 time.sleep(1)
            #                 if remaining_quantity > 0:
            #                     response = self.dhan.place_slice_order(security_id=security_id,
            #                         exchange_segment=dhan.NSE_FNO,
            #                         transaction_type=dhan.SELL,
            #                         quantity=remaining_quantity,
            #                         order_type=dhan.MARKET,
            #                         product_type=dhan.MARGIN,
            #                         price=0,
            #                         validity='DAY')
            #                 trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                 trade.save()
            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("DHAN_EXPIRY_HEDGE_BUY Cancellation failed: {}".format(str(e)))

            # if timestamp.minute % 2 == 0 and timestamp.second == 59:
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_EXPIRY_HEDGE_BUY')
            #         & Q(order_status='ORDER_PLACED_DHAN_EXPIRY'))
            #     for trade in existing_trades:
            #         try:
            #             metadata = trade.get_metadata_as_dict()
            #             sl_order_id_list = metadata['sl_order_id_list']
            #             is_traded = True
            #             for order_id in sl_order_id_list:
            #                 sl_order = dhan.get_order_by_id(order_id)
            #                 sl_order_data = sl_order['data']
            #                 if isinstance(sl_order['data'], dict):
            #                     sl_order_data = sl_order['data']
            #                 else:
            #                     sl_order_data = sl_order['data'][0]

            #                 if sl_order_data['orderStatus'] == 'PENDING' or sl_order_data['orderStatus'] == 'TRANSIT':
            #                     is_traded = False
            #             if is_traded:
            #                 trade.order_status = 'ORDER_EXIT_EXECUTED_DHAN'
            #                 trade.save()
            #         except Exception as e:
            #             traceback.print_exc()
            #             logging.info("DHAN_EXPIRY_HEDGE_BUY Order Status Check failed: {}".format(str(e)))

            # if timestamp.second == 59:
            #     existing_scalper_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_EXPIRY_HEDGE_BUY')
            #         & Q(order_status='ORDER_PLACED_DHAN_EXPIRY'))
            #     if not existing_scalper_trades:
            #         time.sleep(2)
            #         cancelled_waiting_trades = TelegramTrade.objects.filter(
            #             Q(entry_type='DHAN_HEDGE')
            #             & ~Q(order_status='EXPIRED')
            #             & Q(metadata__icontains='CANCELLED_WAITING_EXPIRY'))

            #         for trade in cancelled_waiting_trades:
            #             trade.order_status = 'NOT_PLACED_DHAN'
            #             metadata = trade.get_metadata_as_dict()
            #             total_fund = self.dhan.get_fund_limits()['data']['sodLimit']
            #             if 'quantity' in metadata:
            #                 trade.quantity = int(((metadata['quantity'] * 1000000) / total_fund) / 15) * 15
            #             else:
            #                 trade.quantity = int(((trade.quantity * 1000000) / total_fund) / 15) * 15
            #             if 'updated_order_status' in metadata:
            #                 del metadata['updated_order_status']
            #             trade.set_metadata_from_dict(metadata)
            #             trade.save()

            if timestamp.minute % 15 == 0 and timestamp.second == 59:
                try:
                    positions = dhan.get_positions()['data']
                    funds = dhan.get_fund_limits()['data']
                    logging.info(positions)
                    logging.info(funds)
                    if timestamp.minute % 30 == 0:
                        self.gmail_queue.append({'subject': 'Dhan Positions List',
                                                 'email_content': json.dumps({'positions': positions, 'funds': funds})})
                except Exception as e:
                    traceback.print_exc()
                    self.gmail_service.send_email(
                        'Dhan failed to get positions and funds',
                        traceback.format_exc())
                    logging.info("Dhan failed to get positions and funds: {}".format(str(e)))

            if timestamp.hour == 15 and timestamp.minute % 15 == 0 and timestamp.second == 59:
                existing_scalper_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today))
                
                for trade in existing_scalper_trades:
                    self.logger.info(f"Trade: {trade.__dict__}")

                    # Access the history for this specific trade
                    history_records = trade.history.all()

                    # Log the history entries
                    for historical_record in history_records:
                        self.logger.info(f"Historical Record: {historical_record.__dict__}, Changed on: {historical_record.history_date}")

            # kill_switch = self.check_exit_criteria(IST, dhan, kill_switch, start_of_today, tick_map, timestamp)
                            

                            
            # TODO: Use minute data as a last resort to exit trades at any cost
            # if timestamp.second == 59:
            #     existing_trades = TelegramTrade.objects.filter(
            #         Q(created_at_time__gte=start_of_today)
            #         & Q(entry_type='DHAN_EXPIRY_HEDGE_BUY'))
            #     if existing_trades:
            #         for trade in existing_trades:
            #             metadata = trade.get_metadata_as_dict()
            #             next_target_price = metadata['next_target_price']
            #             trailing_price = metadata['trailing_price']
            #             security_id = metadata['security_id']

            #             sl_order_id_list = metadata['sl_order_id_list']

            #             for order_id in sl_order_id_list:
            #                 sl_order = dhan.get_order_by_id(order_id)
            #                 sl_order_data = sl_order['data']
            #                 if isinstance(sl_order['data'], dict):
            #                     sl_order_data = sl_order['data']
            #                 else:
            #                     sl_order_data = sl_order['data'][0]

            time.sleep(1)

    def check_exit_criteria(self, redis_map):
        IST = pytz.timezone('Asia/Kolkata')
        # Get today's date
        today_date = datetime.now(IST).date()
        # Create a datetime object for today at 12:01 AM
        start_of_today = datetime.combine(today_date, datetime.min.time())
        dhan = self.dhan
        kill_switch = False
        log_email_sent = False
        prev_reset_thread = None
        while True:
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
            tick_map = self.redis_map.get('dhan_tick_data')
            if timestamp.second >= 0:
                try:
                    pair_scalper_placed_trades = TelegramTrade.objects.filter(
                        Q(created_at_time__gte=start_of_today)
                        & Q(entry_type='DHAN_PAIR_SCALPER')
                        & Q(order_status='ORDER_PLACED_DHAN'))
    
                    if not pair_scalper_placed_trades:
                        logging.info("Checking net pnl worst case")
                        positions = dhan.get_positions()['data']
                        total_fund = 500000
                        net_pnl = 0
                        manual_trade = False
                        for position in positions:
                            cost_price = position['costPrice']
                            security_id = position['securityId']
                            net_quantity = position['netQty']
                            strike_price = int(position['drvStrikePrice'])
                            expiry_date = position['drvExpiryDate']
                            option_type = position['drvOptionType']
                            if net_quantity > 0:
                                try:
                                    option_type = 'CE' if option_type == 'CALL' else 'PE'
                                    if len(expiry_date) == 10:
                                        # Date is in 'YYYY-MM-DD' format
                                        datetime_obj = datetime.strptime(expiry_date, '%Y-%m-%d')
                                    else:
                                        # Date is in 'YYYY-MM-DD HH:MM:SS' format
                                        datetime_obj = datetime.strptime(expiry_date, '%Y-%m-%d %H:%M:%S')
    
                                    # Format the datetime object to '14 AUG' format
                                    formatted_date = datetime_obj.strftime('%d %b').upper()
    
                                    existing_trade = TelegramTrade.objects.filter(
                                        Q(index_strike_price=strike_price)
                                        & Q(expiry=formatted_date)
                                        & Q(option_type=option_type)
                                        & Q(quantity=net_quantity)
                                        & (~Q(order_status='EXPIRED') & ~Q(
                                            order_status='ORDER_EXIT_EXECUTED_DHAN'))).first()
    
                                    if not existing_trade:
                                        manual_trade = True
                                        logging.info("Found manual trades or unexpected trades. Closing all trades.")
                                except Exception as e:
                                    traceback.print_exc()
                                    self.gmail_service.send_email(
                                        'Failed while checking for manual trades',
                                        traceback.format_exc())
                                    logging.info("Failed while checking for manual trades: {}".format(str(e)))
    
                            curr_tick_data = tick_map.get(str(security_id), {})
                            if 'LTP' in curr_tick_data:
                                ltp = float(curr_tick_data['LTP'])
    
                                ltt = curr_tick_data['LTT']
                                today_date = datetime.now(IST).date()
                                time_obj = datetime.strptime(ltt, "%H:%M:%S").time()
                                combined_datetime = datetime.combine(today_date, time_obj)
    
                                now = datetime.now(IST)
                                now = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
                                time_diff = now - combined_datetime
                                diff_in_seconds = abs(time_diff.total_seconds())
    
                                if diff_in_seconds >= 10:
                                    min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
                                                                         instrument_type='OPTIDX')
                                    ltp = min_data['data']['close'][-1]
                            else:
                                temp_min_data = dhan.intraday_minute_data(security_id, exchange_segment='NSE_FNO',
                                                                          instrument_type='OPTIDX')
                                ltp = temp_min_data['data']['close'][-1]
                                time.sleep(1)
                            pnl = net_quantity * (ltp - cost_price)
                            net_pnl += pnl
    
                        # Reached worst case, total loss is less than 10% of total margin
                        # Exit all in worst case
                        if (net_pnl < 0 and abs(net_pnl) >= total_fund * 0.20) or manual_trade:
                            logging.info(
                                "Reached worst case! total loss is less than 10 percent of total margin or manual trade was found")
                            order_list = dhan.get_order_list()['data']
                            for order in order_list:
                                order_id = order['orderId']
                                order_status = order['orderStatus']
                                if order['orderStatus'] == 'PENDING':
                                    dhan.cancel_order(order_id)
    
                            time.sleep(2)
    
                            # Exit all sell positions first to exit hedge position
                            for position in positions:
                                security_id = position['securityId']
                                net_quantity = position['netQty']
                                product_type = position['productType']
    
                                if net_quantity < 0:
                                    self.dhan.place_slice_order(security_id=security_id,
                                                                exchange_segment=dhan.NSE_FNO,
                                                                transaction_type=dhan.BUY,
                                                                quantity=abs(net_quantity),
                                                                order_type=dhan.MARKET,
                                                                product_type=product_type,
                                                                price=0,
                                                                validity='DAY')
                                    time.sleep(1)
    
                            # Exit all buy positions
                            for position in positions:
                                security_id = position['securityId']
                                net_quantity = position['netQty']
                                product_type = position['productType']
    
                                if net_quantity > 0:
                                    self.dhan.place_slice_order(security_id=security_id,
                                                                exchange_segment=dhan.NSE_FNO,
                                                                transaction_type=dhan.SELL,
                                                                quantity=abs(net_quantity),
                                                                order_type=dhan.MARKET,
                                                                product_type=product_type,
                                                                price=0,
                                                                validity='DAY')
                                    time.sleep(1)
    
                        if manual_trade and not kill_switch:
                            logging.info("Found manual trade. Activating kill switch. Need to manually deactivate it.")
                            dhan.kill_switch(status='ACTIVATE')
                            time.sleep(5)
                            self.dhan_web_manager.activate_kill_switch()
                            kill_switch = True
                except Exception as e:
                    traceback.print_exc()
                    self.gmail_service.send_email(
                        'Dhan Position Worst Case Check failed',
                        traceback.format_exc())
                    logging.info("Dhan Position Worst Case Check failed: {}".format(str(e)))

            if timestamp.second % 5 == 0:
                try:
                    queue_len = len(self.gmail_queue)
                    if queue_len > 0:
                        email_data = self.gmail_queue[queue_len - 1]
                        self.gmail_service.send_email(email_data['subject'], email_data['email_content'])
                        self.gmail_queue.pop(queue_len - 1)
                except Exception as e:
                    traceback.print_exc()
                    logging.info("Failed while sending email from queue")

            if timestamp.second == 59:
                try:
                    self.gmail_service.transfer_aws_dhan_messages()
                except Exception as e:
                    traceback.print_exc()
                    logging.info("Failed while forwarding aws messages")

            if timestamp.second % 5 == 0:
                try:
                    if timestamp.minute % 15 == 0 and timestamp.second == 10:
                        self.dhan_web_manager.remove_all_inactive_aws_sessions(self.aws_hostname)
                    self.dhan_web_manager.remove_all_other_active_sessions(self.aws_hostname)
                except Exception as e:
                    traceback.print_exc()
                    self.gmail_service.send_email("Failed while removing inactive and unauthorised sessions",
                                                  traceback.format_exc())
                    logging.info("Failed while removing inactive and unauthorised sessions. resetting password")
                    try:
                        self.dhan_web_manager.clear_cache()
                        self.dhan_web_manager.reset_password()
                    except Exception as e:
                        traceback.print_exc()
                        self.gmail_service.send_email("Failed again while resetting password as part of removing"
                                                      " inactive and unauthorised sessions", traceback.format_exc())

            if timestamp.hour == 15 and timestamp.minute >= 15 and not log_email_sent:
                self.gmail_service.send_email_with_attachment('Celery Worker Log', 'Please check Celery Worker Log',
                                                         '/home/ec2-user/services/algo-trade/trading_django/celery_worker.log')
                log_email_sent = True

            time.sleep(1)

    def reset_dhan_password_pin(self):
        # try:
        #     self.dhan_web_manager.login()
        #     self.dhan_web_manager.reset_pin()
        #     self.dhan_web_manager.reset_password()
        # except Exception as e:
        #     try:
        #         self.dhan_web_manager.clear_cache()
        #         self.dhan_web_manager.reset_password()
        #     except Exception as e:
        #         pass
        #     traceback.print_exc()
        #     self.gmail_service.send_email(
        #         'Dhan Password/PIN Reset Failed',
        #         traceback.format_exc())
        #     logging.info("Dhan Password/PIN Reset Failed: {}".format(str(e)))
        try:
            self.dhan_web_manager.remove_all_other_active_sessions(self.aws_hostname)
        except Exception as e:
            traceback.print_exc()
            self.gmail_service.send_email('Failed while removing unauthorised session', traceback.format_exc())
