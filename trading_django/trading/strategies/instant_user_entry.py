import logging
import bisect

from trading.strategies.entry import Entry
from trading.helpers import get_ist_datetime, get_nearest_tens


class InstantUserEntry(Entry):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.risk = 6000
        self.exit_target_percent_list = [70, 30]

    def check_entry_criteria_and_update_metadata_and_status(self, kite, tick_last_price, trade, inst_token, timestamp, tick_map):
        metadata = super().check_entry_criteria_and_update_metadata_and_status(kite,
                                                                               tick_last_price,
                                                                               trade,
                                                                               inst_token, timestamp, tick_map)
        # if metadata['price_point_at_entry_time'] == 'ABOVE':
        #     if metadata['close_count_below_entry_price'] > 0:
        #         if metadata['close_count_above_entry_price'] >= 2:
        #             trade.order_status = 'NOT_PLACED_ENTRY_ALLOWED'
        # super().update_stop_loss_for_normal_entry(trade, metadata, timestamp)
        # if metadata['close_count_above_entry_price'] >= 2:
        trade.order_status = 'NOT_PLACED_ENTRY_ALLOWED'
        metadata['estimated_stop_loss_percent'] = metadata['given_stop_loss_percent']
        self.discount_percent_list.append(metadata['given_stop_loss_percent'])
        self.discount_percent_list.sort()
        # super().update_stop_loss_for_normal_entry(trade, metadata, timestamp)
        trade.set_metadata_from_dict(metadata)
        trade.save()

    def process_prices_and_quantities(self, trade):
        metadata = trade.get_metadata_as_dict()
        real_stop_loss_percent = metadata['estimated_stop_loss_percent']
        if trade.entry_end_price is None or trade.entry_end_price == trade.entry_start_price:
            trade.entry_end_price = round(trade.entry_start_price * 1.02, 1)
        # Discount percent is same as stop loss percent
        first_target_price_1_to_1_ror = trade.entry_end_price * self.reward_to_risk_ratio * (
                100 + real_stop_loss_percent) / 100

        curr_first_target_price = trade.exit_first_target_price
        curr_second_target_price = trade.exit_second_target_price
        curr_third_target_price = trade.exit_third_target_price

        metadata['targets'] = [curr_first_target_price,
                               curr_second_target_price,
                               curr_third_target_price]

        self.process_quantities(trade, metadata, real_stop_loss_percent)

        # trade.entry_start_price = discounted_entry_start_price
        # trade.exit_stop_loss_price = round(trade.entry_start_price * (1 - (real_stop_loss_percent / 100)), 1)

        if trade.exit_first_target_price != curr_first_target_price:
            trade.exit_first_target_price = curr_first_target_price
        if trade.exit_second_target_price != curr_second_target_price:
            trade.exit_second_target_price = curr_second_target_price
        if trade.exit_third_target_price != curr_third_target_price:
            trade.exit_third_target_price = curr_third_target_price
        # if trade.exit_stop_loss_price == 0:
        #     trade.exit_stop_loss_price = round(
        #         trade.entry_start_price * (1 - (self.hero_zero_stop_loss_percent / 100)), 1)
        # if prices_changed:
        trade.order_status = 'NOT_PLACED_PRICES_PROCESSED'
        # reset close_count_below_stop_loss_price to 0 as prices changes
        metadata['close_count_below_stop_loss_price'] = 0
        trade.set_metadata_from_dict(metadata)
        trade.save()
