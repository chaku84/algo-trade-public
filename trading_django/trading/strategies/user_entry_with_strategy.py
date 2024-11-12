import logging
import talib
import numpy as np
import re
import json

from datetime import datetime, timedelta, date
from trading.strategies.entry import Entry
from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.strategies.rolling_redis_queue import RollingRedisQueue


class UserEntryWithStrategy(Entry):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.risk = 0
        self.exit_target_percent_list = [20, 50, 30]

    def check_entry_criteria_and_update_metadata_and_status(self, kite, tick_last_price, trade, inst_token, timestamp, tick_map):
        metadata = super().check_entry_criteria_and_update_metadata_and_status(kite,
                                                                               tick_last_price,
                                                                               trade,
                                                                               inst_token, timestamp, tick_map)
        # trade_created_time = get_ist_datetime(trade.created_at_time)
        # rolling_redis_queue = RollingRedisQueue('%s_%s_%s' % (inst_token, trade.entry_type, date.today()), 30)
        # if not rolling_redis_queue.key_exists() or rolling_redis_queue.get_size() == 0:
        #     min_data = kite.historical_data(inst_token,
        #                                     timestamp - timedelta(minutes=30),
        #                                     timestamp, "minute", False)
        #     close_prices = np.array([data['close'] for data in min_data])
        #     for price in close_prices:
        #         rolling_redis_queue.enqueue({'timestamp': timestamp, 'price': price})
        #     # rolling_redis_queue.enqueue(tick_last_price)
        # else:
        #     # assert rolling_redis_queue.get_size() == 30
        #     last_added_timestamp = rolling_redis_queue.get_last()['timestamp']
        #     last_added_timestamp_obj = datetime.strptime(last_added_timestamp, '%Y-%m-%d %H:%M:%S.%f%z')
        #
        #     time_diff = timestamp - last_added_timestamp_obj
        #
        #     # Convert the difference to minutes
        #     minutes_diff = int(time_diff.total_seconds() / 60)
        #
        #     if minutes_diff >= 2:
        #         min_data = kite.historical_data(inst_token,
        #                                         timestamp - timedelta(minutes=minutes_diff-1),
        #                                         timestamp, "minute", False)
        #         # close_prices = np.array([data['close'] for data in min_data])
        #         for data in min_data:
        #             rolling_redis_queue.enqueue({'timestamp': timestamp, 'price': data['close']})
        #     else:
        #         rolling_redis_queue.enqueue({'timestamp': timestamp, 'price': tick_last_price})
        #     # assert rolling_redis_queue.get_size() == 30
        #     close_prices = [data['price'] for data in rolling_redis_queue.fetch_queue()]
        #     close_prices = np.array(close_prices)
        # timestamp = get_ist_datetime(timestamp)
        min_data = kite.historical_data(inst_token,
                                        timestamp - timedelta(minutes=30),
                                        timestamp, "minute", False)
        # print(inst_token)
        # print(timestamp)
        # print(timestamp - timedelta(minutes=30))
        # print(json.dumps(min_data, default=str))
        close_prices = np.array([data['close'] for data in min_data])

        # Calculate the Bollinger Bands
        # Length of the moving average window (number of periods)
        ma_length = 10
        # Number of standard deviations for the upper and lower bands
        num_std_dev = 2

        upper_band, middle_band, lower_band = talib.BBANDS(close_prices, timeperiod=ma_length, nbdevup=num_std_dev,
                                                           nbdevdn=num_std_dev)

        # Calculate RSI
        rsi_period = 14  # RSI period
        rsi = talib.RSI(close_prices, timeperiod=rsi_period)

        # Calculate moving average
        ma_period = 10  # MA period
        ma = talib.SMA(close_prices, timeperiod=ma_period)
        if rsi[-1] >= 60:
            metadata['rsi_count_above_60'] = metadata.get('rsi_count_above_60', 0) + 1
        elif 'rsi_count_above_60' not in metadata:
            metadata['rsi_count_above_60'] = 0

        if metadata['market_high_price'] >= trade.exit_first_target_price:
            trade.order_status = 'EXPIRED'
        elif metadata['rsi_count_above_60'] > 0 and rsi[-1] < 60 and metadata['close_count_above_entry_price'] >= 1:
            trade.entry_start_price = round(ma[-1] - ((ma[-1] - lower_band[-1]) / 3), 1) * 0.98
            trade.entry_end_price = round(ma[-1] - ((ma[-1] - lower_band[-1]) / 3), 1)
            trade.order_status = 'NOT_PLACED_ENTRY_ALLOWED'
            # rolling_redis_queue.delete_key()

        super().update_stop_loss_for_normal_entry(trade, metadata, timestamp)

        # if metadata['price_point_at_entry_time'] == 'ABOVE':
        #     if metadata['close_count_below_entry_price'] > 0:
        #         if metadata['close_count_above_entry_price'] >= 2:
        #             trade.order_status = 'NOT_PLACED_ENTRY_ALLOWED'
        # if metadata['close_count_above_entry_price'] >= 2:
        #     trade.order_status = 'NOT_PLACED_ENTRY_ALLOWED'
        trade.set_metadata_from_dict(metadata)
        trade.save()
