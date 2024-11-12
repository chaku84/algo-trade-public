import os
import time
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from tips.gmail import get_telegram_otp
from datetime import datetime


class Telegram(object):
    __instance = None
    __driver = None

    def __init__(self):
        self.chrome_driver_path = '/usr/local/bin/chromedriver'
        if self.chrome_driver_path not in os.environ['PATH']:
            os.environ["PATH"] = os.environ["PATH"] + ":" + self.chrome_driver_path
        if Telegram.__instance is None:
            Telegram.__instance = self

    @staticmethod
    def get_instance():
        if Telegram.__instance is None:
            Telegram()
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Optional: Run in headless mode
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.54 Safari/537.36")
            chrome_options.add_argument("--window-size=1920,1080")

            Telegram.__instance.__driver = webdriver.Chrome(options=chrome_options)
            # Telegram.__instance.__driver = webdriver.Chrome()
        return Telegram.__instance

    def refresh_instance(self):
        # Explicit method to refresh the driver if needed
        if self.__driver is not None:
            self.__driver.quit()
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Optional: Run in headless mode
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument('--disable-gpu')

            self.__driver = webdriver.Chrome(options=chrome_options)
            # self.__driver = webdriver.Chrome()

    def login_into_telegram(self):
        driver = self.__driver
        telegram_cookies_path = '/home/ec2-user/services/algo-trade/trading_django/tips/telegram_cookies.pkl'
        # self.delete_old_cookies(filename=telegram_cookies_path)
        if os.path.exists(telegram_cookies_path):
            print("loading telegram cookies")
            driver.get('https://web.telegram.org/a/#-1001934806263')
            time.sleep(5)
            with open(telegram_cookies_path, 'rb') as session_file:
                session_data = pickle.load(session_file)

                # Load cookies
                for cookie in session_data.get('cookies', []):
                    driver.add_cookie(cookie)

                # Load local storage
                local_storage_data = session_data.get('local_storage', {})
                for key, value in local_storage_data.items():
                    print(key)
                    driver.execute_script("window.localStorage.setItem(arguments[0], arguments[1]);", key, value)
            # time.sleep(10)
            driver.execute_script("window.location.reload();")
            # driver.get('https://web.telegram.org/a/#-1001934806263')
            time.sleep(10)
        else:
            driver.get('https://web.telegram.org/a/#-1001934806263')
            time.sleep(10)
            button_xpath = "//button[text()='Log in by phone Number']"
            login_button = driver.find_element(By.XPATH, button_xpath)

            # Perform actions with the button (e.g., click)
            login_button.click()

            time.sleep(5)

            input_id = "sign-in-phone-number"
            phone_input = driver.find_element(By.ID, input_id)

            # Perform actions with the input (e.g., type text)
            phone_input.send_keys("9565529742")

            time.sleep(2)

            next_button_xpath = "//button[text()='Next']"
            next_button = driver.find_element(By.XPATH, next_button_xpath)

            otp_sent_timestamp = time.time()
            next_button.click()

            time.sleep(15)


            def check_if_invalid_code():
                # Locate the label element by text using XPath
                try:
                    label_xpath = "//label[contains(text(), 'Invalid code.')]"
                    invalid_code_label = driver.find_element(By.XPATH, label_xpath)
                    return True
                except Exception as e:
                    print(e)
                    return False


            count = 5
            while count > 0:
                otp_code = get_telegram_otp(otp_sent_timestamp)

                otp_input_id = "sign-in-code"
                otp_input = driver.find_element(By.ID, otp_input_id)

                # Perform actions with the input (e.g., type text)
                otp_input.send_keys(otp_code)
                count = count - 1
                time.sleep(10)
                if not check_if_invalid_code():
                    break
                else:
                    otp_input.clear()

            time.sleep(15)

        time.sleep(30)

        # xpath_expression = "//a[.//div/div/div/h3[contains(text(), 'MGTA Research & education Members only')]]"
        # xpath_expression = "//a[.//div/div/div/h3[contains(text(), 'Private channel (MGTA)')]]"
        xpath_expression = "//a[.//div/div/div/h3[contains(text(), 'RISHAB | TRADER (PREMIUM)')]]"
        # xpath_expression = "//a[.//div/div/div/h3[contains(text(), 'Mine Airtel 1')]]"

        # Find the anchor element using the XPath expression
        anchor_element = driver.find_element(By.XPATH, xpath_expression)
        print("Found anchor element")

        # Save cookies and local storage to a file
        session_data = {
            'cookies': driver.get_cookies(),
            'local_storage': driver.execute_script("return window.localStorage;")
        }
        with open(telegram_cookies_path, 'wb') as session_file:
            pickle.dump(session_data, session_file)

        time.sleep(15)
        # Perform actions with the selected anchor element (e.g., click)
        anchor_element.click()

        time.sleep(10)


    def get_telegram_messages(self, channel_name='Seepak Jio'):
        driver = self.__driver
        # if channel_name != 'Mine Airtel 1':
        if channel_name != 'RISHAB | TRADER (PREMIUM)💰':
            xpath_expression = "//a[.//div/div/div/h3[contains(text(), '%s')]]" % channel_name
            anchor_element = driver.find_element(By.XPATH, xpath_expression)
            print("Found Rishab Trader anchor element")

            time.sleep(15)
            anchor_element.click()
            time.sleep(10)

            # Switch Back to Market Guide
            xpath_expression = "//a[.//div/div/div/h3[contains(text(), 'Seepak Jio')]]"
            anchor_element = driver.find_element(By.XPATH, xpath_expression)
            print("Found MGTA anchor element")

            time.sleep(15)
            anchor_element.click()
            time.sleep(10)

        # Locate the parent div with class "messages-container"
        parent_div = driver.find_element(By.CLASS_NAME, 'messages-container')

        # Locate all child divs with class "message-date-group" within the parent div
        date_groups = parent_div.find_elements(By.CLASS_NAME, 'message-date-group')

        message_map_list = []
        # Iterate through each date group
        for date_group in date_groups:
            date_div = date_group.find_element(By.XPATH, './/div[contains(@class, "sticky-date")]')
            date = date_div.text
            # print(date)

            # if date.lower() == 'yesterday':

            # Locate all child divs with ids in the format "message<no>" within the date group
            message_divs = date_group.find_elements(By.XPATH, './/div[starts-with(@id, "message")]')

            # Iterate through each message div
            for message_div in message_divs:
                try:
                    message_map = {}
                    message_map['date'] = date
                    message_div_id = message_div.get_attribute('id')
                    # print(message_div_id)
                    message_map['message_id'] = message_div_id
                    # Locate the div with class "text-content" within the message div
                    text_content_div = message_div.find_element(By.XPATH, './/div[contains(@class, "text-content")]')

                    # Extract and print the text content
                    final_text = text_content_div.text
                    message_map['text'] = final_text
                    message_map_list.append(message_map)

                    # print("Final Text:", final_text)
                except Exception:
                    pass

        return message_map_list

    def delete_old_cookies(self, filename='telegram_cookies.pkl', max_age_hours=12):
        # Check if the file exists
        if os.path.exists(filename):
            # Get the creation time of the file
            creation_time = os.path.getctime(filename)

            # Calculate the age of the file in hours
            age_hours = (time.time() - creation_time) / 3600

            # If the file is older than the specified time, delete it
            if age_hours > max_age_hours:
                os.remove(filename)
                print(f"Deleted old cookies file ({filename})")


# tel = Telegram.get_instance()
# tel.login_into_telegram()
# tel.get_telegram_messages()
