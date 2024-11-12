import logging
import calendar
from datetime import datetime
import talib
import numpy as np
from login import Login
from instruments import Instruments
from common import get_price, get_nearest_expiry
import pandas as pd



login = Login()
login.login()
kite = login.kite
access_token = login.access_token
request_token = login.request_token

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

interval = '3minute'  # Timeframe for historical data

# Fetch historical data
today = pd.Timestamp.now().date()
from_date = today - pd.Timedelta(days=10)  # 30 days historical data
to_date = today

historical_data = kite.historical_data(instrument_token=256265, from_date=from_date, to_date=to_date, interval=interval)

# Convert data to DataFrame
df = pd.DataFrame(historical_data)

# Calculate RSI (Relative Strength Index) and moving averages
df['rsi'] = talib.RSI(df['close'], timeperiod=7)
df['sma_50'] = talib.SMA(df['close'], timeperiod=50)
df['sma_200'] = talib.SMA(df['close'], timeperiod=200)

# Initialize position and entry price
position = None
entry_price = 0


# Define a simple momentum strategy with exit logic
def momentum_strategy(data):
    global position
    global entry_price

    if data['rsi'].iloc[-1] > 70 and data['close'].iloc[-1] > data['sma_50'].iloc[-1] > data['sma_200'].iloc[-1]:
        if position != 'buy':
            # Buy the option
            print('Buy:', 'Price:', data['close'].iloc[-1])
            position = 'buy'
            entry_price = data['close'].iloc[-1]
        return 'HOLD'

    elif data['rsi'].iloc[-1] < 50:
        if position == 'buy':
            # Sell the option
            print('Sell:', 'Exit Price:', data['close'].iloc[-1], 'Entry Price:', entry_price)
            position = None
            entry_price = 0
        return 'SELL'

    else:
        return 'HOLD'


# Implement the strategy
for i in range(len(df)):
    signal = momentum_strategy(df.iloc[:i + 1])
    print("Signal:", signal)
