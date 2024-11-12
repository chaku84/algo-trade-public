import logging
import bisect
import re
import math
import time
import traceback
from datetime import datetime, timedelta

from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.models import Funds
from django.db.models import Q


class Entry(object):
    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.risk = 5000
        self.discount_percent_list = [4, 8, 13, 17, 25, 33, 50, 67, 78]
        self.exit_target_percent_list = [80, 10, 10]
        # self.discount_exit_target_percent_list = [50, 30, 10, 10]
        self.discount_time = '11:30'
        self.nifty_lot_size = 50
        self.bank_nifty_lot_size = 15
        self.mid_cap_nifty_lot_size = 75
        self.sensex_lot_size = 10
        self.reward_to_risk_ratio = 1
        self.hero_zero_stop_loss_percent = 67

    def check_entry_criteria_and_update_metadata_and_status(self, kite, tick_last_price, trade, inst_token, timestamp, tick_map):
        trade.entry_end_price = trade.entry_start_price
        admin_fund = Funds.objects.filter(
                    Q(user_login__email='seepak12@gmail.com')
                ).first()
        self.risk = (admin_fund.investment_amount_per_year * admin_fund.risk_percentage) / 100
        # self.logger.info(admin_fund.created_by)
        # self.logger.info(admin_fund.investment_amount_per_year)
        # self.logger.info(admin_fund.risk_percentage)
        metadata = trade.get_metadata_as_dict()
        if metadata is None:
            metadata = {'entry_start_price': trade.entry_start_price,
                        'entry_end_price': trade.entry_end_price,
                        'exit_stop_loss_price': trade.exit_stop_loss_price}
        else:
            metadata['entry_start_price'] = trade.entry_start_price
            metadata['entry_end_price'] = trade.entry_end_price
            metadata['exit_stop_loss_price'] = trade.exit_stop_loss_price
            if 'forced_risk' in metadata:
                self.risk = metadata['forced_risk']
        
        if 'negative_position' not in metadata:
            net_positions = kite.positions()['net']
            net_pnl = 0
            sl_cnt = 0
            for position in net_positions:
                net_pnl += position['pnl']
                if position['pnl'] < 0 and abs(position['pnl']) >= self.risk * 0.1:
                    sl_cnt += int(abs(position['pnl']) / self.risk)
            
            if (net_pnl < 0 and sl_cnt >= 2) or (net_pnl < 0 and int(abs(net_pnl) / self.risk) >= 2):
                metadata['negative_position'] = True
            
            if (net_pnl > 0 and int(abs(net_pnl) / self.risk) >= 2):
                self.risk /= 3
            
        trade_created_time = get_ist_datetime(trade.created_at_time)
        if 'price_point_at_entry_time' not in metadata:
            # if trade.entry_end_price is not None:
            #     trade.entry_start_price = round((trade.entry_start_price + trade.entry_end_price) / 2, 1)
            if timestamp.minute == trade_created_time.minute:
                entry_time_price = trade.entry_start_price

            else:
                entry_time_min_data = kite.historical_data(inst_token,
                                                           trade_created_time - timedelta(minutes=2),
                                                           trade_created_time, "minute", False)
                if len(entry_time_min_data) > 0:
                    entry_time_price = entry_time_min_data[len(entry_time_min_data) - 1]['close']
                else:
                    entry_time_price = tick_last_price
            if entry_time_price >= trade.entry_start_price:
                metadata['price_point_at_entry_time'] = 'ABOVE'
            else:
                metadata['price_point_at_entry_time'] = 'BELOW'

        if 'given_stop_loss_percent' not in metadata:
            stop_loss_percent = ((trade.entry_end_price - trade.exit_stop_loss_price) / trade.entry_end_price) * 100
            metadata['given_stop_loss_percent'] = abs(stop_loss_percent)
            metadata['estimated_stop_loss_percent'] = self.discount_percent_list[
                min(max(0, bisect.bisect_left(self.discount_percent_list, stop_loss_percent)),
                 len(self.discount_percent_list) - 1)]

        close_count_above_entry_price = metadata.get('close_count_above_entry_price', 0)
        close_count_below_entry_price = metadata.get('close_count_below_entry_price', 0)
        close_count_below_stop_loss_price = metadata.get('close_count_below_stop_loss_price', 0)
        market_high_price = metadata.get('market_high_price', 0)
        # last_15_min_data = kite.historical_data(inst_token,
        #                                         trade_created_time - timedelta(minutes=15),
        #                                         trade_created_time - timedelta(minutes=1), "minute", False)
        # for data in last_15_min_data:
        #     if data['close'] >= metadata['entry_start_price']:
        #         close_count_above_entry_price += 1
        #     else:
        #         close_count_below_entry_price += 1
        if timestamp.second % 59 == 0:
            prev_min_data = kite.historical_data(inst_token,
                                                    trade_created_time,
                                                    timestamp, "minute", False)
            close_count_above_entry_price = 0
            close_count_below_entry_price = 0      
            for data in prev_min_data:
                if data['close'] >= metadata['entry_start_price']:
                    close_count_above_entry_price += 1
                else:
                    close_count_below_entry_price += 1
            # if tick_last_price >= trade.entry_end_price:
            #     self.logger.info("hour: %s, minute: %s, second: %s, tick_last_price: %s" % (timestamp.hour, timestamp.minute, timestamp.second, tick_last_price))
            #     close_count_above_entry_price += 1
            # else:
            #     close_count_below_entry_price += 1
            if tick_last_price <= metadata['exit_stop_loss_price']:
                close_count_below_stop_loss_price += 1
        if tick_map[inst_token]['high'] >= market_high_price:
            market_high_price = tick_map[inst_token]['high']
        metadata['market_high_price'] = market_high_price
        metadata['close_count_above_entry_price'] = close_count_above_entry_price
        # metadata['close_count_below_entry_price'] = close_count_below_entry_price
        # metadata['close_count_below_stop_loss_price'] = close_count_below_stop_loss_price
        if 'inst_token' not in metadata:
            metadata['inst_token'] = inst_token
        if 'exchange' not in metadata:
            metadata['exchange'] = 'NFO'
            if trade.index_name == 'SENSEX':
                metadata['exchange'] = 'BFO'
        if 'funds' not in metadata:
            margins = kite.margins()
            metadata['funds'] = margins['equity']['net']
        if trade.exit_second_target_price is None:
            trade.exit_second_target_price = trade.exit_first_target_price
        if trade.exit_third_target_price is None:
            trade.exit_third_target_price = trade.exit_first_target_price
        return metadata

    def update_stop_loss_for_normal_entry(self, trade, metadata, timestamp):
        # if metadata['given_stop_loss_percent'] <= 17:
        #     metadata['estimated_stop_loss_percent'] = 17
        # elif metadata['given_stop_loss_percent'] <= 33:
        #     metadata['estimated_stop_loss_percent'] = 33
        # else:
        #     metadata['estimated_stop_loss_percent'] = 67
        expiry = trade.expiry.replace(' ', '')
        curr_expiry_date = int(re.findall(r'\d+', expiry)[0])
        if curr_expiry_date == timestamp.day or curr_expiry_date == (timestamp + timedelta(days=1)).day:
            # Is Today expiry
            if timestamp.hour < 11 or (timestamp.hour == 11 and timestamp.minute <= 30) and\
                    metadata['estimated_stop_loss_percent'] <= 33:
                metadata['estimated_stop_loss_percent'] = 33
            else:
                metadata['estimated_stop_loss_percent'] = 67

    def process_quantities(self, trade, metadata, real_stop_loss_percent):
        quantity_stop_loss_percent = self.discount_percent_list[
            min(bisect.bisect_left(self.discount_percent_list, real_stop_loss_percent),
                len(self.discount_percent_list) - 1)]
        if quantity_stop_loss_percent <= 10:
            quantity_stop_loss_percent = 13
        quantity_stop_loss_percent = real_stop_loss_percent
        lot_size = 50
        trade_name = trade.index_name.replace(' ', '')
        if trade_name == 'NIFTY':
            lot_size = self.nifty_lot_size
        elif trade_name == 'BANKNIFTY':
            lot_size = self.bank_nifty_lot_size
        elif trade_name == 'MIDCPNIFTY':
            lot_size = self.mid_cap_nifty_lot_size
        elif trade_name == 'SENSEX':
            lot_size = self.sensex_lot_size
        estimated_quantity = self.risk / ((quantity_stop_loss_percent / 100) * trade.entry_end_price)
        max_loop_cnt = 100
        while 'funds' in metadata and trade.entry_end_price * estimated_quantity >= metadata['funds'] and max_loop_cnt > 0:
            required_margin = trade.entry_end_price * estimated_quantity
            estimated_quantity = max(lot_size, int(metadata['funds'] / trade.entry_end_price) - lot_size)
            self.logger.info("Reqruied Margin: {} is greater than the avaiable funds: {}."
            " So Updating estimated_quantity to {}".format(required_margin, metadata['funds'], estimated_quantity))
            max_loop_cnt -= 1
        estimated_quantity = max(lot_size, estimated_quantity)
        estimated_quantity = int(int(estimated_quantity / lot_size) * lot_size)
        trade.quantity = estimated_quantity
        remaining_quantity = estimated_quantity
        percent_sum = 100
        prev_target_quantity_sum = 0
        metadata['quantities'] = []
        for i in range(len(self.exit_target_percent_list)):
            curr_target_quantity = 0
            if remaining_quantity > 0:
                curr_target_quantity = math.floor(
                    (remaining_quantity * self.exit_target_percent_list[i] / percent_sum) / lot_size) * lot_size
                if curr_target_quantity == 0:
                    curr_target_quantity = remaining_quantity
                if curr_target_quantity + prev_target_quantity_sum > estimated_quantity:
                    curr_target_quantity -= lot_size
            metadata['quantities'].append(curr_target_quantity)
            remaining_quantity -= curr_target_quantity
            percent_sum -= self.exit_target_percent_list[i]
            prev_target_quantity_sum += curr_target_quantity
        # pass

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
        trade.exit_stop_loss_price = round(trade.entry_start_price * (1 - (real_stop_loss_percent / 100)), 1)

        if trade.exit_first_target_price != curr_first_target_price:
            trade.exit_first_target_price = curr_first_target_price
        if trade.exit_second_target_price != curr_second_target_price:
            trade.exit_second_target_price = curr_second_target_price
        if trade.exit_third_target_price != curr_third_target_price:
            trade.exit_third_target_price = curr_third_target_price
        if trade.exit_stop_loss_price == 0:
            trade.exit_stop_loss_price = round(
                trade.entry_start_price * (1 - (self.hero_zero_stop_loss_percent / 100)), 1)
        # if prices_changed:
        trade.order_status = 'NOT_PLACED_PRICES_PROCESSED'
        # reset close_count_below_stop_loss_price to 0 as prices changes
        metadata['close_count_below_stop_loss_price'] = 0
        trade.set_metadata_from_dict(metadata)
        trade.save()

    def place_order(self, kite, trade, trading_symbol, last_price):
        # order = kite.place_gtt(
        #     trigger_type=kite.GTT_TYPE_OCO,
        #     tradingsymbol=trading_symbol,
        #     exchange="NFO",
        #     trigger_values=[trade.entry_start_price,
        #                     trade.entry_end_price],
        #     last_price=last_price,
        #     orders=[{
        #         "exchange": "NFO",
        #         "tradingsymbol": trading_symbol,
        #         "transaction_type": "BUY",
        #         "quantity": trade.quantity,
        #         "order_type": "LIMIT",
        #         "product": kite.PRODUCT_MIS,
        #         "price": trade.entry_start_price - 0.5
        #     },
        #         {
        #             "exchange": "NFO",
        #             "tradingsymbol": trading_symbol,
        #             "transaction_type": "BUY",
        #             "quantity": trade.quantity,
        #             "order_type": "LIMIT",
        #             "product": kite.PRODUCT_MIS,
        #             "price": trade.entry_end_price - 0.5
        #         }
        #     ])
        if self.risk > 0 and trade.quantity > 0:
            metadata = trade.get_metadata_as_dict()
            exchange = metadata.get('exchange', 'NFO')
            order = kite.place_gtt(
                trigger_type=kite.GTT_TYPE_SINGLE,
                tradingsymbol=trading_symbol,
                exchange=exchange,
                trigger_values=[round(trade.entry_end_price, 1)],
                last_price=last_price,
                orders=[
                    {
                        "exchange": exchange,
                        "tradingsymbol": trading_symbol,
                        "transaction_type": "BUY",
                        "quantity": trade.quantity,
                        "order_type": "LIMIT",
                        "product": kite.PRODUCT_MIS,
                        "price": round(trade.entry_end_price * 1.02, 1)
                    }
                ])
            order_id = str(order['trigger_id'])
            trade.order_id = order_id
            trade.order_status = 'ORDER_ENTRY_PLACED'
            trade.save()

    def check_if_order_is_executed(self, kite, placed_trade, trading_symbol, last_price):
        gtt_trigger = kite.get_gtt(placed_trade.order_id)
        metadata = placed_trade.get_metadata_as_dict()
        actual_entry_price = placed_trade.entry_start_price
        if gtt_trigger['status'] == 'triggered':
            metadata = placed_trade.get_metadata_as_dict()
            if gtt_trigger['orders'][0]['result'] is not None and \
                    gtt_trigger['orders'][0]['result']['order_result']['status'] == 'success':
                try:
                    order_id = gtt_trigger['orders'][0]['result']['order_result']['order_id']
                    order_history = kite.order_history(order_id)
                    order_history_len = len(order_history)
                    if 'status' in order_history[order_history_len-1] and order_history[order_history_len-1]['status'] != 'COMPLETE':
                        kite.cancel_order(kite.VARIETY_REGULAR, order_id)
                        time.sleep(0.5)
                        prev_order = order_history[order_history_len-1]
                        exchange = metadata.get('exchange', 'NFO')
                        order_id = kite.place_order(
                            tradingsymbol=prev_order['tradingsymbol'],
                            exchange=exchange,
                            transaction_type="BUY",
                            quantity=prev_order['quantity'],
                            variety=kite.VARIETY_REGULAR,
                            order_type=kite.ORDER_TYPE_MARKET,
                            product=kite.PRODUCT_MIS,
                            validity=kite.VALIDITY_DAY,
                            price=last_price)
                        self.logger.info("GTT is triggered but limit order status is still not complete. "
                        "So, deleted existing limit order and placed market order. New Order ID: {}".format(order_id))
                except Exception as e:
                    self.logger.error("ERROR in checking GTT limit order: {}".format(str(e)))
                placed_trade.order_status = 'ORDER_ENTRY_EXECUTED'
                actual_entry_price = gtt_trigger["condition"]["trigger_values"][0]
            elif gtt_trigger['orders'][1]['result'] is not None and \
                    gtt_trigger['orders'][1]['result']['order_result'][
                        'status'] == 'success':
                placed_trade.order_status = 'ORDER_ENTRY_EXECUTED'
                actual_entry_price = gtt_trigger["condition"]["trigger_values"][1]
            # placed_trade.entry_start_price = actual_entry_price
            # placed_trade.entry_end_price = actual_entry_price

            # Update stop loss and first 1:1 target prices
            # metadata = placed_trade.get_metadata_as_dict()

            real_stop_loss_percent = metadata['estimated_stop_loss_percent']
            # placed_trade.exit_stop_loss_price = round(
            #     placed_trade.entry_start_price * (1 - (real_stop_loss_percent / 100)), 1)

            first_target_price_1_to_1_ror = placed_trade.entry_end_price * self.reward_to_risk_ratio * (
                    100 + real_stop_loss_percent) / 100
            curr_first_target_price = get_nearest_tens(first_target_price_1_to_1_ror)
            # metadata['targets'][0] = curr_first_target_price
            placed_trade.set_metadata_from_dict(metadata)

            placed_trade.save()
        elif abs(last_price - gtt_trigger['orders'][0]['price']) <= gtt_trigger['orders'][0]['price'] * 0.01:
            self.logger.info("Price is within 1% of buy range. Cancelling Buy GTT Order and Placing Market Order.")
            trigger_id = placed_trade.order_id
            try:
                kite.delete_gtt(trigger_id)
                order_id = kite.place_order(
                    tradingsymbol=trading_symbol,
                    exchange=metadata.get('exchange', 'NFO'),
                    transaction_type=kite.TRANSACTION_TYPE_BUY,
                    quantity=gtt_trigger['orders'][0]['quantity'],
                    variety=kite.VARIETY_REGULAR,
                    order_type=kite.ORDER_TYPE_MARKET,
                    product=kite.PRODUCT_MIS,
                    validity=kite.VALIDITY_DAY,
                    price=last_price)
                self.logger.info("Placed Market Buy Order. New Order ID: {}".format(order_id))
                placed_trade.order_status = 'ORDER_ENTRY_EXECUTED'
                placed_trade.save()
            except Exception as e:
                traceback.print_exc()
                self.logger.error("Found Exception while deleting buy gtt order. trigger_id: {}".format(trigger_id))


