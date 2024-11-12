from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
# >>> from selenium import webdriver
# >>> from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
import pyotp

logging.basicConfig(filename='zerodha_data.log', level=logging.INFO,
                    format='%(asctime)s - %(message)s')

# dhan = dhanhq("1101185196",
#               "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzI4MTQ0NTI5LCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTEwMTE4NTE5NiJ9.fjYXcAvYPYS7Jf_wg-sU1VZbensWGQytAr23PW63mIRNzxWhfzQSlT6inykHyLAlAI3q7OEXO5cFBtI0BzZPCg")
# charts = dhan.historical_minute_charts(symbol='BANKNIFTY', exchange_segment='IDX_I', instrument_type='INDEX',
#                                        expiry_code=0, from_date='2023-01-01', to_date='2024-09-05')
# date_list = []
# for curr_date in charts['data']['start_Time']:
#     date_list.append(dhan.convert_to_date_time(curr_date).strftime('%Y-%m-%d'))


def update_without_overwrite(existing_data, new_data):
    # Iterate through the new_data items
    for key, value in new_data.items():
        # Only update if the key is not in existing_data
        if key not in existing_data:
            existing_data[key] = value

    return existing_data

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
    existing_data = update_without_overwrite(existing_data, data)
    # existing_data.update(data)

    # Write the updated data back to the file
    with open(filename, 'w') as json_file:
        json.dump(existing_data, json_file, indent=4)  # indent=4 for readable formatting


def get_driver_instance(profile='profile1'):
    logging.info("profile: %s" % profile)
    chrome_driver_path = '/usr/local/bin/chromedriver'

    if chrome_driver_path not in os.environ['PATH']:
        os.environ["PATH"] = os.environ["PATH"] + ":" + chrome_driver_path

    chrome_options = Options()
    # chrome_options.add_argument("--remote-debugging-port=9222")
    port = 9222
    # chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:%s" % (port+int(profile[-1]) - 1))
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("user-data-dir=/tmp/%s" % profile)

    driver = webdriver.Chrome(options=chrome_options)
    driver.get('https://kite.zerodha.com/chart/ext/ciq/INDICES/NIFTY%20BANK/260105')
    time.sleep(5)
    try:
        wait = WebDriverWait(driver, 15)
        user_id_field = wait.until(EC.presence_of_element_located((By.ID, "userid")))
        # user_id_field = driver.find_element(By.ID, "userid")
        password_field = driver.find_element(By.ID, "password")

        # if user_id_field is not None and user_id_field.tag_name == 'input' and profile != 'profile1':
        #     user_id_field.send_keys("KVA617")
        # if password_field is not None:
        password_field.clear()
        time.sleep(2)
        password_field.send_keys("xxx")

        password_field.send_keys(Keys.RETURN)

        time.sleep(5)

        # password_field.clear()
        # time.sleep(1)
        # password_field.send_keys("xxxx")
        #
        # password_field.send_keys(Keys.RETURN)

        secret_key_2fa = "xxxx"

        # Create a TOTP object using the secret key
        totp = pyotp.TOTP(secret_key_2fa)

        # Generate the TOTP code
        totp_code = totp.now()

        logging.info("Generated TOTP Code: %s" % totp_code)

        time.sleep(2)
        totp_field = driver.find_element(By.XPATH, "//input[@label='External TOTP']")
        totp_field.send_keys(totp_code)

        time.sleep(2)
    except Exception:
        traceback.print_exc()
    
    driver.get('https://kite.zerodha.com/chart/ext/ciq/INDICES/NIFTY%20BANK/260105')
    time.sleep(5)

    # iframe = driver.find_element(By.TAG_NAME, "iframe")
    # driver.switch_to.frame(iframe)

    wait = WebDriverWait(driver, 60)
    iframe = wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
    # iframe = driver.find_element(By.TAG_NAME, "iframe")
    driver.switch_to.frame(iframe)

    return driver


def extract_data_for_a_day(data, driver, index_list, st_tm_index, prev_expiry, thread_no):
    # start_time = dhan.convert_to_date_time(charts['data']['start_Time'][-(st_tm_index + 1)])
    # start_time_str = start_time.strftime('%Y-%m-%d')
    # if start_time_str == '2024-08-14':
    #     continue
    # if st_tm_index in [260, 240, 210, 180]:
    #     return prev_expiry
    driver.get('https://kite.zerodha.com/chart/ext/ciq/INDICES/NIFTY%20BANK/260105')
    wait = WebDriverWait(driver, 60)
    iframe = wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
    # iframe = driver.find_element(By.TAG_NAME, "iframe")
    driver.switch_to.frame(iframe)
    data = {}
    total_days = 52 * 5
    logging.info("day: %s" % st_tm_index)
    diff_days = total_days - st_tm_index
    diff_days = 30
    logging.info("day_diff: %s" % diff_days)
    graph_element = driver.find_element(By.CLASS_NAME, 'stx-subholder')

    actions = ActionChains(driver)
    wait = WebDriverWait(driver, 10)

    for i in range(diff_days):
        for j in range(5):
            actions = actions.click_and_hold(graph_element)
            actions = actions.move_by_offset(555, 0)
            actions.release().perform()
            time.sleep(0.1)
        actions = actions.click_and_hold(graph_element)
        actions = actions.move_by_offset(230, 0)
        actions.release().perform()
        time.sleep(0.1)

    logging.info("permormed shifts")

    time.sleep(0.1)
    
    for i in range(3 * 130):
        x_offset_diff = -6

        for x_offset in range(560, -560, x_offset_diff):
            actions.move_to_element_with_offset(graph_element, x_offset, 10).perform()

            open_element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//stx-hu-tooltip-field[@field='Open']//stx-hu-tooltip-field-value")))
            high_element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//stx-hu-tooltip-field[@field='High']//stx-hu-tooltip-field-value")))
            low_element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//stx-hu-tooltip-field[@field='Low']//stx-hu-tooltip-field-value")))
            close_element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//stx-hu-tooltip-field[@field='Close']//stx-hu-tooltip-field-value")))

            date_element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//stx-hu-tooltip-field[@field='DT']//stx-hu-tooltip-field-value")))

            # Fetch the innerHTML using JavaScript
            open_price = driver.execute_script("return arguments[0].innerHTML;", open_element)
            high_price = driver.execute_script("return arguments[0].innerHTML;", high_element)
            low_price = driver.execute_script("return arguments[0].innerHTML;", low_element)
            close_price = driver.execute_script("return arguments[0].innerHTML;", close_element)
            date_value = driver.execute_script("return arguments[0].innerHTML;", date_element)
            
            data[date_value] = {'open_price': open_price, 'high_price': high_price, 'low_price': low_price,
                                'close_price': close_price}
            # time.sleep(0.1)

        # time.sleep(0.1)
        actions = actions.click_and_hold(graph_element)
        actions = actions.move_by_offset(555, 0)
        actions.release().perform()

        actions = actions.click_and_hold(graph_element)
        actions = actions.move_by_offset(555, 0)
        actions.release().perform()

        if len(data.keys()) >= 360:
            write_to_file(data, 'zerodha_banknifty.json')
            data = {}

        # time.sleep(0.1)

    write_to_file(data, 'zerodha_banknifty.json')

    return prev_expiry


# Function to execute in each thread (includes is_last_index and thread_no)
def execute_for_range(index_list, prev_expiry, thread_no):
    logging.info("thread_no: %s" % thread_no)
    driver = get_driver_instance(profile='profile%s' %thread_no)
    # option_texts = login_into_go_charting_and_get_expiry_list(driver)
    data = {}
    prev_expiry = None
    for st_tm_index in index_list:
        # is_last_index = (st_tm_index == end_index - 1)  # Check if it's the last index for this thread
        found_excetion = False
        first_loop = True
        while found_excetion or first_loop:
            try:
                first_loop = False
                prev_expiry = extract_data_for_a_day(data, driver, index_list, st_tm_index, prev_expiry, thread_no)
                found_excetion = False
            except Exception as e:
                logging.info("Found Exception... Retrying after 1 Minute")
                traceback.print_exc()
                found_excetion = True
                time.sleep(60)

    return prev_expiry


# Divide work into chunks for each thread
def divide_work_into_threads(prev_expiry=None, num_threads=6):
    # data_length = len(charts['data']['start_Time'])
    data_length = 52 * 5
    chunk_size = data_length // num_threads
    futures = []

    indexes_per_thread = [[] for _ in range(num_threads)]
    for index in range(data_length, 0, -130):
        thread_id = index % num_threads  # Assign index serialndely
        indexes_per_thread[thread_id].append(index)
        break
    

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        for i in range(num_threads):
            # Define the range for each thread
            start_index = i * chunk_size
            # Ensure last thread processes any leftover indices
            end_index = (i + 1) * chunk_size if i != num_threads - 1 else data_length
            # Submit the task to the thread pool, including thread number `i`
            futures.append(executor.submit(execute_for_range, indexes_per_thread[i], prev_expiry, i+1))

        # Collect results from threads
        for future in concurrent.futures.as_completed(futures):
            prev_expiry = future.result()  # Update prev_expiry based on thread results

    return prev_expiry


if __name__ == '__main__':
    logging.info("Started collecting go charting data")
    # Usage
    prev_expiry = divide_work_into_threads(prev_expiry=None, num_threads=1)

    # logging.info(data)

# iframe = driver.find_element(By.TAG_NAME, "iframe")
# driver.switch_to.frame(iframe)
# 
# open_element = wait.until(EC.presence_of_element_located((By.XPATH, "//stx-hu-tooltip-field[@field='Open']//stx-hu-tooltip-field-value")))
# high_element = wait.until(EC.presence_of_element_located((By.XPATH, "//stx-hu-tooltip-field[@field='High']//stx-hu-tooltip-field-value")))
# low_element = wait.until(EC.presence_of_element_located((By.XPATH, "//stx-hu-tooltip-field[@field='Low']//stx-hu-tooltip-field-value")))
# close_element = wait.until(EC.presence_of_element_located((By.XPATH, "//stx-hu-tooltip-field[@field='Close']//stx-hu-tooltip-field-value")))
# 
# # Fetch the innerHTML using JavaScript
# open_price = driver.execute_script("return arguments[0].innerHTML;", open_element)
# high_price = driver.execute_script("return arguments[0].innerHTML;", high_element)
# low_price = driver.execute_script("return arguments[0].innerHTML;", low_element)
# close_price = driver.execute_script("return arguments[0].innerHTML;", close_element)
# 
# # logging.info or return the OHLC values
# logging.info(f"Open: {open_price}")
# logging.info(f"High: {high_price}")
# logging.info(f"Low: {low_price}")
# logging.info(f"Close: {close_price}")
