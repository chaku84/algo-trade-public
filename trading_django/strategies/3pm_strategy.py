import logging
from kiteconnect import KiteConnect, KiteTicker
import requests
import pyotp
import json
import os
import time
from kiteconnect.exceptions import TokenException
import calendar
import math
from datetime import datetime
import talib
import traceback
import numpy as np
import bisect
from login import Login
from instruments import Instruments
from common import get_price, get_nearest_expiry


login = Login()
login.login()
kite = login.kite
access_token = login.access_token
request_token = login.request_token



# # Place an order
# try:
#     order_id = kite.place_order(tradingsymbol="INFY",
#                                 exchange=kite.EXCHANGE_NSE,
#                                 transaction_type=kite.TRANSACTION_TYPE_BUY,
#                                 quantity=1,
#                                 variety=kite.VARIETY_AMO,
#                                 order_type=kite.ORDER_TYPE_MARKET,
#                                 product=kite.PRODUCT_CNC,
#                                 validity=kite.VALIDITY_DAY)
#
#     logging.info("Order placed. ID is: {}".format(order_id))
# except Exception as e:
#     logging.info("Order placement failed: {}".format(e.message))


inst_obj = Instruments(kite)
inst_obj.load_instruments()
inst_obj.update_tokens_and_expiry()

instruments = inst_obj.instruments
risk_percent = inst_obj.risk_percent
reward_percent = inst_obj.reward_percent
max_allowed_lots = inst_obj.max_allowed_lots
nifty_option_inst_token_map = inst_obj.nifty_option_inst_token_map
bank_nifty_option_inst_token_map = inst_obj.bank_nifty_option_inst_token_map
nifty_price_list = inst_obj.nifty_price_list
bank_nifty_price_list = inst_obj.bank_nifty_price_list
nifty_nearest_expiry = inst_obj.nifty_nearest_expiry
bank_nifty_nearest_expiry = inst_obj.bank_nifty_nearest_expiry
min_nifty_expiry_diff = inst_obj.min_nifty_expiry_diff
min_bank_nifty_expiry_diff = inst_obj.min_bank_nifty_expiry_diff
nifty_50_inst_token = inst_obj.nifty_50_inst_token
bank_nifty_inst_token = inst_obj.bank_nifty_inst_token
nifty_expiry_list = inst_obj.nifty_expiry_list
bank_nifty_expiry_list = inst_obj.bank_nifty_expiry_list

# print(nifty_option_inst_token_map)

# nifty_nearest_expiry = '23AUG'

nifty_nearest_expiry = get_nearest_expiry(nifty_expiry_list, datetime.now())
print(nifty_nearest_expiry)

print(instruments[0])

def analyse_3pm_strategy():
    count = 0
    profit_count = 0
    profit_percent = 0
    year = 2023
    for month in range(1):
        month+= 8
        for day in range(10):
            day += 0
            print("Month: %s" %calendar.month_name[month+1])
            try:
                from_date = datetime(year, month+1, day+1, 9, 30)  # Replace with the desired start date and time
                to_date = datetime(year, month + 1, day+1, 15, 30)  # Replace with the desired end date and time

                # nifty_nearest_expiry = '23824'
                print(nifty_nearest_expiry)

                # Get historical data from Kite API (minute candle)
                historical_data = kite.historical_data(nifty_50_inst_token, from_date, to_date, "minute", False)

                # Extract low and high prices from the historical data between 2:55 pm and 2:59 pm
                _2_55_candle_data = kite.historical_data(nifty_50_inst_token, datetime(year, month+1, day + 1, 14, 55), datetime(year, month+1, day + 1, 15, 10), '5minute')
                if len(_2_55_candle_data) < 1:
                    continue

                entry_low_price = _2_55_candle_data[0]['low']
                entry_high_price = _2_55_candle_data[0]['high']

                print("entry_low_price: %s" % entry_low_price)
                print("entry_high_price: %s" % entry_high_price)

                # Calculate 9-period Exponential Moving Average (EMA) for exit criteria
                ema_period = 9
                close_prices = [item['close'] for item in historical_data]

                ema_values = talib.EMA(np.array(close_prices), timeperiod=ema_period)

                # print(close_prices)
                # print(ema_values)

                # Initialize position and entry price
                position = None
                entry_price = None
                entry_option_price = None

                max_diff_ema = 0
                is_position_open = False
                position_time = None

                # Backtesting loop
                for i in range(len(historical_data)):
                    date = historical_data[i]['date']
                    # print(date)
                    if date.timestamp() < datetime(year, month+1, day + 1, 15, 0, 0).timestamp():
                        continue
                    current_close = close_prices[i]
                    current_ema = ema_values[i]
                    print(current_close)
                    print(current_ema)

                    # Entry condition: Buy PE if current price is below low, Buy CE if current price is above high
                    if position is None:
                        if current_close < entry_low_price:
                            entry_price = current_close
                            position = "Long PE"
                            itm_nifty_price = get_price('ITM',1, 'PUT', nifty_price_list, entry_price)
                            put_option_inst_token = nifty_option_inst_token_map["NIFTY-%s-%s-PE" % (nifty_nearest_expiry, itm_nifty_price)]
                            print("NIFTY-%s-%s-PE" % (nifty_nearest_expiry, itm_nifty_price))
                            curr_put_option_price = kite.historical_data(put_option_inst_token, date, datetime.fromtimestamp(date.timestamp() + 120), 'minute')[0]['close']
                            entry_option_price = curr_put_option_price
                            print("entry_option_price: %s" %entry_option_price)
                            print(f"{date}: Buy PE at {entry_price}")
                            is_position_open = True
                            position_time = date.timestamp()
                        elif current_close > entry_high_price:
                            entry_price = current_close
                            position = "Long CE"
                            itm_nifty_price = get_price('ITM', 1, 'CALL', nifty_price_list, entry_price)
                            call_option_inst_token = nifty_option_inst_token_map["NIFTY-%s-%s-CE" % (nifty_nearest_expiry, itm_nifty_price)]
                            print("NIFTY-%s-%s-PE" % (nifty_nearest_expiry, itm_nifty_price))
                            curr_call_option_price = kite.historical_data(call_option_inst_token, date, datetime.fromtimestamp(date.timestamp() + 120),
                                                 'minute')[0]['close']
                            entry_option_price = curr_call_option_price
                            print("entry_option_price: %s" %entry_option_price)
                            print(f"{date}: Buy CE at {entry_price}")
                            is_position_open = True
                            position_time = date.timestamp()

                    # Exit condition: Sell if EMA difference decreases by 1% or more
                    if position is not None and date.timestamp() > position_time:
                        diff_ema = abs(current_close - current_ema)
                        # itm_nifty_price = get_price('ITM', 1, 'PUT' if position == 'Long PE' else 'CALL', nifty_price_list, current_close)
                        # print("NIFTY%s%s%s" % (nifty_nearest_expiry, itm_nifty_price, 'PE' if position == 'Long CE' else 'CE'))
                        option_inst_token = call_option_inst_token if position == 'Long CE' else put_option_inst_token
                        curr_option_price = \
                        kite.historical_data(option_inst_token, date, datetime.fromtimestamp(date.timestamp() + 120),
                                             'minute')[0]['close']
                        close_option_price = curr_option_price
                        print("close_option_price: %s" %close_option_price)
                        is_position_open = False
                        if (1 - (diff_ema / max_diff_ema)) >= 0.1\
                                :
                            print(f"{date}: Sell {position} at {current_close}")
                            position = None
                            count += 1
                            if position == 'Long CE':
                                if current_close > entry_price:
                                    profit_count += 1
                                # print(((close_option_price - entry_option_price) / entry_option_price) * 100)
                                profit_percent += max(-1, ((curr_option_price - entry_option_price) / entry_option_price) * 100)

                            else:
                                if current_close < entry_price:
                                    profit_count += 1
                                # print(((close_option_price - entry_option_price) / entry_option_price) * 100)
                                profit_percent += max(-1, ((curr_option_price - entry_option_price) / entry_option_price) * 100)
                            # if profit_percent < 0:
                            #     print("Lost all money")
                            #     break
                        else:
                            max_diff_ema = max(max_diff_ema, diff_ema)
                if is_position_open:
                    print("Positions are still open")
                    raise RuntimeException("Positions are still open")
                else:
                    break
            except Exception as e:
                print(e)
            print("Monthly Profit percent: %s" %profit_percent)

    print(count)
    print(profit_count)
    print(profit_percent)


# analyse_3pm_strategy()

curr_nifty_price = 20168
call_itm_nifty_price = get_price('ITM', 1, 'CALL', nifty_price_list, curr_nifty_price)
call_option_inst_token = nifty_option_inst_token_map["NIFTY-%s-%s-CE" % (nifty_nearest_expiry, call_itm_nifty_price)]
#
#
from_date = datetime.fromtimestamp(datetime.now().timestamp() - 60000)
to_date = datetime.now()
historical_data = kite.historical_data(call_option_inst_token, from_date, to_date, "minute", False)
call_option_chart_close_price = historical_data[0]['close']
print(call_option_chart_close_price)
# try:
#     order_id = kite.place_order(tradingsymbol="NIFTY2392120200PE",
#                                 exchange="NFO",
#                                 transaction_type=kite.TRANSACTION_TYPE_BUY,
#                                 quantity=50,
#                                 variety=kite.VARIETY_REGULAR,
#                                 order_type=kite.ORDER_TYPE_MARKET,
#                                 product=kite.PRODUCT_NRML,
#                                 validity=kite.VALIDITY_DAY)
#
#
#     logging.info("Order placed. ID is: {}".format(order_id))
#
#     order_history = kite.order_history(order_id)
#     logging.info(order_history)
#     last_price = order_history[len(order_history) - 1]['average_price']
#
#     # last_price = 63.95
#
#     order = kite.place_gtt(trigger_type=kite.GTT_TYPE_OCO,
#                            tradingsymbol="NIFTY2392120200PE",
#                            exchange="NFO",
#                            trigger_values=[last_price * 0.9 - 0.5, last_price * 1.1 + 0.5],
#                            last_price=last_price,
#                            orders=[{
#                               "exchange": "NFO",
#                               "tradingsymbol": "NIFTY2392120200PE",
#                               "transaction_type": "SELL",
#                               "quantity": 50,
#                               "order_type": "LIMIT",
#                               "product": "NRML",
#                               "price": last_price * 0.9
#                             },
#                                {
#                                    "exchange": "NFO",
#                                    "tradingsymbol": "NIFTY2392120200PE",
#                                    "transaction_type": "SELL",
#                                    "quantity": 50,
#                                    "order_type": "MARKET",
#                                    "product": "NRML",
#                                    "price": last_price * 1.1
#                                }
#                            ])
# except Exception as e:
#     logging.info("Order placement failed: {}".format(e.message))

put_itm_nifty_price = get_price('ITM', 1, 'PUT', nifty_price_list, curr_nifty_price)
put_option_inst_token = nifty_option_inst_token_map["NIFTY-%s-%s-PE" % (nifty_nearest_expiry, put_itm_nifty_price)]

kws = KiteTicker("2s3d6ngrn9fa5bsf", access_token)

def on_ticks(ws, ticks):
    # Callback to receive ticks.
    logging.debug("Ticks: {}".format(ticks))
    for tick in ticks:
        if tick['instrument_token'] == nifty_50_inst_token:
            curr_nifty_price = tick['ohlc']['close']
            curr_call_itm_nifty_price = get_price('ITM', 1, 'CALL', nifty_price_list, curr_nifty_price)
            print("NIFTY-%s-%s-CE" % (nifty_nearest_expiry, curr_call_itm_nifty_price))
            curr_call_option_inst_token = nifty_option_inst_token_map[
                "NIFTY-%s-%s-CE" % (nifty_nearest_expiry, curr_call_itm_nifty_price)]

            is_inst_token_updated = False
            if curr_call_option_inst_token != kws.call_option_inst_token:
                kws.call_option_inst_token = curr_call_option_inst_token
                is_inst_token_updated = True

            curr_put_itm_nifty_price = get_price('ITM', 1, 'PUT', nifty_price_list, curr_nifty_price)
            curr_put_option_inst_token = nifty_option_inst_token_map[
                "NIFTY-%s-%s-PE" % (nifty_nearest_expiry, curr_put_itm_nifty_price)]
            print("NIFTY-%s-%s-PE" % (nifty_nearest_expiry, curr_put_itm_nifty_price))

            if curr_put_option_inst_token != kws.put_option_inst_token:
                kws.put_option_inst_token = curr_put_option_inst_token
                is_inst_token_updated = True

            if is_inst_token_updated:
                kws.connect()
    # time.sleep(60)

    # if datetime.now().hour >= 16:
    #     kws.close()

def on_connect(ws, response):
    # Callback on successful connect.
    # Subscribe to a list of instrument_tokens (RELIANCE and ACC here).

    ws.subscribe([nifty_50_inst_token])

    # Set RELIANCE to tick in `full` mode.
    ws.set_mode(ws.MODE_FULL, [nifty_50_inst_token])

def on_close(ws, code, reason):
    # On connection close stop the main loop
    # Reconnection will not happen after executing `ws.stop()`
    # ws.stop()
    ws.stop()
    print(f"WebSocket closed with code {code}: {reason}")


# Assign the callbacks.
kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.call_option_inst_token = call_option_inst_token
kws.put_option_inst_token = put_option_inst_token

# Infinite loop on the main thread. Nothing after this will run.
# You have to use the pre-defined callbacks to manage subscriptions.
kws.connect()


# Place an mutual fund order
# kite.place_mf_order(
#     tradingsymbol="INF090I01239",
#     transaction_type=kite.TRANSACTION_TYPE_BUY,
#     amount=5000,
#     tag="mytag"
# )
#
# # Cancel a mutual fund order
# kite.cancel_mf_order(order_id="order_id")
#
# # Get mutual fund instruments
# kite.mf_instruments()
