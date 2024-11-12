import threading
import random
import string
import time
import logging
import functools
import ipaddress
import os
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains

from tips.gmail import GmailService
from trading.helpers import get_ist_datetime, get_nearest_tens


class DhanWebManager(object):
    def __init__(self):
        self.driver = None
        self.gmail_service = GmailService()
        self.logger = logging.getLogger(__name__)
        # Create a global lock
        self.lock = threading.Lock()
        self.kill_switch_activated = False

    # Retry decorator function
    def retry(max_retries=3, delay=5, exception=Exception):
        def decorator_retry(func):
            @functools.wraps(func)
            def wrapper_retry(self, *args, **kwargs):
                attempts = 0
                while attempts < max_retries:
                    # with self.lock:
                    try:
                        return func(self, *args, **kwargs)  # Try executing the function
                    except exception as e:
                        attempts += 1
                        print(f"Attempt {attempts} failed with error: {e}. Retrying in {delay} seconds...")
                        self.gmail_service.send_email(
                            f'Failure in Dhan Web Manager. Retrying in {delay} seconds...',
                            f"Attempt {attempts} failed with error: {e}. Retrying in {delay} seconds...")
                        self.quit_driver_instance()
                        time.sleep(1)
                        self.create_driver_instance()
                        time.sleep(delay)  # Wait before retrying
                self.logger.error(f"Failed after {max_retries} attempts.")
                raise Exception(f"Failed after {max_retries} attempts.") # Reraise the last exception after all retries

            return wrapper_retry

        return decorator_retry
        
    def create_driver_instance(self):
        chrome_driver_path = '/usr/local/bin/chromedriver'
        if chrome_driver_path not in os.environ['PATH']:
            os.environ["PATH"] = os.environ["PATH"] + ":" + chrome_driver_path
        chrome_options = Options()
        # chrome_options.add_argument("user-data-dir=/tmp/profile1")
        # chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        # chrome_options.add_argument("--remote-debugging-port=9222")

        chrome_options.add_argument("--headless")  # Optional: Run in headless mode
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)
        driver.get('https://web.dhan.co')
        self.driver = driver
        self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
        self.driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        driver.delete_all_cookies()
        return driver

    def quit_driver_instance(self):
        self.driver.quit()

    @retry(max_retries=3, delay=5, exception=Exception)
    def login(self):
        driver = self.driver
        driver.delete_all_cookies()
        self.driver.get('https://web.dhan.co/index/profile')
        time.sleep(5)
        is_logged_in = False
        user_names = driver.find_elements(By.XPATH, "//span[contains(@class, 'user-name')]")
        if len(user_names) > 0:
            is_logged_in = True
            return True

        self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
        self.driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        driver.execute_script("window.location.reload();")
        time.sleep(2)
        scanner = self.driver.find_elements(By.CLASS_NAME, 'loginQr')
        actions = ActionChains(self.driver)
        actions.click_and_hold(scanner[0])
        actions.release().perform()
        time.sleep(0.1)
        input = self.driver.find_element(By.ID, 'mat-input-1')
        input.send_keys('9565529742\n')
        time.sleep(1)
        dhan_pwd_path = 'dhan_password.txt'
        dhan_pwd = ''
        with open(dhan_pwd_path, 'r') as pwd_file:
            dhan_pwd = pwd_file.read()
        input2 = self.driver.find_element(By.ID, 'mat-input-2')
        input2.send_keys('%s\n' % dhan_pwd)
        time.sleep(5)
        inputs = self.driver.find_elements(By.XPATH, "//input[@autocomplete='one-time-code']")
        # TODO: Extract otp from GmailService
        otp = self.gmail_service.get_dhan_otp(otp_sent_timestamp=(datetime.now() - timedelta(seconds=10)), otp_type='Login')
        for i in range(6):
            inputs[i].send_keys(otp[i])
            time.sleep(0.5)
        time.sleep(2)
        button = self.driver.find_element(By.XPATH, "//button[text()='Proceed Ahead to Trade ']")
        button.send_keys('\n')
        print("Logged In!")

    @retry(max_retries=3, delay=5, exception=Exception)
    def logout(self):
        driver = self.driver
        is_logged_in = False
        user_names = driver.find_elements(By.XPATH, "//span[contains(@class, 'user-name')]")
        if len(user_names) > 0:
            is_logged_in = True
        if not is_logged_in:
            return True
        actions = ActionChains(self.driver)
        actions.click_and_hold(user_names[0])
        actions.release().perform()

        logout_anchor = self.driver.find_element(By.XPATH, "//a[text()='Logout']")
        logout_anchor.click()
        time.sleep(1)
        user_names = driver.find_elements(By.XPATH, "//span[contains(@class, 'user-name')]")
        if len(user_names) == 0:
            return True
        return False

    @retry(max_retries=3, delay=5, exception=Exception)
    def reset_api_token(self):
        driver = self.driver
        driver.get('https://web.dhan.co/index/profile')
        api_button = driver.find_element(By.XPATH, "//span[text()=' DhanHQ Trading APIs ']")
        api_button.click()
        time.sleep(0.1)
        revoke_button = driver.find_element(By.XPATH, "//span[text()='Revoke']")
        revoke_button.click()
        time.sleep(0.1)
        confirm_button = driver.find_element(By.CLASS_NAME, 'confirmButtonsIcons')
        confirm_button.click()
        time.sleep(0.1)
        expand_button = driver.find_element(By.XPATH, "//span[text()='Expand']")
        expand_button.click()
        time.sleep(0.5)

        app_name = '%s-%s' % ('temp', int(time.time()))
        app_name_input = driver.find_element(By.CLASS_NAME, 'nameinput')
        app_name_input.send_keys(app_name)

        expiry_dropdown = driver.find_element(By.XPATH, "//select[@name='expiry']")
        expiry_dropdown.click()
        dropdown = Select(expiry_dropdown)
        dropdown.select_by_visible_text('30 Days')

        gen_token_button = driver.find_element(By.XPATH, "//button[text()='Generate Token']")
        gen_token_button.click()

        time.sleep(0.5)

        token_element = driver.find_element(By.XPATH,
                                            "//div[contains(@class, 'tokencolumn')]//div[contains(@class, 'textoverflow')]")
        token = token_element.text
        tokens_file_path = 'dhan_token.txt'
        # print(token)
        with open(tokens_file_path, 'w') as token_file:
            token_file.write(token)

        print("API token was reset successfully!")
            
        return token

    @retry(max_retries=3, delay=5, exception=Exception)
    def reset_password(self):
        driver = self.driver
        self.logout()
        scanner = self.driver.find_elements(By.CLASS_NAME, 'loginQr')
        actions = ActionChains(self.driver)
        actions.click_and_hold(scanner[0])
        actions.release().perform()
        time.sleep(0.1)
        input = self.driver.find_element(By.ID, 'mat-input-1')
        input.send_keys('9565529742\n')

        time.sleep(0.5)

        forgot_pwd_button = driver.find_element(By.XPATH, "//span[text()='Forgot Password?']")
        forgot_pwd_button.click()

        email_input = self.driver.find_element(By.CLASS_NAME, 'loginformcontrol')
        email_input.send_keys('ablibraryhub@gmail.com\n')
        time.sleep(5)
        inputs = self.driver.find_elements(By.XPATH, "//input[@autocomplete='one-time-code']")
        # TODO: Extract otp from GmailService
        otp = self.gmail_service.get_dhan_otp(otp_sent_timestamp=(datetime.now() - timedelta(seconds=10)), otp_type='Password')
        for i in range(6):
            inputs[i].send_keys(otp[i])
            time.sleep(0.3)

        button = driver.find_element(By.XPATH, "//button[text()='Proceed to Password Reset']")
        button.click()

        new_password = self.generate_password()

        time.sleep(1)

        new_pwd_element = self.driver.find_element(By.XPATH, "//input[@placeholder='Enter New Password']")
        new_pwd_element.send_keys(new_password)

        repeat_pwd_element = self.driver.find_element(By.XPATH, "//input[@placeholder='Enter Password Again']")
        repeat_pwd_element.send_keys(new_password)

        change_button = driver.find_element(By.XPATH, "//button[text()='Change Password']")
        change_button.click()

        dhan_pwd_path = 'dhan_password.txt'
        with open(dhan_pwd_path, 'w') as pwd_file:
            pwd_file.write(new_password)

        print("Dhan Password was reset successfully!")

    @retry(max_retries=3, delay=5, exception=Exception)
    def reset_pin(self):
        driver = self.driver
        driver.get('https://web.dhan.co/index/profile')
        time.sleep(5)
        manage_pin_button = driver.find_element(By.XPATH, "//span[text()=' Manage PIN or 2FA authentication ']")
        manage_pin_button.click()

        generate_otp_button = driver.find_element(By.XPATH, "//button[text()='Generate OTP to Verify']")
        generate_otp_button.click()

        time.sleep(5)

        inputs = self.driver.find_elements(By.XPATH, "//input[@autocomplete='one-time-code']")
        otp = self.gmail_service.get_dhan_otp(otp_sent_timestamp=(datetime.now() - timedelta(seconds=10)), otp_type='PIN')
        print("otp: %s" % otp)
        print("inputs_len: %s" % len(inputs))
        for i in range(6):
            inputs[i].send_keys(otp[i % 6])
            time.sleep(0.3)

        continue_button = driver.find_element(By.XPATH, "//button[text()='Continue']")
        continue_button.click()

        time.sleep(1)

        dhan_pwd_path = 'dhan_password.txt'
        dhan_pwd = ''
        with open(dhan_pwd_path, 'r') as pwd_file:
            dhan_pwd = pwd_file.read()

        pwd_element = self.driver.find_element(By.XPATH, "//input[@placeholder='Enter your password to confirm']")
        pwd_element.send_keys(dhan_pwd)

        inputs = self.driver.find_elements(By.XPATH, "//input[@autocomplete='one-time-code']")
        # TODO: Extract otp from GmailService
        pin = self.generate_pin()
        for i in range(12):
            inputs[i].send_keys(pin[i%6])
            time.sleep(0.5)

        continue_button = driver.find_element(By.XPATH, "//button[text()='Continue']")
        continue_button.click()
        
        time.sleep(2)

        self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
        self.driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        driver.delete_all_cookies()
        driver.execute_script("window.location.reload();")

        time.sleep(3)

        dhan_pin_path = 'dhan_pin.txt'
        with open(dhan_pin_path, 'w') as pwd_file:
            pwd_file.write(pin)

        print("Dhan PIN was reset successfully!")

    @retry(max_retries=3, delay=5, exception=Exception)
    def clear_cache(self):
        driver = self.driver
        time.sleep(2)
        self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
        self.driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        driver.delete_all_cookies()
        driver.execute_script("window.location.reload();")
        time.sleep(3)

    @retry(max_retries=3, delay=5, exception=Exception)
    def withdraw_funds(self, amount):
        driver = self.driver
        self.login()
        driver.get('https://web.dhan.co/index/money')
        time.sleep(5)

        withdraw_button = driver.find_element(By.XPATH, "//span[text()=' Withdraw Money ']")
        withdraw_button.click()

        time.sleep(2)

        money_input = driver.find_element(By.CLASS_NAME, 'money_input')
        money_input.clear()
        time.sleep(1)
        money_input.send_keys(amount)

        confirm_button = driver.find_element(By.XPATH, "//button[text()=' Confirm Request ']")
        confirm_button.click()

        time.sleep(2)

        pay_out_button = driver.find_element(By.XPATH, "//span[text()=' Pay-Ins / Pay-Outs ']")
        pay_out_button.click()
        
        time.sleep(2)

        image_path = 'withdrawal_screenshot.png'
        driver.save_screenshot(image_path)

        print("Dhan Fund Withdrawal was successful!")

    @retry(max_retries=3, delay=5, exception=Exception)
    def add_funds(self, amount):
        driver = self.driver
        self.login()

        driver.get('https://web.dhan.co/index/money')
        time.sleep(5)

        add_money_input = driver.find_element(By.CLASS_NAME, 'add_money_box')
        add_money_input.clear()
        time.sleep(1)
        add_money_input.send_keys(amount)

        add_money_button = driver.find_element(By.XPATH, "//button[text()='Add Money for Investing']")
        add_money_button.click()

        time.sleep(2)

        add_money_to_account = driver.find_element(By.XPATH, "//span[text()=' Add Money to Account']")
        add_money_to_account.click()
        
        time.sleep(120)

        image_path = 'add_fund_screenshot.png'
        driver.save_screenshot(image_path)

        print("Dhan Add Fund was successful!")

    @retry(max_retries=3, delay=5, exception=Exception)
    def activate_kill_switch(self):
        driver = self.driver
        self.login()

        driver.get('https://web.dhan.co/index/money')
        time.sleep(5)

        traders_control = driver.find_element(By.XPATH, "//span[text()=' Traders Controls ']")
        traders_control.click()

        time.sleep(1)

        kill_switch_tab = driver.find_element(By.XPATH, "//span[text()=' Kill Switch for Over-Trading ']")
        kill_switch_tab.click()

        time.sleep(1)

        activate_kill_switch_button = driver.find_element(By.XPATH, "//button[text()='Activate Kill Switch']")
        activate_kill_switch_button.click()

        time.sleep(1)

        confirm_button = driver.find_element(By.CLASS_NAME, 'confirmButtonsIcons')
        confirm_button.click()

        time.sleep(5)

        checkbox = driver.find_element(By.CLASS_NAME, "mat-checkbox-frame")
        actions = ActionChains(self.driver)
        actions.click_and_hold(checkbox)
        actions.release().perform()

        time.sleep(0.5)

        deactivate_kill_switch_button = driver.find_element(By.XPATH, "//button[text()='Deactivate Kill Switch']")
        deactivate_kill_switch_button.click()

        time.sleep(1)
        driver.execute_script("window.location.reload();")
        time.sleep(5)

        traders_control = driver.find_element(By.XPATH, "//span[text()=' Traders Controls ']")
        traders_control.click()

        time.sleep(1)

        kill_switch_tab = driver.find_element(By.XPATH, "//span[text()=' Kill Switch for Over-Trading ']")
        kill_switch_tab.click()

        time.sleep(1)

        activate_kill_switch_button = driver.find_element(By.XPATH, "//button[text()='Activate Kill Switch']")
        activate_kill_switch_button.click()
        
        time.sleep(1)

        confirm_button = driver.find_element(By.CLASS_NAME, 'confirmButtonsIcons')
        confirm_button.click()

        time.sleep(1)

        image_path = 'kill_switch.png'
        driver.save_screenshot(image_path)

        print("Activated Kill Switch Successfully.")
        self.gmail_service.send_email(
            'Activated Kill Switch Successfully.',
            "Activated Kill Switch Successfully. Please check root cause why it happened.")

    @retry(max_retries=3, delay=5, exception=Exception)
    def remove_all_other_active_sessions(self, aws_hostname):
        aws_ip = self.extract_aws_ip(aws_hostname)
        if aws_ip is None:
            self.gmail_service.send_email(
                'AWS IP NOT FOUND',
                "AWS EC2 Instance IP is not found. Activating Kill Switch. Please Check email.")
            self.activate_kill_switch()
        driver = self.driver
        is_logged_in = False
        user_names = driver.find_elements(By.XPATH, "//span[contains(@class, 'user-name')]")
        if len(user_names) > 0:
            is_logged_in = True
        if not is_logged_in:
            self.login()

        if driver.current_url != 'https://web.dhan.co/index/money':
            driver.get('https://web.dhan.co/index/money')
            time.sleep(5)

        traders_control = driver.find_element(By.XPATH, "//span[text()=' Traders Controls ']")
        traders_control.click()

        time.sleep(1)

        active_session_tab = driver.find_element(By.XPATH, "//span[text()=' Active session ']")
        active_session_tab.click()
        
        time.sleep(1)

        max_device_count = 50
        while max_device_count > 0:
            session_texts = driver.find_elements(By.CLASS_NAME, 'session_text')
            logout_buttons = driver.find_elements(By.CLASS_NAME, 'logouttxt')
            unautorised_devices = []
            found_one = False
            for i in range(len(session_texts) - 1, -1, -1):
                session_text = session_texts[i]
                curr_session_text = session_text.text
                splitted_session = curr_session_text.split('/')
                if len(splitted_session) >= 2:
                    ip_text = splitted_session[1].split(':')
                    if len(ip_text) >= 2:
                        ip_address = ip_text[1].strip()
                        print(ip_address)
                        if self.check_ip_version(ip_address) == 'IPv6' or ip_address != aws_ip:
                            print("Found IPv6 address or unauthorised ip address. Removing this ip: %s" % ip_address)
                            self.gmail_service.send_email(
                                'Unauthorised Dhan Access from ip: %s' % ip_address,
                                "Unauthoised person with ip details: %s is trying to access Dhan."
                                " Removing this ip adress from active session." % splitted_session[1])
                            unautorised_devices.append(logout_buttons[i])
                            found_one = True
                            logout_buttons[i].click()
                            time.sleep(0.5)
                if found_one:
                    break
            max_device_count -= 1
            if not found_one:
                break
        # for device in unautorised_devices:
        #     device.click()
        #     time.sleep(0.5)

    @retry(max_retries=3, delay=5, exception=Exception)
    def remove_all_inactive_aws_sessions(self, aws_hostname):
        aws_ip = self.extract_aws_ip(aws_hostname)
        if aws_ip is None and not self.kill_switch_activated:
            self.gmail_service.send_email(
                'AWS IP NOT FOUND',
                "AWS EC2 Instance IP is not found. Activating Kill Switch. Please Check email.")
            self.activate_kill_switch()
        driver = self.driver
        is_logged_in = False
        user_names = driver.find_elements(By.XPATH, "//span[contains(@class, 'user-name')]")
        if len(user_names) > 0:
            is_logged_in = True
        self.login()

        if driver.current_url != 'https://web.dhan.co/index/money':
            driver.get('https://web.dhan.co/index/money')
            time.sleep(5)

        traders_control = driver.find_element(By.XPATH, "//span[text()=' Traders Controls ']")
        traders_control.click()

        time.sleep(1)

        active_session_tab = driver.find_element(By.XPATH, "//span[text()=' Active session ']")
        active_session_tab.click()

        time.sleep(1)

        max_device_count = 50
        while max_device_count > 0:
            session_texts = driver.find_elements(By.CLASS_NAME, 'session_text')
            logout_buttons = driver.find_elements(By.CLASS_NAME, 'logouttxt')
            unautorised_devices = []
            found_one = False
            if len(session_texts) <= 1:
                break
            for i in range(len(session_texts) - 1, -1, -1):
                session_text = session_texts[i]
                curr_session_text = session_text.text
                splitted_session = curr_session_text.split('/')
                if len(splitted_session) >= 2:
                    ip_text = splitted_session[1].split(':')
                    if len(ip_text) >= 2:
                        ip_address = ip_text[1].strip()
                        # print(ip_address)
                        if ip_address == aws_ip:
                            # print("Extra ip address. Removing this ip: %s" % ip_address)
                            # self.gmail_service.send_email(
                            #     'Unauthorised Dhan Access from ip: %s' % ip_address,
                            #     "Unauthoised person with ip details: %s is trying to access Dhan."
                            #     " Removing this ip adress from active session." % splitted_session[1])
                            unautorised_devices.append(logout_buttons[i])
                            found_one = True
                            logout_buttons[i].click()
                            time.sleep(0.5)
                if found_one:
                    break
            max_device_count -= 1
            if not found_one:
                break

    def extract_aws_ip(self, hostname):
        if hostname is None:
            return None
        # hostname = "ec2-3-111-53-153.ap-south-1.compute.amazonaws.com"

        # Regular expression pattern to extract the IP address
        pattern = r'ec2-(\d{1,3})-(\d{1,3})-(\d{1,3})-(\d{1,3})'

        # Search for the pattern in the hostname
        match = re.search(pattern, hostname)

        # Extract the IP address if the pattern matches
        if match:
            ip_address = '.'.join(match.groups())
            return ip_address
        else:
            return None

    def check_ip_version(self, ip):
        try:
            ip_obj = ipaddress.ip_address(ip)
            if isinstance(ip_obj, ipaddress.IPv4Address):
                return "IPv4"
            elif isinstance(ip_obj, ipaddress.IPv6Address):
                return "IPv6"
        except ValueError:
            return "IPv6"

    def generate_pin(self):
        return '%s' % random.randint(100000, 999999)

    def generate_password(self):
        # Generate 3 lowercase alphabets
        lower_chars = random.choices(string.ascii_lowercase, k=3)
        # Generate 1 uppercase alphabet
        upper_char = random.choice(string.ascii_uppercase)
        # Generate 4 digits
        digits = random.choices(string.digits, k=4)

        # Combine the characters and shuffle them to create randomness
        password_chars = lower_chars + [upper_char] + digits
        random.shuffle(password_chars)

        # Join the list into a single string as the final password
        password = ''.join(password_chars)
        return password

            


if __name__ == '__main__':
    dwm = DhanWebManager()
    # gmail_service.transfer_aws_dhan_messages()
    dwm.create_driver_instance()
    dwm.login()
    # dwm.reset_api_token()
    #
    # start_tm = time.time()
    # dwm.reset_password()
    # dwm.login()
    # dwm.reset_pin()
    # end_tm = time.time()
    #
    # print("time_diff: %s" % (end_tm - start_tm))
    #
    # dwm.login()
    # dwm.withdraw_funds(1000)
    # dwm.add_funds(1000)

    # start_tm = time.time()
    # dwm.login()
    # dwm.reset_pin()
    # dwm.reset_password()
    # end_tm = time.time()
    # print("time_diff: %s" % (end_tm - start_tm))

    # get_telegram_otp()
    dwm.remove_all_other_active_sessions("ec2-35-154-28-3.ap-south-1.compute.amazonaws.com")
        

