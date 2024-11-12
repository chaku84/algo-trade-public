import logging
import bisect
import traceback
import time
from datetime import datetime, timedelta

from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.strategies.discounted_entry import DiscountedEntry


class Exit(object):
    def __init__(self, entry_obj=None):
        self.logger = logging.getLogger(__name__)

        self.entry_obj = entry_obj if entry_obj is not None else DiscountedEntry()

        # Entry Object variables
        # self.risk = 5000
        # self.discount_percent_list = [4, 8, 13, 17, 25, 33, 50, 67]
        # self.exit_target_percent_list = [80, 10, 10]
        # self.discount_time = '11:30'
        self.nifty_lot_size = 50
        self.bank_nifty_lot_size = 15
        self.reward_to_risk_ratio = 1
        self.quantity = 0
        self.hero_zero_stop_loss_percent = 67

    def place_exit_gtt_orders(self, kite, placed_trade, trading_symbol, last_price):
        metadata = placed_trade.get_metadata_as_dict()
        quantities = metadata['quantities']
        targets = metadata['targets']
        # Create GTT for first target
        trigger_id_list = []
        try:
            positive_quantity_cnt = 0
            for index in range(len(quantities)):
                if quantities[index] == 0:
                    break
                positive_quantity_cnt += 1
            for index in range(len(targets)):
                target_price = targets[index]
                if quantities[index] == 0:
                    continue
                if index == positive_quantity_cnt - 1:
                    target_price = 100000
                # metadata = trade.get_metadata_as_dict()
                exchange = metadata.get('exchange', 'NFO')
                order = kite.place_gtt(
                    trigger_type=kite.GTT_TYPE_OCO,
                    tradingsymbol=trading_symbol,
                    exchange=exchange,
                    trigger_values=[placed_trade.exit_stop_loss_price, round(target_price * 0.975, 1)],
                    last_price=last_price,
                    orders=[{
                        "exchange": exchange,
                        "tradingsymbol": trading_symbol,
                        "transaction_type": "SELL",
                        "quantity": quantities[index],
                        "order_type": "LIMIT",
                        "product": kite.PRODUCT_MIS,
                        "price": round(placed_trade.exit_stop_loss_price * 0.975, 1)
                    },
                        {
                            "exchange": exchange,
                            "tradingsymbol": trading_symbol,
                            "transaction_type": "SELL",
                            "quantity": quantities[index],
                            "order_type": "LIMIT",
                            "product": kite.PRODUCT_MIS,
                            "price": round(target_price, 1)
                        }
                    ])
                print(order)
                trigger_id_list.append(str(order['trigger_id']))
            if len(trigger_id_list) > 0:
                placed_trade.order_status = 'ORDER_EXIT_GTT_PLACED:%s' % (','.join(trigger_id_list))
                placed_trade.save()
        except Exception as e:
            # Exit at market as it's a trigger issue
            exchange = metadata.get('exchange', 'NFO')
            total_quantity = 0
            for quantity in quantities:
                total_quantity += quantity
            order_id = kite.place_order(
                tradingsymbol=trading_symbol,
                exchange=exchange,
                transaction_type="SELL",
                quantity=total_quantity,
                variety=kite.VARIETY_REGULAR,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_MIS,
                validity=kite.VALIDITY_DAY,
                price=last_price)
            self.logger.info("Order Exit GTT Placement Failed. So, placed market exit order. New Order ID: {}".format(order_id))
            placed_trade.order_status = 'NOT_PLACED'
            self.logger.info("Updated order_status to NOT_PLACED for re-entry.")
            placed_trade.save()
            # raise e
        # placed_trade.save()

    def update_targets_status_and_trail_stop_loss(self, kite, placed_trade, trading_symbol, last_price, timestamp):
        splitted_order_status = placed_trade.order_status.split(':')
        trigger_id_list = splitted_order_status[1].split(',')
        status_prefix = splitted_order_status[0]
        curr_target = 0
        if 'TARGET_HIT' in status_prefix:
            curr_target = int(status_prefix.replace('_TARGET_HIT', ''))
        # if len(trigger_id_list) == 3:
        metadata = placed_trade.get_metadata_as_dict()
        exchange = metadata.get('exchange', 'NFO')
        quantities = metadata['quantities']
        positive_quantity_cnt = 0
        last_quantity = 0
        for index in range(len(quantities)):
            if quantities[index] == 0:
                break
            last_quantity = quantities[index]
            positive_quantity_cnt += 1
        # self.logger.info("inside update_targets_status_and_trail_stop_loss")
        if curr_target == positive_quantity_cnt - 1:
            # self.logger.info("last target in update_targets_status_and_trail_stop_loss")
            try:
                if 'stop_loss_trail_prices' not in metadata:
                    stop_loss_trail_prices = [placed_trade.entry_end_price]
                    stop_loss_trail_prices.extend(metadata['targets'])
                    last_percent_change = 0.1
                    trail_length = len(stop_loss_trail_prices)
                    if len(stop_loss_trail_prices) == 1:
                        last_percent_change = 1
                    else:
                        last_percent_change = (stop_loss_trail_prices[trail_length-1] - stop_loss_trail_prices[trail_length-2]) / stop_loss_trail_prices[trail_length-2]
                    last_value = stop_loss_trail_prices[trail_length-1]
                    while trail_length < curr_target + 3:
                        stop_loss_trail_prices.append(round(last_value * (1 + last_percent_change), 1))
                        trail_length += 1
                        last_value = stop_loss_trail_prices[trail_length-1]
                    metadata['stop_loss_trail_prices'] = stop_loss_trail_prices
                    metadata['sl_trail_percent'] = last_percent_change
                    placed_trade.set_metadata_from_dict(metadata)
                    placed_trade.save()
                else:
                    stop_loss_trail_prices = metadata['stop_loss_trail_prices']
                # self.logger.info("stop_loss_trail_prices: {}".format(stop_loss_trail_prices))
                # self.logger.info("last_price: {}".format(last_price))
                # self.logger.info("curr_target: {}".format(curr_target))
                # self.logger.info("trigger_id_list: {}".format(trigger_id_list))
                curr_trigger_id_list = trigger_id_list
                for trigger_id in curr_trigger_id_list:
                    if last_price >= stop_loss_trail_prices[curr_target + 1]:
                        shifted_sl_trail_prices = metadata['stop_loss_trail_prices']
                        curr_gtt_trigger = kite.get_gtt(trigger_id)
                        curr_trigger_condition = curr_gtt_trigger["condition"]
                        self.logger.info("Modifying GTT under update_targets_status_and_trail_stop_loss")
                        kite.modify_gtt(
                            trigger_id=trigger_id,
                            trigger_type=kite.GTT_TYPE_OCO,
                            tradingsymbol=trading_symbol,
                            exchange=exchange,
                            trigger_values=[round(shifted_sl_trail_prices[curr_target] * 0.98, 1),
                                            curr_trigger_condition["trigger_values"][1]],
                            last_price=last_price,
                            orders=[{
                                "exchange": exchange,
                                "tradingsymbol": trading_symbol,
                                "transaction_type": "SELL",
                                "quantity": last_quantity,
                                "order_type": "LIMIT",
                                "product": kite.PRODUCT_MIS,
                                "price": round(shifted_sl_trail_prices[curr_target] * 0.96, 1)
                            },
                                {
                                    "exchange": exchange,
                                    "tradingsymbol": trading_symbol,
                                    "transaction_type": "SELL",
                                    "quantity": last_quantity,
                                    "order_type": "LIMIT",
                                    "product": kite.PRODUCT_MIS,
                                    "price": curr_gtt_trigger['orders'][1]['price']
                                }
                            ])
                        shifted_sl_trail_prices[curr_target] = shifted_sl_trail_prices[curr_target + 1]
                        shifted_sl_trail_prices[curr_target + 1] = shifted_sl_trail_prices[curr_target + 2]
                        shifted_sl_trail_prices[curr_target + 2] = round(shifted_sl_trail_prices[curr_target + 2] 
                                                                         * (1 + metadata['sl_trail_percent']), 1)
                        metadata['stop_loss_trail_prices'] = shifted_sl_trail_prices
                        placed_trade.set_metadata_from_dict(metadata)
                        placed_trade.save()
            except Exception as e:
                traceback.print_exc()
                self.logger.error("Found Exception while trailing last stop loss")
        gtt_trigger = kite.get_gtt(trigger_id_list[0])
        if gtt_trigger['status'] == 'triggered':
            if gtt_trigger['orders'][0]['result'] is not None and \
                    gtt_trigger['orders'][0]['result']['order_result']['status'] == 'success':
                placed_trade.order_status = 'ORDER_EXIT_GTT_EXECUTED:%s,STOP_LOSS_HIT' % curr_target
            if gtt_trigger['orders'][1]['result'] is not None and \
                    gtt_trigger['orders'][1]['result']['order_result']['status'] == 'success':
                curr_trigger_id_list = trigger_id_list[1:] if len(trigger_id_list) > 1 else []
                # metadata = placed_trade.get_metadata_as_dict()
                stop_loss_trail_prices = [placed_trade.entry_end_price]
                stop_loss_trail_prices.extend(metadata['targets'])
                for trigger_id in curr_trigger_id_list:
                    curr_gtt_trigger = kite.get_gtt(trigger_id)
                    curr_trigger_condition = curr_gtt_trigger["condition"]
                    kite.modify_gtt(
                        trigger_id=trigger_id,
                        trigger_type=kite.GTT_TYPE_OCO,
                        tradingsymbol=trading_symbol,
                        exchange=exchange,
                        trigger_values=[round(stop_loss_trail_prices[curr_target] * 0.98, 1),
                                        curr_trigger_condition["trigger_values"][1]],
                        last_price=last_price,
                        orders=[{
                            "exchange": exchange,
                            "tradingsymbol": trading_symbol,
                            "transaction_type": "SELL",
                            "quantity": curr_gtt_trigger['orders'][0]['quantity'],
                            "order_type": "LIMIT",
                            "product": kite.PRODUCT_MIS,
                            "price": round(stop_loss_trail_prices[curr_target] * 0.96, 1)
                        },
                            {
                                "exchange": exchange,
                                "tradingsymbol": trading_symbol,
                                "transaction_type": "SELL",
                                "quantity": curr_gtt_trigger['orders'][1]['quantity'],
                                "order_type": "LIMIT",
                                "product": kite.PRODUCT_MIS,
                                "price": curr_gtt_trigger['orders'][1]['price']
                            }
                        ])
                placed_trade.order_status = '%s_TARGET_HIT:%s' % (
                    (curr_target + 1), ','.join([str(s) for s in curr_trigger_id_list]))
                if placed_trade.order_status[-1] == ':':
                    placed_trade.order_status = 'ORDER_EXIT_GTT_EXECUTED:%s' % (curr_target + 1)
            placed_trade.save()

    def cancel_gtt_and_all_orders_below_range(self, kite, placed_trade, trading_symbol, last_price):
        pass
        # if last_price < placed_trade.entry_start_price:
        #     try:
        #         splitted_order_status = placed_trade.order_status.split(':')
        #         trigger_id_list = splitted_order_status[1].split(',')
        #         total_quantity = 0
        #         for trigger_id in trigger_id_list:
        #             gtt_trigger = kite.get_gtt(trigger_id)
        #             total_quantity = total_quantity + gtt_trigger['orders'][0]['quantity']
        #             if gtt_trigger['orders'][0]['result'] is not None and \
        #                     gtt_trigger['orders'][0]['result']['order_result']['status'] == 'success':
        #                 order_id = gtt_trigger['orders'][0]['result']['order_result']['order_id']
        #                 kite.cancel_order(kite.VARIETY_REGULAR, order_id)
        #             if gtt_trigger['orders'][1]['result'] is not None and \
        #                     gtt_trigger['orders'][1]['result']['order_result']['status'] == 'success':
        #                 order_id = gtt_trigger['orders'][1]['result']['order_result']['order_id']
        #                 kite.cancel_order(kite.VARIETY_REGULAR, order_id)
        #             kite.delete_gtt(trigger_id)
        #         time.sleep(0.05)
        #         order_id = kite.place_order(
        #             tradingsymbol=trading_symbol,
        #             exchange="NFO",
        #             transaction_type=kite.TRANSACTION_TYPE_SELL,
        #             quantity=total_quantity,
        #             variety=kite.VARIETY_REGULAR,
        #             order_type=kite.ORDER_TYPE_MARKET,
        #             product=kite.PRODUCT_MIS,
        #             validity=kite.VALIDITY_DAY,
        #             price=last_price)
        #         self.logger.info("Cancelled GTT and All Limit Orders related to GTT.")
        #     except Exception as e:
        #         self.logger.error("ERROR: Exception while cancelling GTT and all limit orders related to GTT.")
        #         traceback.print_exc()
        #         
                
    def cancel_gtt_and_all_orders(self, kite, placed_trade, trading_symbol, last_price):
        pass
    