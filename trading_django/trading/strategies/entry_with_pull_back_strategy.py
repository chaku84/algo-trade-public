import logging
import bisect
import math
import time
import talib
import pandas as pd
import numpy as np
import traceback

from trading.strategies.instant_entry import InstantEntry
from trading.helpers import get_ist_datetime, get_nearest_tens, my_timedelta
from trading.models import TelegramTrade
from datetime import datetime, timedelta

from django.db.models import Q


class EntryWithPullBackStrategy(InstantEntry):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.risk = 1000
        self.exit_target_percent_list = [80, 20]
        self.fib_retracement_percent = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
        self.index_min_data = []

    def convert_date(self, date_str):
        # Parse the date string
        date_obj = datetime.strptime(date_str, '%d%b')

        # Get the last two digits of the current year
        year_suffix = str(datetime.now().year)[-2:]

        # Get the month without leading zero
        month = str(date_obj.month)

        # Get the date with leading zero if necessary
        day = str(date_obj.day).zfill(2)

        # Concatenate the components to form the desired format
        converted_date = f"{year_suffix}{month}{day}"

        return converted_date

    def historical_data(self, kite, bank_nifty_inst_token, from_date,
                                                    now, period, continuous):
        # if self.index_min_data is not None and len(self.index_min_data) > 0:
        #     start_time = self.index_min_data[0]['date']
        #     end_time = self.index_min_data[-1]['date']
        #     if start_time <= from_date and now <=end_time:
        #         updated_list = []
        #         for data in self.index_min_data:
        #             if data['date'] >= from_date and data['date'] <= now:
        #                 updated_list.append(data)
        #         if len(updated_list) > 0:
        #             return updated_list

        retrial_cnt = 10
        while retrial_cnt > 0:
            try:
                min_data = kite.historical_data(bank_nifty_inst_token, from_date,
                                                now, period, continuous)
            except Exception as e:
                traceback.print_exc()
                retrial_cnt -= 1
                if retrial_cnt == 0:
                    return None
                time.sleep(5)
                continue
            break
        return min_data

    def generate_trade_based_on_fib(self, kite, tick_map, nearest_expiry_map, now=datetime.now(), analyse=False):
        self.logger.info(now)
        fragment_sizes = {'NIFTY': [3, 9, 27], 'BANKNIFTY': [6, 18, 54]}
        nifty_inst_token = 256265
        bank_nifty_inst_token = 260105
       
        close = tick_map[260105]['last_price'] if not analyse else tick_map['260105']['last_price']

        nearest_strike_price = int(close) - (int(close) % 100)
        atm_price = -1

        if abs(nearest_strike_price - close) < abs(nearest_strike_price + 100 - close):
            atm_price = nearest_strike_price
        else:
            atm_price = nearest_strike_price + 100
        
        bank_nifty_pe_first_otm_price = atm_price - 100
        bank_nifty_ce_first_otm_price = atm_price + 100

        bank_nifty_pe_first_itm_price = atm_price + 100
        bank_nifty_ce_first_itm_price = atm_price - 100


        price_map_list_to_be_processed = [
            {'price': bank_nifty_ce_first_otm_price, 'option_type': 'CE'},
            {'price': bank_nifty_pe_first_otm_price, 'option_type': 'PE'}
        ]

        for price_map in price_map_list_to_be_processed:
            price = price_map['price']
            option_type = price_map['option_type']
            # if option_type == 'CE':
            #     continue
            # Considering BANKNIFTY 1st OTM and CE for now
            bank_nifty_nearest_expiry = nearest_expiry_map.get('BANKNIFTY')
            bank_nifty_ce_first_otm_price = price

            possible_trading_symbol1 = 'BANKNIFTY%s%s%s' % (bank_nifty_nearest_expiry, bank_nifty_ce_first_otm_price, option_type)
            possible_trading_symbol2 = 'BANKNIFTY%s%s%s' % (self.convert_date(bank_nifty_nearest_expiry), bank_nifty_ce_first_otm_price, option_type)

            bank_nifty_ce_first_otm_inst_token = -1
            for tick in tick_map.values():
                if 'trading_symbol' in tick and tick['trading_symbol'].startswith('BANKNIFTY'):
                    trading_symbol = tick['trading_symbol']
                    if trading_symbol == possible_trading_symbol1 or trading_symbol == possible_trading_symbol2:
                        # self.logger.info(trading_symbol)
                        bank_nifty_ce_first_otm_inst_token = tick['instrument_token']

            # if bank_nifty_ce_first_otm_inst_token == -1:
            #     self.logger.error("Could not find inst_token. Returning")
            #     return

            # self.logger.info("bank_nifty_{}_first_itm_inst_token: {}".format(option_type, bank_nifty_ce_first_otm_inst_token))

            # now = get_ist_datetime(datetime.now())
            from_date = my_timedelta(now, '-', timedelta(days=2))

            min_data = self.historical_data(kite, bank_nifty_inst_token, from_date,
                                                    now, "minute", False)
            max_day_diff = 14
            while min_data[0]['date'].day == now.day and max_day_diff > 0:
                from_date = my_timedelta(from_date, '-', timedelta(days=1))
                min_data = self.historical_data(kite, bank_nifty_inst_token, from_date,
                                                now, "minute", False)
                max_day_diff -= 1
            min_data_len = len(min_data)
            # self.logger.info(min_data[0])
            # self.logger.info(min_data[min_data_len-1])
            if option_type == 'PE':
                for curr_min_data in min_data:
                    prev_min_data_low = curr_min_data['low']
                    prev_min_data_high = curr_min_data['high']
                    prev_min_data_open = curr_min_data['open']
                    prev_min_data_close = curr_min_data['close']
                    curr_min_data['low'] = -prev_min_data_high
                    curr_min_data['close'] = -prev_min_data_open
                    curr_min_data['high'] = -prev_min_data_low
                    curr_min_data['open'] = -prev_min_data_close

            # Loop through different fragment sizes later
            curr_fragment_size = fragment_sizes['BANKNIFTY'][0]
            entry_allowed = False

            #    /\
            #   /  \
            # \/
            # t0, t1, t2, t3
            # Define low,high & close price as cp0,hp0,lp0 & cp1,hp1,lp1... at t0 & t1 respectively
            # m0, m1, m2, m3 index of min_data at t0, t1, t2, t3
            # Check if it is able to make above shape
            # market is currently at t3
            lp3 = min_data[min_data_len - 1]['low']
            cp3 = min_data[min_data_len - 1]['close']
            m3 = min_data_len - 1

            hp2 = -1
            lp2 = -1
            cp2 = -1
            
            hp1 = -1
            lp1 = -1
            cp1 = -1

            m1 = -1
            m2 = -1

            prev_m1 = -1
            prev_m2 = -1
            prev_candle_cnt = -1

            curr_timestamp = 't23'
            prev_low = -1
            unverified = False
            # verified23 = False
            # verified12 = False
            verified13 = False
            low_till_now = min_data[min_data_len - 2]['low']
            high_till_now = min_data[min_data_len - 2]['high']

            candle_cnt = 0
            for i in range(1, min_data_len):
                candle_cnt += 1
                curr_low = min_data[min_data_len - 1 - i]['low']
                curr_close = min_data[min_data_len - 1 - i]['close']
                curr_high = min_data[min_data_len - 1 - i]['high']
                if curr_low < low_till_now:
                    low_till_now = curr_low
                    m1 = min_data_len - 1 - i
                if curr_high > high_till_now:
                    high_till_now = curr_high
                    m2 = min_data_len - 1 - i
                # low_till_now = min(low_till_now, curr_low)
                # high_till_now = max(high_till_now, curr_high)
                
                if candle_cnt <= 180 and m1 < m2 and m1 != -1 and m2 != -1:
                    found = True
                    satisfied = 0
                    verified23 = False
                    verified12 = False
                    # if now.hour == 10 and now.minute == 9:
                    #     self.logger.info("curr_high: %s" % curr_high)
                    for j in range(3):
                        left_index = m2 - (j + 1)
                        right_index = m2 + (j + 1)
                        if left_index < 0 or left_index >= min_data_len or right_index < 0 or right_index >= min_data_len:
                            continue
                        # if now.hour == 12 and now.minute == 4:
                        #     self.logger.info("low_till_now: %s, high_till_now: %s" % (low_till_now, high_till_now))
                        #     self.logger.info("left_index: %s, right_index: %s" % (left_index, right_index))
                        #     self.logger.info("min_data[left_index]['high']: %s" % min_data[left_index]['high'])
                        #     self.logger.info("min_data[right_index]['high']: %s" % min_data[right_index]['high'])
                        if min_data[left_index]['high'] > high_till_now or min_data[right_index]['high'] > high_till_now:
                            found = False
                            break
                        satisfied += 1
                    if found and satisfied == 3:
                        hp2 = min_data[m2]['high']
                        lp2 = min_data[m2]['low']
                        cp2 = min_data[m2]['close']
                        # Reverify all the points in t23
                        unverified_temp = False
                        for j in range(m2 + 1, min_data_len - 1):
                            if j < 0 or j >= min_data_len:
                                continue
                            if min_data[j]['low'] < lp3 or min_data[j]['high'] > hp2:
                                unverified_temp = True
                                break
                        if unverified_temp:
                            # self.logger.error("Failed while reverification of t23. Check another")
                            continue
                        verified23 = True
                        # self.logger.info("Finally reverification of t23 succeeded, candle_cnt: %s" %candle_cnt)

                    found = True
                    satisfied = 0
                    # if now.hour == 10 and now.minute == 9:
                        # self.logger.info("curr_low: %s" % curr_low)
                    for j in range(3):
                        left_index = m1 - (j + 1)
                        right_index = m1 + (j + 1)
                        if left_index < 0 or left_index >= min_data_len or right_index < 0 or right_index >= min_data_len:
                            continue
                        # if now.hour == 12 and now.minute == 4:
                        #     self.logger.info("low_till_now: %s, high_till_now: %s" % (low_till_now, high_till_now))
                        #     self.logger.info("left_index: %s, right_index: %s" % (left_index, right_index))
                        #     self.logger.info("min_data[left_index]['low']: %s" % min_data[left_index]['low'])
                        #     self.logger.info("min_data[right_index]['low']: %s" % min_data[right_index]['low'])
                        if min_data[left_index]['low'] < low_till_now or min_data[right_index]['low'] < low_till_now:
                            found = False
                            break
                        satisfied += 1
                    if found and satisfied == 3:
                        hp1 = min_data[m1]['high']
                        lp1 = min_data[m1]['low']
                        cp1 = min_data[m1]['close']
                        # Reverify all the points in t12
                        unverified_temp = False
                        for j in range(m1 + 1, m2):
                            # if now.hour == 12 and now.minute == 4:
                            #     self.logger.info("j: %s" %j)
                            #     self.logger.info("lp1: %s" % lp1)
                            #     self.logger.info("hp2: %s" % hp2)
                            #     self.logger.info("min_data[j]['low']: %s" % min_data[j]['low'])
                            #     self.logger.info("min_data[j]['high']: %s" % min_data[j]['high'])
                            if min_data[j]['low'] < lp1 or min_data[j]['high'] > hp2:
                                unverified_temp = True
                                break
                        if unverified_temp:
                            # self.logger.error("Failed while reverification of t12. Check another")
                            continue
                        curr_timestamp = 't01'
                        # m1 = min_data_len - 1 -i
                        verified12 = True
                        # self.logger.info("Finally reverification of t12 succeeded, candle_cnt: %s" %candle_cnt)
                    
                    if verified12 and verified23:
                        verified13 = True
                        prev_m1 = m1
                        prev_m2 = m2
                        prev_candle_cnt = candle_cnt
                    
                # if curr_timestamp == 't23':
                #     found = True
                #     satisfied = 0
                #     # if now.hour == 10 and now.minute == 9:
                #     #     self.logger.info("curr_high: %s" % curr_high)
                #     for j in range(3):
                #         left_index = min_data_len - 1 - i - (j + 1)
                #         right_index = min_data_len - 1 - i + (j + 1)
                #         if left_index < 0 or left_index >= min_data_len or right_index < 0 or right_index >= min_data_len:
                #             continue
                #         # if now.hour == 10 and now.minute == 9:
                #         #     self.logger.info("left_index: %s, right_index: %s" % (left_index, right_index))
                #         #     self.logger.info("min_data[left_index]['high']: %s" % min_data[left_index]['high'])
                #         #     self.logger.info("min_data[right_index]['high']: %s" % min_data[right_index]['high'])
                #         if min_data[left_index]['high'] > curr_high or min_data[right_index]['high'] > curr_high:
                #             found = False
                #             break
                #         satisfied += 1
                #     if found and satisfied == 3:
                #         hp2 = curr_high
                #         lp2 = curr_low
                #         cp2 = curr_close
                #         # Reverify all the points in t23
                #         unverified_temp = False
                #         for j in range(min_data_len - i, min_data_len - 1):
                #             if j < 0 or j >= min_data_len:
                #                 continue
                #             if min_data[j]['low'] < lp3 or min_data[j]['high'] > hp2:
                #                 unverified_temp = True
                #                 break
                #         if unverified_temp:
                #             # self.logger.error("Failed while reverification of t23. Check another")
                #             continue
                #         curr_timestamp = 't12'
                #         m2 = min_data_len - 1 -i
                #         verified23 = True
                #         self.logger.info("Finally reverification of t23 succeeded")
                # if curr_timestamp == 't12':
                #     found = True
                #     satisfied = 0
                #     # if now.hour == 10 and now.minute == 9:
                #         # self.logger.info("curr_low: %s" % curr_low)
                #     for j in range(3):
                #         left_index = min_data_len - 1 - i - (j + 1)
                #         right_index = min_data_len - 1 - i + (j + 1)
                #         if left_index < 0 or left_index >= min_data_len or right_index < 0 or right_index >= min_data_len:
                #             continue
                #         # if now.hour == 10 and now.minute == 9:
                #             # self.logger.info("left_index: %s, right_index: %s" % (left_index, right_index))
                #             # self.logger.info("min_data[left_index]['low']: %s" % min_data[left_index]['low'])
                #             # self.logger.info("min_data[right_index]['low']: %s" % min_data[right_index]['low'])
                #         if min_data[left_index]['low'] < curr_low or min_data[right_index]['low'] < curr_low:
                #             found = False
                #             break
                #         satisfied += 1
                #     if found and satisfied == 3:
                #         hp1 = curr_high
                #         lp1 = curr_low
                #         cp1 = curr_close
                #         # Reverify all the points in t12
                #         unverified_temp = False
                #         for j in range(min_data_len - i, m2):
                #             # if now.hour == 10 and now.minute == 9:
                #                 # self.logger.info("j: %s" %j)
                #                 # self.logger.info("lp1: %s" % lp1)
                #                 # self.logger.info("hp2: %s" % hp2)
                #                 # self.logger.info("min_data[j]['low']: %s" % min_data[j]['low'])
                #                 # self.logger.info("min_data[j]['high']: %s" % min_data[j]['high'])
                #             if min_data[j]['low'] < lp1 or min_data[j]['high'] > hp2:
                #                 unverified_temp = True
                #                 break
                #         if unverified_temp:
                #             # self.logger.error("Failed while reverification of t12. Check another")
                #             continue
                #         curr_timestamp = 't01'
                #         m1 = min_data_len - 1 -i
                #         verified12 = True
                #         self.logger.info("Finally reverification of t12 succeeded")

            # if unverified:
            #     return

            self.verify_banknifty_structure()

            if prev_m1 != -1 and prev_m2 != -1:
                hp2 = min_data[prev_m2]['high']
                lp2 = min_data[prev_m2]['low']
                cp2 = min_data[prev_m2]['close']

                hp1 = min_data[prev_m1]['high']
                lp1 = min_data[prev_m1]['low']
                cp1 = min_data[prev_m1]['close']

                m1 = prev_m1
                m2 = prev_m2

                verified13 = True

            # self.logger.info("hp1: %s, lp1: %s, cp1: %s, hp2: %s, lp2: %s, cp2: %s, lp3: %s, cp3: %s" %(hp1, lp1, cp1, hp2, lp2, cp2, lp3, cp3))
            # if m1 != -1:
            #     self.logger.info("m1: %s", min_data[m1])

            # if m2 != -1:
            #     self.logger.info("m2: %s", min_data[m2])

            # if verified13:
            #     self.logger.error("reverification of t13 succeeded.")

            if lp1 == -1 or hp2 == -1 or lp1 >= lp3:
                unverified = True
                # self.logger.error("Failed while structure verification of lp1, cp1, hp2 & lp3.")

            fib_high_low_diff = hp2 - lp1
            retracement_price_list = []
            for percent in self.fib_retracement_percent:
                # if percent == 0 or percent == 1:
                #     continue
                retracement_price_list.append((hp2 - round(fib_high_low_diff * percent, 1)))

            telegram_trade = None
            for i in range(5, 2, -1):
                if lp3 <= retracement_price_list[i] and not unverified and verified13 and prev_candle_cnt >= 15 and (retracement_price_list[i-1] - retracement_price_list[i+1]) >= 30:
                    close_prices = np.array([data['close'] for data in min_data])
                    
                    df = pd.DataFrame(min_data)
                    df.set_index('date', inplace=True)
                    last_candle_patterns = self.identify_last_candlestick_pattern(df)
                        # Calculate RSI
                    df['RSI'] = talib.RSI(df['close'], timeperiod=14)

                    # Calculate MACD
                    df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)

                    # Calculate Volume Moving Average
                    df['Volume_MA'] = df['volume'].rolling(window=20).mean()

                    # Volume Spike (volume > 1.5 times the moving average volume)
                    df['Volume_Spike'] = (df['volume'] > 1.5 * df['Volume_MA']).astype(int)

                    # Combine signals for potential reversals
                    df['Reversal_Signal'] = ((last_candle_patterns['Bullish_Engulfing'] == 1) |
                                            (last_candle_patterns['Hammer'] == 1) |
                                            ((df['RSI'] < 30) & (df['RSI'].shift(1) >= 30)) |
                                            ((df['MACD'] > df['MACD_Signal']) & (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1))) |
                                            (df['Volume_Spike'] == 1)).astype(int)

                    df['SMA50'] = talib.SMA(df['close'], timeperiod=50)
                    df['SMA200'] = talib.SMA(df['close'], timeperiod=200)
                    # Ensure the trade is in the direction of the trend
                    df['up_trend'] = (df['close'] > df['SMA50']) & (df['SMA50'] > df['SMA200'])

                    df['down_trend'] = (df['close'] < df['SMA50']) & (df['SMA50'] < df['SMA200'])
                    
                    found_reversal = df['Reversal_Signal'][-1] == 1
                    # for i in range(5):
                    #     if len(df['Reversal_Signal']) >= 5 and df['Reversal_Signal'][-i-1] == 1:
                    #         found_reversal = True
                    #         break

                    if found_reversal:
                        # self.logger.info("retracement_price_list: %s" % retracement_price_list)
                        today_date = now.date()
                        # Create a datetime object for today at 12:01 AM
                        start_of_today = datetime.combine(today_date, datetime.min.time())
                        telegram_trade = TelegramTrade()
                        telegram_trade.index_name = 'BANKNIFTY'
                        telegram_trade.index_strike_price = bank_nifty_ce_first_otm_price
                        telegram_trade.option_type = option_type
                        telegram_trade.expiry = bank_nifty_nearest_expiry
                        telegram_trade.entry_start_price = retracement_price_list[i+1]
                        telegram_trade.entry_end_price = retracement_price_list[i-1]
                        # f1 = (1.8 * e - s) / 0.8
                        # target_fraction = (self.exit_target_percent_list[0] / 100)
                        # f1 = ((1 + target_fraction) * e - s) / target_fraction
                        e = retracement_price_list[i-1]
                        s = retracement_price_list[i+1]
                        target_fraction = self.exit_target_percent_list[0] / 100
                        f1 = ((1 + target_fraction) * e - s) / target_fraction
                        f1 = round(f1, 1)
                        telegram_trade.exit_first_target_price = f1
                        telegram_trade.exit_second_target_price = f1 + (f1 - e)
                        telegram_trade.exit_third_target_price = f1 + 2 * (f1 - e)
                        telegram_trade.exit_stop_loss_price = retracement_price_list[i+1]
                        telegram_trade.created_at_time = now
                        telegram_trade.order_status = 'ANALYSE' if analyse else 'NOT_PLACED'
                        telegram_trade.entry_type = 'PULL_BACK_STRATEGY'
                        telegram_trade.set_metadata_from_dict({'forced_risk': 1000, 'up_trend': df['up_trend'][-1], 'down_trend': df['down_trend'][-1]})
                        existing_telegram_trades = TelegramTrade.objects.filter(
                            Q(created_at_time__gte=start_of_today) & Q(index_name='BANKNIFTY')
                            & Q(index_strike_price=telegram_trade.index_strike_price)
                            & Q(option_type=telegram_trade.option_type)
                            & Q(entry_start_price=telegram_trade.entry_start_price)
                            & Q(entry_end_price=telegram_trade.entry_end_price)
                            & Q(exit_stop_loss_price=telegram_trade.exit_stop_loss_price)
                            & Q(exit_first_target_price=telegram_trade.exit_first_target_price)
                            & ~Q(order_status='CANCELLED')
                        )
                        if len(existing_telegram_trades) > 0:
                            self.logger.info("Skipping creating new trade as there is already existing order")
                            telegram_trade = None
                            continue
                        
                        last_5min_telegram_trades = TelegramTrade.objects.filter(
                            Q(created_at_time__gte=(now - timedelta(minutes=5)))
                            & Q(created_at_time__lte=now)
                            & Q(index_name='BANKNIFTY')
                            & Q(option_type=telegram_trade.option_type)
                            & Q(order_status='ANALYSE')
                        )
                        if len(last_5min_telegram_trades) > 0:
                            self.logger.info("Skipping creating new trade as there is already existing order in last 5 min.")
                            telegram_trade = None
                            continue
                        telegram_trade.save()
                        break
                
            if telegram_trade is not None and analyse:
                current_time = get_ist_datetime(datetime.now())
                date_after_1_day = my_timedelta(now, '+', timedelta(days=1))
                if date_after_1_day >= current_time:
                    date_after_1_day = current_time
                future_min_data = self.historical_data(kite, bank_nifty_inst_token, now,
                                            date_after_1_day, "minute", False)
                future_min_data_len = len(future_min_data)
                # self.logger.info("future_min_data[0]: %s" % future_min_data[0])
                # self.logger.info("future_min_data[len-1]: %s" %future_min_data[future_min_data_len-1])
                if option_type == 'PE':
                    for curr_min_data in future_min_data:
                        prev_min_data_low = curr_min_data['low']
                        prev_min_data_high = curr_min_data['high']
                        prev_min_data_open = curr_min_data['open']
                        prev_min_data_close = curr_min_data['close']
                        curr_min_data['low'] = -prev_min_data_high
                        curr_min_data['close'] = -prev_min_data_open
                        curr_min_data['high'] = -prev_min_data_low
                        curr_min_data['open'] = -prev_min_data_close

                target_hit_cnt = 0
                sl_hit_cnt = 0
                entered = False
                for i in range(0, future_min_data_len):
                    curr_low = future_min_data[i]['low']
                    # curr_close = min_data[min_data_len - 1 - i]['close']
                    curr_high = future_min_data[i]['high']

                    if curr_low <= telegram_trade.exit_stop_loss_price and entered:
                        sl_hit_cnt = 1
                        break
                    
                    if entered and target_hit_cnt >= 1 and curr_low <= telegram_trade.entry_end_price:
                        sl_hit_cnt = 1
                        break

                    if telegram_trade.entry_end_price <= curr_high:
                        entered = True
                    
                    if target_hit_cnt == 0 and telegram_trade.exit_first_target_price <= curr_high and entered:
                        target_hit_cnt = 1

                    if target_hit_cnt == 1 and telegram_trade.exit_second_target_price <= curr_high and entered:
                        target_hit_cnt = 2
                    
                    if target_hit_cnt >= 1 and telegram_trade.exit_third_target_price <= curr_high and entered:
                        target_hit_cnt = 3
                        break
                
                profit_percent = 0

                if target_hit_cnt >= 1 and entered:
                    profit_percent = abs((e - s) / e)
                    if target_hit_cnt >= 2 and entered:
                        last_quantity_share = self.exit_target_percent_list[len(self.exit_target_percent_list) - 1] / 100
                        profit_percent += (target_hit_cnt * (f1 - e) * last_quantity_share / e)
                elif sl_hit_cnt == 1 and entered:
                    profit_percent = -abs((s - e) / e)

                metadata = telegram_trade.get_metadata_as_dict()
                metadata['sl_hit_cnt'] = sl_hit_cnt
                metadata['target_hit_cnt'] = target_hit_cnt
                metadata['profit_percent'] = profit_percent
                metadata['trade_entered'] = entered

                telegram_trade.set_metadata_from_dict(metadata)
                telegram_trade.save()

    def identify_last_candlestick_pattern(self, df):
        # Get the last row's data
        last_open = df['open'].iloc[-1]
        last_high = df['high'].iloc[-1]
        last_low = df['low'].iloc[-1]
        last_close = df['close'].iloc[-1]

        # Create a DataFrame with the last row's data for talib functions
        last_candle_df = pd.DataFrame({
            'open': [last_open],
            'high': [last_high],
            'low': [last_low],
            'close': [last_close]
        })

        # Identify Bullish Engulfing pattern
        last_candle_df['Bullish_Engulfing'] = talib.CDLENGULFING(last_candle_df['open'], last_candle_df['high'], last_candle_df['low'], last_candle_df['close'])
        last_candle_df['Bullish_Engulfing'] = last_candle_df['Bullish_Engulfing'].apply(lambda x: 1 if x > 0 else 0)
        
        # Identify Hammer pattern
        last_candle_df['Hammer'] = talib.CDLHAMMER(last_candle_df['open'], last_candle_df['high'], last_candle_df['low'], last_candle_df['close'])
        last_candle_df['Hammer'] = last_candle_df['Hammer'].apply(lambda x: 1 if x > 0 else 0)

        return last_candle_df[['Bullish_Engulfing', 'Hammer']].iloc[0]

    def verify_banknifty_structure(self):
        return True

    def cancel_trade_if_sl_crossed(self, kite, tick_map, nearest_expiry_map, bank_nifty_option_inst_token_map):
        bank_nifty_nearest_expiry = nearest_expiry_map.get('BANKNIFTY')
        today_date = datetime.now().date()
        # Create a datetime object for today at 12:01 AM
        start_of_today = datetime.combine(today_date, datetime.min.time())
        trades = TelegramTrade.objects.filter(
            Q(created_at_time__gte=start_of_today) &
            Q(entry_type='PULL_BACK_STRATEGY') &
            (Q(order_status='NOT_PLACED') | Q(order_status='NOT_PLACED_PRICES_PROCESSED') | Q(metadata__icontains='ORDER_ENTRY_PLACED'))
        )
        for trade in trades:
            inst_token_key = "BANKNIFTY-%s-%s-%s" % (
            self.get_complete_date(bank_nifty_nearest_expiry), trade.index_strike_price, trade.option_type)
            
            inst_token = bank_nifty_option_inst_token_map.get(inst_token_key)

            close = tick_map[inst_token]['last_price']

            if close <= trade.exit_stop_loss_price:
                existing_metadata = trade.get_metadata_as_dict()
                if existing_metadata is None:
                    existing_metadata = {}
                existing_metadata['updated_order_status'] = 'CANCELLED'
                trade.set_metadata_from_dict(existing_metadata)
                trade.save()

    def generate_trade_based_on_strategy(self, kite, tick_map, nearest_expiry_map, now=datetime.now()):
        fragment_sizes = {'NIFTY': [3, 9, 27], 'BANKNIFTY': [6, 18, 54]}
        nifty_inst_token = 256265
        bank_nifty_inst_token = 260105
        
        niftyStrikePrices = set()
        bankNiftyStrikePrices = set()
        niftyPrice = 0
        bankNiftyPrice = 0

        for tick in tick_map.values():
            if 'trading_symbol' in tick and tick['trading_symbol'].startswith('NIFTY'):
                tradingSymbol = tick['trading_symbol']
                optionType = tradingSymbol[-2:]
                strikePrice = tradingSymbol[-7:].replace(optionType, '')
                niftyStrikePrices.add(int(strikePrice))
            elif 'trading_symbol' in tick and tick['trading_symbol'].startswith('BANKNIFTY'):
                tradingSymbol = tick['trading_symbol']
                optionType = tradingSymbol[-2:]
                strikePrice = tradingSymbol[-7:].replace(optionType, '')
                bankNiftyStrikePrices.add(int(strikePrice))
            elif tick.get('instrument_token') == nifty_inst_token:
                niftyPrice = tick.get('last_price')
            elif tick.get('instrument_token') == bank_nifty_inst_token:
                bankNiftyPrice = tick.get('last_price')
        
        niftyStrikePrices = list(niftyStrikePrices)
        bankNiftyStrikePrices = list(bankNiftyStrikePrices)

        niftyStrikePrices.sort()
        bankNiftyStrikePrices.sort()

        niftyAtmIndex = -1
        niftyAtmDiff = 9999999999
        for index, price in enumerate(niftyStrikePrices):
            absDiff = abs(niftyPrice - price)
            if absDiff < niftyAtmDiff:
                niftyAtmDiff = absDiff
                niftyAtmIndex = index

        bankNiftyAtmIndex = -1
        bankNiftyAtmDiff = 9999999999
        for index, price in enumerate(bankNiftyStrikePrices):
            absDiff = abs(bankNiftyPrice - price)
            if absDiff < bankNiftyAtmDiff:
                bankNiftyAtmDiff = absDiff
                bankNiftyAtmIndex = index
        
        niftyCeFirstItmIndex = max(0, niftyAtmIndex - 1)
        niftyCeFirstOtmIndex = min(niftyAtmIndex + 1, len(niftyStrikePrices) - 1)

        niftyPeFirstItmIndex = min(niftyAtmIndex + 1, len(niftyStrikePrices) - 1)
        niftyPeFirstOtmIndex = max(0, niftyAtmIndex - 1)

        bankNiftyCeFirstItmIndex = max(0, bankNiftyAtmIndex - 1)
        bankNiftyCeFirstOtmIndex = min(bankNiftyAtmIndex + 1, len(bankNiftyStrikePrices) - 1)

        bankNiftyPeFirstItmIndex = min(bankNiftyAtmIndex + 1, len(bankNiftyStrikePrices) - 1)
        bankNiftyPeFirstOtmIndex = max(0, bankNiftyAtmIndex - 1)

        # Considering BANKNIFTY 1st OTM and CE for now
        bank_nifty_nearest_expiry = nearest_expiry_map.get('BANKNIFTY')
        bank_nifty_ce_first_otm_price = bankNiftyStrikePrices[bankNiftyCeFirstOtmIndex]

        possible_trading_symbol1 = 'BANKNIFTY%s%sCE' % (bank_nifty_nearest_expiry, bank_nifty_ce_first_otm_price)
        possible_trading_symbol2 = 'BANKNIFTY%s%sCE' % (self.convert_date(bank_nifty_nearest_expiry), bank_nifty_ce_first_otm_price)

        bank_nifty_ce_first_otm_inst_token = -1
        for tick in tick_map.values():
            if 'trading_symbol' in tick and tick['trading_symbol'].startswith('BANKNIFTY'):
                trading_symbol = tick['trading_symbol']
                if trading_symbol == possible_trading_symbol1 or trading_symbol == possible_trading_symbol2:
                    self.logger.info(trading_symbol)
                    bank_nifty_ce_first_otm_inst_token = tick['instrument_token']

        if bank_nifty_ce_first_otm_inst_token == -1:
            self.logger.error("Could not find inst_token. Returning")
            return

        self.logger.info("bank_nifty_ce_first_otm_inst_token: {}".format(bank_nifty_ce_first_otm_inst_token))

        # now = get_ist_datetime(datetime.now())
        from_date = now - timedelta(days=1)

        min_data = self.historical_data(kite, bank_nifty_ce_first_otm_inst_token, from_date,
                                        now, "minute", False)
        min_data_len = len(min_data)
        self.logger.info(min_data[0])
        self.logger.info(min_data[min_data_len-1])

        # Loop through different fragment sizes later
        curr_fragment_size = fragment_sizes['BANKNIFTY'][0]

        # Define LH1, LH2, LH3 based on fragment size
        # Check low of each candle and tag it like 1,2,3 if it comes just below LHi 
        # Check for closing after LH3 at the end

        lh3 = int(min_data[min_data_len - 1]['close'] / curr_fragment_size) * curr_fragment_size
        self.logger.info("lh3: {}".format(lh3))
        lh2 = lh3 - curr_fragment_size
        lh1 = lh2 - curr_fragment_size
        lh0 = lh1 - curr_fragment_size

        lh4 = lh3 + curr_fragment_size
        lh5 = lh4 + curr_fragment_size
        lh7 = lh5 + (2 * curr_fragment_size)
        lh9 = lh7 + (2 * curr_fragment_size)

        prev_tag = -1
        tag_order_switched = False # False for decreasing order
        entry_allowed = False

        candle_tag_list = []
        for i in range(min_data_len):
            curr_low = min_data[min_data_len - 1 - i]['low']
            candle_tag = -1
            
            if curr_low <= lh0:
                candle_tag = 0
            elif curr_low <= lh1:
                candle_tag = 1
            elif curr_low <= lh2:
                candle_tag = 2
            elif curr_low <= lh3:
                candle_tag = 3
            else:
                candle_tag = 3
            
            candle_tag_list.append(candle_tag)

            if prev_tag != -1:
                if (prev_tag < candle_tag and (prev_tag == 1)):
                    tag_order_switched = True
                if not tag_order_switched:
                    if prev_tag < candle_tag:
                        entry_allowed = False
                        break
                else:
                    if prev_tag > candle_tag:
                        entry_allowed = False
                        break
            
            # if tag_order_switched and candle_tag == 3 and min_data[min_data_len - 1 - i]['close'] >= lh3:
            #     entry_allowed = True
            #     break

            if tag_order_switched and candle_tag == 3:
                entry_allowed = True
                break

            prev_tag = candle_tag

        self.logger.info(candle_tag_list)

        if entry_allowed:
            telegram_trade = TelegramTrade()
            telegram_trade.index_name = 'BANKNIFTY'
            telegram_trade.index_strike_price = bank_nifty_ce_first_otm_price
            telegram_trade.option_type = 'CE'
            telegram_trade.expiry = bank_nifty_nearest_expiry
            telegram_trade.entry_start_price = lh0
            telegram_trade.entry_end_price = lh2
            telegram_trade.exit_first_target_price = lh5
            telegram_trade.exit_second_target_price = lh7
            telegram_trade.exit_third_target_price = lh9
            telegram_trade.exit_stop_loss_price = lh0
            telegram_trade.created_at_time = now
            telegram_trade.order_status = 'NOT_PLACED'
            telegram_trade.entry_type = 'PULL_BACK_STRATEGY'
            telegram_trade.set_metadata_from_dict({'forced_risk': 1000})

            telegram_trade.save()
            # self.logger.info("Entry Allowed")
            # self.logger.info(now)


        
        bank_nifty_nearest_expiry = nearest_expiry_map.get('BANKNIFTY')
        bank_nifty_pe_first_otm_price = bankNiftyStrikePrices[bankNiftyPeFirstOtmIndex]

        possible_trading_symbol1 = 'BANKNIFTY%s%sPE' % (bank_nifty_nearest_expiry, bank_nifty_pe_first_otm_price)
        possible_trading_symbol2 = 'BANKNIFTY%s%sPE' % (self.convert_date(bank_nifty_nearest_expiry), bank_nifty_pe_first_otm_price)

        bank_nifty_pe_first_otm_inst_token = -1
        for tick in tick_map.values():
            if 'trading_symbol' in tick and tick['trading_symbol'].startswith('BANKNIFTY'):
                trading_symbol = tick['trading_symbol']
                if trading_symbol == possible_trading_symbol1 or trading_symbol == possible_trading_symbol2:
                    bank_nifty_pe_first_otm_inst_token = tick['instrument_token']
                    self.logger.info(trading_symbol)

        if bank_nifty_pe_first_otm_inst_token == -1:
            self.logger.error("Could not find inst_token. Returning")
            return

        self.logger.info("bank_nifty_pe_first_otm_inst_token: {}".format(bank_nifty_pe_first_otm_inst_token))

        # now = datetime.now()
        from_date = now - timedelta(days=1)

        min_data = self.historical_data(kite, bank_nifty_pe_first_otm_inst_token, from_date,
                                        now, "minute", False)
        min_data_len = len(min_data)
        self.logger.info(min_data[0])
        self.logger.info(min_data[min_data_len-1])

        # Loop through different fragment sizes later
        curr_fragment_size = fragment_sizes['BANKNIFTY'][0]

        # Define LH1, LH2, LH3 based on fragment size
        # Check low of each candle and tag it like 1,2,3 if it comes just below LHi 
        # Check for closing after LH3 at the end

        lh3 = int(min_data[min_data_len - 1]['close'] / curr_fragment_size) * curr_fragment_size
        self.logger.info("lh3: {}".format(lh3))
        lh2 = lh3 - curr_fragment_size
        lh1 = lh2 - curr_fragment_size
        lh0 = lh1 - curr_fragment_size

        lh4 = lh3 + curr_fragment_size
        lh5 = lh4 + curr_fragment_size
        lh7 = lh5 + (2 * curr_fragment_size)
        lh9 = lh7 + (2 * curr_fragment_size)

        prev_tag = -1
        tag_order_switched = False # False for decreasing order
        entry_allowed = False

        candle_tag_list = []
        for i in range(min_data_len):
            curr_low = min_data[min_data_len - 1 - i]['low']
            candle_tag = -1
            
            if curr_low < lh0:
                candle_tag = 0
            elif curr_low <= lh1:
                candle_tag = 1
            elif curr_low <= lh2:
                candle_tag = 2
            elif curr_low <= lh3:
                candle_tag = 3
            else:
                candle_tag = 3

            candle_tag_list.append(candle_tag)

            if prev_tag != -1:
                if (prev_tag < candle_tag and (prev_tag == 1)):
                    tag_order_switched = True
                if not tag_order_switched:
                    if prev_tag < candle_tag:
                        entry_allowed = False
                        break
                else:
                    if prev_tag > candle_tag:
                        entry_allowed = False
                        break
            
            # if tag_order_switched and candle_tag == 3 and min_data[min_data_len - 1 - i]['close'] >= lh3:
            #     entry_allowed = True
            #     break

            if tag_order_switched and candle_tag == 3:
                entry_allowed = True
                break

            prev_tag = candle_tag
        
        self.logger.info(candle_tag_list)

        if entry_allowed:
            telegram_trade = TelegramTrade()
            telegram_trade.index_name = 'BANKNIFTY'
            telegram_trade.index_strike_price = bank_nifty_pe_first_otm_price
            telegram_trade.option_type = 'PE'
            telegram_trade.expiry = bank_nifty_nearest_expiry
            telegram_trade.entry_start_price = lh0
            telegram_trade.entry_end_price = lh2
            telegram_trade.exit_first_target_price = lh5
            telegram_trade.exit_second_target_price = lh7
            telegram_trade.exit_third_target_price = lh9
            telegram_trade.exit_stop_loss_price = lh0
            telegram_trade.created_at_time = now
            telegram_trade.order_status = 'NOT_PLACED'
            telegram_trade.entry_type = 'PULL_BACK_STRATEGY'
            telegram_trade.set_metadata_from_dict({'forced_risk': 1000})

            telegram_trade.save()

    def generate_intraday_test_trade(self, kite, nearest_expiry_map, inst_token_map):
        sample_tick_map_data = { "265": { "tradable": False, "mode": "ltp", "instrument_token": 265, "last_price": 74329.45, "high": 74571.21, "low": 73369.76 }, "256265": { "tradable": False, "mode": "full", "instrument_token": 256265, "last_price": 22558.5, "ohlc": { "high": 22625.95, "low": 22305.25, "open": 22316.9, "close": 22402.4 }, "change": 0.6968003428204056, "exchange_timestamp": "2024-04-25 10:00:06", "high": 22624.75, "low": 21960.2 }, 
        "260105": { "tradable": False, "mode": "ltp", "instrument_token": 260105, "last_price": 48499.2, "high": 48621.9, "low": 47755.35 }, "288009": { "tradable": False, "mode": "ltp", "instrument_token": 288009, "last_price": 10876.1, "high": 10891.85, "low": 10809.5 }, "9148930": { "tradable": True, "mode": "ltp", "instrument_token": 9148930, "last_price": 308.2, "trading_symbol": "MIDCPNIFTY24APR10600CE", "high": 308.9, "low": 232.2 }, "9149442": { "tradable": True, "mode": "ltp", "instrument_token": 9149442, "last_price": 8.2, "trading_symbol": "MIDCPNIFTY24APR10600PE", "high": 24.35, "low": 6.85 }, "9149698": { "tradable": True, "mode": "ltp", "instrument_token": 9149698, "last_price": 276.05, "trading_symbol": "MIDCPNIFTY24APR10625CE", "high": 280.6, "low": 224.1 }, "9149954": { "tradable": True, "mode": "ltp", "instrument_token": 9149954, "last_price": 9.45, "trading_symbol": "MIDCPNIFTY24APR10625PE", "high": 19.65, "low": 7.95 }, "9150210": { "tradable": True, "mode": "ltp", "instrument_token": 9150210, "last_price": 258, "trading_symbol": "MIDCPNIFTY24APR10650CE", "high": 258.1, "low": 191.3 }, "9150466": { "tradable": True, "mode": "ltp", "instrument_token": 9150466, "last_price": 10.65, 
        "trading_symbol": "MIDCPNIFTY24APR10650PE", "high": 23.15, "low": 9.35 }, "9150722": { "tradable": True, "mode": "ltp", "instrument_token": 9150722, "last_price": 236.9, "trading_symbol": "MIDCPNIFTY24APR10675CE", "high": 236.9, "low": 171.65 }, "9150978": { "tradable": True, "mode": "ltp", "instrument_token": 9150978, "last_price": 12.3, "trading_symbol": "MIDCPNIFTY24APR10675PE", "high": 27.35, "low": 11.1 }, "9151234": { "tradable": True, "mode": "ltp", "instrument_token": 9151234, "last_price": 214, "trading_symbol": "MIDCPNIFTY24APR10700CE", "high": 214.25, "low": 142.2 }, "9151490": { "tradable": True, "mode": "ltp", "instrument_token": 9151490, "last_price": 14.6, "trading_symbol": "MIDCPNIFTY24APR10700PE", "high": 42.25, "low": 13 }, "9151746": { "tradable": True, "mode": "ltp", "instrument_token": 9151746, "last_price": 189.1, "trading_symbol": "MIDCPNIFTY24APR10725CE", "high": 191.1, "low": 128.05 }, "9152002": { "tradable": True, "mode": "ltp", "instrument_token": 9152002, "last_price": 16.85, "trading_symbol": "MIDCPNIFTY24APR10725PE", "high": 38.25, "low": 15.4 }, "9152258": { "tradable": True, "mode": "ltp", "instrument_token": 9152258, "last_price": 169.05, "trading_symbol": "MIDCPNIFTY24APR10750CE", "high": 169.05, "low": 110 }, "9152514": { "tradable": True, "mode": "ltp", "instrument_token": 9152514, "last_price": 19.5, "trading_symbol": "MIDCPNIFTY24APR10750PE", "high": 48.8, "low": 18.25 }, "9153538": { "tradable": True, "mode": "ltp", "instrument_token": 9153538, "last_price": 147.55, "trading_symbol": "MIDCPNIFTY24APR10775CE", "high": 147.55, "low": 76.1 }, "9153794": { "tradable": True, "mode": "ltp", "instrument_token": 9153794, "last_price": 23.05, "trading_symbol": "MIDCPNIFTY24APR10775PE", "high": 59, "low": 21.8 }, "9154050": { "tradable": True, "mode": "ltp", "instrument_token": 9154050, "last_price": 125.55, "trading_symbol": "MIDCPNIFTY24APR10800CE", "high": 126.6, "low": 76.8 }, "9154306": { "tradable": True, "mode": "ltp", "instrument_token": 9154306, "last_price": 26.25, "trading_symbol": "MIDCPNIFTY24APR10800PE", "high": 72, "low": 26.1 }, "9157378": { "tradable": True, "mode": "ltp", "instrument_token": 9157378, "last_price": 106.85, "trading_symbol": "MIDCPNIFTY24APR10825CE", "high": 107.1, "low": 56.8 }, "9157634": { "tradable": True, "mode": "ltp", "instrument_token": 9157634, "last_price": 31.55, "trading_symbol": "MIDCPNIFTY24APR10825PE", "high": 78.5, "low": 31.55 }, "9157890": { "tradable": True, "mode": "ltp", "instrument_token": 9157890, "last_price": 86.2, "trading_symbol": "MIDCPNIFTY24APR10850CE", "high": 89.5, "low": 50 }, "9158658": { "tradable": True, "mode": "ltp", "instrument_token": 9158658, "last_price": 38.6, "trading_symbol": "MIDCPNIFTY24APR10850PE", "high": 91.45, "low": 37.25 }, "9158914": { "tradable": True, "mode": "ltp", "instrument_token": 9158914, "last_price": 68.45, "trading_symbol": "MIDCPNIFTY24APR10875CE", "high": 73.55, "low": 40 }, "9159938": { "tradable": True, "mode": "ltp", "instrument_token": 9159938, "last_price": 46, "trading_symbol": "MIDCPNIFTY24APR10875PE", "high": 100.15, "low": 45.35 }, "9160194": { "tradable": True, "mode": "ltp", "instrument_token": 9160194, "last_price": 55.4, "trading_symbol": "MIDCPNIFTY24APR10900CE", "high": 59.3, "low": 24.6 }, "9160706": { "tradable": True, "mode": "ltp", "instrument_token": 9160706, "last_price": 56, "trading_symbol": "MIDCPNIFTY24APR10900PE", "high": 123.85, "low": 55.05 }, "9160962": { "tradable": True, "mode": "ltp", "instrument_token": 9160962, "last_price": 41.95, "trading_symbol": "MIDCPNIFTY24APR10925CE", "high": 46.45, "low": 20.9 }, "9161218": { "tradable": True, "mode": "ltp", "instrument_token": 9161218, "last_price": 67.1, "trading_symbol": "MIDCPNIFTY24APR10925PE", "high": 133.4, "low": 66.75 }, "9161474": { "tradable": True, "mode": "ltp", "instrument_token": 9161474, "last_price": 30.85, "trading_symbol": "MIDCPNIFTY24APR10950CE", "high": 35.7, "low": 10.8 }, "9161730": { "tradable": True, "mode": "ltp", "instrument_token": 9161730, "last_price": 82.85, "trading_symbol": "MIDCPNIFTY24APR10950PE", "high": 152, "low": 81.3 }, "9163522": { "tradable": True, "mode": "ltp", "instrument_token": 9163522, "last_price": 22.5, "trading_symbol": "MIDCPNIFTY24APR10975CE", "high": 27.35, "low": 8 }, "9163778": { "tradable": True, "mode": "ltp", "instrument_token": 9163778, "last_price": 99.1, "trading_symbol": "MIDCPNIFTY24APR10975PE", "high": 171.35, "low": 98.3 }, "9165570": { "tradable": True, "mode": "ltp", "instrument_token": 9165570, "last_price": 16.75, "trading_symbol": "MIDCPNIFTY24APR11000CE", "high": 20.9, "low": 8 }, "9165826": { 
            "tradable": True, "mode": "ltp", "instrument_token": 9165826, "last_price": 115, "trading_symbol": "MIDCPNIFTY24APR11000PE", "high": 193, "low": 115 }, "9166082": { "tradable": True, "mode": "ltp", "instrument_token": 9166082, "last_price": 11.65, "trading_symbol": "MIDCPNIFTY24APR11025CE", "high": 15.35, "low": 6 }, "9166338": { "tradable": True, "mode": "ltp", "instrument_token": 9166338, "last_price": 136.85, "trading_symbol": "MIDCPNIFTY24APR11025PE", "high": 213.4, "low": 136.8 }, "9166594": { "tradable": True, "mode": "ltp", "instrument_token": 9166594, "last_price": 8.05, "trading_symbol": "MIDCPNIFTY24APR11050CE", "high": 11.35, "low": 3.25 }, "9166850": { "tradable": True, "mode": "ltp", "instrument_token": 9166850, "last_price": 158.25, "trading_symbol": "MIDCPNIFTY24APR11050PE", "high": 236, "low": 158.25 }, "9167106": { "tradable": True, "mode": "ltp", "instrument_token": 9167106, "last_price": 5.5, "trading_symbol": "MIDCPNIFTY24APR11075CE", "high": 8.3, "low": 3 }, "9167362": { "tradable": True, "mode": "ltp", "instrument_token": 9167362, "last_price": 193.95, "trading_symbol": "MIDCPNIFTY24APR11075PE", "high": 252, "low": 192.05 }, "9167618": { "tradable": True, "mode": "ltp", "instrument_token": 9167618, "last_price": 3.75, "trading_symbol": "MIDCPNIFTY24APR11100CE", "high": 6.1, "low": 2.55 }, "9167874": { "tradable": True, "mode": "ltp", "instrument_token": 9167874, "last_price": 204, "trading_symbol": "MIDCPNIFTY24APR11100PE", "high": 281, "low": 204 }, "9339650": { "tradable": True, "mode": "ltp", "instrument_token": 9339650, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610600CE", "high": 314.75, "low": 0 }, "9340162": { "tradable": True, "mode": "ltp", "instrument_token": 9340162, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610600PE", "high": 54, "low": 0 }, "9341954": { "tradable": True, "mode": "ltp", "instrument_token": 9341954, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610625CE", "high": 296.2, "low": 0 }, "9342722": { "tradable": True, "mode": "ltp", "instrument_token": 9342722, "last_price": 66.55, "trading_symbol": "MIDCPNIFTY2450610625PE", "high": 66.55, "low": 60.4 }, "9344514": { "tradable": True, "mode": "ltp", "instrument_token": 9344514, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610650CE", "high": 278.3, "low": 0 }, "9344770": { "tradable": True, "mode": "ltp", "instrument_token": 9344770, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610650PE", "high": 67.45, "low": 0 }, "9345282": { "tradable": True, "mode": "ltp", "instrument_token": 9345282, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610675CE", "high": 260.95, "low": 0 }, "9345538": { "tradable": True, "mode": "ltp", "instrument_token": 9345538, "last_price": 75.05, "trading_symbol": "MIDCPNIFTY2450610675PE", "high": 75.05, "low": 75.05 }, "9352450": { "tradable": True, "mode": "ltp", "instrument_token": 9352450, "last_price": 251, "trading_symbol": "MIDCPNIFTY2450610700CE", "high": 257.9, "low": 204.85 }, "9352706": { "tradable": True, "mode": "ltp", "instrument_token": 9352706, "last_price": 48.15, "trading_symbol": "MIDCPNIFTY2450610700PE", "high": 75, "low": 47 }, "9353218": { "tradable": True, "mode": "ltp", "instrument_token": 9353218, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610725CE", "high": 228.05, "low": 0 }, "9353986": { "tradable": True, "mode": "ltp", "instrument_token": 9353986, "last_price": 59.35, "trading_symbol": "MIDCPNIFTY2450610725PE", "high": 75.9, "low": 59.35 }, "9354242": { "tradable": True, "mode": "ltp", "instrument_token": 9354242, "last_price": 227.9, "trading_symbol": "MIDCPNIFTY2450610750CE", "high": 227.9, "low": 174.7 }, "9354498": { "tradable": True, "mode": "ltp", "instrument_token": 9354498, "last_price": 101.45, "trading_symbol": "MIDCPNIFTY2450610750PE", "high": 101.45, "low": 101.45 }, "9354754": { "tradable": True, "mode": "ltp", "instrument_token": 9354754, "last_price": 172.3, "trading_symbol": "MIDCPNIFTY2450610775CE", "high": 172.3, "low": 172.3 }, "9356034": { "tradable": True, "mode": "ltp", "instrument_token": 9356034, "last_price": 67.5, "trading_symbol": "MIDCPNIFTY2450610775PE", "high": 111.55, "low": 67.5 }, "9356802": { "tradable": True, "mode": "ltp", "instrument_token": 9356802, "last_price": 182, "trading_symbol": "MIDCPNIFTY2450610800CE", "high": 184.55, "low": 140 }, "9357058": { "tradable": True, "mode": "ltp", "instrument_token": 9357058, "last_price": 75, "trading_symbol": "MIDCPNIFTY2450610800PE", "high": 115, "low": 75 }, "9357826": { "tradable": True, "mode": "ltp", "instrument_token": 9357826, "last_price": 150.8, "trading_symbol": "MIDCPNIFTY2450610825CE", "high": 167.6, "low": 130.05 }, "9358082": { "tradable": True, "mode": "ltp", "instrument_token": 9358082, "last_price": 140.35, "trading_symbol": "MIDCPNIFTY2450610825PE", "high": 140.35, "low": 133.65 }, "9358338": { "tradable": True, "mode": "ltp", "instrument_token": 9358338, "last_price": 149.25, "trading_symbol": "MIDCPNIFTY2450610850CE", "high": 154.65, "low": 115 }, "9358594": { "tradable": True, "mode": "ltp", "instrument_token": 9358594, "last_price": 89.95, "trading_symbol": "MIDCPNIFTY2450610850PE", "high": 135, "low": 89.95 }, "9358850": { "tradable": True, "mode": "ltp", "instrument_token": 9358850, "last_price": 130.05, "trading_symbol": "MIDCPNIFTY2450610875CE", "high": 159.55, "low": 100.1 }, "9359106": { "tradable": True, "mode": "ltp", "instrument_token": 9359106, "last_price": 166.25, "trading_symbol": "MIDCPNIFTY2450610875PE", "high": 166.25, "low": 158.3 }, "9361922": { "tradable": True, "mode": "ltp", "instrument_token": 9361922, "last_price": 118, "trading_symbol": "MIDCPNIFTY2450610900CE", "high": 120.2, "low": 85.2 }, "9363202": { "tradable": True, "mode": "ltp", "instrument_token": 9363202, "last_price": 112.95, "trading_symbol": "MIDCPNIFTY2450610900PE", "high": 154.1, "low": 110 }, "9363458": { "tradable": True, "mode": "ltp", "instrument_token": 9363458, "last_price": 128.2, "trading_symbol": "MIDCPNIFTY2450610925CE", "high": 128.2, "low": 0 }, "9364226": { "tradable": True, "mode": "ltp", "instrument_token": 9364226, "last_price": 185.6, "trading_symbol": "MIDCPNIFTY2450610925PE", "high": 185.6, "low": 185.6 }, "9364482": { "tradable": True, "mode": "ltp", "instrument_token": 9364482, "last_price": 101, "trading_symbol": "MIDCPNIFTY2450610950CE", "high": 111.75, "low": 0 }, "9365250": { "tradable": True, "mode": "ltp", "instrument_token": 9365250, "last_price": 200.2, "trading_symbol": "MIDCPNIFTY2450610950PE", "high": 200.2, "low": 200.2 }, "9366018": { "tradable": True, "mode": "ltp", "instrument_token": 9366018, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610975CE", "high": 102.05, "low": 0 }, "9366274": { "tradable": True, "mode": "ltp", "instrument_token": 9366274, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450610975PE", "high": 215.45, "low": 0 }, "9370114": { "tradable": True, "mode": "ltp", "instrument_token": 9370114, "last_price": 69.05, "trading_symbol": "MIDCPNIFTY2450611000CE", "high": 72, "low": 54 }, "9370370": { "tradable": True, "mode": "ltp", "instrument_token": 9370370, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450611000PE", "high": 231.3, "low": 0 }, "9370626": { "tradable": True, "mode": "ltp", "instrument_token": 9370626, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450611025CE", "high": 84.5, "low": 0 }, "9370882": { "tradable": True, "mode": "ltp", "instrument_token": 9370882, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450611025PE", "high": 247.75, "low": 0 }, "9371138": { "tradable": True, "mode": "ltp", "instrument_token": 9371138, "last_price": 69.9, "trading_symbol": "MIDCPNIFTY2450611050CE", "high": 69.9, "low": 69.9 }, "9371906": { "tradable": True, "mode": "ltp", "instrument_token": 9371906, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450611050PE", "high": 264.8, "low": 0 }, "9372162": { "tradable": True, "mode": "ltp", "instrument_token": 9372162, "last_price": 58, "trading_symbol": "MIDCPNIFTY2450611075CE", "high": 69.25, "low": 58 }, "9372674": { "tradable": True, "mode": "ltp", "instrument_token": 9372674, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450611075PE", "high": 282.4, "low": 0 }, "9372930": { "tradable": True, "mode": "ltp", "instrument_token": 9372930, "last_price": 57.9, "trading_symbol": "MIDCPNIFTY2450611100CE", "high": 64.35, "low": 0 }, "9374722": { "tradable": True, "mode": "ltp", "instrument_token": 9374722, "last_price": 0, "trading_symbol": "MIDCPNIFTY2450611100PE", "high": 300.55, "low": 0 }, "10519810": { "tradable": True, "mode": "ltp", "instrument_token": 10519810, "last_price": 644.05, "trading_symbol": "NIFTY2450221950CE", "high": 705.45, "low": 448.15 }, "10520066": { "tradable": True, "mode": "ltp", "instrument_token": 10520066, "last_price": 17.55, "trading_symbol": "NIFTY2450221950PE", "high": 32, "low": 13.2 }, "10520322": { "tradable": True, "mode": "ltp", "instrument_token": 10520322, "last_price": 595, "trading_symbol": "NIFTY2450222000CE", "high": 660.85, "low": 402.15 }, "10520578": { "tradable": True, "mode": "ltp", "instrument_token": 10520578, "last_price": 20.6, "trading_symbol": "NIFTY2450222000PE", "high": 38.35, "low": 15.8 }, "10520834": { "tradable": True, "mode": "ltp", "instrument_token": 10520834, "last_price": 546.75, "trading_symbol": 
            "NIFTY2450222050CE", "high": 612, "low": 360 }, "10521090": { "tradable": True, "mode": "ltp", "instrument_token": 10521090, "last_price": 24, "trading_symbol": "NIFTY2450222050PE", "high": 51, "low": 19 }, "10529282": { "tradable": True, "mode": "ltp", "instrument_token": 10529282, "last_price": 506.75, "trading_symbol": "NIFTY2450222100CE", "high": 568.5, "low": 319.3 }, "10529794": { "tradable": True, "mode": "ltp", "instrument_token": 10529794, "last_price": 28.35, "trading_symbol": "NIFTY2450222100PE", "high": 55.15, "low": 23.25 }, "10530050": { "tradable": True, "mode": "ltp", "instrument_token": 10530050, "last_price": 459.35, "trading_symbol": "NIFTY2450222150CE", "high": 518, "low": 280.1 }, "10530306": { "tradable": True, "mode": "ltp", "instrument_token": 10530306, "last_price": 33.15, "trading_symbol": "NIFTY2450222150PE", "high": 67.25, "low": 27.75 }, "10532098": { "tradable": True, "mode": "ltp", "instrument_token": 10532098, "last_price": 415, "trading_symbol": "NIFTY2450222200CE", "high": 477, "low": 242 }, "10532354": { "tradable": True, "mode": "ltp", "instrument_token": 10532354, "last_price": 39.3, "trading_symbol": "NIFTY2450222200PE", "high": 82.2, "low": 33.4 }, "10533634": { "tradable": True, "mode": "ltp", "instrument_token": 10533634, "last_price": 372.35, "trading_symbol": "NIFTY2450222250CE", "high": 434, "low": 208.15 }, "10533890": { "tradable": True, "mode": "ltp", "instrument_token": 10533890, "last_price": 45.95, "trading_symbol": "NIFTY2450222250PE", "high": 95, "low": 39.95 }, "10544386": { "tradable": True, "mode": "ltp", "instrument_token": 10544386, "last_price": 332, "trading_symbol": "NIFTY2450222300CE", "high": 392.8, "low": 176 }, "10544642": { "tradable": True, "mode": "ltp", "instrument_token": 10544642, "last_price": 55.1, "trading_symbol": "NIFTY2450222300PE", "high": 111.55, "low": 48.4 }, "10547714": { "tradable": True, "mode": "ltp", "instrument_token": 10547714, "last_price": 287.85, "trading_symbol": "NIFTY2450222350CE", "high": 351, "low": 146.25 }, "10548226": { "tradable": True, "mode": "ltp", "instrument_token": 10548226, "last_price": 63.45, "trading_symbol": "NIFTY2450222350PE", "high": 130.9, "low": 57.35 }, "10548994": { "tradable": True, "mode": "ltp", "instrument_token": 10548994, "last_price": 253.35, "trading_symbol": "NIFTY2450222400CE", "high": 311.5, "low": 119.3 }, "10549250": { "tradable": True, "mode": "ltp", "instrument_token": 10549250, "last_price": 76, "trading_symbol": "NIFTY2450222400PE", "high": 153.9, "low": 68.4 }, "10561026": { "tradable": True, "mode": "ltp", "instrument_token": 10561026, "last_price": 216.1, "trading_symbol": "NIFTY2450222450CE", "high": 273.6, "low": 96.4 }, "10562818": { "tradable": True, "mode": "ltp", "instrument_token": 10562818, "last_price": 89.1, "trading_symbol": "NIFTY2450222450PE", "high": 181, "low": 81.6 }, "10563586": { "tradable": True, "mode": "ltp", "instrument_token": 10563586, "last_price": 181.75, "trading_symbol": "NIFTY2450222500CE", "high": 236.05, "low": 75.25 }, "10563842": { "tradable": True, "mode": "ltp", "instrument_token": 10563842, "last_price": 105.5, "trading_symbol": "NIFTY2450222500PE", "high": 219.6, "low": 95.15 }, "10571778": { "tradable": True, "mode": "ltp", "instrument_token": 10571778, "last_price": 151, "trading_symbol": "NIFTY2450222550CE", "high": 203.25, "low": 58.85 }, "10572034": { "tradable": True, "mode": "ltp", "instrument_token": 10572034, "last_price": 125, "trading_symbol": "NIFTY2450222550PE", "high": 245, "low": 111.9 }, "10573314": { "tradable": True, "mode": "ltp", "instrument_token": 10573314, "last_price": 122.5, "trading_symbol": "NIFTY2450222600CE", "high": 171.1, "low": 44.55 }, "10573570": { "tradable": True, "mode": "ltp", "instrument_token": 10573570, "last_price": 146.8, "trading_symbol": "NIFTY2450222600PE", "high": 280, "low": 130.4 }, "10574082": { "tradable": True, "mode": "ltp", "instrument_token": 10574082, "last_price": 98, "trading_symbol": "NIFTY2450222650CE", "high": 142.8, "low": 30.25 }, "10575362": { "tradable": True, "mode": "ltp", "instrument_token": 10575362, "last_price": 169.85, "trading_symbol": "NIFTY2450222650PE", "high": 319.7, "low": 151.55 }, "10575618": { "tradable": True, "mode": "ltp", "instrument_token": 10575618, "last_price": 75.85, "trading_symbol": "NIFTY2450222700CE", "high": 117, "low": 24.4 }, "10575874": { "tradable": True, "mode": "ltp", "instrument_token": 10575874, "last_price": 200.75, "trading_symbol": "NIFTY2450222700PE", "high": 369.8, "low": 176 }, "10578178": { "tradable": True, "mode": 
            "ltp", "instrument_token": 10578178, "last_price": 57, "trading_symbol": "NIFTY2450222750CE", "high": 94.5, "low": 15.4 }, "10578434": { "tradable": True, "mode": "ltp", "instrument_token": 10578434, "last_price": 229.1, "trading_symbol": "NIFTY2450222750PE", "high": 400.7, "low": 204.25 }, "10579202": { "tradable": True, "mode": "ltp", "instrument_token": 10579202, "last_price": 42.05, "trading_symbol": "NIFTY2450222800CE", "high": 75.4, "low": 12.6 }, "10579458": { "tradable": True, "mode": "ltp", "instrument_token": 10579458, "last_price": 267.1, "trading_symbol": "NIFTY2450222800PE", "high": 445, "low": 235 }, "10581762": { "tradable": True, "mode": "ltp", "instrument_token": 10581762, "last_price": 30.25, "trading_symbol": "NIFTY2450222850CE", "high": 58.7, "low": 8.65 }, "10582018": { "tradable": True, "mode": "ltp", "instrument_token": 10582018, "last_price": 302.25, "trading_symbol": "NIFTY2450222850PE", "high": 475.25, "low": 268 }, "10582274": { "tradable": True, "mode": "ltp", "instrument_token": 10582274, "last_price": 20.9, "trading_symbol": "NIFTY2450222900CE", "high": 45.5, "low": 6.5 }, "10582530": { "tradable": True, "mode": "ltp", "instrument_token": 10582530, "last_price": 345.75, "trading_symbol": "NIFTY2450222900PE", "high": 540, "low": 305 }, "10584322": { "tradable": True, "mode": "ltp", "instrument_token": 10584322, "last_price": 14.5, "trading_symbol": "NIFTY2450222950CE", "high": 36.15, "low": 5.4 }, "10584578": { "tradable": True, "mode": "ltp", "instrument_token": 10584578, "last_price": 383.15, "trading_symbol": "NIFTY2450222950PE", "high": 565.8, "low": 346 }, "11167234": { "tradable": True, "mode": "ltp", "instrument_token": 11167234, "last_price": 1489.25, "trading_symbol": "BANKNIFTY2450847200CE", "high": 1545.7, "low": 1087.1 }, "11167490": { "tradable": True, "mode": "ltp", "instrument_token": 11167490, "last_price": 126.5, "trading_symbol": "BANKNIFTY2450847200PE", "high": 215.4, "low": 126.05 }, "11168258": { "tradable": True, "mode": "ltp", "instrument_token": 11168258, "last_price": 1360.3, "trading_symbol": "BANKNIFTY2450847300CE", "high": 1432, "low": 1018.05 }, "11170050": { "tradable": True, "mode": "ltp", "instrument_token": 11170050, "last_price": 140.75, "trading_symbol": "BANKNIFTY2450847300PE", "high": 243, "low": 139 }, "11170562": { "tradable": True, "mode": "ltp", "instrument_token": 11170562, "last_price": 1326.85, "trading_symbol": "BANKNIFTY2450847400CE", "high": 1366.7, "low": 935.6 }, "11171074": { "tradable": True, "mode": "ltp", "instrument_token": 11171074, "last_price": 174.95, "trading_symbol": "BANKNIFTY2450847400PE", "high": 265.5, "low": 154.5 }, "11171330": { "tradable": True, "mode": "ltp", "instrument_token": 11171330, "last_price": 1255, "trading_symbol": "BANKNIFTY2450847500CE", "high": 1318.45, "low": 638.35 }, "11171586": { "tradable": True, "mode": "ltp", "instrument_token": 11171586, "last_price": 170.4, "trading_symbol": "BANKNIFTY2450847500PE", "high": 300, "low": 170 }, "11172354": { "tradable": True, "mode": "ltp", "instrument_token": 11172354, "last_price": 1151.2, "trading_symbol": "BANKNIFTY2450847600CE", "high": 1240, "low": 793.4 }, "11173122": { "tradable": True, "mode": "ltp", "instrument_token": 11173122, "last_price": 193.7, "trading_symbol": "BANKNIFTY2450847600PE", "high": 329, "low": 189.1 }, "11173890": { "tradable": True, "mode": "ltp", "instrument_token": 11173890, "last_price": 1083.45, "trading_symbol": "BANKNIFTY2450847700CE", "high": 1145, "low": 677.55 }, "11174402": { "tradable": True, "mode": "ltp", "instrument_token": 11174402, "last_price": 205.65, "trading_symbol": "BANKNIFTY2450847700PE", "high": 355.45, "low": 205.65 }, "11175426": { "tradable": True, "mode": "ltp", "instrument_token": 11175426, "last_price": 1010, "trading_symbol": "BANKNIFTY2450847800CE", "high": 1069.8, "low": 655.7 }, "11177218": { "tradable": True, "mode": "ltp", "instrument_token": 11177218, "last_price": 231.75, "trading_symbol": "BANKNIFTY2450847800PE", "high": 379.8, "low": 230.2 }, "11177730": { "tradable": True, "mode": "ltp", "instrument_token": 11177730, "last_price": 921.25, "trading_symbol": "BANKNIFTY2450847900CE", "high": 1002.05, "low": 598.95 }, "11178242": { "tradable": True, "mode": "ltp", "instrument_token": 11178242, "last_price": 257.1, "trading_symbol": "BANKNIFTY2450847900PE", "high": 419, "low": 255.1 }, "11178498": { "tradable": True, "mode": "ltp", "instrument_token": 11178498, "last_price": 860.7, "trading_symbol": "BANKNIFTY2450848000CE", "high": 930.55, "low": 479 }, "11178754": { "tradable": True, "mode": "ltp", "instrument_token": 11178754, "last_price": 288.6, "trading_symbol": "BANKNIFTY2450848000PE", "high": 514.85, "low": 278.9 }, "11179778": { "tradable": True, "mode": "ltp", "instrument_token": 11179778, "last_price": 800, "trading_symbol": "BANKNIFTY2450848100CE", "high": 860, "low": 474.3 }, "11180546": { "tradable": True, "mode": "ltp", "instrument_token": 11180546, "last_price": 313.8, "trading_symbol": "BANKNIFTY2450848100PE", "high": 551.85, "low": 301.25 }, "11180802": { "tradable": True, "mode": "ltp", "instrument_token": 11180802, "last_price": 735.45, "trading_symbol": "BANKNIFTY2450848200CE", "high": 797.7, "low": 360.15 }, "11181058": { "tradable": True, "mode": "ltp", "instrument_token": 11181058, "last_price": 349, "trading_symbol": "BANKNIFTY2450848200PE", "high": 609.6, "low": 343.15 }, "11181314": { "tradable": True, "mode": "ltp", "instrument_token": 11181314, "last_price": 661.15, "trading_symbol": "BANKNIFTY2450848300CE", "high": 730, "low": 381.05 }, "11182850": { "tradable": True, "mode": "ltp", "instrument_token": 11182850, "last_price": 390.8, "trading_symbol": "BANKNIFTY2450848300PE", "high": 598.85, "low": 377.6 }, "11183106": { "tradable": True, "mode": "ltp", "instrument_token": 11183106, "last_price": 609, "trading_symbol": "BANKNIFTY2450848400CE", "high": 670.5, "low": 331.6 }, "11185154": { "tradable": True, "mode": "ltp", "instrument_token": 11185154, "last_price": 424.6, "trading_symbol": "BANKNIFTY2450848400PE", "high": 699, "low": 417.2 }, "11185410": { "tradable": True, "mode": "ltp", "instrument_token": 11185410, "last_price": 549.05, "trading_symbol": "BANKNIFTY2450848500CE", "high": 611.5, "low": 277 }, "11185666": { "tradable": True, "mode": "ltp", "instrument_token": 11185666, "last_price": 470, "trading_symbol": "BANKNIFTY2450848500PE", "high": 708.6, "low": 456.95 }, "11185922": { "tradable": True, "mode": "ltp", "instrument_token": 11185922, "last_price": 489, "trading_symbol": "BANKNIFTY2450848600CE", "high": 554.4, "low": 237 }, "11194626": { "tradable": True, "mode": "ltp", "instrument_token": 11194626, "last_price": 519, "trading_symbol": "BANKNIFTY2450848600PE", "high": 765.75, "low": 500.8 }, "11194882": { "tradable": True, "mode": "ltp", "instrument_token": 11194882, "last_price": 443, "trading_symbol": "BANKNIFTY2450848700CE", "high": 499.75, "low": 223.75 }, "11195138": { "tradable": True, "mode": "ltp", "instrument_token": 11195138, "last_price": 560, "trading_symbol": "BANKNIFTY2450848700PE", "high": 839.6, "low": 547 }, "11195394": { "tradable": True, "mode": "ltp", "instrument_token": 11195394, "last_price": 376.9, "trading_symbol": "BANKNIFTY2450848800CE", "high": 450, "low": 180 }, "11195650": { "tradable": True, "mode": "ltp", "instrument_token": 11195650, "last_price": 577.85, "trading_symbol": "BANKNIFTY2450848800PE", "high": 934.3, "low": 577.85 }, "11196162": { "tradable": True, "mode": "ltp", "instrument_token": 11196162, "last_price": 349.4, "trading_symbol": "BANKNIFTY2450848900CE", "high": 400.75, "low": 166.05 }, "11196418": { "tradable": True, "mode": "ltp", "instrument_token": 11196418, "last_price": 667.8, "trading_symbol": "BANKNIFTY2450848900PE", "high": 996.4, "low": 652.95 }, "11196674": { "tradable": True, "mode": "ltp", "instrument_token": 11196674, "last_price": 311.95, "trading_symbol": "BANKNIFTY2450849000CE", "high": 358.4, "low": 122.3 }, "11196930": { "tradable": True, "mode": "ltp", "instrument_token": 11196930, "last_price": 725.9, "trading_symbol": "BANKNIFTY2450849000PE", "high": 1053.75, "low": 704.6 }, "11198466": { "tradable": True, "mode": "ltp", "instrument_token": 11198466, "last_price": 269.1, "trading_symbol": "BANKNIFTY2450849100CE", "high": 316.8, "low": 120.35 }, "11201538": { "tradable": True, "mode": "ltp", "instrument_token": 11201538, "last_price": 787.3, "trading_symbol": "BANKNIFTY2450849100PE", "high": 1160.45, "low": 780.95 }, "11203330": { "tradable": True, "mode": "ltp", "instrument_token": 11203330, "last_price": 234.85, "trading_symbol": "BANKNIFTY2450849200CE", "high": 279.95, "low": 98.65 }, "11205122": { "tradable": True, "mode": "ltp", "instrument_token": 11205122, "last_price": 862.35, "trading_symbol": "BANKNIFTY2450849200PE", "high": 1229, "low": 826.3 }, "12672002": { "tradable": True, "mode": "ltp", "instrument_token": 12672002, "last_price": 1375.15, "trading_symbol": "BANKNIFTY2443047200CE", "high": 1461.8, "low": 918.4 }, "12672258": { "tradable": True, "mode": "ltp", "instrument_token": 12672258, "last_price": 44.95, "trading_symbol": "BANKNIFTY2443047200PE", "high": 103.2, "low": 43.45 }, "12672514": { "tradable": True, "mode": "ltp", "instrument_token": 12672514, "last_price": 1293.15, "trading_symbol": 
            "BANKNIFTY2443047300CE", "high": 1355, "low": 797 }, "12672770": { "tradable": True, "mode": "ltp", "instrument_token": 12672770, "last_price": 51.9, "trading_symbol": "BANKNIFTY2443047300PE", "high": 121.4, "low": 49.9 }, "12673026": { "tradable": True, "mode": "ltp", "instrument_token": 12673026, "last_price": 1201.95, "trading_symbol": "BANKNIFTY2443047400CE", "high": 1277.7, "low": 722 }, "12673282": { "tradable": True, "mode": "ltp", "instrument_token": 12673282, "last_price": 59.7, "trading_symbol": "BANKNIFTY2443047400PE", "high": 150, "low": 56.9 }, "12673538": { "tradable": True, "mode": "ltp", "instrument_token": 12673538, "last_price": 1101.1, "trading_symbol": "BANKNIFTY2443047500CE", "high": 1180, "low": 612.35 }, "12673794": { "tradable": True, "mode": "ltp", "instrument_token": 12673794, "last_price": 69, "trading_symbol": "BANKNIFTY2443047500PE", "high": 166.5, "low": 65.75 }, "12674306": { "tradable": True, "mode": "ltp", "instrument_token": 12674306, "last_price": 1014.9, "trading_symbol": "BANKNIFTY2443047600CE", "high": 1131.45, "low": 505.9 }, "12674562": { "tradable": True, "mode": "ltp", "instrument_token": 12674562, "last_price": 78.45, "trading_symbol": "BANKNIFTY2443047600PE", "high": 192.5, "low": 75.75 }, "12674818": { "tradable": True, "mode": "ltp", "instrument_token": 12674818, "last_price": 930.95, "trading_symbol": "BANKNIFTY2443047700CE", "high": 1007.15, "low": 485.5 }, "12675074": { "tradable": True, "mode": "ltp", "instrument_token": 12675074, "last_price": 93.45, "trading_symbol": "BANKNIFTY2443047700PE", "high": 223.9, "low": 88 }, "12675330": { "tradable": True, "mode": "ltp", "instrument_token": 12675330, "last_price": 840.4, "trading_symbol": "BANKNIFTY2443047800CE", "high": 920, "low": 420 }, "12676098": { "tradable": True, "mode": "ltp", "instrument_token": 12676098, "last_price": 107.55, "trading_symbol": "BANKNIFTY2443047800PE", "high": 260.95, "low": 101.5 }, "12676866": { "tradable": True, "mode": "ltp", "instrument_token": 12676866, "last_price": 769.85, "trading_symbol": "BANKNIFTY2443047900CE", "high": 837.8, "low": 362.55 }, "12677122": { "tradable": True, "mode": "ltp", "instrument_token": 12677122, "last_price": 125.85, "trading_symbol": "BANKNIFTY2443047900PE", "high": 288, "low": 117.55 }, "12677378": { "tradable": True, "mode": "ltp", "instrument_token": 12677378, "last_price": 685, "trading_symbol": "BANKNIFTY2443048000CE", "high": 756.25, "low": 306 }, "12677634": { "tradable": True, "mode": "ltp", "instrument_token": 12677634, "last_price": 143, "trading_symbol": "BANKNIFTY2443048000PE", "high": 338.55, "low": 136.5 }, "12677890": { "tradable": True, "mode": "ltp", "instrument_token": 12677890, "last_price": 607, "trading_symbol": "BANKNIFTY2443048100CE", "high": 678.25, "low": 257.55 }, "12678146": { "tradable": True, "mode": "ltp", "instrument_token": 12678146, "last_price": 168, "trading_symbol": "BANKNIFTY2443048100PE", "high": 379.7, "low": 158.45 }, "12679938": { "tradable": True, "mode": "ltp", "instrument_token": 12679938, "last_price": 535, "trading_symbol": 
            "BANKNIFTY2443048200CE", "high": 604.65, "low": 213.55 }, "12680194": { "tradable": True, "mode": "ltp", "instrument_token": 12680194, "last_price": 196.45, "trading_symbol": "BANKNIFTY2443048200PE", "high": 449.95, "low": 183.55 }, "12680450": { "tradable": True, "mode": "ltp", "instrument_token": 12680450, "last_price": 460.8, "trading_symbol": "BANKNIFTY2443048300CE", "high": 534.3, "low": 175.1 }, "12681218": { "tradable": True, "mode": "ltp", "instrument_token": 12681218, "last_price": 223.15, "trading_symbol": "BANKNIFTY2443048300PE", "high": 495.8, "low": 212.5 }, "12682498": { "tradable": True, "mode": "ltp", "instrument_token": 12682498, "last_price": 401.3, "trading_symbol": "BANKNIFTY2443048400CE", "high": 468.35, "low": 142.55 }, "12682754": { "tradable": True, "mode": "ltp", "instrument_token": 12682754, "last_price": 258, "trading_symbol": "BANKNIFTY2443048400PE", "high": 573.05, "low": 244.6 }, "12683010": { "tradable": True, "mode": "ltp", "instrument_token": 12683010, "last_price": 335, "trading_symbol": "BANKNIFTY2443048500CE", "high": 405.75, "low": 116.65 }, "12683778": { "tradable": True, "mode": "ltp", "instrument_token": 12683778, "last_price": 298.7, "trading_symbol": "BANKNIFTY2443048500PE", "high": 620, "low": 281.65 }, "12685058": { "tradable": True, "mode": "ltp", "instrument_token": 12685058, "last_price": 283, "trading_symbol": "BANKNIFTY2443048600CE", "high": 349.2, "low": 93.7 }, "12685314": { "tradable": True, "mode": "ltp", "instrument_token": 12685314, "last_price": 346.15, "trading_symbol": "BANKNIFTY2443048600PE", "high": 732, "low": 325.45 }, "12685826": { "tradable": True, "mode": "ltp", "instrument_token": 12685826, "last_price": 236, "trading_symbol": "BANKNIFTY2443048700CE", "high": 296.75, "low": 67.15 }, "12686082": { "tradable": True, "mode": "ltp", "instrument_token": 12686082, "last_price": 397.1, "trading_symbol": "BANKNIFTY2443048700PE", "high": 798.2, "low": 372.8 }, "12686338": { "tradable": True, "mode": "ltp", "instrument_token": 12686338, "last_price": 190, "trading_symbol": "BANKNIFTY2443048800CE", "high": 250, "low": 60.35 }, "12686594": { "tradable": True, "mode": "ltp", "instrument_token": 12686594, "last_price": 449, "trading_symbol": "BANKNIFTY2443048800PE", "high": 869.95, "low": 426 }, "12686850": { "tradable": True, "mode": "ltp", "instrument_token": 12686850, "last_price": 154.95, "trading_symbol": "BANKNIFTY2443048900CE", "high": 208.35, "low": 45.55 }, "12687618": { "tradable": True, "mode": "ltp", "instrument_token": 12687618, "last_price": 515, "trading_symbol": "BANKNIFTY2443048900PE", "high": 955.7, "low": 484 }, "12687874": { "tradable": True, "mode": "ltp", "instrument_token": 12687874, "last_price": 123.45, "trading_symbol": "BANKNIFTY2443049000CE", "high": 172.5, "low": 36.45 }, "12688130": { "tradable": True, "mode": "ltp", "instrument_token": 12688130, "last_price": 583.85, "trading_symbol": "BANKNIFTY2443049000PE", "high": 1072.5, "low": 550 }, "12688386": { "tradable": True, "mode": "ltp", "instrument_token": 12688386, "last_price": 95, "trading_symbol": "BANKNIFTY2443049100CE", "high": 140.9, "low": 28.15 }, "12688642": { "tradable": True, "mode": "ltp", "instrument_token": 12688642, "last_price": 660, "trading_symbol": "BANKNIFTY2443049100PE", "high": 1100, "low": 619.55 }, "12689922": { "tradable": True, "mode": "ltp", "instrument_token": 12689922, "last_price": 75, "trading_symbol": 
            "BANKNIFTY2443049200CE", "high": 115, "low": 21.4 }, "12690178": { "tradable": True, "mode": "ltp", "instrument_token": 12690178, "last_price": 725.6, "trading_symbol": "BANKNIFTY2443049200PE", "high": 1192.3, "low": 694.75 }, "17429506": { "tradable": True, "mode": "ltp", "instrument_token": 17429506, "last_price": 620.2, "trading_symbol": "NIFTY24APR21950CE", "high": 695.25, "low": 382.95 }, "17429762": { "tradable": True, "mode": "ltp", "instrument_token": 17429762, "last_price": 0.25, "trading_symbol": "NIFTY24APR21950PE", "high": 9.5, "low": 0.05 }, "17430018": { "tradable": True, "mode": "ltp", "instrument_token": 17430018, "last_price": 572.7, "trading_symbol": "NIFTY24APR22000CE", "high": 645.6, "low": 334 }, "17430274": { "tradable": True, "mode": "ltp", "instrument_token": 17430274, "last_price": 0.1, "trading_symbol": "NIFTY24APR22000PE", "high": 11.35, "low": 0.05 }, "17430530": { "tradable": True, "mode": "ltp", "instrument_token": 17430530, "last_price": 523.05, "trading_symbol": "NIFTY24APR22050CE", "high": 598.1, "low": 285.4 }, "17430786": { "tradable": True, "mode": "ltp", "instrument_token": 17430786, "last_price": 0.1, "trading_symbol": "NIFTY24APR22050PE", "high": 15, "low": 0.05 }, "17431042": { "tradable": True, "mode": "ltp", "instrument_token": 17431042, "last_price": 471.3, "trading_symbol": "NIFTY24APR22100CE", "high": 546.6, "low": 237.1 }, "17431298": { "tradable": True, "mode": "ltp", "instrument_token": 17431298, "last_price": 0.1, "trading_symbol": "NIFTY24APR22100PE", "high": 20.15, "low": 0.05 }, "17431554": { "tradable": True, "mode": "ltp", "instrument_token": 17431554, "last_price": 422.75, "trading_symbol": "NIFTY24APR22150CE", "high": 499, "low": 190.4 }, "17431810": { "tradable": True, "mode": "ltp", "instrument_token": 17431810, "last_price": 0.1, "trading_symbol": "NIFTY24APR22150PE", "high": 27.4, "low": 0.05 }, "17432066": { "tradable": True, "mode": "ltp", "instrument_token": 17432066, "last_price": 373.15, "trading_symbol": "NIFTY24APR22200CE", "high": 448.1, "low": 146.25 }, "17432322": { "tradable": True, "mode": "ltp", "instrument_token": 17432322, "last_price": 0.1, "trading_symbol": "NIFTY24APR22200PE", "high": 38.8, "low": 0.05 }, "17433090": { "tradable": True, "mode": "ltp", "instrument_token": 17433090, "last_price": 321, "trading_symbol": "NIFTY24APR22250CE", "high": 397.85, "low": 106.5 }, "17433346": { "tradable": True, "mode": "ltp", "instrument_token": 17433346, "last_price": 0.15, "trading_symbol": "NIFTY24APR22250PE", "high": 56.1, "low": 0.05 }, "17434114": { "tradable": True, "mode": "ltp", "instrument_token": 17434114, "last_price": 272.5, "trading_symbol": "NIFTY24APR22300CE", "high": 350.2, "low": 70 }, "17434370": { "tradable": True, "mode": "ltp", "instrument_token": 17434370, "last_price": 0.2, "trading_symbol": "NIFTY24APR22300PE", "high": 71.5, "low": 0.1 }, "17435138": { "tradable": True, "mode": "ltp", "instrument_token": 17435138, "last_price": 222, "trading_symbol": "NIFTY24APR22350CE", "high": 301.05, "low": 41.8 }, "17435394": { "tradable": True, "mode": "ltp", "instrument_token": 17435394, "last_price": 0.45, "trading_symbol": "NIFTY24APR22350PE", "high": 96, "low": 0.05 }, "17435650": { "tradable": True, "mode": "ltp", "instrument_token": 17435650, "last_price": 171.3, "trading_symbol": "NIFTY24APR22400CE", "high": 250.5, "low": 21.65 }, "17435906": { "tradable": True, "mode": "ltp", "instrument_token": 17435906, "last_price": 0.15, "trading_symbol": "NIFTY24APR22400PE", "high": 113, "low": 0.05 }, "17436674": { "tradable": True, "mode": "ltp", "instrument_token": 17436674, "last_price": 121.9, "trading_symbol": "NIFTY24APR22450CE", "high": 203.35, "low": 11.05 }, "17436930": { "tradable": True, "mode": "ltp", "instrument_token": 17436930, "last_price": 0.1, "trading_symbol": "NIFTY24APR22450PE", "high": 153, "low": 0.1 }, "17437186": { "tradable": True, "mode": "ltp", "instrument_token": 17437186, "last_price": 72, "trading_symbol": "NIFTY24APR22500CE", "high": 155.85, "low": 5 }, "17437442": { "tradable": True, "mode": "ltp", "instrument_token": 17437442, "last_price": 0.2, "trading_symbol": "NIFTY24APR22500PE", "high": 193.6, "low": 0.2 }, "17437698": { "tradable": True, "mode": "ltp", "instrument_token": 17437698, "last_price": 22, "trading_symbol": "NIFTY24APR22550CE", "high": 110.5, "low": 2.35 }, "17437954": { "tradable": True, "mode": "ltp", "instrument_token": 17437954, "last_price": 0.15, "trading_symbol": "NIFTY24APR22550PE", "high": 243.6, "low": 0.15 }, "17438210": { "tradable": True, "mode": "ltp", "instrument_token": 17438210, "last_price": 0.3, "trading_symbol": "NIFTY24APR22600CE", "high": 67.45, "low": 0.2 }, "17438466": { "tradable": True, "mode": "ltp", "instrument_token": 17438466, "last_price": 28.95, "trading_symbol": "NIFTY24APR22600PE", "high": 283.05, "low": 8.05 }, "17438722": { "tradable": True, "mode": "ltp", "instrument_token": 17438722, "last_price": 0.2, "trading_symbol": "NIFTY24APR22650CE", "high": 36.65, "low": 0.1 }, "17438978": { "tradable": True, "mode": "ltp", "instrument_token": 17438978, "last_price": 78.7, "trading_symbol": "NIFTY24APR22650PE", "high": 318.2, "low": 34.25 }, "17439234": { "tradable": True, "mode": "ltp", "instrument_token": 17439234, "last_price": 0.15, "trading_symbol": "NIFTY24APR22700CE", "high": 17.65, "low": 0.05 }, "17439490": { "tradable": True, "mode": "ltp", "instrument_token": 17439490, "last_price": 128.75, "trading_symbol": "NIFTY24APR22700PE", "high": 383.95, "low": 64.8 }, "17439746": { "tradable": True, "mode": "ltp", "instrument_token": 17439746, "last_price": 0.2, "trading_symbol": "NIFTY24APR22750CE", "high": 8.1, "low": 0.05 }, "17440002": { "tradable": True, "mode": "ltp", "instrument_token": 17440002, "last_price": 179.05, "trading_symbol": "NIFTY24APR22750PE", "high": 427.35, "low": 107.75 }, "17440258": { "tradable": True, "mode": "ltp", "instrument_token": 17440258, "last_price": 0.05, "trading_symbol": "NIFTY24APR22800CE", "high": 3.25, "low": 0.05 }, "17440514": { "tradable": True, "mode": "ltp", "instrument_token": 17440514, "last_price": 228.8, "trading_symbol": "NIFTY24APR22800PE", "high": 473.85, "low": 155.8 }, "17440770": { "tradable": True, "mode": "ltp", "instrument_token": 17440770, "last_price": 0.05, "trading_symbol": "NIFTY24APR22850CE", "high": 1.25, "low": 0.05 }, "17441026": { "tradable": True, "mode": "ltp", "instrument_token": 17441026, "last_price": 278.55, "trading_symbol": "NIFTY24APR22850PE", "high": 525.3, "low": 205 }, "17441282": { "tradable": True, "mode": "ltp", "instrument_token": 17441282, "last_price": 0.05, "trading_symbol": "NIFTY24APR22900CE", "high": 0.85, "low": 0.05 }, "17441538": { "tradable": True, "mode": "ltp", "instrument_token": 17441538, "last_price": 327.95, "trading_symbol": "NIFTY24APR22900PE", "high": 585.9, "low": 254.8 }, "17449474": { "tradable": True, "mode": "ltp", "instrument_token": 17449474, "last_price": 0.05, "trading_symbol": "NIFTY24APR22950CE", "high": 0.7, "low": 0.05 }, "17463810": { "tradable": True, "mode": "ltp", "instrument_token": 17463810, "last_price": 376.15, "trading_symbol": "NIFTY24APR22950PE", "high": 615.75, "low": 306.55 }, "210125061": { "tradable": True, "mode": "ltp", "instrument_token": 210125061, "last_price": 28, "trading_symbol": "SENSEX24APR73200PE", "high": 116.45, "low": 25 }, "210138117": { "tradable": True, "mode": "ltp", "instrument_token": 210138117, "last_price": 1278.75, "trading_symbol": "SENSEX24APR73100CE", "high": 1417.4, "low": 668.75 }, "210342917": { "tradable": True, "mode": "ltp", "instrument_token": 210342917, "last_price": 1452.9, "trading_symbol": "SENSEX24APR72900CE", "high": 1580, "low": 836.4 }, "210598917": { "tradable": True, "mode": "ltp", "instrument_token": 210598917, "last_price": 17, "trading_symbol": "SENSEX24APR72900PE", "high": 71.25, "low": 14.05 }, "210974725": { "tradable": True, "mode": "ltp", "instrument_token": 210974725, "last_price": 56.95, "trading_symbol": "SENSEX24APR73600PE", "high": 243.6, "low": 50.55 }, "210984197": { "tradable": True, "mode": "ltp", "instrument_token": 210984197, "last_price": 906.2, "trading_symbol": "SENSEX24APR73500CE", "high": 1060.35, "low": 369.85 }, "211124229": { "tradable": True, "mode": "ltp", "instrument_token": 211124229, "last_price": 23, "trading_symbol": "SENSEX24APR73100PE", "high": 99, "low": 17.85 }, "211136773": { "tradable": True, "mode": "ltp", "instrument_token": 211136773, "last_price": 1380.55, "trading_symbol": "SENSEX24APR73000CE", "high": 1520.5, "low": 748.6 }, "211244037": { "tradable": True, "mode": "ltp", "instrument_token": 211244037, "last_price": 48, "trading_symbol": "SENSEX24APR73500PE", "high": 203.35, "low": 41.7 }, "211254533": { "tradable": True, "mode": "ltp", "instrument_token": 211254533, "last_price": 996.85, "trading_symbol": "SENSEX24APR73400CE", "high": 1141.85, "low": 405.55 }, "211396869": { "tradable": True, "mode": "ltp", "instrument_token": 211396869, "last_price": 19.55, "trading_symbol": "SENSEX24APR73000PE", "high": 82.75, "low": 16.35 }, "211513093": { "tradable": True, "mode": "ltp", "instrument_token": 211513093, "last_price": 39.85, "trading_symbol": 
            "SENSEX24APR73400PE", "high": 169.65, "low": 35.4 }, "212277253": { "tradable": True, "mode": "ltp", "instrument_token": 212277253, "last_price": 1085.85, "trading_symbol": "SENSEX24APR73300CE", "high": 1234.2, "low": 511.35 }, "212518405": { "tradable": True, "mode": "ltp", "instrument_token": 212518405, "last_price": 722.9, "trading_symbol": "SENSEX24APR73700CE", "high": 878.85, "low": 242 }, "212663557": { "tradable": True, "mode": "ltp", "instrument_token": 212663557, "last_price": 30.5, "trading_symbol": "SENSEX24APR73300PE", "high": 141.5, "low": 29.7 }, "212676357": { "tradable": True, "mode": "ltp", "instrument_token": 212676357, "last_price": 1175, "trading_symbol": "SENSEX24APR73200CE", "high": 1322.65, "low": 577.25 }, "212778245": { "tradable": True, "mode": "ltp", "instrument_token": 212778245, "last_price": 70.6, "trading_symbol": "SENSEX24APR73700PE", "high": 289.95, "low": 60.45 }, "212791045": { "tradable": True, "mode": "ltp", "instrument_token": 212791045, "last_price": 813.8, "trading_symbol": "SENSEX24APR73600CE", "high": 952.5, "low": 299.8 }, "213441541": { "tradable": True, "mode": "ltp", "instrument_token": 213441541, "last_price": 594.8, "trading_symbol": "SENSEX24APR74900PE", "high": 1145.3, "low": 512.75 }, "213445637": { "tradable": True, "mode": "ltp", "instrument_token": 213445637, "last_price": 91.05, "trading_symbol": "SENSEX24APR74800CE", "high": 165.55, "low": 12.3 }, "213477893": { "tradable": True, "mode": "ltp", "instrument_token": 213477893, "last_price": 268.45, "trading_symbol": "SENSEX24APR74400PE", "high": 778.25, "low": 230.5 }, "213480709": { "tradable": True, "mode": "ltp", "instrument_token": 213480709, "last_price": 271.6, "trading_symbol": "SENSEX24APR74300CE", "high": 415.05, "low": 48.5 }, "213500933": { "tradable": True, "mode": "ltp", "instrument_token": 213500933, "last_price": 520, "trading_symbol": "SENSEX24APR74800PE", "high": 1094.4, "low": 445.95 }, "213506053": { "tradable": True, "mode": "ltp", "instrument_token": 213506053, "last_price": 115, "trading_symbol": "SENSEX24APR74700CE", "high": 203.5, "low": 19.35 }, "213534469": { "tradable": True, "mode": "ltp", "instrument_token": 213534469, "last_price": 215, "trading_symbol": "SENSEX24APR74300PE", "high": 691.25, "low": 192.8 }, "213536517": { "tradable": True, "mode": "ltp", "instrument_token": 213536517, "last_price": 329.75, "trading_symbol": "SENSEX24APR74200CE", "high": 480.45, "low": 65.35 }, "213554181": { "tradable": True, "mode": "ltp", "instrument_token": 213554181, "last_price": 451.45, "trading_symbol": "SENSEX24APR74700PE", "high": 1043.35, "low": 384.55 }, "213581573": { "tradable": True, "mode": "ltp", "instrument_token": 213581573, "last_price": 178, "trading_symbol": "SENSEX24APR74200PE", "high": 610.7, "low": 159.85 }, "213626117": { "tradable": True, "mode": "ltp", "instrument_token": 213626117, "last_price": 554.15, "trading_symbol": "SENSEX24APR73900CE", "high": 705.15, "low": 151.85 }, "213672453": { "tradable": True, "mode": "ltp", "instrument_token": 213672453, "last_price": 93.4, "trading_symbol": "SENSEX24APR73900PE", "high": 401.1, "low": 89.5 }, "213695493": { "tradable": True, "mode": "ltp", "instrument_token": 213695493, "last_price": 138, "trading_symbol": "SENSEX24APR74600CE", "high": 248.25, "low": 18.15 }, "213723397": { "tradable": True, "mode": "ltp", "instrument_token": 213723397, "last_price": 397.3, "trading_symbol": "SENSEX24APR74100CE", "high": 548.4, "low": 87.2 }, "213741573": { "tradable": True, "mode": "ltp", "instrument_token": 213741573, "last_price": 395, "trading_symbol": "SENSEX24APR74600PE", "high": 950, "low": 327.9 }, "213745413": { "tradable": True, "mode": "ltp", "instrument_token": 213745413, "last_price": 192, "trading_symbol": "SENSEX24APR74500CE", "high": 296.85, "low": 30 }, "213770757": { "tradable": True, "mode": "ltp", "instrument_token": 213770757, "last_price": 68, "trading_symbol": "SENSEX24APR74900CE", "high": 130.2, "low": 8.5 }, "213774597": { "tradable": True, "mode": "ltp", "instrument_token": 213774597, "last_price": 138, "trading_symbol": "SENSEX24APR74100PE", "high": 535.7, "low": 131.5 }, "213776389": { "tradable": True, "mode": "ltp", "instrument_token": 213776389, "last_price": 477, "trading_symbol": "SENSEX24APR74000CE", "high": 625.95, "low": 115.05 }, "213797381": { "tradable": True, "mode": "ltp", "instrument_token": 213797381, "last_price": 326, "trading_symbol": "SENSEX24APR74500PE", "high": 865.25, "low": 276.55 }, "213800453": { "tradable": True, "mode": "ltp", "instrument_token": 213800453, "last_price": 214.15, "trading_symbol": "SENSEX24APR74400CE", "high": 355, "low": 34.35 }, "213817093": { "tradable": True, "mode": "ltp", "instrument_token": 213817093, "last_price": 639.25, "trading_symbol": "SENSEX24APR73800CE", "high": 787.6, "low": 188.65 }, "213824773": { "tradable": True, "mode": "ltp", "instrument_token": 213824773, "last_price": 118, "trading_symbol": "SENSEX24APR74000PE", "high": 468.15, "low": 107.8 }, "213867525": { "tradable": True, "mode": "ltp", "instrument_token": 213867525, "last_price": 80, "trading_symbol": "SENSEX24APR73800PE", "high": 341.1, "low": 74 }, "222608901": { "tradable": True, "mode": "ltp", "instrument_token": 222608901, "last_price": 274.95, "trading_symbol": "SENSEX2450373600PE", "high": 442.85, "low": 258.05 }, "222609925": { "tradable": True, "mode": "ltp", "instrument_token": 222609925, "last_price": 1160.15, "trading_symbol": "SENSEX2450373500CE", "high": 1263.85, "low": 696.4 }, "222610949": { "tradable": True, "mode": "ltp", "instrument_token": 222610949, "last_price": 325.4, "trading_symbol": "SENSEX2450373800PE", "high": 519.85, "low": 309.75 }, "222611461": { "tradable": True, "mode": "ltp", "instrument_token": 222611461, "last_price": 522.8, "trading_symbol": "SENSEX2450374500CE", "high": 641.55, "low": 251.3 }, "222612485": { "tradable": True, "mode": "ltp", "instrument_token": 222612485, "last_price": 978.45, "trading_symbol": "SENSEX2450373700CE", "high": 1130, "low": 601 }, "222612997": { "tradable": True, "mode": "ltp", "instrument_token": 222612997, "last_price": 180.65, "trading_symbol": "SENSEX2450373100PE", "high": 299.4, "low": 160 }, "222614021": { "tradable": True, "mode": "ltp", "instrument_token": 222614021, "last_price": 442.65, "trading_symbol": "SENSEX2450374700CE", "high": 442.65, "low": 272.15 }, "222614533": { "tradable": True, "mode": "ltp", "instrument_token": 222614533, "last_price": 1560, "trading_symbol": 
            "SENSEX2450373000CE", "high": 1560, "low": 1195.25 }, "222616325": { "tradable": True, "mode": "ltp", "instrument_token": 222616325, "last_price": 205.05, "trading_symbol": "SENSEX2450373300PE", "high": 354.45, "low": 194.3 }, "222617349": { "tradable": True, "mode": "ltp", "instrument_token": 222617349, "last_price": 801, "trading_symbol": "SENSEX2450374000CE", "high": 954.2, "low": 383.6 }, "222618117": { "tradable": True, "mode": "ltp", "instrument_token": 222618117, "last_price": 290.85, "trading_symbol": "SENSEX2450374900CE", "high": 420.7, "low": 216.95 }, "222619397": { "tradable": True, "mode": "ltp", "instrument_token": 222619397, "last_price": 518, "trading_symbol": "SENSEX2450374300PE", "high": 736.1, "low": 484.95 }, "222619909": { "tradable": True, "mode": "ltp", "instrument_token": 222619909, "last_price": 175.05, "trading_symbol": "SENSEX2450372900PE", "high": 175.05, "low": 175.05 }, "222620933": { "tradable": True, "mode": "ltp", "instrument_token": 222620933, "last_price": 677, "trading_symbol": "SENSEX2450374200CE", "high": 793.65, "low": 360.3 }, "222622469": { "tradable": True, "mode": "ltp", "instrument_token": 222622469, "last_price": 590, "trading_symbol": "SENSEX2450374500PE", "high": 860.3, "low": 570 }, "222624261": { "tradable": True, "mode": "ltp", "instrument_token": 222624261, "last_price": 577, "trading_symbol": "SENSEX2450374400CE", "high": 691.5, "low": 293.8 }, "222625541": { "tradable": True, "mode": "ltp", "instrument_token": 222625541, "last_price": 665.7, "trading_symbol": "SENSEX2450374700PE", "high": 994.95, "low": 500 }, "222626565": { "tradable": True, "mode": "ltp", "instrument_token": 222626565, "last_price": 460.2, "trading_symbol": "SENSEX2450374600CE", "high": 761.45, "low": 303.35 }, "222627077": { "tradable": True, "mode": "ltp", "instrument_token": 222627077, "last_price": 396, "trading_symbol": "SENSEX2450374000PE", "high": 666, "low": 373.35 }, "222627845": { "tradable": True, "mode": "ltp", "instrument_token": 222627845, "last_price": 1139.45, "trading_symbol": "SENSEX2450374900PE", "high": 1139.45, "low": 1139.45 }, "222629381": { "tradable": True, "mode": "ltp", "instrument_token": 222629381, "last_price": 243.35, "trading_symbol": "SENSEX2450374800CE", "high": 243.35, "low": 243.35 }, "222629893": { "tradable": True, "mode": "ltp", "instrument_token": 222629893, "last_price": 465, "trading_symbol": "SENSEX2450374200PE", "high": 678.1, "low": 450.2 }, "222631941": { "tradable": True, "mode": "ltp", "instrument_token": 222631941, "last_price": 749.5, "trading_symbol": "SENSEX2450374100CE", "high": 849.2, "low": 408.25 }, "222633989": { "tradable": True, "mode": "ltp", "instrument_token": 222633989, "last_price": 580, "trading_symbol": "SENSEX2450374400PE", "high": 797, "low": 497.7 }, "222635013": { "tradable": True, "mode": "ltp", "instrument_token": 222635013, "last_price": 605, "trading_symbol": "SENSEX2450374300CE", "high": 740.8, "low": 326 }, "222636037": { "tradable": True, "mode": "ltp", "instrument_token": 222636037, "last_price": 1249.2, "trading_symbol": "SENSEX2450372900CE", "high": 1249.2, "low": 1249.2 }, "222637061": { "tradable": True, "mode": "ltp", "instrument_token": 222637061, "last_price": 914.6, "trading_symbol": "SENSEX2450374600PE", "high": 926.35, "low": 871 }, "222638853": { "tradable": True, "mode": "ltp", "instrument_token": 222638853, "last_price": 853.9, "trading_symbol": "SENSEX2450373900CE", "high": 989.3, "low": 454.4 }, "222640645": { "tradable": True, "mode": "ltp", "instrument_token": 222640645, "last_price": 1066.05, "trading_symbol": "SENSEX2450374800PE", "high": 1066.05, "low": 1066.05 }, "222640901": { "tradable": True, "mode": "ltp", "instrument_token": 222640901, "last_price": 1026.55, "trading_symbol": "SENSEX2450373200CE", "high": 1026.55, "low": 1026.55 }, "222642181": { "tradable": True, "mode": "ltp", "instrument_token": 222642181, "last_price": 246.4, "trading_symbol": "SENSEX2450373500PE", "high": 449.1, "low": 237.15 }, "222642437": { "tradable": True, "mode": "ltp", "instrument_token": 222642437, "last_price": 417.05, "trading_symbol": "SENSEX2450374100PE", "high": 693.65, "low": 404.45 }, "222643461": { "tradable": True, "mode": "ltp", "instrument_token": 222643461, "last_price": 890.3, "trading_symbol": "SENSEX2450373400CE", "high": 890.3, "low": 890.3 }, "222644741": { "tradable": True, "mode": "ltp", "instrument_token": 222644741, "last_price": 283.15, "trading_symbol": "SENSEX2450373700PE", "high": 486.4, "low": 282.45 }, "222646277": { "tradable": True, "mode": "ltp", "instrument_token": 222646277, "last_price": 1040.95, "trading_symbol": "SENSEX2450373600CE", "high": 1206.75, "low": 618.05 }, "222647813": { "tradable": True, "mode": "ltp", "instrument_token": 222647813, "last_price": 164.3, "trading_symbol": "SENSEX2450373000PE", "high": 285, "low": 147.8 }, "222648581": { "tradable": True, "mode": "ltp", "instrument_token": 222648581, "last_price": 350, "trading_symbol": "SENSEX2450373900PE", "high": 593, "low": 338.25 }, "222650117": { "tradable": True, "mode": "ltp", "instrument_token": 222650117, "last_price": 921.7, "trading_symbol": "SENSEX2450373800CE", "high": 1055.5, "low": 506.05 }, "222650629": { "tradable": True, "mode": "ltp", "instrument_token": 222650629, "last_price": 192.2, "trading_symbol": "SENSEX2450373200PE", "high": 330.55, "low": 184.1 }, "222652165": { "tradable": True, "mode": "ltp", "instrument_token": 222652165, "last_price": 1098.4, "trading_symbol": "SENSEX2450373100CE", "high": 1098.4, "low": 1098.4 }, "222653701": { "tradable": True, "mode": "ltp", "instrument_token": 222653701, "last_price": 227.5, "trading_symbol": "SENSEX2450373400PE", "high": 362.95, "low": 219.95 }, "222654725": { "tradable": True, "mode": "ltp", "instrument_token": 222654725, "last_price": 957.15, "trading_symbol": "SENSEX2450373300CE", "high": 957.15, "low": 957.15 } }

        self.logger.info("inside generate_intraday_test_trade")
        bank_nifty_nearest_expiry = nearest_expiry_map.get('BANKNIFTY')
        from_date = get_ist_datetime(datetime.now())-timedelta(days=522)
        to_date = get_ist_datetime(datetime.now())
        index_min_data = []
        curr_to_date = from_date
        while curr_to_date < to_date:
            curr_to_date = curr_to_date + timedelta(days=59)
            if curr_to_date > to_date:
                curr_from_date = curr_to_date - timedelta(days=58)
                curr_to_date = to_date
            else:
                curr_from_date = curr_to_date - timedelta(days=58)
                if curr_to_date == from_date + timedelta(days=59):
                    curr_from_date = curr_to_date - timedelta(days=59)
            index_min_data.extend(self.historical_data(kite, 260105, curr_from_date,
                                            curr_to_date, "minute", False))
        
        self.index_min_data = index_min_data
        
        # bank_nifty_nearest_expiry = '30APR'
        nearest_expiry_map['BANKNIFTY'] = bank_nifty_nearest_expiry

        for data in index_min_data:
            date = data['date']

            close = data['close']

            sample_tick_map_data['260105']['last_price'] = close

            nearest_strike_price = int(close) - (int(close) % 100)
            atm_price = -1

            if abs(nearest_strike_price - close) < abs(nearest_strike_price + 100 - close):
                atm_price = nearest_strike_price
            else:
                atm_price = nearest_strike_price + 100
            
            bank_nifty_pe_first_otm_price = atm_price - 100
            bank_nifty_ce_first_otm_price = atm_price + 100

            bank_nifty_pe_first_itm_price = atm_price + 100
            bank_nifty_ce_first_itm_price = atm_price - 100


            # bank_nifty_nearest_expiry = '24430'

            # CE Side
            possible_trading_symbol1 = 'BANKNIFTY%s%sCE' % (bank_nifty_nearest_expiry, bank_nifty_ce_first_otm_price)
            possible_trading_symbol2 = 'BANKNIFTY%s%sCE' % (self.convert_date(bank_nifty_nearest_expiry), bank_nifty_ce_first_otm_price)

            inst_token_key = "BANKNIFTY-%s-%s-%s" % (
            self.get_complete_date(bank_nifty_nearest_expiry), bank_nifty_ce_first_otm_price, 'CE')

            inst_token = inst_token_map.get(inst_token_key)

            sample_tick_map_data['%s' % inst_token] = { "tradable": True, "mode": "ltp", "instrument_token": inst_token, "last_price": 205.05, "trading_symbol": possible_trading_symbol2, "high": 354.45, "low": 194.3 }

            # CE ITM
            possible_trading_symbol1 = 'BANKNIFTY%s%sCE' % (bank_nifty_nearest_expiry, bank_nifty_ce_first_itm_price)
            possible_trading_symbol2 = 'BANKNIFTY%s%sCE' % (self.convert_date(bank_nifty_nearest_expiry), bank_nifty_ce_first_itm_price)

            inst_token_key = "BANKNIFTY-%s-%s-%s" % (
            self.get_complete_date(bank_nifty_nearest_expiry), bank_nifty_ce_first_itm_price, 'CE')

            inst_token = inst_token_map.get(inst_token_key)

            sample_tick_map_data['%s' % inst_token] = { "tradable": True, "mode": "ltp", "instrument_token": inst_token, "last_price": 205.05, "trading_symbol": possible_trading_symbol2, "high": 354.45, "low": 194.3 }


            # PE Side
            possible_trading_symbol1 = 'BANKNIFTY%s%sPE' % (bank_nifty_nearest_expiry, bank_nifty_pe_first_otm_price)
            possible_trading_symbol2 = 'BANKNIFTY%s%sPE' % (self.convert_date(bank_nifty_nearest_expiry), bank_nifty_pe_first_otm_price)

            inst_token_key = "BANKNIFTY-%s-%s-%s" % (
            self.get_complete_date(bank_nifty_nearest_expiry), bank_nifty_pe_first_otm_price, 'PE')

            inst_token = inst_token_map.get(inst_token_key)

            sample_tick_map_data['%s' % inst_token] = { "tradable": True, "mode": "ltp", "instrument_token": inst_token, "last_price": 205.05, "trading_symbol": possible_trading_symbol2, "high": 354.45, "low": 194.3 }

            # PE ITM
            possible_trading_symbol1 = 'BANKNIFTY%s%sPE' % (bank_nifty_nearest_expiry, bank_nifty_pe_first_itm_price)
            possible_trading_symbol2 = 'BANKNIFTY%s%sPE' % (self.convert_date(bank_nifty_nearest_expiry), bank_nifty_pe_first_itm_price)

            inst_token_key = "BANKNIFTY-%s-%s-%s" % (
            self.get_complete_date(bank_nifty_nearest_expiry), bank_nifty_pe_first_itm_price, 'PE')

            inst_token = inst_token_map.get(inst_token_key)

            sample_tick_map_data['%s' % inst_token] = { "tradable": True, "mode": "ltp", "instrument_token": inst_token, "last_price": 205.05, "trading_symbol": possible_trading_symbol2, "high": 354.45, "low": 194.3 }


            self.generate_trade_based_on_fib(kite, sample_tick_map_data, nearest_expiry_map, now=date, analyse=True)

            time.sleep(1)

        trades = TelegramTrade.objects.filter(
                Q(order_status='ANALYSE')
            ).order_by('created_at_time')
        total_sum = 0
        drawdown_loss_cnt = 0
        max_drawdown = -100000
        max_drawdown_loss_cnt = -100000
        consecutive_loss_cnt = 0
        max_consecutive_loss_cnt = 0
        consecutive_loss_percent = 0
        max_consecutive_loss_percent = -100000
        last_trade = None
        profit_cnt = 0
        loss_cnt = 0
        ror = 0
        for trade in trades:
            metadata = trade.get_metadata_as_dict()
            profit_percent = metadata['profit_percent']
            target_hit_cnt = metadata['target_hit_cnt']
            sl_hit_cnt = metadata['sl_hit_cnt']
            entry_end_price = trade.entry_end_price
            exit_first_target_price = trade.exit_first_target_price
            exit_second_target_price = trade.exit_second_target_price
            exit_third_target_price = trade.exit_third_target_price
            exit_stop_loss_price = trade.exit_stop_loss_price
            curr_ror = 0
            if target_hit_cnt == 1:
                curr_ror = 0.8 * (exit_first_target_price - entry_end_price) / (entry_end_price - exit_stop_loss_price)
            elif target_hit_cnt == 2:
                curr_ror = 0.8 * (exit_first_target_price - entry_end_price) / (entry_end_price - exit_stop_loss_price)
                # curr_ror += 0.2 * (exit_second_target_price - entry_end_price) / (entry_end_price - exit_stop_loss_price)
            elif target_hit_cnt == 3:
                curr_ror = 0.8 * (exit_first_target_price - entry_end_price) / (entry_end_price - exit_stop_loss_price)
                curr_ror += 0.2 * (exit_third_target_price - entry_end_price) / (entry_end_price - exit_stop_loss_price)
            elif sl_hit_cnt == 1:
                curr_ror -= 1
            metadata['ror'] = curr_ror
            ror += curr_ror
            total_sum += profit_percent
            if profit_percent > 0:
                drawdown_loss_cnt -= 1
                consecutive_loss_cnt = 0
                consecutive_loss_percent = 0
                profit_cnt += 1
            elif profit_percent < 0:
                drawdown_loss_cnt += 1
                consecutive_loss_cnt += 1
                consecutive_loss_percent += profit_percent
                loss_cnt += 1
            if total_sum < 0:
                max_drawdown = max(max_drawdown, total_sum)
            
            max_drawdown_loss_cnt = max(max_drawdown_loss_cnt, drawdown_loss_cnt)

            max_consecutive_loss_cnt = max(consecutive_loss_cnt, max_consecutive_loss_cnt)

            max_consecutive_loss_percent = max(max_consecutive_loss_percent, consecutive_loss_percent)

            trade.set_metadata_from_dict(metadata)
            trade.save()

            last_trade = trade

        self.logger.info("max_drawdown percent: %s" % max_drawdown)
        self.logger.info("max_drawdown_loss_cnt: %s" % max_drawdown_loss_cnt)
        self.logger.info("max_consecutive_loss_cnt: %s" % max_consecutive_loss_cnt)
        self.logger.info("max_consecutive_loss_percent: %s" % max_consecutive_loss_percent)
        self.logger.info("profit_cnt: %s" % profit_cnt)
        self.logger.info("loss_cnt: %s" % loss_cnt)

        self.logger.info("net_profit percent: %s" % total_sum)
        self.logger.info("net_ror: %s" % ror)

        
        
        if last_trade is not None:
            metadata = last_trade.get_metadata_as_dict()
            metadata['net_ror'] = ror
            last_trade.set_metadata_from_dict(metadata)
            last_trade.save()
        #     metadata = last_trade.get_metadata_as_dict()
            metadata['max_drawdown_percent'] = max_drawdown
            metadata['max_drawdown_loss_cnt'] = max_drawdown_loss_cnt
            metadata['max_consecutive_loss_cnt'] = max_consecutive_loss_cnt
            metadata['max_consecutive_loss_percent'] = max_consecutive_loss_percent
            metadata['profit_cnt'] = profit_cnt
            metadata['loss_cnt'] = loss_cnt
            metadata['net_profit_percent'] = total_sum
            last_trade.set_metadata_from_dict(metadata)
            last_trade.save()

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


            



        

