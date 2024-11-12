import logging
import bisect

from trading.strategies.entry import Entry
from trading.helpers import get_ist_datetime, get_nearest_tens


class NormalEntry(Entry):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.risk = 0

    def check_entry_criteria_and_update_metadata_and_status(self, kite, tick_last_price, trade, inst_token, timestamp, tick_map):
        metadata = super().check_entry_criteria_and_update_metadata_and_status(kite,
                                                                               tick_last_price,
                                                                               trade,
                                                                               inst_token, timestamp, tick_map)
        # if metadata['price_point_at_entry_time'] == 'ABOVE':
        #     if metadata['close_count_below_entry_price'] > 0:
        #         if metadata['close_count_above_entry_price'] >= 2:
        #             trade.order_status = 'NOT_PLACED_ENTRY_ALLOWED'
        super().update_stop_loss_for_normal_entry(trade, metadata, timestamp)
        if metadata['close_count_above_entry_price'] >= 2:
            trade.order_status = 'NOT_PLACED_ENTRY_ALLOWED'
        trade.set_metadata_from_dict(metadata)
        trade.save()

