import logging
import re
import math
import pytz
import copy

from kiteconnect import KiteConnect, KiteTicker
import requests
import pyotp
import json
import os
import time
from kiteconnect.exceptions import TokenException
import calendar
import math
from datetime import datetime, timedelta
import talib
import traceback
import numpy as np
import bisect
import asyncio
import websockets
from strategies.login import Login
from strategies.instruments import Instruments
from trading.kite_manager import KiteManager
from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.authentication import validate_jwt_token
# from strategies.common import get_price, get_nearest_expiry
# from asgiref.sync import async_to_sync


from trading.models import TelegramMessage, TelegramTrade, UserTrade, CombinedUserTrade
from django.db.models import Q, ForeignKey


class UserTradingManager(object):
    __instance = None

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.kite = KiteManager().kite
        
    def place_order(self, user, payload):
        '''
        {'stopLossPercentage': 17.647058823529413, 'stopLossPrice': 280.0, 'entryStartPrice': 340.0, 'entryEndPrice': 350.0, 'targetMap': {'0': '400', '1': '440'}, 'quantityShareMap': {'0': '80', '1': '20'}, 'trailingStopLossMap': {'0': '340'}, 'optionFormDetail': {'transactionType': 'BUY', 'index': 'BANKNIFTY', 'strikePrice': 'CE', 'expiry': '3/20/2024'}, 'risk': 1000.0}
        '''
        print(payload)
        user_trade = UserTrade()
        now = get_ist_datetime(datetime.utcnow())
        now = datetime(year=now.year, month=now.month, day=now.day, hour=now.hour, minute=now.minute, second=now.second)
        user_trade.created_at_time = now
        user_trade.updated_at_time = now
        user_trade.updated_by = user
        user_trade.username = user
        user_trade.index_name = payload['optionFormDetail']['index']
        user_trade.index_strike_price = payload['optionFormDetail']['strikePrice']
        user_trade.option_type = payload['optionFormDetail']['optionType']
        user_trade.expiry = payload['optionFormDetail']['expiry']
        date = datetime.strptime(payload['optionFormDetail']['expiry'], '%m/%d/%Y')
        # Format the date as "day month_name" (e.g., "27 March")
        formatted_date = date.strftime('%d %B')
        user_trade.expiry = formatted_date
        # user_trade.inst_token = models.IntegerField(null=True)
        user_trade.order_status = 'NOT_PLACED'
        user_trade.order_id = ''
        del payload['optionFormDetail']
        user_trade.set_metadata_from_dict(payload)
        user_trade.entry_type = 'INSTANT_USER'
        user_trade.combined_user_trade = None
        user_trade.save()
        # combined_user_trade = models.ForeignKey(CombinedUserTrade, on_delete=models.DO_NOTHING)
        # combined_user_trade = None
        # combined_user_trade = CombinedUserTrade.objects.filter(
        #     Q(created_at_time=now) & Q(index_name=user_trade.index_name)
        #     & Q(index_strike_price=user_trade.index_strike_price)
        #     & Q(option_type=user_trade.option_type)
        #     & Q(expiry=formatted_date)
        #     & Q(entry_type=user_trade.entry_type)
        # ).first()
        # if combined_user_trade is None:
        #     combined_user_trade = CombinedUserTrade()
        #     combined_user_trade.created_at_time = now
        #     combined_user_trade.updated_at_time = now
        #     combined_user_trade.updated_by = user
        #     combined_user_trade.username = user
        #     combined_user_trade.index_name = user_trade.index_name
        #     combined_user_trade.index_strike_price = user_trade.index_strike_price
        #     combined_user_trade.option_type = user_trade.option_type
        #     combined_user_trade.expiry = formatted_date
        #     combined_user_trade.transaction_type = 'BUY'
        #     combined_user_trade.order_status = 'NOT_PLACED'
        #     child_trade = copy.deepcopy(combined_user_trade)
        return {'success': True, 'message': 'Order Placed successfully', 'data': {}}

    def queryset_to_dict(self, queryset):
        result_dict = []
        for obj in queryset:
            obj_dict = {}
            for field in obj._meta.fields:
                if isinstance(field, ForeignKey):
                    # If the field is a ForeignKey, get the related object's primary key
                    related_obj = getattr(obj, field.name)
                    if related_obj:
                        obj_dict[field.name] = related_obj.pk
                    else:
                        obj_dict[field.name] = None
                else:
                    obj_dict[field.name] = getattr(obj, field.name)
            result_dict.append(obj_dict)
        return result_dict

    def get_orders(self, user):
        print(user)
        self.logger.info(user)
        now = get_ist_datetime(datetime.utcnow())
        now = datetime(year=now.year, month=now.month, day=now.day)
        user_trades = UserTrade.objects.filter(
            Q(created_at_time__gte=now) & Q(username=user)
        )
        self.logger.info(user_trades)
        return {'success': True, 'message': 'Order Placed successfully', 'data': self.queryset_to_dict(user_trades)}
        
    