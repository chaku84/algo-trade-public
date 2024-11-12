import logging
import bisect
import traceback
import time
from datetime import datetime, timedelta

from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.strategies.exit import Exit


class InstantUserExit(Exit):
    def __init__(self, entry_obj=None):
        super().__init__(entry_obj)
        self.logger = logging.getLogger(__name__)

    def cancel_gtt_and_all_orders_below_range(self, kite, placed_trade, trading_symbol, last_price):
        if last_price < placed_trade.entry_start_price:
            try:
                splitted_order_status = placed_trade.order_status.split(':')
                trigger_id_list = splitted_order_status[1].split(',')
                total_quantity = 0
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
                    exchange="NFO",
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
                metadata = placed_trade.get_metadata_as_dict()
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
                exchange="NFO",
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
