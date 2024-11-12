import logging
from kiteconnect import KiteConnect, KiteTicker
import requests
import pyotp
import json
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import os
import time
from kiteconnect.exceptions import TokenException
import calendar
import math
from datetime import datetime
import talib
import traceback
import numpy as np
import bisect

class Instruments():
    def __init__(self, kite):
        self.kite = kite
        self.instruments = []
        self.risk_percent = 5
        self.reward_percent = 5
        self.max_allowed_lots = 1
        self.nifty_option_inst_token_map = {}
        self.bank_nifty_option_inst_token_map = {}
        self.mid_cap_nifty_option_inst_token_map = {}
        self.sensex_option_inst_token_map = {}
        self.nifty_price_list = set([])
        self.bank_nifty_price_list = set([])
        self.mid_cap_nifty_price_list = set([])
        self.sensex_price_list = set([])
        self.nifty_nearest_expiry = ''
        self.bank_nifty_nearest_expiry = ''
        self.mid_cap_nifty_nearest_expiry = ''
        self.sensex_nearest_expiry = ''
        self.min_nifty_expiry_diff = 10 ** 17
        self.min_bank_nifty_expiry_diff = 10 ** 17
        self.min_mid_cap_nifty_expiry_diff = 10 ** 17
        self.min_sensex_expiry_diff = 10 ** 17
        self.nifty_50_inst_token = 0
        self.bank_nifty_inst_token = 0
        self.mid_cap_nifty_inst_token = 0
        self.sensex_inst_token = 0
        self.nifty_expiry_list = []
        self.bank_nifty_expiry_list = []
        self.mid_cap_nifty_expiry_list = []
        self.sensex_expiry_list = []
        self.inst_token_to_trading_symbol_map = {}

    def load_instruments(self):
        file_creation_date = 0
        if os.path.exists("instruments.json"):
            file_creation_date = os.path.getctime("instruments.json")

        if datetime.now().timestamp() - file_creation_date > 18 * 60 * 60:
            # Get instruments
            self.instruments = self.kite.instruments()
            json_object = json.dumps(self.instruments, indent=4, sort_keys=True, default=str)

            self.instruments = json.loads(json_object)

            with open("instruments.json", "w") as outfile:
                outfile.write(json_object)
        else:
            with open('instruments.json', 'r') as openfile:
                self.instruments = json.load(openfile)

    def update_tokens_and_expiry(self):
        for inst in self.instruments:
            if inst['segment'] == 'NFO-OPT':
                self.inst_token_to_trading_symbol_map[inst['instrument_token']] = inst['tradingsymbol']
                inst['expiry'] = datetime.fromisoformat(inst['expiry']) if inst[
                                                                               'expiry'] != '' else datetime.fromisoformat(
                    '2000-01-01')
                now = datetime.now()
                timestamp_diff = datetime(inst['expiry'].year, inst['expiry'].month,
                                          inst['expiry'].day).timestamp() - datetime(now.year, now.month,
                                                                                     now.day).timestamp()
                map_key = "%s-%s-%s-%s" % (
                inst['name'], inst['expiry'].date().isoformat(), int(inst['strike']), inst['instrument_type'])
                if inst['name'] == 'NIFTY':
                    self.nifty_option_inst_token_map[map_key] = inst['instrument_token']
                    self.nifty_price_list.add(math.trunc(float(inst['strike'])))
                    if inst['expiry'].timestamp() not in self.nifty_expiry_list:
                        self.nifty_expiry_list.append(inst['expiry'].timestamp())
                    if timestamp_diff >= 0 and timestamp_diff <= self.min_nifty_expiry_diff:
                        self.min_nifty_expiry_diff = timestamp_diff
                        self.nifty_nearest_expiry = "%s%s" % (
                        inst['expiry'].day, calendar.month_name[inst['expiry'].month][:3].upper())
                if inst['name'] == 'BANKNIFTY':
                    if inst['expiry'].timestamp() not in self.bank_nifty_expiry_list:
                        self.bank_nifty_expiry_list.append(inst['expiry'].timestamp())
                    self.bank_nifty_option_inst_token_map[map_key] = inst['instrument_token']
                    self.bank_nifty_price_list.add(math.trunc(float(inst['strike'])))
                    if timestamp_diff >= 0 and timestamp_diff <= self.min_bank_nifty_expiry_diff:
                        self.min_bank_nifty_expiry_diff = timestamp_diff
                        self.bank_nifty_nearest_expiry = "%s%s" % (
                        inst['expiry'].day, calendar.month_name[inst['expiry'].month][:3].upper())
                if inst['name'] == 'MIDCPNIFTY':
                    if inst['expiry'].timestamp() not in self.mid_cap_nifty_expiry_list:
                        self.mid_cap_nifty_expiry_list.append(inst['expiry'].timestamp())
                    self.mid_cap_nifty_option_inst_token_map[map_key] = inst['instrument_token']
                    self.mid_cap_nifty_price_list.add(math.trunc(float(inst['strike'])))
                    if timestamp_diff >= 0 and timestamp_diff <= self.min_mid_cap_nifty_expiry_diff:
                        self.min_mid_cap_nifty_expiry_diff = timestamp_diff
                        self.mid_cap_nifty_nearest_expiry = "%s%s" % (
                        inst['expiry'].day, calendar.month_name[inst['expiry'].month][:3].upper())
            if inst['segment'] == 'BFO-OPT':
                self.inst_token_to_trading_symbol_map[inst['instrument_token']] = inst['tradingsymbol']
                inst['expiry'] = datetime.fromisoformat(inst['expiry']) if inst[
                                                                               'expiry'] != '' else datetime.fromisoformat(
                    '2000-01-01')
                now = datetime.now()
                timestamp_diff = datetime(inst['expiry'].year, inst['expiry'].month,
                                          inst['expiry'].day).timestamp() - datetime(now.year, now.month,
                                                                                     now.day).timestamp()
                map_key = "%s-%s-%s-%s" % (
                inst['name'], inst['expiry'].date().isoformat(), int(inst['strike']), inst['instrument_type'])
                if inst['name'] == 'SENSEX':
                    if inst['expiry'].timestamp() not in self.sensex_expiry_list:
                        self.sensex_expiry_list.append(inst['expiry'].timestamp())
                    self.sensex_option_inst_token_map[map_key] = inst['instrument_token']
                    self.sensex_price_list.add(math.trunc(float(inst['strike'])))
                    if timestamp_diff >= 0 and timestamp_diff <= self.min_sensex_expiry_diff:
                        self.min_sensex_expiry_diff = timestamp_diff
                        self.sensex_nearest_expiry = "%s%s" % (
                        inst['expiry'].day, calendar.month_name[inst['expiry'].month][:3].upper())
            if inst['segment'] == 'INDICES':
                if inst['name'] == 'NIFTY 50':
                    self.nifty_50_inst_token = math.trunc(float(inst['instrument_token']))
                if inst['name'] == 'NIFTY BANK':
                    self.bank_nifty_inst_token = math.trunc(float(inst['instrument_token']))
                if inst['name'] == 'NIFTY MIDCAP SELECT (MIDCPNIFTY)':
                    self.mid_cap_nifty_inst_token = math.trunc(float(inst['instrument_token']))
                if inst['name'] == 'SENSEX':
                    self.sensex_inst_token = math.trunc(float(inst['instrument_token']))

        self.nifty_expiry_list = sorted(self.nifty_expiry_list)
        self.bank_nifty_expiry_list = sorted(self.bank_nifty_expiry_list)
        self.mid_cap_nifty_expiry_list = sorted(self.mid_cap_nifty_expiry_list)
        self.sensex_expiry_list = sorted(self.sensex_expiry_list)
        self.nifty_price_list = sorted(list(self.nifty_price_list))
        self.bank_nifty_price_list = sorted(list(self.bank_nifty_price_list))
        self.mid_cap_nifty_price_list = sorted(list(self.mid_cap_nifty_price_list))
        self.sensex_price_list = sorted(list(self.sensex_price_list))
        print(self.nifty_nearest_expiry)
        print(self.bank_nifty_nearest_expiry)
        print(self.nifty_50_inst_token)
        print(self.bank_nifty_inst_token)
        print(self.nifty_expiry_list)
        print(self.nifty_price_list)