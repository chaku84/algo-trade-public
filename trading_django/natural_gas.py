from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from dhanhq import dhanhq

import os
import time
import pandas as pd
import logging
import traceback
import pexpect
import json
import math

logging.basicConfig(level=logging.INFO)


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
        json.dump(existing_data, json_file)  # indent=4 for readable formatting



chrome_driver_path = '/usr/local/bin/chromedriver'

# os.environ["PATH"] = os.environ["PATH"] + ":" + chrome_driver_path

# dhan = dhanhq("1101185196",
#               "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzI1NTA2Njg2LCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTEwMTE4NTE5NiJ9.O6_uqlpwZucYaziSVQJtmaW-VqatBQhx8xCvugLFa4lXhFnUohitqLsZHi6l_f2rsmzYpRxq6TbjZ3Wo27Vx5w")

chrome_options = Options()
# chrome_options.add_argument("--remote-debugging-port=9222")
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
# chrome_options.add_argument("--headless")
driver = webdriver.Chrome(options=chrome_options)
driver.get('https://gocharting.com/terminal?ticker=MCX:NATURALGAS24JULFUT')

time.sleep(5)

collapse_button = driver.find_elements(By.ID, 'collapse-left-bar')[1]
collapse_button_style = collapse_button.get_attribute('style')
print(collapse_button_style)
if collapse_button_style == 'right: 5px;':
    collapse_button.click()
    time.sleep(1)

expired_button = driver.find_element(By.ID, 'expiredfno-icontab')
expired_button.click()

time.sleep(1)

# search_index = driver.find_elements(By.ID, 'input-search-ticks-input')
# search_index.send_keys('BANKNIFTY')

# time.sleep(1)

search = driver.find_elements(By.CLASS_NAME, 'ticker-search')
search[1].send_keys('NATURALGAS')

time.sleep(1)

button = driver.find_elements(By.CLASS_NAME, 'stunnerrow')
button[0].click()

time.sleep(2)

all_divs = driver.find_elements(By.CSS_SELECTOR, 'div')
for div in all_divs:
    if div.text == 'Futures':
        print("Found Futures Icon")
        div.click()
        break

time.sleep(1)

expiry_dropdown = driver.find_element(By.CSS_SELECTOR, 'select')
expiry_dropdown.click()

dropdown = Select(expiry_dropdown)
options = dropdown.options
option_texts = [option.text for option in options]

print(option_texts)


# charts = dhan.historical_minute_charts(symbol='BANKNIFTY', exchange_segment='IDX_I', instrument_type='INDEX',
#                                        expiry_code=0, from_date='2024-01-01', to_date='2024-08-15')
data = {}
# date_list = []
# for curr_date in charts['data']['start_Time']:
#     date_list.append(dhan.convert_to_date_time(curr_date).strftime('%Y-%m-%d'))
# prev_expiry = None
# for st_tm_index in range(len(charts['data']['start_Time'])):
# start_time = dhan.convert_to_date_time(charts['data']['start_Time'][-(st_tm_index + 1)])
# start_time_str = start_time.strftime('%Y-%m-%d')
# if start_time_str == '2024-08-14':
#     continue
# data[start_time_str] = {}
# open_price = int((charts['data']['open'][-(st_tm_index + 1)] + 50) / 100) * 100
for index in range(len(option_texts)):
    if index <= 6:
        continue
    nearest_expiry_dt = option_texts[index]
    option_expiry_length = len(option_texts)
    
    # while index < option_expiry_length:
    #     curr_expiry = datetime.strptime(option_texts[index], '%Y-%m-%d')
    #     if curr_expiry < start_time:
    #         break
    #     nearest_expiry_dt = option_texts[index]
    #     index += 1
    # if prev_expiry is not None and prev_expiry != nearest_expiry_dt:
    #     write_to_file(data, '%s.json' % prev_expiry.replace('-', '_'))
    #     data = {start_time_str: {}}
    
    prev_expiry = nearest_expiry_dt
    # print("Processing index: %s, start_time: %s , expiry: %s" % (index, start_time, nearest_expiry_dt))
    
    dropdown.select_by_visible_text(nearest_expiry_dt)
    
    # input = driver.find_elements(By.CSS_SELECTOR, 'input')
    #
    # input[2].clear()
    # input[2].send_keys(price_str)
    
    time.sleep(1)

    
    all_rows = driver.find_elements(By.CLASS_NAME, 'rt-tr-group')
    
    print("all_row length: %s" % len(all_rows))
    
    for row in all_rows:
        if row is not None and 'FUTURE' in row.text:
            data[row.text] = []
            # option_type = 'CE' if 'CE' in row.text else 'PE'
            # data[start_time_str][price_str][option_type] = []
            svg = row.find_element(By.CSS_SELECTOR, 'svg')
            svg.click()
    
            time.sleep(1)
    
            period_dropdown = driver.find_element(By.ID, 'interval-selector-btn')
            period_dropdown.click()
    
            time.sleep(1)
    
            all_divs = driver.find_elements(By.CSS_SELECTOR, 'div')
            for div in all_divs:
                if div.get_attribute('title') == 'Daily':
                    print("Found Daily dropdown")
                    div.click()
                    break
            # print("all_divs lenght: %s" % len(all_divs))
            # all_divs[3888].click()
    
            time.sleep(0.2)
    
            refresh_button = driver.find_element(By.ID, 'refresh-button')
            refresh_button.click()
    
            time.sleep(0.1)
    
            graph_element = driver.find_element(By.CLASS_NAME, 'gocharting-pos-abs')
    
            actions = ActionChains(driver)
    
            actions = actions.click_and_hold(graph_element)
            actions = actions.move_by_offset(132, 0)
            actions.release().perform()
    
            print("permormed 132 shift")
    
            time.sleep(0.1)
    
            # one_minute_data = []
            # day_diff = 0
            # print("day_diff: %s" % day_diff)
            # no_of_shifts = int(math.floor((day_diff * 360) / 99))
            # remaining_shift_size = int(6.74 * ((day_diff * 360) % 99))
            # print("no_of_shifts:%s, remaining_shift_size: %s" % (no_of_shifts, remaining_shift_size))
            # for i in range(no_of_shifts):
            #     actions = actions.click_and_hold(graph_element)
            #     actions = actions.move_by_offset(674, 0)
            #     actions.release().perform()
            #     time.sleep(5)
            # if no_of_shifts > 0 and remaining_shift_size > 0:
            #     actions = actions.click_and_hold(graph_element)
            #     actions = actions.move_by_offset(remaining_shift_size, 0)
            #     actions.release().perform()
            #     time.sleep(5)

            count = 0
            st_time = datetime.strptime(option_texts[index], '%Y-%m-%d')
            st_time = datetime(st_time.year, st_time.month, st_time.day, 23, 29)
            for i in range(1):
                x_offset_diff = -5

                is_nan = False
    
                for x_offset in range(336, -336, -5):
                    actions.move_to_element_with_offset(graph_element, x_offset, 10).perform()
    
                    tooltip = driver.find_element(By.CLASS_NAME, 'tooltip-ohlc')
    
                    tooltip_children = tooltip.find_elements(By.XPATH, './*')
                    str = ''
                    for t in tooltip_children:
                        str += t.text
    
                    # print(str)
                    if len(data[row.text]) == 0 or \
                            data[row.text][-1] != str:
                        data[row.text].append(str)
                        print("%s %s" % (st_time, str))
                        count += 1
                        st_time = st_time - timedelta(minutes = 1)

                        if count == 870:
                            count = 0
                            st_time = datetime(st_time.year, st_time.month, st_time.day, 23, 29)

                    if 'NaN' in str or 'NaN%' in str:
                        is_nan = True
                        break
                    # time.sleep(0.1)
                if is_nan:
                    break
    
                # time.sleep(0.1)
                actions = actions.click_and_hold(graph_element)
                actions = actions.move_by_offset(674, 0)
                actions.release().perform()
    
                time.sleep(1)
                # break
    
            # print("start_time: %s, price_str: %s, option_type: %s" % (start_time, price_str, option_type))
            # print(data[start_time_str][price_str][option_type])
    
            time.sleep(0.1)

    time.sleep(1)
    # data[list(data.keys())[0]] = data[list(data.keys())[0]][1:]
    write_to_file(data, 'natural_gas_daily.json')
    # print(data)
