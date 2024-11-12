import logging
import re
import copy
import traceback
import pytz
import time
from datetime import datetime, timedelta
from threading import Thread

from tips.market_guide import Telegram
from trading.models import TelegramMessage, TelegramTrade, EntryType
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from django.db.models import Q


class TradingManager(object):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.telegram = Telegram.get_instance()
        # self.telegram = None

    def schedule_task(self, payload):
        try:
            interval, _ = IntervalSchedule.objects.get_or_create(every=payload['interval_in_seconds'],
                                                                 period=IntervalSchedule.SECONDS)
            PeriodicTask.objects.create(
                interval=interval,
                start_time=payload['start_time'],
                name=payload['task_schedule_name'],
                task=payload['task_path']
                # task = "trading.tasks.process_telegram_messages",
                # args=json.dumps(["arg1", "arg2"])
                # one_off=True
            )
        except Exception as e:
            self.logger.error("ERROR: {}".format(str(e)))
            return False
        return True

    def login_into_telegram(self):
        self.telegram.refresh_instance()
        self.telegram.login_into_telegram()

    def process_telegram_messages_and_presist(self):
        self.logger.info("inside process_telegram_messages_and_presist")
        thread = Thread(target=self.process_telegram_messages_and_presist_loop_util)
        thread.start()

    def process_telegram_messages_and_presist_loop_util(self):
        # print("process_telegram_messages_and_presist")
        while True:
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
            if now.hour < 8 or now.hour >= 16:
                time.sleep(60 * 60)
                print("Skipping process_telegram_messages as market is closed!")
                continue
            if now.second % 55 == 0:
                print("process_telegram_messages")
            # self.process_telegram_messages_and_presist_util()
            # if now.hour == 3 and now.minute % 2 and now.second % 59 == 0:
            #     self.process_telegram_messages_and_presist_util(sell=True)
            if now.second % 55 == 0:
                self.process_telegram_messages_and_presist_util(sell=True)
            time.sleep(1)

    def process_telegram_messages_and_presist_util(self, sell=False):
        # print("process_telegram_messages_and_presist")
        if sell:
            message_map_list = self.telegram.get_telegram_messages('RISHAB | TRADER (PREMIUM)💰')
            # message_map_list = self.telegram.get_telegram_messages('Mine Airtel 1')
        else:
            message_map_list = self.telegram.get_telegram_messages()
        for message_map in message_map_list:
            telegram_message = TelegramMessage()
            telegram_message.message_id = message_map['message_id']
            text_pattern = r'[^a-zA-Z0-9\s]'
            cleaned_string = re.sub(text_pattern, '', message_map['text'])
            telegram_message.text = cleaned_string.encode('utf-8')
            # print("text length: %s" % len(telegram_message.text))
            time = '09:30 AM'
            time_pattern = r'\b(?:0?[1-9]|1[0-2]):[0-5][0-9] [APMapm]{2}\b'
            match = re.search(time_pattern, message_map['text'])
            is_message_edited = False
            if match:
                time = match.group(0)
                if 'edited' in message_map['text']:
                    is_message_edited = True
            else:
                print("No match found.")
            # print("time: %s" % time)
            date = self.update_datetime_with_time(
                self.convert_day_string_to_date(message_map['date'].strip()), time)

            telegram_message.created_at_time = date
            existing_message = TelegramMessage.objects.filter(Q(created_at_time=date) & Q(message_id=message_map['message_id'])).first()
            today_date = datetime.now().date()
            # Create a datetime object for today at 12:01 AM
            start_of_today = datetime.combine(today_date, datetime.min.time())

            # entry_placed_trades = TelegramTrade.objects.filter(
            #     Q(created_at_time__gte=start_of_today) & Q(order_status='ORDER_ENTRY_PLACED')
            # )
            # is_new_message = False
            # if existing_message is not None:
            #     existing_message = TelegramMessage.objects.filter(Q(text__icontains=cleaned_string)).first()
            #     if existing_message is None:
            #         telegram_message.save()
            #         is_new_message = True
            decoded_value = ''
            found_duplicate = False
            existing_messages = TelegramMessage.objects.filter(Q(created_at_time=date) & Q(message_id=message_map['message_id']))
            if is_message_edited and existing_messages is not None and len(existing_messages) > 0 and telegram_message is not None:
                # self.logger.info(is_message_edited)
                for temp in existing_messages:
                    db_value = temp.text
                    if db_value.startswith("b'") and db_value.endswith("'"):
                        byte_string = db_value[2:-1]
                    else:
                        raise ValueError("The input string is not in the expected format")

                    # Convert the string representation to an actual bytes object
                    byte_value = bytes(byte_string, 'utf-8').decode('unicode_escape').encode('latin1')

                    # Decode the bytes object to a string
                    decoded_value = byte_value.decode('utf-8')
                    if decoded_value == telegram_message.text.decode('utf-8'):
                        found_duplicate = True

                    # self.logger.info(decoded_value)
                    # self.logger.info(telegram_message.text.decode('utf-8'))
            if existing_message is None or (is_message_edited and not found_duplicate):
                if existing_message is None:
                    is_message_edited = False
                telegram_message.save()
                is_new_message = True
                self.parse_trade_info_from_message_and_persist(message_map['text'].strip(), date, is_message_edited, message_map, sell)
                self.parse_sell_trade_info_from_message_and_persist(message_map['text'].strip(), date, is_message_edited, message_map, sell)

        # pass

    def parse_trade_info_from_message_and_persist(self, text, date, is_message_edited, message_map, sell=False):
        if sell:
            return
        lower_text = text.lower()
        if 'nifty' not in lower_text and 'bank nifty' not in lower_text and 'midcpnifty' not in lower_text and 'sensex' not in lower_text:
            return
        splitted_text = text.split('\n')
        index_name = 'BANK NIFTY' if re.search('bank\s+nifty', lower_text) else 'NIFTY'
        if 'midcpnifty' in lower_text or 'midcap' in lower_text or ('mid' in lower_text and 'cap' in lower_text):
            index_name = 'MIDCPNIFTY'
        if 'sensex' in lower_text:
            index_name = 'SENSEX'
        telegram_trade = TelegramTrade()
        telegram_trade.index_name = index_name
        telegram_trade.created_at_time = date
        try:
            found_option_info = False
            found_entry_prices = False
            found_targets = False
            found_stop_loss = False
            for curr_text in splitted_text:
                lower_curr_text = curr_text.lower()
                option_info_pattern = re.compile(r'^(\d+\s+[a-zA-Z]+)\s*\( (\d+\s+[a-zA-Z]+\s+expiry) \)$')
                pattern_with_parentheses = re.compile(
                    r'^(\d+\s+[a-zA-Z]+\s*[a-zA-Z]*)\s*\(\s*(\d+\s+[a-zA-Z]+\s+expiry)\s*\)\s*$')
                pattern_without_parentheses = re.compile(
                    r'^(\d+\s+[a-zA-Z]+\s*[a-zA-Z]*)\s*(\d+\s+[a-zA-Z]+\s+expiry)\s*$')

                # Example usage
                # text = "47800 CE ( 20 DEC EXPIRY )"
                strike_price_text = lower_curr_text.replace('(', '').replace(')', '')
                option_info_match = pattern_with_parentheses.match(strike_price_text.strip())
                if option_info_match is None:
                    option_info_match = pattern_without_parentheses.match(strike_price_text.strip())
                if option_info_match:
                    group1 = option_info_match.group(1)
                    group2 = option_info_match.group(2)
                    telegram_trade.index_strike_price = int(''.join(re.findall(r'\d+', group1)))
                    telegram_trade.option_type = ''.join(re.findall(r'[a-zA-Z]', group1))
                    telegram_trade.option_type = telegram_trade.option_type.upper()
                    group2 = group2.replace('EXPIRY', '').replace('expiry', '').replace(' ', '').strip()
                    curr_date = int(''.join(re.findall(r'\d+', group2)))
                    month = ''.join(re.findall(r'[a-zA-Z]', group2))
                    month = month.upper()
                    telegram_trade.expiry = '%s %s' % (curr_date, month)
                    found_option_info = True
                elif not found_entry_prices and ('buy' in lower_curr_text or 'between' in lower_curr_text or found_option_info):
                    numbers = re.findall(r'\d+', lower_curr_text)
                    if len(numbers) >= 1:
                        telegram_trade.entry_start_price = numbers[0]
                        telegram_trade.entry_end_price = numbers[0]
                        found_entry_prices = True
                    if len(numbers) >= 2:
                        # telegram_trade.entry_start_price = numbers[0]
                        # telegram_trade.entry_end_price = numbers[1]
                        telegram_trade.entry_start_price = min(int(numbers[0]), int(numbers[1]))
                        telegram_trade.entry_end_price = max(int(numbers[0]), int(numbers[1]))
                        found_entry_prices = True
                elif not found_targets and ('profit' in lower_curr_text or found_entry_prices):
                    numbers = re.findall(r'\d+', lower_curr_text)
                    if len(numbers) >= 1:
                        telegram_trade.exit_first_target_price = numbers[0]
                        found_targets = True
                    if len(numbers) >= 2:
                        telegram_trade.exit_second_target_price = numbers[1]
                        found_targets = True
                    if len(numbers) >= 3:
                        telegram_trade.exit_third_target_price = numbers[2]
                        found_targets = True
                elif not found_stop_loss and (('stop' in lower_curr_text and 'loss' in lower_curr_text) or found_targets):
                    numbers = re.findall(r'\d+', lower_curr_text)
                    if len(numbers) >= 1:
                        telegram_trade.exit_stop_loss_price = numbers[0]
                        found_stop_loss = True
                    if 'hero' in lower_curr_text and 'zero' in lower_curr_text:
                        telegram_trade.exit_stop_loss_price = 0
                        found_stop_loss = True
            
            updated_order_status = None
            if lower_text.strip().find('cancelled') >= 0:
                updated_order_status = 'CANCEL'
            elif splitted_text[0].strip().find('exit at') >= 0:
                try:
                    updated_order_status = ' '.join(splitted_text[0].strip().split()[0:3]).upper()
                except Exception:
                    self.logger.error("Failed while updating order_status for EXIT AT case")
                    updated_order_status = 'EXIT_AT_CMP'
            # self.logger.info("is_message_edited: {}".format(is_message_edited))
            if is_message_edited:
                existing_telegram_trades = list(TelegramTrade.objects.filter(
                    Q(index_name=telegram_trade.index_name)
                    & Q(index_strike_price=telegram_trade.index_strike_price)
                    & Q(option_type=telegram_trade.option_type)
                ))
                if len(existing_telegram_trades) > 0 and existing_telegram_trades[0] is not None:
                    # existing_telegram_trade = existing_telegram_trades[0]
                    for existing_telegram_trade in existing_telegram_trades:
                        if 'NOT_PLACED' in existing_telegram_trade.order_status:
                            existing_telegram_trade.order_status = 'EXPIRED'
                            existing_telegram_trade.save()
                        else:
                            existing_metadata = existing_telegram_trade.get_metadata_as_dict()
                            if existing_metadata is None:
                                existing_metadata = {}
                            existing_metadata['updated_order_status'] = 'CANCELLED'
                            existing_telegram_trade.set_metadata_from_dict(existing_metadata)
                            existing_telegram_trade.save()
                else:
                    self.logger.error("message was edited but no existing message was found")
            skip_new_trade = False
            # self.logger.info("updated_order_status: {}".format(updated_order_status))
            if updated_order_status is not None:
                today_date = datetime.now().date()
                # Create a datetime object for today at 12:01 AM
                start_of_today = datetime.combine(today_date, datetime.min.time())
                existing_telegram_trades = TelegramTrade.objects.filter(
                    Q(created_at_time__gte=start_of_today) & Q(index_name=telegram_trade.index_name)
                    & Q(index_strike_price=telegram_trade.index_strike_price)
                    & Q(option_type=telegram_trade.option_type)
                    & Q(entry_start_price=telegram_trade.entry_start_price)
                    & Q(entry_end_price=telegram_trade.entry_end_price)
                    & Q(exit_stop_loss_price=telegram_trade.exit_stop_loss_price)
                )
                # self.logger.info("existing_telegram_trades len: {}".format(len(existing_telegram_trades)))
                for existing_telegram_trade in existing_telegram_trades:
                    # self.logger.info("existing_telegram_trade: {}".format(existing_telegram_trade))
                    if existing_telegram_trade is None:
                        continue
                    existing_metadata = existing_telegram_trade.get_metadata_as_dict()
                    if existing_metadata is None:
                        existing_metadata = {}
                    existing_metadata['updated_order_status'] = updated_order_status
                    existing_telegram_trade.set_metadata_from_dict(existing_metadata)
                    # existing_telegram_trade.order_status = updated_order_status
                    existing_telegram_trade.save()
                    skip_new_trade = True
                # telegram_trade.order_status = 'NOT_PLACED'
                # entry_types = EntryType.objects.all()
                # if len(entry_types) == 0:
                #     telegram_trade.save()
                # else:
                #     for type_obj in entry_types:
                #         new_telegram_trade = copy.deepcopy(telegram_trade)
                #         new_telegram_trade.entry_type = type_obj.entry_type
                #         new_telegram_trade.save()

            else:
                telegram_trade.order_status = 'NOT_PLACED'
                entry_types = EntryType.objects.all()
                if len(entry_types) == 0:
                    telegram_trade.save()
                else:
                    for type_obj in entry_types:
                        new_telegram_trade = copy.deepcopy(telegram_trade)
                        new_telegram_trade.entry_type = type_obj.entry_type
                        new_telegram_trade.order_id = ''
                        new_telegram_trade.save()
        except Exception as e:
            traceback.print_exc()
            self.logger.error("ERROR: {}".format("Failed while converting telegram message to trade"))

        # pass

    def parse_sell_trade_info_from_message_and_persist(self, text, date, is_message_edited, message_map, sell=False):
        upper_text = text.upper()
        splitted_text = upper_text.split('\n')

        # Hold until any of the hedge trades are in waiting state 
        while True:
            cancelled_waiting_trades = TelegramTrade.objects.filter(
                Q(entry_type='DHAN_HEDGE')
                & ~Q(order_status='EXPIRED')
                & Q(metadata__icontains='CANCELLED_WAITING'))
            if not cancelled_waiting_trades:
                break
            time.sleep(60)

        try:
            is_trade_message = False

            newly_added_trades = []
            for curr_text in splitted_text:
                # print(curr_text)
                telegram_trade = TelegramTrade()
                telegram_trade.index_name = 'BANKNIFTY'
                telegram_trade.created_at_time = date
                pattern = r'(BUY|SELL)\s+(BN|NIFTY|FINN)\s+(\d+)([A-Z]+)\s+(\d+)QTY'
                pattern2 = r'(BUY|SELL)\s+(BN|NIFTY|FINN)\s+(\d+)([A-Z]+)\s+(\d+)?\s*([A-Z]+)?\s*(\d+)QTY'
                match = re.search(pattern, curr_text)
                match2 = re.search(pattern2, curr_text)
                is_new_trade = False
                is_trade_message = is_trade_message or ((match is not None) or (match2 is not None))
                if match:
                    action_type = match.group(1)
                    index_name = match.group(2)
                    if index_name == 'BN':
                        index_name = 'BANKNIFTY'
                    elif index_name == 'NIFTY':
                        index_name = 'NIFTY'
                    elif index_name == 'FINN':
                        index_name = 'FINNIFTY'
                    telegram_trade.index_name = index_name
                    strike_price = int(match.group(3))
                    telegram_trade.index_strike_price = strike_price
                    option_type = match.group(4)
                    telegram_trade.option_type = option_type
                    quantity = int(match.group(5))
                    telegram_trade.quantity = quantity
                    message_id = message_map['message_id'] if 'message_id' in message_map else ''
                    metadata = {'action_type': action_type, 'strategy': 'DHAN_HEDGE', 'message_id': message_map['message_id'],
                        'quantity': quantity}
                    telegram_trade.set_metadata_from_dict(metadata)
                    telegram_trade.expiry = 'latest'
                    diff = False
                    create_new_trade = False
                    exact_match_trade = TelegramTrade.objects.filter(
                        Q(entry_type='DHAN_HEDGE')
                        & Q(index_name=telegram_trade.index_name)
                        & Q(index_strike_price=telegram_trade.index_strike_price)
                        & Q(option_type=telegram_trade.option_type)
                        & Q(expiry=telegram_trade.expiry)
                        & Q(metadata__icontains='"message_id": "%s"' % message_id)
                    ).first()
                    if is_message_edited:
                        existing_telegram_trades = list(TelegramTrade.objects.filter(
                            Q(entry_type='DHAN_HEDGE')
                            & Q(metadata__icontains='"message_id": "%s"' % message_id)
                        ).order_by('-created_at_time'))
                        if len(existing_telegram_trades) > 0 and existing_telegram_trades[0] is not None:
                            existing_telegram_trade = existing_telegram_trades[0]
                            if not exact_match_trade:
                                diff = True
                            # if telegram_trade.quantity != existing_telegram_trade.quantity:
                            #     diff = True
                            if diff:
                                for existing_telegram_trade in existing_telegram_trades:
                                    if existing_telegram_trade.id in newly_added_trades:
                                        continue
                                    if 'NOT_PLACED' in existing_telegram_trade.order_status:
                                        existing_telegram_trade.order_status = 'EXPIRED'
                                        existing_telegram_trade.save()
                                    else:
                                        existing_metadata = existing_telegram_trade.get_metadata_as_dict()
                                        if existing_metadata is None:
                                            existing_metadata = {}
                                        existing_metadata['updated_order_status'] = 'CANCELLED'
                                        existing_telegram_trade.set_metadata_from_dict(existing_metadata)
                                        existing_telegram_trade.save()
                        else:
                            self.logger.error("message was edited but no existing message was found")
                            create_new_trade = True
                        if diff:
                            create_new_trade = True
                    else:
                        create_new_trade = True
                        
                    if create_new_trade and not exact_match_trade:
                        telegram_trade.entry_start_price = -1
                        telegram_trade.entry_end_price = -1
                        telegram_trade.exit_first_target_price = -1
                        telegram_trade.exit_second_target_price = -1
                        telegram_trade.exit_third_target_price = -1
                        telegram_trade.exit_stop_loss_price = -1
                        telegram_trade.order_status = 'NOT_PLACED_DHAN'
                        telegram_trade.entry_type = 'DHAN_HEDGE'
                        telegram_trade.order_id = ''
                        telegram_trade.save()
                        newly_added_trades.append(telegram_trade.id)
                        is_new_trade = True
                elif match2:
                    action_type = match2.group(1)
                    index_name = match2.group(2)
                    if index_name == 'BN':
                        index_name = 'BANKNIFTY'
                    elif index_name == 'NIFTY':
                        index_name = 'NIFTY'
                    elif index_name == 'FINN':
                        index_name = 'FINNIFTY'
                    telegram_trade.index_name = index_name
                    strike_price = int(match2.group(3))
                    telegram_trade.index_strike_price = strike_price
                    option_type = match2.group(4)
                    telegram_trade.option_type = option_type
                    day = match2.group(5)
                    month = match2.group(6)[:3]
                    expiry = '%s %s' % (day, month)
                    telegram_trade.expiry = expiry
                    quantity = int(match2.group(7))
                    telegram_trade.quantity = quantity
                    message_id = message_map['message_id'] if 'message_id' in message_map else ''
                    metadata = {'action_type': action_type, 'strategy': 'DHAN_HEDGE', 'message_id': message_map['message_id'],
                        'quantity': quantity}
                    telegram_trade.set_metadata_from_dict(metadata)
                    # telegram_trade.expiry = 'latest'
                    diff = False
                    create_new_trade = False
                    exact_match_trade = TelegramTrade.objects.filter(
                        Q(entry_type='DHAN_HEDGE')
                        & Q(index_name=telegram_trade.index_name)
                        & Q(index_strike_price=telegram_trade.index_strike_price)
                        & Q(option_type=telegram_trade.option_type)
                        & Q(expiry=telegram_trade.expiry)
                        & Q(metadata__icontains='"message_id": "%s"' % message_id)
                    ).first()
                    if is_message_edited:
                        existing_telegram_trades = list(TelegramTrade.objects.filter(
                            Q(entry_type='DHAN_HEDGE')
                            & Q(metadata__icontains='"message_id": "%s"' % message_id)
                        ).order_by('-created_at_time'))
                        if len(existing_telegram_trades) > 0 and existing_telegram_trades[0] is not None:
                            existing_telegram_trade = existing_telegram_trades[0]
                            # TODO: Check the diff between existing_telegram_trade and new telegram_trade
                            # If there is a diff, then only cancel or expire existing and create new trade
                            # Otherwise no need to cancel or expire existing and create new trade
                            if not exact_match_trade:
                                diff = True
                            # if telegram_trade.quantity != existing_telegram_trade.quantity:
                            #     diff = True
                            if diff:
                                for existing_telegram_trade in existing_telegram_trades:
                                    if existing_telegram_trade.id in newly_added_trades:
                                        continue
                                    if 'NOT_PLACED' in existing_telegram_trade.order_status:
                                        existing_telegram_trade.order_status = 'EXPIRED'
                                        existing_telegram_trade.save()
                                    else:
                                        existing_metadata = existing_telegram_trade.get_metadata_as_dict()
                                        if existing_metadata is None:
                                            existing_metadata = {}
                                        existing_metadata['updated_order_status'] = 'CANCELLED'
                                        existing_telegram_trade.set_metadata_from_dict(existing_metadata)
                                        existing_telegram_trade.save()
                        else:
                            self.logger.error("message was edited but no existing message was found")
                            create_new_trade = True
                        if diff:
                            create_new_trade = True
                    else:
                        create_new_trade = True
                    
                    if create_new_trade and not exact_match_trade:
                        telegram_trade.entry_start_price = -1
                        telegram_trade.entry_end_price = -1
                        telegram_trade.exit_first_target_price = -1
                        telegram_trade.exit_second_target_price = -1
                        telegram_trade.exit_third_target_price = -1
                        telegram_trade.exit_stop_loss_price = -1
                        telegram_trade.order_status = 'NOT_PLACED_DHAN'
                        telegram_trade.entry_type = 'DHAN_HEDGE'
                        telegram_trade.order_id = ''
                        telegram_trade.save()
                        newly_added_trades.append(telegram_trade.id)
                        is_new_trade = True

                pattern = r'(SL|TGT)\s+-\s+(BN|NIFTY|FINN)\s+(\d+)([A-Z]+)\s+(\d+)QTY\s+-\s+(HOLD\s+TILL\s+EXPIRY|[\d.,\s]+)'
                pattern2 = r'(SL|TGT)\s+-\s+(BN|NIFTY|FINN)\s+(\d+)([A-Z]+)\s+(\d+)?\s*([A-Z]+)?\s*(\d+)QTY\s+-\s+(HOLD\s+TILL\s+EXPIRY|[\d.,\s]+)'
                match = re.search(pattern, curr_text)
                match2 = re.search(pattern2, curr_text)
                is_trade_message = is_trade_message or ((match is not None) or (match2 is not None))
                if match:
                    is_stop_loss = match.group(1) == 'SL'
                    is_target = match.group(1) == 'TGT'
                    index_name = match.group(2)
                    if index_name == 'BN':
                        index_name = 'BANKNIFTY'
                    elif index_name == 'NIFTY':
                        index_name = 'NIFTY'
                    elif index_name == 'FINN':
                        index_name = 'FINNIFTY'
                    strike_price = int(match.group(3))
                    option_type = match.group(4)
                    quantity = match.group(5)
                    prices = match.group(6)
                    if 'HOLD' in prices and 'TILL' in prices and 'EXPIRY' in prices:
                        continue
                    prices = [float(i) for i in prices.split(',')]
                    existing_telegram_trade = TelegramTrade.objects.filter(
                            Q(index_name=index_name)
                            & Q(index_strike_price=strike_price)
                            & Q(option_type=option_type)
                            & Q(entry_type='DHAN_HEDGE')
                            & ~Q(order_status='EXPIRED')
                            & ~Q(metadata__icontains='"CANCELLED"')
                            & Q(metadata__icontains='"SELL"')
                        ).order_by('-created_at_time').first()
                    if existing_telegram_trade is not None:
                        existing_metadata = existing_telegram_trade.get_metadata_as_dict()
                        if is_stop_loss:
                            existing_metadata['stop_loss'] = prices[0]
                        if is_target:
                            existing_metadata['targets'] = prices
                        existing_telegram_trade.set_metadata_from_dict(existing_metadata)
                        existing_telegram_trade.save()
                elif match2:
                    is_stop_loss = match2.group(1) == 'SL'
                    is_target = match2.group(1) == 'TGT'
                    index_name = match2.group(2)
                    if index_name == 'BN':
                        index_name = 'BANKNIFTY'
                    elif index_name == 'NIFTY':
                        index_name = 'NIFTY'
                    elif index_name == 'FINN':
                        index_name = 'FINNIFTY'
                    strike_price = int(match2.group(3))
                    option_type = match2.group(4)
                    day = match2.group(5)
                    month = match2.group(6)[:3]
                    expiry = '%s %s' % (day, month)
                    quantity = match2.group(7)
                    prices = match2.group(8)
                    if 'HOLD' in prices and 'TILL' in prices and 'EXPIRY' in prices:
                        continue
                    prices = [float(i) for i in prices.split(',')]
                    existing_telegram_trade = TelegramTrade.objects.filter(
                            Q(index_name=index_name)
                            & Q(index_strike_price=strike_price)
                            & Q(option_type=option_type)
                            & Q(entry_type='DHAN_HEDGE')
                            & ~Q(order_status='EXPIRED')
                            & ~Q(metadata__icontains='"CANCELLED"')
                            & Q(metadata__icontains='"SELL"')
                        ).order_by('-created_at_time').first()
                    # print(index_name)
                    # print(strike_price)
                    # print(option_type)
                    # print(existing_telegram_trade)
                    if existing_telegram_trade is not None:
                        print("Found existing_telegram_trade")
                        existing_metadata = existing_telegram_trade.get_metadata_as_dict()
                        if is_stop_loss:
                            existing_metadata['stop_loss'] = prices[0]
                        if is_target:
                            existing_metadata['targets'] = prices
                        existing_telegram_trade.set_metadata_from_dict(existing_metadata)
                        existing_telegram_trade.save()

            if not is_trade_message:
                exit_condition = False
                if 'EXIT' in upper_text or 'CLOSE' in upper_text or ('TARGET' in upper_text and 'DONE' in upper_text):
                    exit_condition = True
                exit_legs = 'BOTH'
                if 'CALL' in upper_text and 'PUT' not in upper_text:
                    exit_legs = 'CALL'
                elif 'PUT' in upper_text and 'CALL' not in upper_text:
                    exit_legs = 'PUT'

                if exit_condition and (exit_legs == 'CALL' or exit_legs == 'BOTH'):
                    existing_telegram_trades = TelegramTrade.objects.filter(
                            Q(option_type='CE')
                            & Q(created_at_time__lte=date)
                            & Q(entry_type='DHAN_HEDGE')
                            & (Q(order_status='ORDER_PLACED_DHAN') | Q(order_status='SL_TARGET_ORDER_PLACED_DHAN'))
                        )
                    for trade in existing_telegram_trades:
                        metadata = trade.get_metadata_as_dict()
                        metadata['updated_order_status'] = 'CANCELLED'
                        trade.set_metadata_from_dict(metadata)
                        trade.save()
                
                if exit_condition and (exit_legs == 'PUT' or exit_legs == 'BOTH'):
                    existing_telegram_trades = TelegramTrade.objects.filter(
                            Q(option_type='PE')
                            & Q(created_at_time__lte=date)
                            & Q(entry_type='DHAN_HEDGE')
                            & (Q(order_status='ORDER_PLACED_DHAN') | Q(order_status='SL_TARGET_ORDER_PLACED_DHAN'))
                        )
                    for trade in existing_telegram_trades:
                        metadata = trade.get_metadata_as_dict()
                        metadata['updated_order_status'] = 'CANCELLED'
                        trade.set_metadata_from_dict(metadata)
                        trade.save()

            if is_new_trade:
                existing_telegram_trades = TelegramTrade.objects.filter(
                        Q(entry_type='DHAN_HEDGE')
                        & (Q(order_status='ORDER_PLACED_DHAN') | Q(order_status='SL_TARGET_ORDER_PLACED_DHAN'))
                    )
                for trade in existing_telegram_trades:
                    metadata = trade.get_metadata_as_dict()
                    metadata['updated_order_status'] = 'CANCELLED'
                    trade.set_metadata_from_dict(metadata)
                    trade.save()

        except Exception as e:
            traceback.print_exc()
            self.logger.error("ERROR: {}".format("Failed while converting telegram message to dhan hedge trade"))

    def convert_day_string_to_date(self, day_string):
        # Map day strings to corresponding weekdays
        day_mapping = {'Monday': 0,
                       'Tuesday': 1,
                       'Wednesday': 2,
                       'Thursday': 3,
                       'Friday': 4,
                       'Saturday': 5,
                       'Sunday': 6}

        # Get the current date and time
        current_datetime = datetime.now()

        if day_string == 'Today':
            return current_datetime
        elif day_string == 'Yesterday':
            return current_datetime - timedelta(days=1)
        elif day_string in day_mapping:
            # Calculate the difference in days between the current day and the target day
            day_difference = (current_datetime.weekday() - day_mapping[day_string] + 7) % 7
            if day_difference == 0:
                day_difference = 7

            # Subtract the difference to get the target day's date
            target_date = current_datetime - timedelta(days=day_difference)

            return target_date
        else:
            try:
                # Try to parse the input as a date format like "November 16"
                target_date = datetime.strptime(day_string, "%B %d")
                # Check if the parsed date is in the future, adjust the year accordingly
                if target_date > current_datetime:
                    target_date = target_date.replace(year=current_datetime.year - 1)
                return target_date
            except ValueError:
                pass  # Continue to handle other cases

        return current_datetime

    def update_datetime_with_time(self, original_datetime, new_time):
        # Parse the new time string to a datetime object (assuming it's in the format "12:52 PM")
        new_time_obj = datetime.strptime(new_time, "%I:%M %p").time()

        # Extract the date part from the original datetime
        date_part = original_datetime.date()

        # Combine the date part and the new time to create the updated datetime object
        updated_datetime = datetime.combine(date_part, new_time_obj)

        return updated_datetime

