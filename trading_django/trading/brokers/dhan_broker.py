import logging
import bisect
import re
import math
import time
import traceback
from datetime import datetime, timedelta

from dhanhq import dhanhq, marketfeed
from trading.brokers.broker import Broker
from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.models import Funds
from django.db.models import Q


class DhanBroker(object):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DhanBroker, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.client_id = "1101185196"
            self.access_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzIyODU1MDE1LCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTEwMTE4NTE5NiJ9.fj7Wf4rBPGdYgTbwl01PF_o_KR9otfqAv5o95nlvUb4xidJDIC5KCXZyCCF-zPowWyHm-t2QUy72QIt70LHvEQ"
            self.dhan = dhanhq("1101185196", self.access_token)

            nifty_trading_symbol = 'BANKNIFTY 28 SEP 47600 CALL'
            nifty_option_security_id_map = {}
            nifty_price_list = set([])
            self.bank_nifty_option_security_id_map = {}
            self.bank_nifty_price_list = set([])
            finnifty_option_security_id_map = {}
            finnifty_price_list = set([])
            nifty_nearest_expiry = ''
            self.bank_nifty_nearest_expiry = ''
            finnifty_nearest_expiry = ''
            min_nifty_expiry_diff = 10 ** 17
            min_bank_nifty_expiry_diff = 10 ** 17
            min_finnifty_expiry_diff = 10 ** 17
            nifty_50_security_id = 0
            bank_nifty_security_id = 0
            finnifty_security_id = 0
            security_id_to_trading_symbol_map = {}
            with open('/home/ec2-user/services/algo-trade/api-scrip-master.csv', mode='r') as file:
                csvFile = csv.reader(file)
                for lines in csvFile:
                    if lines[3] == 'OPTIDX' and lines[12] == 'W':
                        weekly_timestamp = datetime.fromisoformat(lines[8].split(' ')[0].replace('/', '-')).timestamp()
                        timestamp_diff = weekly_timestamp - datetime.now().timestamp()
                        if lines[5].find('NIFTY') == 0:
                            security_id_to_trading_symbol_map[lines[2]]=lines[7]
                            nifty_option_security_id_map[lines[7]] = lines[2]
                            nifty_price_list.add(math.trunc(float(lines[9])))
                            if timestamp_diff > 0 and timestamp_diff < min_nifty_expiry_diff:
                                min_nifty_expiry_diff = timestamp_diff
                                nifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                        if lines[5].find('BANKNIFTY') == 0:
                            security_id_to_trading_symbol_map[lines[2]]=lines[7]
                            self.bank_nifty_option_security_id_map[lines[7]] = lines[2]
                            self.bank_nifty_price_list.add(math.trunc(float(lines[9])))
                            if timestamp_diff > 0 and timestamp_diff < min_bank_nifty_expiry_diff:
                                min_bank_nifty_expiry_diff = timestamp_diff
                                self.bank_nifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                        if lines[5].find('FINNIFTY') == 0:
                            security_id_to_trading_symbol_map[lines[2]]=lines[7]
                            finnifty_option_security_id_map[lines[7]] = lines[2]
                            finnifty_price_list.add(math.trunc(float(lines[9])))
                            if timestamp_diff > 0 and timestamp_diff < min_finnifty_expiry_diff:
                                min_finnifty_expiry_diff = timestamp_diff
                                finnifty_nearest_expiry = ' '.join(lines[7].split(' ')[1:3])
                    if lines[3] == 'INDEX':
                        if lines[7] == 'Nifty 50':
                            nifty_50_security_id = lines[2]
                            security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        if lines[7] == 'Nifty Bank':
                            bank_nifty_security_id = lines[2]
                            security_id_to_trading_symbol_map[lines[2]]=lines[7]
                        if lines[7] == 'Fin Nifty':
                            finnifty_security_id = lines[2]
                            security_id_to_trading_symbol_map[lines[2]]=lines[7]
            nifty_price_list = sorted(list(nifty_price_list))
            self.bank_nifty_price_list = sorted(list(bank_nifty_price_list))
            finnifty_price_list = sorted(list(finnifty_price_list))


    def positions(self):
        self.dhan.get_positions()


    def historical_data(self, instrument_token, from_date, to_date, interval, continuous=False, oi=False, kite=None, dhan_symbol=None, dhan_exchange_segment=None, dhan_instrument_type=None, dhan_expiry_code=None):
        # nifty_historical_data = self.dhan.historical_daily_data(symbol='NIFTY', exchange_segment='IDX_I', instrument_type='INDEX', expiry_code=0, from_date=from_date,to_date=to_date)
        if interval == 'minute':
            return kite.historical_data(instrument_token, from_date, to_date, interval, continuous, oi)
        return self.dhan.historical_daily_data(dhan_symbol, dhan_exchange_segment, dhan_instrument_type, dhan_expiry_code, from_date, to_date)


    def get_fund_limits(self):
        return self.dhan.get_fund_limits()

    def margins(self):
        return self.dhan.get_fund_limits()


    # def place_gtt(self, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders):
    #     self.kite.place_gtt(trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders)


    # def get_gtt(self, trigger_id):
    #     self.kite.get_gtt(trigger_id)

    def get_order_list(self):
        self.dhan.get_order_list()

    def get_order_by_id(self, order_id):
        return self.dhan.get_trade_book(order_id)

    def get_trade_history(self, from_date, to_date, page_number):
        return self.dhan.get_trade_history(from_date,to_date,page_number=0)

    def cancel_order(self, variety, order_id, parent_order_id=None):
        self.kite.cancel_order(variety, order_id, parent_order_id)
    

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
        return self.dhan.place_slice_order(security_id='52175',  #NiftyPE
            exchange_segment=dhan.NSE_FNO,
            transaction_type=dhan.BUY,
            quantity=quantity,              #nifty freeze quantity is 1800
            order_type=dhan.MARKET,
            product_type=dhan.INTRA,
            price=0)


    # def delete_gtt(self, trigger_id):
    #     self.delete_gtt(trigger_id)

    


        
