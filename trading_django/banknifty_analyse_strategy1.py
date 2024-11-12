from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from dhanhq import dhanhq
from PIL import Image
from datetime import datetime, timedelta

import math
import json
import time
import os
import pytesseract
import re
import logging

logging.basicConfig(filename='banknifty_analyse.log', level=logging.INFO,
                    format='%(asctime)s - %(message)s')
# Example usage:
time_range_map_list = [
    {"day_diff": -0.5, "start": "14:11", "end": "09:34", "minute_diff": 100},
    {"day_diff": 0, "start": "12:32", "end": "14:10", "minute_diff": 99},
    {"day_diff": 0, "start": "10:52", "end": "12:31", "minute_diff": 100},
    {"day_diff": 0.5, "start": "15:28", "end": "10:51", "minute_diff": 99},
    {"day_diff": 1, "start": "13:48", "end": "15:27", "minute_diff": 100},
    {"day_diff": 1, "start": "12:09", "end": "13:47", "minute_diff": 99},
    {"day_diff": 1, "start": "10:29", "end": "12:08", "minute_diff": 100},
    {"day_diff": 1.5, "start": "15:04", "end": "10:28", "minute_diff": 100},
    {"day_diff": 2, "start": "13:25", "end": "15:03", "minute_diff": 99},
    {"day_diff": 2, "start": "11:45", "end": "13:24", "minute_diff": 100},
    {"day_diff": 2, "start": "10:06", "end": "11:44", "minute_diff": 99},
    {"day_diff": 2.5, "start": "14:42", "end": "10:05", "minute_diff": 99},
    {"day_diff": 3, "start": "13:03", "end": "14:41", "minute_diff": 99},
    {"day_diff": 3, "start": "11:23", "end": "13:02", "minute_diff": 100},
    {"day_diff": 3, "start": "09:44", "end": "11:22", "minute_diff": 99},
    {"day_diff": 3.5, "start": "14:20", "end": "09:43", "minute_diff": 99},
    {"day_diff": 4, "start": "12:40", "end": "14:19", "minute_diff": 100},
    {"day_diff": 4, "start": "11:01", "end": "12:39", "minute_diff": 99},
    {"day_diff": 4, "start": "09:21", "end": "11:00", "minute_diff": 100},
    {"day_diff": 4.5, "start": "13:58", "end": "09:20", "minute_diff": 98},
    {"day_diff": 5, "start": "12:18", "end": "13:57", "minute_diff": 100},
    {"day_diff": 5, "start": "10:39", "end": "12:17", "minute_diff": 99},
    {"day_diff": 5.5, "start": "15:14", "end": "10:38", "minute_diff": 100},
    {"day_diff": 6, "start": "13:35", "end": "15:13", "minute_diff": 99},
    {"day_diff": 6, "start": "11:51", "end": "13:34", "minute_diff": 104},
    {"day_diff": 6, "start": "10:11", "end": "11:50", "minute_diff": 100},
    {"day_diff": 6.5, "start": "14:45", "end": "10:10", "minute_diff": 101},
    {"day_diff": 7, "start": "12:56", "end": "14:44", "minute_diff": 109},
    {"day_diff": 7, "start": "09:53", "end": "12:55", "minute_diff": 183},
    {"day_diff": 7.5, "start": "14:20", "end": "09:52", "minute_diff": 108},
]

def write_to_file(data, filename):
    # Check if the file exists to avoid FileNotFoundError
    if os.path.exists(filename):
        # Read the existing data from the file
        with open(filename, 'r') as json_file:
            try:
                existing_data = json.load(json_file)
            except json.JSONDecodeError:
                existing_data = {}  # If file is empty or corrupt, start with an empty dictionary
    else:
        existing_data = {}

    # Update the existing data with new data
    existing_data.update(data)

    # Write the updated data back to the file
    with open(filename, 'w') as json_file:
        json.dump(existing_data, json_file, indent=4)  # indent=4 for readable formatting

def find_market_day_diff(curr_date, expiry_date, all_dates_list):
    def parse_date(date_str):
        try:
            # Try parsing as "YYYY-MM-DD"
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            # If it fails, parse as "YY/MM/DD"
            return datetime.strptime(date_str, "%d/%m/%y")
    expiry_date_formatted = parse_date(expiry_date).strftime("%d/%m/%y")
    cnt = -1
    print("curr_date: %s, expiry_date_formatted: %s" % (curr_date, expiry_date_formatted))
    if curr_date == expiry_date_formatted:
        return 0
    for date in all_dates_list:
        if date == expiry_date_formatted:
            cnt = 0
        if cnt >= 0:
            cnt += 1
        if date == curr_date:
            break
    return cnt

def get_nearest_expiry(curr_date, expiry_list):
    def parse_date(date_str):
        try:
            # Try parsing as "YYYY-MM-DD"
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            # If it fails, parse as "YY/MM/DD"
            return datetime.strptime(date_str, "%d/%m/%y")

    # Convert curr_date to a datetime object
    # curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date_dt = parse_date(curr_date)

    # Convert all expiry dates to datetime objects
    expiry_dates_dt = [datetime.strptime(date, "%Y-%m-%d") for date in expiry_list]

    # Find all dates greater than the current date
    future_dates = [date for date in expiry_dates_dt if date >= curr_date_dt]

    # Find the nearest future date
    nearest_expiry = min(future_dates) if future_dates else None

    # Convert the nearest expiry back to string if it's not None
    nearest_expiry_str = nearest_expiry.strftime("%Y-%m-%d") if nearest_expiry else None

    # Display the result
    logging.info("curr_date: %s, nearest_expiry_str: %s" % (curr_date, nearest_expiry_str))
    return nearest_expiry_str


def login_into_go_charting_and_get_expiry_list(driver):
    is_logged_in = False
    login_button = driver.find_element(By.ID, 'login-avatar')
    image_elements = login_button.find_elements(By.CSS_SELECTOR, 'img')
    dismiss_buttons = driver.find_elements(By.ID, 'notification-dismiss')
    if len(dismiss_buttons) > 0:
        dismiss_buttons[0].click()
        time.sleep(1)
    if len(image_elements) > 0:
        logging.info("Already Logged In!")
        is_logged_in = True
    if not is_logged_in:
        image_element = driver.find_element(By.CSS_SELECTOR, 'img[src="/assets/image/IN.svg"]')
        driver.execute_script("arguments[0].style.display = 'none';", image_element)
        time.sleep(1)  # Wait for changes to take effect
        login_button = driver.find_element(By.ID, 'login-avatar')
        login_button.click()
        time.sleep(1)
        email_input = driver.find_element(By.ID, 'email_field')
        email_input.send_keys('chandan5284ssb@gmail.com')
        password_input = driver.find_element(By.ID, 'password_field')
        password_input.send_keys('xxx')
        time.sleep(0.1)
        all_buttons = driver.find_elements(By.CSS_SELECTOR, 'button')
        for button in all_buttons:
            if button.text == 'Sign In':
                logging.info("Found Sign In Button")
                button.click()
                break
        time.sleep(2)
    collapse_button = driver.find_elements(By.ID, 'collapse-left-bar')[1]
    collapse_button_style = collapse_button.get_attribute('style')
    logging.info(collapse_button_style)
    if collapse_button_style == 'right: 5px;':
        collapse_button.click()
    time.sleep(1)
    collapse_button = driver.find_elements(By.ID, 'collapse-left-bar')[1]
    collapse_button_style = collapse_button.get_attribute('style')
    search = driver.find_elements(By.CLASS_NAME, 'ticker-search')
    logging.info("search button length: %s" % len(search))
    max_loop_count = 3
    while len(search) < 2 and max_loop_count > 0:
        # Locate the element you want to hover over
        element_to_hover = driver.find_element(By.ID, 'alerts-icontab')

        # Perform the hover action
        actions = ActionChains(driver)
        actions.move_to_element(element_to_hover).perform()

        # Pause for a moment to ensure the hover effect takes place
        time.sleep(1)

        buttons = driver.find_elements(By.XPATH, "//button[./*[name()='svg'] and @style]")
        down_button = None
        for button in buttons:
            if 'position: absolute' in button.get_attribute('style'):
                down_button = button

        for i in range(10):
            down_button.click()

        time.sleep(1)

        expired_button = driver.find_element(By.ID, 'expiredfno-icontab')
        expired_button.click()
        time.sleep(1)
        search = driver.find_elements(By.CLASS_NAME, 'ticker-search')
        logging.info("search button length: %s" % len(search))
        max_loop_count -= 1
    time.sleep(1)
    search[1].clear()
    search[1].send_keys('BANKNIFTY')
    time.sleep(1)
    button = driver.find_elements(By.CLASS_NAME, 'stunnerrow')
    button[0].click()
    time.sleep(1)
    expiry_dropdown = driver.find_element(By.CSS_SELECTOR, 'select')
    expiry_dropdown.click()
    dropdown = Select(expiry_dropdown)
    options = dropdown.options
    option_texts = [option.text for option in options]
    return option_texts

def get_market_minutes(time_str):
    """Converts a time in 'HH:MM' format to market minutes since 9:15 AM."""
    hours, minutes = map(int, time_str.split(":"))
    total_minutes = hours * 60 + minutes
    market_open = 9 * 60 + 15  # 9:15 AM in minutes
    market_close = 15 * 60 + 29  # 3:29 PM in minutes

    if total_minutes < market_open:
        # If the time is before 9:15 AM, set to 9:15 AM.
        return 0
    elif total_minutes > market_close:
        # If the time is after 3:29 PM, set to the end of the market day.
        return market_close - market_open

    return total_minutes - market_open


def get_shifts_and_offset(time_range_map_list, curr_time, curr_day_diff):
    curr_time_min = get_market_minutes(curr_time)
    for i in range(len(time_range_map_list)):
        curr_dict = time_range_map_list[i]
        if abs(curr_dict['day_diff'] - curr_day_diff) <= 0.5:
            logging.info(curr_dict)
            diff_min = 0
            type = ''
            if curr_dict['day_diff'] < curr_day_diff:
                first_st_min = get_market_minutes(curr_dict['start'])
                first_end_min = get_market_minutes("15:29")

                # second_st_min = get_market_minutes("09:15")
                # second_end_min = get_market_minutes(curr_dict['end'])
                
                if first_st_min <= curr_time_min <= first_end_min:
                    diff_min = curr_time_min - first_st_min
                    type = 'FRONT'

                # if second_st_min <= curr_time_min <= second_end_min:
                #     diff_min = second_end_min - curr_time_min
                #     type = 'BACK'
            elif curr_dict['day_diff'] > curr_day_diff:
                # first_st_min = get_market_minutes(curr_dict['start'])
                # first_end_min = get_market_minutes("15:29")

                second_st_min = get_market_minutes("09:15")
                second_end_min = get_market_minutes(curr_dict['end'])

                # if first_st_min <= curr_time_min <= first_end_min:
                #     diff_min = curr_time_min - first_st_min
                #     type = 'FRONT'

                if second_st_min <= curr_time_min <= second_end_min:
                    diff_min = second_end_min - curr_time_min
                    type = 'BACK'
            else:
                first_st_min = get_market_minutes(curr_dict['start'])
                first_end_min = get_market_minutes("15:29")

                if first_st_min <= curr_time_min <= first_end_min:
                    diff_min = curr_time_min - first_st_min
                    type = 'FRONT'

            pixel_diff = 666 / 99
            logging.info("pixel_diff: %s" % pixel_diff)
            logging.info("diff_min: %s" % diff_min)
            if type == 'FRONT':
                shifts = i
                offset = -330 + diff_min * pixel_diff
                return {'shifts': shifts, 'offset': offset}

            if type == 'BACK':
                shifts = i
                offset = 336 - diff_min * pixel_diff
                return {'shifts': shifts, 'offset': offset}
    return None


def extract_datetime(text):
    pattern = r"(\b\d{2}\b)\s(\w{3})\s(\d{2})\s(\d{2}:\d{2})"

    # Search for the pattern in the text
    match = re.search(pattern, text)

    # Extracting the matched groups if a match is found
    if match:
        date, month, year, time = match.groups()
        # Combine the extracted components into a single string
        date_str = f"{date} {month} {year} {time}"

        # Convert the combined string into a datetime object using strptime
        date_obj = datetime.strptime(date_str, "%d %b %y %H:%M")

        print(f"Datetime object: {date_obj}")
        print(f"Formatted datetime: {date_obj.strftime('%Y-%m-%d %H:%M:%S')}")
        return date_obj
    else:
        print("No match found.")
        return None


def extract_prices(text):
    # Define regex patterns to extract Open, High, Low, and Close prices
    pattern = r"O:(\d+(\.\d+)?)H:(\d+(\.\d+)?)L:(\d+(\.\d+)?)C:(\d+(\.\d+)?)"

    # Search for the pattern in the text
    match = re.search(pattern, text)
    if match:
        # Extracted values for Open, High, Low, and Close
        open_price = float(match.group(1))
        high_price = float(match.group(3))
        low_price = float(match.group(5))
        close_price = float(match.group(7))

        return {
            "Open": open_price,
            "High": high_price,
            "Low": low_price,
            "Close": close_price
        }
    else:
        return {}


def get_premium_date(driver, expiry, strike_price, option_type, day_diff, curr_date, from_time='09:15', min_duration=60):
    trading_symbol = "%s-%s-%s-%s" % (
        'BANKNIFTY',
        expiry, strike_price, option_type)
    filename = '/Users/chandack/Documents/algo-trade/trading_django/premium_data.json'
    file_premium_data = {}
    with open(filename, 'r') as file:
        file_premium_data = json.load(file)

    premium_data = {}
    found = True
    for i in range(min_duration):
        curr_minute = int(from_time.split(':')[0]) * 60 + int(from_time.split(':')[1])
        curr_minute = curr_minute + i
        clock_hours = '0%s' % int(curr_minute / 60)
        clock_minutes = '0%s' % int(curr_minute % 60)
        clock = '%s:%s' % (clock_hours[-2:], clock_minutes[-2:])

        key = '%s-%s' % (trading_symbol, clock)
        if key in file_premium_data:
            premium_data[key] = file_premium_data[key]
        else:
            found = False

    if found:
        return premium_data

    expiry_dropdown = driver.find_element(By.CSS_SELECTOR, 'select')
    expiry_dropdown.click()

    dropdown = Select(expiry_dropdown)
    dropdown.select_by_visible_text(expiry)

    input = driver.find_elements(By.CSS_SELECTOR, 'input')
    input[2].clear()
    input[2].send_keys(strike_price)
    time.sleep(0.1)

    all_rows = driver.find_elements(By.CLASS_NAME, 'rt-tr-group')
    strike_price_str = '%s' % strike_price
    for row in all_rows:
        if strike_price_str in row.text and option_type in row.text:
            svg = row.find_element(By.CSS_SELECTOR, 'svg')
            svg.click()
            time.sleep(1)

    period_dropdown = driver.find_element(By.ID, 'interval-selector-btn')
    period_dropdown.click()
    time.sleep(1)
    all_divs = driver.find_elements(By.CSS_SELECTOR, 'div')
    for div in all_divs:
        if div is not None and div.get_attribute('title') == '1 Minute':
            logging.info("Found 1 Minute dropdown")
            div.click()
            break

    time.sleep(0.1)

    refresh_button = driver.find_element(By.ID, 'refresh-button')
    refresh_button.click()

    time.sleep(0.1)

    data = get_shifts_and_offset(time_range_map_list, from_time, day_diff)
    shifts = data['shifts']
    offset = data['offset']
    logging.info(f"Number of shifts: {data['shifts']}, X Offset: {data['offset']}")

    graph_element = driver.find_element(By.CLASS_NAME, 'gocharting-pos-abs')
    actions = ActionChains(driver)

    pixel_diff = 666 / 99
    for i in range(shifts):
        actions = actions.click_and_hold(graph_element)
        actions = actions.move_by_offset(pixel_diff * 100, 0)
        actions.release().perform()
        time.sleep(0.5)

    should_verify_image = False
    prev_minute = int(from_time.split(':')[0]) * 60 + int(from_time.split(':')[1])
    
    min_index = 0
    max_loop_cnt = 1000
    curr_offset = offset
    while min_index < min_duration and max_loop_cnt > 0:
        curr_minute = prev_minute + min_index
        logging.info("curr_minute: %s" % curr_minute)
        clock_hours = '0%s' % int(curr_minute / 60)
        clock_minutes = '0%s' % int(curr_minute % 60)
        clock = '%s:%s' % (clock_hours[-2:], clock_minutes[-2:])
        logging.info("premium clock: %s" % clock)
        
        if curr_offset > 336:
            curr_offset = -330
            actions = actions.click_and_hold(graph_element)
            actions = actions.move_by_offset(-pixel_diff * 100, 0)
            actions.release().perform()
            time.sleep(0.5)
            should_verify_image = True
        else:
            should_verify_image = False
        if curr_offset <= -330 or min_index == 0:
            should_verify_image = True
        actions.move_to_element_with_offset(graph_element, curr_offset, 10).perform()
        time.sleep(0.5)
        if should_verify_image:
            image_path = 'time_%s.png' % int(curr_offset + 330)
            cropped_image_path = 'cropped_%s.png' % int(curr_offset + 330)
            driver.save_screenshot(image_path)
            time.sleep(1)
            full_image = Image.open(image_path)
            x = 110
            if curr_offset > -330 + 6 * pixel_diff:
                x = x + 2 * (curr_offset - (-330 + 6 * pixel_diff))
            cropped_image = full_image.crop((x, 1080, x + 18 * 2 * pixel_diff, 1130))
            logging.info("%s %s" % (x, x + 18 * 2 * pixel_diff))
            cropped_image.save(cropped_image_path)
            extracted_text = pytesseract.image_to_string(cropped_image)
            logging.info("extracted_text: %s" % extracted_text)
            time.sleep(0.5)
            curr_offset += pixel_diff
            os.remove(image_path)
            os.remove(cropped_image_path)
            if clock in extracted_text:
                logging.info("image time: %s & actual time: %s matched successfully!" % (extracted_text, clock))
            else:
                extracted_date = extract_datetime(extracted_text)
                logging.info("extracted_date: %s" % extracted_date)
                if extracted_date is None and curr_offset > 330:
                    logging.info("Skipping as extracted_date is None and curr_offset is %s" % curr_offset)
                    curr_offset = -330
                    actions = actions.click_and_hold(graph_element)
                    actions = actions.move_by_offset(-pixel_diff * 100, 0)
                    actions.release().perform()
                    time.sleep(0.5)
                    should_verify_image = True
                    continue
                if extracted_date is not None:
                    min_diff = (extracted_date.hour * 60 + extracted_date.minute) - curr_minute
                    logging.info("extracted_date min_diff: %s" % min_diff)
                    if abs(min_diff) >= 5:
                        logging.info("min_diff is too large")
                        raise ValueError("min_diff is too large")
                    curr_offset = curr_offset - (min_diff * pixel_diff)
                    should_verify_image = True
                    continue

        actions.move_to_element_with_offset(graph_element, curr_offset, 10).perform()
        time.sleep(0.5)
        tooltip = driver.find_element(By.CLASS_NAME, 'tooltip-ohlc')
        tooltip_children = tooltip.find_elements(By.XPATH, './*')
        str = ''
        for t in tooltip_children:
            str += t.text

        key = '%s-%s' % (trading_symbol, clock)
        logging.info("%s %s" % (key, str))
        premium_data[key] = extract_prices(str)

        curr_offset = curr_offset + pixel_diff
        min_index += 1
        max_loop_cnt -= 1

    write_to_file(premium_data, filename)
    return premium_data
    
    
    


bn_min_file_path = '/Users/chandack/Documents/algo-trade/trading_django/banknifty_minute_data.json'
banknifty_min_data = {}
with open(bn_min_file_path, 'r') as file:
    banknifty_min_data = json.load(file)

unique_dates = {key.split()[0] for key in banknifty_min_data.keys()}

# Sort dates in reverse order
# all_dates_list = list(sorted(unique_dates))
# Convert date strings to datetime objects
date_objects = [datetime.strptime(date, '%d/%m/%y') for date in unique_dates]

# Sort the datetime objects
date_objects.sort(reverse=True)

# Convert the sorted datetime objects back to strings in 'dd/mm/yy' format
all_dates_list = [date.strftime('%d/%m/%y') for date in date_objects]

print(all_dates_list)


chrome_options = Options()
# chrome_options.add_argument("--headless")
chrome_options.add_argument("user-data-dir=/tmp/profile1")
chrome_options.add_argument("--remote-debugging-port=9222")
driver = webdriver.Chrome(options=chrome_options)
driver.get("https://gocharting.com/terminal?ticker=NSE:NIFTY")
time.sleep(5)

expiry_list = login_into_go_charting_and_get_expiry_list(driver)
graph_element = driver.find_element(By.CLASS_NAME, 'gocharting-pos-abs')
actions = ActionChains(driver)

for curr_date in all_dates_list:
    nearest_expiry_date = get_nearest_expiry(curr_date, expiry_list)
    if nearest_expiry_date is None:
        continue
    day_diff = find_market_day_diff(curr_date, nearest_expiry_date, all_dates_list)
    logging.info("curr_date: %s" % curr_date)
    logging.info("day_diff: %s" % day_diff)
    
    curr_minute = 9 * 60 + 16 # 9:15 AM
    for min_index in range(374):
        curr_minute = curr_minute + min_index
        clock_hours = '0%s' % int(curr_minute / 60)
        clock_minutes = '0%s' % int(curr_minute % 60)
        clock = '%s:%s' % (clock_hours[-2:], clock_minutes[-2:])
        dict_key = '%s %s' % (curr_date, clock)
        logging.info("curr_clock: %s" % clock)
        banknifty_price_map = banknifty_min_data[dict_key]
        close_price = banknifty_price_map['close']
        low_price = banknifty_price_map['low']
        high_price = banknifty_price_map['high']
        open_price = banknifty_price_map['open']
        logging.info("close_price: %s" % close_price)

        high_low_diff = (high_price - low_price) * 0.3
        doji_condition = False
        if open_price < low_price + high_low_diff and close_price < low_price + high_low_diff:
            doji_condition = True

        bullish_candle = False
        high_low_diff_max = (high_price - low_price)
        if open_price >= (low_price + (0.5 * high_low_diff_max)) and close_price >= (
                low_price + (0.5 * high_low_diff_max)):
            bullish_candle = True

        if bullish_candle and close_price < open_price:
            logging.info("Skipping trade on %s due to bullish_candle" % curr_date)
            continue

        if close_price <= open_price or doji_condition:
            strike_price = int((close_price) / 100) * 100
            strike_price = (strike_price + 100)
            original_strike_price = strike_price
            expiry = nearest_expiry_date
            option_type = 'PE'
            trading_symbol = "%s-%s-%s-%s" % (
                'BANKNIFTY',
                expiry, strike_price, option_type)

            premium_data = get_premium_date(driver, nearest_expiry_date, strike_price,
                                            option_type, day_diff, curr_date, from_time=clock, min_duration=90)
            print(premium_data)
            last_min_premium_close_price = premium_data['%s-%s' % (trading_symbol, clock)]['Close']
            if last_min_premium_close_price < 100:
                strike_price += 300
            elif last_min_premium_close_price < 200:
                strike_price += 200
            elif last_min_premium_close_price < 250:
                strike_price += 100
            if original_strike_price != strike_price:
                trading_symbol = "%s-%s-%s-%s" % (
                    'BANKNIFTY',
                    expiry, strike_price, option_type)
                premium_data = get_premium_date(driver, nearest_expiry_date, strike_price,
                                                option_type, day_diff, curr_date, from_time=clock, min_duration=90)
                last_min_premium_close_price = premium_data['%s-%s' % (trading_symbol, clock)]['Close']
            entry_price = last_min_premium_close_price
            target_price = last_min_premium_close_price + round(
                (last_min_premium_close_price * 100) / 100, 1)
            sl_price = last_min_premium_close_price - round(
                (last_min_premium_close_price * 10) / 100, 1)
            logging.info("entry_price: %s" % entry_price)
            exit_price = sl_price
            for temp_ind in range(1, 90, 1):
                temp_min = curr_minute + temp_ind
                temp_clock_hours = '0%s' % int(temp_min / 60)
                temp_clock_minutes = '0%s' % int(temp_min % 60)
                temp_clock = '%s:%s' % (temp_clock_hours[-2:], temp_clock_minutes[-2:])
                
                curr_premium_price_map = premium_data['%s-%s' % (trading_symbol, temp_clock)]
                low_prem_price = curr_premium_price_map['Low']
                high_prem_price = curr_premium_price_map['High']
                open_prem_price = curr_premium_price_map['Open']
                close_prem_price = curr_premium_price_map['Close']

                ltp = high_prem_price
                if ltp >= (entry_price * 1.01):
                    sl_price = round(entry_price * 1.005, 1)
                if ltp >= (entry_price * 1.02):
                    sl_price = round(entry_price * 1.01, 1)
                if ltp >= (entry_price * 1.03):
                    sl_price = round(entry_price * 1.02, 1)
                if ltp >= (entry_price * 1.04):
                    sl_price = round(entry_price * 1.03, 1)
                if ltp >= (entry_price * 1.05):
                    sl_price = round(entry_price * 1.03, 1)
                if ltp >= (entry_price * 1.07):
                    sl_price = round(entry_price * 1.04, 1)
                if ltp >= (entry_price * 1.10):
                    sl_price = round(entry_price * 1.05, 1)
                if ltp >= (entry_price * 1.15):
                    sl_price = round(entry_price * 1.05, 1)
                if ltp >= (entry_price * 1.5):
                    sl_price = round(entry_price * 1.2, 1)
                if ltp >= (entry_price * 1.7):
                    sl_price = round(entry_price * 1.4, 1)
                if ltp >= (entry_price * 1.9):
                    sl_price = round(entry_price * 1.6, 1)
                
                if low_prem_price < sl_price:
                    exit_price = sl_price
                    break
            logging.info("exit_price: %s" % exit_price)
            profit_percent = ((exit_price - entry_price) * 100) / entry_price
            output_key = '%s-%s' % (trading_symbol, clock)
            write_to_file({output_key: {'entry_price': entry_price,
                                        'exit_price': exit_price,
                                        'profit_percent': profit_percent}})
                
                
                
                



# # Example values for `curr_time` and `day_diff`
# curr_time = "09:15"  # Current time
# day_diff = 2  # Example day difference between the nearest expiry and curr_date
#
# data = get_shifts_and_offset(time_range_map_list, curr_time, day_diff)
# logging.info(f"Number of shifts: {data['shifts']}, X Offset: {data['offset']}")
