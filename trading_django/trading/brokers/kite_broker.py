import logging
import bisect
import re
import math
import time
import traceback
from datetime import datetime, timedelta

from trading.brokers.broker import Broker
from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.models import Funds
from django.db.models import Q


class KiteBroker(Broker):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(KiteBroker, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.logger = logging.getLogger(__name__)
            self.login = Login()
            self.login.login()
            self.kite = self.login.kite
    

    def positions(self):
        return self.kite.positions()


    def historical_data(self, instrument_token, from_date, to_date, interval, continuous=False, oi=False):
        return self.kite.historical_data(instrument_token, from_date, to_date, interval, continuous, oi)


    def margins(self):
        return self.kite.margins()


    def place_gtt(self, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders):
        return self.kite.place_gtt(trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders)


    def get_gtt(self, trigger_id):
        return self.kite.get_gtt(trigger_id)


    def order_history(self, order_id):
        return self.kite.order_history(order_id)


    def cancel_order(self, variety, order_id, parent_order_id=None):
        return self.kite.cancel_order(variety, order_id, parent_order_id)
    

    def place_order(self,
                    variety,
                    exchange,
                    tradingsymbol,
                    transaction_type,
                    quantity,
                    product,
                    order_type,
                    price=None,
                    validity=None):
        return self.kite.place_order(
            variety,
            exchange,
            tradingsymbol,
            transaction_type,
            quantity,
            product,
            order_type,
            price,
            validity)

    def delete_gtt(self, trigger_id):
        return self.delete_gtt(trigger_id)

    


        
