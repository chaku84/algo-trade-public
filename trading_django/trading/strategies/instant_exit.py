import logging
import bisect
import traceback
import time
from datetime import datetime, timedelta

from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.strategies.exit import Exit
from trading.models import TelegramTrade


class InstantExit(Exit):
    def __init__(self, entry_obj=None):
        super().__init__(entry_obj)
        self.logger = logging.getLogger(__name__)

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
                if quantities[min(index, len(quantities)-1)] == 0:
                    continue
                if index == positive_quantity_cnt - 1:
                    target_price = 100000
                # metadata = trade.get_metadata_as_dict()
                exchange = metadata.get('exchange', 'NFO')
                order = kite.place_gtt(
                    trigger_type=kite.GTT_TYPE_OCO,
                    tradingsymbol=trading_symbol,
                    exchange=exchange,
                    trigger_values=[max(2 * placed_trade.exit_stop_loss_price - placed_trade.entry_end_price, 1), round(target_price, 1)],
                    last_price=last_price,
                    orders=[{
                        "exchange": exchange,
                        "tradingsymbol": trading_symbol,
                        "transaction_type": "SELL",
                        "quantity": quantities[index],
                        "order_type": "LIMIT",
                        "product": kite.PRODUCT_MIS,
                        "price": round(max(2 * placed_trade.exit_stop_loss_price - placed_trade.entry_end_price, 1), 1)
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
            placed_trade.order_status = 'ORDER_EXIT_GTT_PLACED:%s' % (','.join(trigger_id_list))
            placed_trade.save()
        except Exception as e:
            traceback.print_exc()
            placed_trade.order_status = 'ORDER_EXIT_GTT_PLACED:%s' % (','.join(trigger_id_list))
            placed_trade.save()

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

        if timestamp.second % 59 == 0:
            inst_token = metadata['inst_token']
            instance = TelegramTrade.objects.get(id=placed_trade.id)
            history = instance.history.filter(order_status='ORDER_ENTRY_EXECUTED').order_by('history_date').first()
            trade_executed_date = get_ist_datetime(history.history_date)
            prev_min_data = kite.historical_data(inst_token,
                                                    trade_executed_date,
                                                    timestamp, "minute", False)
            close_count_below_stop_loss_price = 0
            for data in prev_min_data:
                if data['close'] <= placed_trade.exit_stop_loss_price:
                    close_count_below_stop_loss_price += 1
            # if tick_last_price >= trade.entry_end_price:
            #     self.logger.info("hour: %s, minute: %s, second: %s, tick_last_price: %s" % (timestamp.hour, timestamp.minute, timestamp.second, tick_last_price))
            #     close_count_above_entry_price += 1
            # else:
            #     close_count_below_entry_price += 1
            if close_count_below_stop_loss_price >= 2:
                metadata['updated_order_status'] = 'CANCELLED'
                placed_trade.set_metadata_from_dict(metadata)
                placed_trade.save()
                return
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
                            trigger_values=[round(shifted_sl_trail_prices[curr_target], 1),
                                            curr_trigger_condition["trigger_values"][1]],
                            last_price=last_price,
                            orders=[{
                                "exchange": exchange,
                                "tradingsymbol": trading_symbol,
                                "transaction_type": "SELL",
                                "quantity": last_quantity,
                                "order_type": "LIMIT",
                                "product": kite.PRODUCT_MIS,
                                "price": round(shifted_sl_trail_prices[curr_target], 1)
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
        # trigger_condition = gtt_trigger["condition"]
        triggered_but_not_executed = False
        if gtt_trigger['status'] == 'triggered':
            triggered_but_not_executed = True
            if gtt_trigger['orders'][0]['result'] is not None and \
                    gtt_trigger['orders'][0]['result']['order_result']['status'] == 'success':
                try:
                    order_id = gtt_trigger['orders'][0]['result']['order_result']['order_id']
                    order_history = kite.order_history(order_id)
                    order_history_len = len(order_history)
                    if 'status' in order_history[order_history_len-1] and order_history[order_history_len-1]['status'] != 'COMPLETE':
                        kite.cancel_order(kite.VARIETY_REGULAR, order_id)
                        time.sleep(0.1)
                        prev_order = order_history[order_history_len-1]
                        exchange = metadata.get('exchange', 'NFO')
                        order_id = kite.place_order(
                            tradingsymbol=prev_order['tradingsymbol'],
                            exchange=exchange,
                            transaction_type=kite.TRANSACTION_TYPE_SELL,
                            quantity=prev_order['quantity'],
                            variety=kite.VARIETY_REGULAR,
                            order_type=kite.ORDER_TYPE_MARKET,
                            product=kite.PRODUCT_MIS,
                            validity=kite.VALIDITY_DAY,
                            price=last_price)
                        self.logger.info("Under update_targets_status_and_trail_stop_loss. GTT is triggered but Stop Loss limit order status is still not complete. "
                        "So, deleted existing limit order and placed market order. New Order ID: {}".format(order_id))
                except Exception as e:
                    self.logger.error("Under update_targets_status_and_trail_stop_loss. ERROR in checking Stop Loss GTT limit order: {}".format(str(e)))
                placed_trade.order_status = 'ORDER_EXIT_GTT_EXECUTED:%s,STOP_LOSS_HIT' % curr_target
                triggered_but_not_executed = False
            if gtt_trigger['orders'][1]['result'] is not None and \
                    gtt_trigger['orders'][1]['result']['order_result']['status'] == 'success':
                try:
                    order_id = gtt_trigger['orders'][1]['result']['order_result']['order_id']
                    order_history = kite.order_history(order_id)
                    order_history_len = len(order_history)
                    if 'status' in order_history[order_history_len-1] and order_history[order_history_len-1]['status'] != 'COMPLETE':
                        kite.cancel_order(kite.VARIETY_REGULAR, order_id)
                        time.sleep(0.1)
                        prev_order = order_history[order_history_len-1]
                        exchange = metadata.get('exchange', 'NFO')
                        order_id = kite.place_order(
                            tradingsymbol=prev_order['tradingsymbol'],
                            exchange=exchange,
                            transaction_type=kite.TRANSACTION_TYPE_SELL,
                            quantity=prev_order['quantity'],
                            variety=kite.VARIETY_REGULAR,
                            order_type=kite.ORDER_TYPE_MARKET,
                            product=kite.PRODUCT_MIS,
                            validity=kite.VALIDITY_DAY,
                            price=last_price)
                        self.logger.info("Under update_targets_status_and_trail_stop_loss. GTT is triggered but target limit order status is still not complete. "
                        "So, deleted existing limit order and placed market order. New Order ID: {}".format(order_id))
                except Exception as e:
                    self.logger.error("Under update_targets_status_and_trail_stop_loss. ERROR in checking target GTT limit order: {}".format(str(e)))
                triggered_but_not_executed = False
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
                        trigger_values=[round(stop_loss_trail_prices[curr_target], 1),
                                        curr_trigger_condition["trigger_values"][1]],
                        last_price=last_price,
                        orders=[{
                            "exchange": exchange,
                            "tradingsymbol": trading_symbol,
                            "transaction_type": "SELL",
                            "quantity": curr_gtt_trigger['orders'][0]['quantity'],
                            "order_type": "LIMIT",
                            "product": kite.PRODUCT_MIS,
                            "price": round(stop_loss_trail_prices[curr_target], 1)
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
        else:
            if last_price <= gtt_trigger['orders'][0]['price']:
                self.logger.info("market price: {} is less than sell GTT stop loss limit price: {}. Cancelling GTT Order and Placing Market Order.".format(last_price, gtt_trigger['orders'][0]['price']))
                trigger_id = trigger_id_list[0]
                try:
                    kite.delete_gtt(trigger_id)
                    order_id = kite.place_order(
                        tradingsymbol=trading_symbol,
                        exchange=metadata.get('exchange', 'NFO'),
                        transaction_type=kite.TRANSACTION_TYPE_SELL,
                        quantity=gtt_trigger['orders'][0]['quantity'],
                        variety=kite.VARIETY_REGULAR,
                        order_type=kite.ORDER_TYPE_MARKET,
                        product=kite.PRODUCT_MIS,
                        validity=kite.VALIDITY_DAY,
                        price=last_price)
                    self.logger.info("Placed Market SELL Stop Loss GTT Order. New Order ID: {}".format(order_id))
                except Exception as e:
                    traceback.print_exc()
                    self.logger.error("Found Exception while deleting sell stop loss gtt order. trigger_id: {}".format(trigger_id))
                placed_trade.order_status = 'ORDER_EXIT_GTT_EXECUTED:%s,STOP_LOSS_HIT' % curr_target
                placed_trade.save()
            
            if last_price >= gtt_trigger['orders'][1]['price'] or abs(last_price - gtt_trigger['orders'][1]['price']) <= gtt_trigger['orders'][1]['price'] * 0.01:
                self.logger.info("market price: {} is greater than sell GTT target limit price: {} or market price is within 1% of sell range. Cancelling GTT Order and Placing Market Order.".format(last_price, gtt_trigger['orders'][1]['price']))
                trigger_id = trigger_id_list[0]
                try:
                    kite.delete_gtt(trigger_id)
                    order_id = kite.place_order(
                        tradingsymbol=trading_symbol,
                        exchange=metadata.get('exchange', 'NFO'),
                        transaction_type=kite.TRANSACTION_TYPE_SELL,
                        quantity=gtt_trigger['orders'][1]['quantity'],
                        variety=kite.VARIETY_REGULAR,
                        order_type=kite.ORDER_TYPE_MARKET,
                        product=kite.PRODUCT_MIS,
                        validity=kite.VALIDITY_DAY,
                        price=last_price)
                    self.logger.info("Placed Market SELL Target GTT Order. New Order ID: {}".format(order_id))
                except Exception as e:
                    traceback.print_exc()
                    self.logger.error("Found Exception while deleting sell target gtt order. trigger_id: {}".format(trigger_id))
                
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
                        trigger_values=[round(stop_loss_trail_prices[curr_target], 1),
                                        curr_trigger_condition["trigger_values"][1]],
                        last_price=last_price,
                        orders=[{
                            "exchange": exchange,
                            "tradingsymbol": trading_symbol,
                            "transaction_type": "SELL",
                            "quantity": curr_gtt_trigger['orders'][0]['quantity'],
                            "order_type": "LIMIT",
                            "product": kite.PRODUCT_MIS,
                            "price": round(stop_loss_trail_prices[curr_target], 1)
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




        # self.logger.info(last_price)

        # triggered_but_not_executed = gtt_trigger['orders'][0]['price'] >= last_price or (gtt_trigger['orders'][1]['price'] <= last_price)
        
        # if triggered_but_not_executed:
        #     # found_open = False
        #     self.logger.info("order triggered_but_not_executed: {}".format(triggered_but_not_executed))
        #     try:
        #         kite.cancel_order(kite.VARIETY_REGULAR, trigger_id_list[0])
        #     except Exception as e:
        #         traceback.print_exc()
        #         self.logger.error("Found Exception while cancelling gtt limit order. trigger_id: {}".format(trigger_id_list[0]))

        #     if gtt_trigger['orders'][0]['result'] is not None and \
        #             gtt_trigger['orders'][0]['result']['order_result']['status'] == 'success':
        #         order_id = gtt_trigger['orders'][0]['result']['order_result']['order_id']
        #         try:
        #             kite.cancel_order(kite.VARIETY_REGULAR, order_id)
        #         except Exception as e:
        #             traceback.print_exc()
        #             self.logger.error("Found Exception while cancelling gtt limit order. order_id: {}".format(order_id))
        #     if gtt_trigger['orders'][1]['result'] is not None and \
        #             gtt_trigger['orders'][1]['result']['order_result']['status'] == 'success':
        #         order_id = gtt_trigger['orders'][1]['result']['order_result']['order_id']
        #         try:
        #             kite.cancel_order(kite.VARIETY_REGULAR, order_id)
        #         except Exception as e:
        #             traceback.print_exc()
        #             self.logger.error("Found Exception while cancelling gtt limit order. order_id: {}".format(order_id))
                
        #     if triggered_but_not_executed:
        #         order_id = kite.place_order(
        #             tradingsymbol=trading_symbol,
        #             exchange=exchange,
        #             transaction_type=kite.TRANSACTION_TYPE_SELL,
        #             quantity=gtt_trigger['orders'][0]['quantity'],
        #             variety=kite.VARIETY_REGULAR,
        #             order_type=kite.ORDER_TYPE_MARKET,
        #             product=kite.PRODUCT_MIS,
        #             validity=kite.VALIDITY_DAY,
        #             price=last_price)
        #         self.logger.info("Cancelled Top GTT and Limit Orders related to GTT."
        #                         " Placed Market Exit Order as there is delay in GTT trigger. Order ID: {}".format(order_id))

        #         if abs(gtt_trigger['orders'][0]['price']-last_price) <= abs(gtt_trigger['orders'][1]['price'] - last_price): # This condition implies that stop loss has been hit
        #             placed_trade.order_status = 'ORDER_EXIT_GTT_EXECUTED:%s,STOP_LOSS_HIT' % curr_target
        #         if abs(gtt_trigger['orders'][0]['price']-last_price) > abs(gtt_trigger['orders'][1]['price'] - last_price): # This condition implies that target has been hit
        #             curr_trigger_id_list = trigger_id_list[1:] if len(trigger_id_list) > 1 else []
        #             # metadata = placed_trade.get_metadata_as_dict()
        #             stop_loss_trail_prices = [placed_trade.entry_end_price]
        #             stop_loss_trail_prices.extend(metadata['targets'])
        #             for trigger_id in curr_trigger_id_list:
        #                 curr_gtt_trigger = kite.get_gtt(trigger_id)
        #                 curr_trigger_condition = curr_gtt_trigger["condition"]
        #                 kite.modify_gtt(
        #                     trigger_id=trigger_id,
        #                     trigger_type=kite.GTT_TYPE_OCO,
        #                     tradingsymbol=trading_symbol,
        #                     exchange=exchange,
        #                     trigger_values=[round(stop_loss_trail_prices[curr_target] * 0.98, 1),
        #                                     curr_trigger_condition["trigger_values"][1]],
        #                     last_price=last_price,
        #                     orders=[{
        #                         "exchange": exchange,
        #                         "tradingsymbol": trading_symbol,
        #                         "transaction_type": "SELL",
        #                         "quantity": curr_gtt_trigger['orders'][0]['quantity'],
        #                         "order_type": "LIMIT",
        #                         "product": kite.PRODUCT_MIS,
        #                         "price": round(stop_loss_trail_prices[curr_target] * 0.96, 1)
        #                     },
        #                         {
        #                             "exchange": exchange,
        #                             "tradingsymbol": trading_symbol,
        #                             "transaction_type": "SELL",
        #                             "quantity": curr_gtt_trigger['orders'][1]['quantity'],
        #                             "order_type": "LIMIT",
        #                             "product": kite.PRODUCT_MIS,
        #                             "price": curr_gtt_trigger['orders'][1]['price']
        #                         }
        #                     ])
        #             placed_trade.order_status = '%s_TARGET_HIT:%s' % (
        #                 (curr_target + 1), ','.join([str(s) for s in curr_trigger_id_list]))
        #             if placed_trade.order_status[-1] == ':':
        #                 placed_trade.order_status = 'ORDER_EXIT_GTT_EXECUTED:%s' % (curr_target + 1)
        #         placed_trade.save()

    def cancel_gtt_and_all_orders_below_range(self, kite, placed_trade, trading_symbol, last_price):
        if last_price < placed_trade.entry_start_price:
            try:
                splitted_order_status = placed_trade.order_status.split(':')
                trigger_id_list = splitted_order_status[1].split(',')
                total_quantity = 0
                metadata = placed_trade.get_metadata_as_dict()
                exchange = metadata.get('exchange', 'NFO')
                for trigger_id in trigger_id_list:
                    gtt_trigger = kite.get_gtt(trigger_id)
                    total_quantity = total_quantity + gtt_trigger['orders'][0]['quantity']
                    if gtt_trigger['orders'][0]['result'] is not None and \
                            gtt_trigger['orders'][0]['result']['order_result']['status'] == 'success':
                        order_id = gtt_trigger['orders'][0]['result']['order_result']['order_id']
                        kite.cancel_order(kite.VARIETY_REGULAR, order_id)
                    if gtt_trigger['orders'][1]['result'] is not None and \
                            gtt_trigger['orders'][1]['result']['order_result']['status'] == 'success':
                        order_id = gtt_trigger['orders'][1]['result']['order_result']['order_id']
                        kite.cancel_order(kite.VARIETY_REGULAR, order_id)
                    try:
                        kite.delete_gtt(trigger_id)
                    except Exception as e:
                        traceback.print_exc()
                        self.logger.error("Found Exception while deleting gtt order. trigger_id: {}".format(trigger_id))
                # time.sleep(0.05)
                order_id = kite.place_order(
                    tradingsymbol=trading_symbol,
                    exchange=exchange,
                    transaction_type=kite.TRANSACTION_TYPE_SELL,
                    quantity=total_quantity,
                    variety=kite.VARIETY_REGULAR,
                    order_type=kite.ORDER_TYPE_MARKET,
                    product=kite.PRODUCT_MIS,
                    validity=kite.VALIDITY_DAY,
                    price=last_price)
                self.logger.info("Cancelled GTT and All Limit Orders related to GTT."
                                 " Placed Market Exit Order. Order ID: {}".format(order_id))
                placed_trade.order_status = 'NOT_PLACED'
                
                if 'range_entry_count' not in metadata:
                    metadata['range_entry_count'] = 1
                else:
                    metadata['range_entry_count'] = metadata['range_entry_count'] + 1
                placed_trade.set_metadata_from_dict(metadata)
                if metadata['range_entry_count'] == 1:
                    placed_trade.order_status = 'CANCELLED'
                placed_trade.save()
                self.logger.info("Updated Order Status for re-entry into range.")
            except Exception as e:
                self.logger.error("ERROR: Exception while cancelling GTT and all limit orders related to GTT.")
                traceback.print_exc()
                
    def cancel_gtt_and_all_orders(self, kite, placed_trade, trading_symbol, last_price):
        try:
            splitted_order_status = placed_trade.order_status.split(':')
            trigger_id_list = splitted_order_status[1].split(',')
            total_quantity = 0
            metadata = placed_trade.get_metadata_as_dict()
            exchange = metadata.get('exchange', 'NFO')
            for trigger_id in trigger_id_list:
                gtt_trigger = kite.get_gtt(trigger_id)
                total_quantity = total_quantity + gtt_trigger['orders'][0]['quantity']
                if gtt_trigger['orders'][0]['result'] is not None and \
                        gtt_trigger['orders'][0]['result']['order_result']['status'] == 'success':
                    order_id = gtt_trigger['orders'][0]['result']['order_result']['order_id']
                    try:
                        kite.cancel_order(kite.VARIETY_REGULAR, order_id)
                    except Exception as e:
                        traceback.print_exc()
                        self.logger.error("Found Exception while cancelling gtt limit order. order_id: {}".format(order_id))
                if gtt_trigger['orders'][1]['result'] is not None and \
                        gtt_trigger['orders'][1]['result']['order_result']['status'] == 'success':
                    order_id = gtt_trigger['orders'][1]['result']['order_result']['order_id']
                    try:
                        kite.cancel_order(kite.VARIETY_REGULAR, order_id)
                    except Exception as e:
                        traceback.print_exc()
                        self.logger.error("Found Exception while cancelling gtt limit order. order_id: {}".format(order_id))

                try:
                    kite.delete_gtt(trigger_id)
                except Exception as e:
                    traceback.print_exc()
                    self.logger.error("Found Exception while deleting gtt order. trigger_id: {}".format(trigger_id))
            time.sleep(0.5)
            order_id = kite.place_order(
                tradingsymbol=trading_symbol,
                exchange=exchange,
                transaction_type=kite.TRANSACTION_TYPE_SELL,
                quantity=total_quantity,
                variety=kite.VARIETY_REGULAR,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_MIS,
                validity=kite.VALIDITY_DAY,
                price=last_price)
            self.logger.info("Cancelled GTT and All Limit Orders related to GTT."
                             " Placed Market Exit Order. Order ID: {}".format(order_id))
            placed_trade.order_status = 'CANCELLED'
            placed_trade.save()
            self.logger.info("Updated Order Status to CANCELLED.")
        except Exception as e:
            self.logger.error("ERROR: Exception while cancelling GTT and all limit orders related to GTT.")
            traceback.print_exc()
