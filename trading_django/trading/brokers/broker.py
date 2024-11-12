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


class Broker(object):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def positions(self):
        pass

    @abstractmethod
    def historical_data(self, instrument_token, from_date, to_date, interval, continuous=False, oi=False):
        pass

    @abstractmethod
    def margins(self):
        pass

    # @abstractmethod
    def place_gtt(self, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders):
        pass

    # @abstractmethod
    def get_gtt(self, trigger_id):
        pass

    @abstractmethod
    def order_history(self, order_id):
        pass

    @abstractmethod
    def cancel_order(self, variety, order_id, parent_order_id=None):
        pass
    
    @abstractmethod
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
        pass
    
    # @abstractmethod
    def delete_gtt(self, trigger_id):
        pass

    


        
