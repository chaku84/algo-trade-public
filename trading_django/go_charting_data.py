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
import concurrent.futures

logging.basicConfig(level=logging.INFO)

dhan = dhanhq("1101185196", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzI4MTQ0NTI5LCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTEwMTE4NTE5NiJ9.fjYXcAvYPYS7Jf_wg-sU1VZbensWGQytAr23PW63mIRNzxWhfzQSlT6inykHyLAlAI3q7OEXO5cFBtI0BzZPCg")
charts = dhan.historical_minute_charts(symbol='BANKNIFTY', exchange_segment='IDX_I', instrument_type='INDEX', expiry_code=0, from_date='2023-01-01', to_date='2024-09-05')
date_list = []
for curr_date in charts['data']['start_Time']:
    date_list.append(dhan.convert_to_date_time(curr_date).strftime('%Y-%m-%d'))

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

def get_driver_instance():
    chrome_driver_path = '/usr/local/bin/chromedriver'

    if chrome_driver_path not in os.environ['PATH']:
        os.environ["PATH"] = os.environ["PATH"] + ":" + chrome_driver_path

    chrome_options = Options()
    # chrome_options.add_argument("--remote-debugging-port=9222")
    # chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    chrome_options.add_argument("--headless")
    # chrome_options.add_argument('--no-sandbox')
    # chrome_options.add_argument("--remote-debugging-port=9222")
    # chrome_options.add_argument('--disable-gpu')
    # chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--headless')


    driver = webdriver.Chrome(options=chrome_options)
    driver.get('https://gocharting.com/terminal?ticker=NSE:NIFTY')
    time.sleep(10)
    return driver

def login_into_go_charting_and_get_expiry_list(driver):
    is_logged_in = False

    login_button = driver.find_element(By.ID, 'login-avatar')
    image_elements = login_button.find_elements(By.CSS_SELECTOR, 'img')

    dismiss_buttons = driver.find_elements(By.ID, 'notification-dismiss')
    if len(dismiss_buttons) > 0:
        dismiss_buttons[0].click()
        time.sleep(1)

    if len(image_elements) > 0:
        print("Already Logged In!")
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
        password_input.send_keys('xxxx')

        time.sleep(0.1)

        all_buttons = driver.find_elements(By.CSS_SELECTOR, 'button')
        for button in all_buttons:
            if button.text == 'Sign In':
                print("Found Sign In Button")
                button.click()
                break

        time.sleep(2)

    collapse_button = driver.find_elements(By.ID, 'collapse-left-bar')[1]
    collapse_button_style = collapse_button.get_attribute('style')
    print(collapse_button_style)
    if collapse_button_style == 'right: 5px;':
        collapse_button.click()

    time.sleep(1)

    collapse_button = driver.find_elements(By.ID, 'collapse-left-bar')[1]
    collapse_button_style = collapse_button.get_attribute('style')

    search = driver.find_elements(By.CLASS_NAME, 'ticker-search')
    print("search button length: %s" % len(search))

    max_loop_count = 3
    while len(search) < 2 and max_loop_count > 0:
        expired_button = driver.find_element(By.ID, 'expiredfno-icontab')
        expired_button.click()

        time.sleep(1)
        search = driver.find_elements(By.CLASS_NAME, 'ticker-search')
        print("search button length: %s" % len(search))
        max_loop_count -= 1

    time.sleep(1)

    # search_index = driver.find_elements(By.ID, 'input-search-ticks-input')
    # search_index.send_keys('BANKNIFTY')

    # time.sleep(1)

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

def extract_data_for_a_day(data, driver, option_texts, st_tm_index, prev_expiry, thread_no):
    start_time = dhan.convert_to_date_time(charts['data']['start_Time'][-(st_tm_index + 1)])
    start_time_str = start_time.strftime('%Y-%m-%d')
    # if start_time_str == '2024-08-14':
    #     continue
    data = {}
    data[start_time_str] = {}
    open_price = int((charts['data']['open'][-(st_tm_index + 1)] + 50) / 100) * 100
    nearest_expiry_dt = option_texts[0]
    index = 0
    option_expiry_length = len(option_texts)

    while index < option_expiry_length:
        curr_expiry = datetime.strptime(option_texts[index], '%Y-%m-%d')
        if curr_expiry < start_time:
            break
        nearest_expiry_dt = option_texts[index]
        index += 1
    # if prev_expiry is not None and prev_expiry != nearest_expiry_dt or is_last_index:
    #     if is_last_index:
    #         prev_expiry = nearest_expiry_dt
    #     write_to_file(data, '%s.json' % prev_expiry.replace('-', '_'))
    #     data = {start_time_str: {}}

    prev_expiry = nearest_expiry_dt
    now = datetime.now()
    formatted_date = now.strftime("%Y-%m-%d %H:%M:%S")
    print("[%s] Processing thread: %s, index: %s, start_time: %s, expiry: %s" % (formatted_date, thread_no, index, start_time, nearest_expiry_dt))

    expiry_dropdown = driver.find_element(By.CSS_SELECTOR, 'select')
    expiry_dropdown.click()

    dropdown = Select(expiry_dropdown)
    dropdown.select_by_visible_text(nearest_expiry_dt)

    input = driver.find_elements(By.CSS_SELECTOR, 'input')
    price_list = [open_price]
    for temp_ind in range(4):
        price_list.append(open_price - (100 * (temp_ind + 1)))
        price_list.append(open_price + (100 * (temp_ind + 1)))
    for strike_price in price_list:
        price_str = '%s' % strike_price
        data[start_time_str][price_str] = {}
        print(price_str)
        input[2].clear()
        input[2].send_keys(price_str)

        time.sleep(0.1)

        all_rows = driver.find_elements(By.CLASS_NAME, 'rt-tr-group')

        print("all_row length: %s" % len(all_rows))

        for row in all_rows:
            if price_str in row.text:
                option_type = 'CE' if 'CE' in row.text else 'PE'
                data[start_time_str][price_str][option_type] = []
                svg = row.find_element(By.CSS_SELECTOR, 'svg')
                svg.click()

                time.sleep(1)

                period_dropdown = driver.find_element(By.ID, 'interval-selector-btn')
                period_dropdown.click()

                time.sleep(3)

                all_divs = driver.find_elements(By.CSS_SELECTOR, 'div')
                for div in all_divs:
                    if div is not None and div.get_attribute('title') == '1 Minute':
                        print("Found 1 Minute dropdown")
                        div.click()
                        break
                # print("all_divs lenght: %s" % len(all_divs))
                # all_divs[3888].click()

                time.sleep(0.1)

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
                day_diff = abs(date_list.index(nearest_expiry_dt) - date_list.index(start_time_str))
                print("day_diff: %s" % day_diff)
                no_of_shifts = int(math.floor((day_diff * 360) / 99))
                remaining_shift_size = int(6.74 * ((day_diff * 360) % 99))
                print("no_of_shifts:%s, remaining_shift_size: %s" % (no_of_shifts, remaining_shift_size))
                for i in range(no_of_shifts):
                    actions = actions.click_and_hold(graph_element)
                    actions = actions.move_by_offset(674, 0)
                    actions.release().perform()
                    time.sleep(0.1)
                if no_of_shifts > 0 and remaining_shift_size > 0:
                    actions = actions.click_and_hold(graph_element)
                    actions = actions.move_by_offset(remaining_shift_size, 0)
                    actions.release().perform()
                    time.sleep(0.1)
                for i in range(5):
                    x_offset_diff = -1

                    for x_offset in range(342, -336, x_offset_diff):
                        if x_offset == 336:
                            x_offset_diff = -6
                        if x_offset == -330:
                            x_offset_diff = -1
                        actions.move_to_element_with_offset(graph_element, x_offset, 10).perform()

                        tooltip = driver.find_element(By.CLASS_NAME, 'tooltip-ohlc')

                        tooltip_children = tooltip.find_elements(By.XPATH, './*')
                        str = ''
                        for t in tooltip_children:
                            str += t.text

                        # print(str)
                        if len(data[start_time_str][price_str][option_type]) == 0 or \
                                data[start_time_str][price_str][option_type][-1] != str:
                            data[start_time_str][price_str][option_type].append(str)
                            print(str)
                        # time.sleep(0.1)

                    # time.sleep(0.1)
                    actions = actions.click_and_hold(graph_element)
                    actions = actions.move_by_offset(674, 0)
                    actions.release().perform()

                    # time.sleep(0.1)

                print("thread: %s, start_time: %s, price_str: %s, option_type: %s" % (thread_no, start_time, price_str, option_type))
                print(data[start_time_str][price_str][option_type])

                time.sleep(0.1)

        time.sleep(0.1)
    
    write_to_file(data, '%s.json' % nearest_expiry_dt.replace('-', '_'))

    return prev_expiry




# Function to execute in each thread (includes is_last_index and thread_no)
def execute_for_range(index_list, prev_expiry, thread_no):
    driver = get_driver_instance()
    option_texts = login_into_go_charting_and_get_expiry_list(driver)
    data = {}
    prev_expiry = None
    for st_tm_index in index_list:
        # is_last_index = (st_tm_index == end_index - 1)  # Check if it's the last index for this thread
        found_excetion = False
        first_loop = True
        while found_excetion or first_loop:
            try:
                first_loop = False
                prev_expiry = extract_data_for_a_day(data, driver, option_texts, st_tm_index, prev_expiry, thread_no)
                found_excetion = False
            except Exception as e:
                print("Found Exception... Retrying after 1 Minute")
                traceback.print_exc()
                found_excetion = True
                time.sleep(60)

    return prev_expiry


# Divide work into chunks for each thread
def divide_work_into_threads(charts, prev_expiry=None, num_threads=6):
    data_length = len(charts['data']['start_Time'])
    chunk_size = data_length // num_threads
    futures = []

    indexes_per_thread = [[] for _ in range(num_threads)]
    for index in range(len(charts['data']['start_Time'])):
        thread_id = index % num_threads  # Assign index serially
        indexes_per_thread[thread_id].append(index)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        for i in range(num_threads):
            # Define the range for each thread
            start_index = i * chunk_size
            # Ensure last thread processes any leftover indices
            end_index = (i + 1) * chunk_size if i != num_threads - 1 else data_length
            # Submit the task to the thread pool, including thread number `i`
            futures.append(executor.submit(execute_for_range, indexes_per_thread[i], prev_expiry, i + 1))

        # Collect results from threads
        for future in concurrent.futures.as_completed(futures):
            prev_expiry = future.result()  # Update prev_expiry based on thread results

    return prev_expiry


if __name__ == '__main__':
    print("Started collecting go charting data")
    # Usage
    prev_expiry = divide_work_into_threads(charts)

    # print(data)
