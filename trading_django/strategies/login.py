import logging
from kiteconnect import KiteConnect, KiteTicker
import requests
import pyotp
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
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

logging.basicConfig(level=logging.DEBUG)

class Login():
    def __init__(self):
        self.kite = KiteConnect(api_key="xxx")
        self.access_token = ''
        self.request_token = ''
        # self.login()

    def login(self):
        self.access_token = ''
        if os.path.exists("access_token.txt"):
            self.access_token = open("access_token.txt", "r").read()
            self.kite.set_access_token(self.access_token)
        else:
            self.request_token = self.get_request_token()

            data = self.kite.generate_session(self.request_token, api_secret="xxx")
            print("access_token: %s" % data["access_token"])
            self.kite.set_access_token(data["access_token"])
            self.access_token = data["access_token"]

            f = open("access_token.txt", "w")
            f.write(data["access_token"])
            f.close()

        try:
            self.kite.orders()
        except Exception:
            self.request_token = self.get_request_token()

            data = self.kite.generate_session(self.request_token, api_secret="xxx")
            print("access_token: %s" % data["access_token"])
            self.kite.set_access_token(data["access_token"])
            self.access_token = data["access_token"]

            f = open("access_token.txt", "w")
            f.write(data["access_token"])
            f.close()

        logging.info(self.kite.orders())

    def get_request_token(self):
        chrome_driver_path = '/usr/local/bin/chromedriver'

        if chrome_driver_path not in os.environ['PATH']:
            os.environ["PATH"] = os.environ["PATH"] + ":" + chrome_driver_path

        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Optional: Run in headless mode
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument('--disable-gpu')

        driver = webdriver.Chrome(options=chrome_options)
        initial_url = "https://kite.zerodha.com/connect/login?v=3&api_key=xxx"

        driver.get(initial_url)

        time.sleep(30)
        user_id_field = driver.find_element(By.ID, "userid")
        password_field = driver.find_element(By.ID, "password")

        user_id_field.send_keys("xxx")
        password_field.send_keys("xxx")

        password_field.send_keys(Keys.RETURN)

        # URL to be invoked
        # initial_url = "https://kite.zerodha.com/connect/login?v=3&api_key=2s3d6ngrn9fa5bsf"
        #
        # # Send a GET request to get the redirection URL
        # response = requests.get(initial_url, allow_redirects=False)
        # redirection_url = response.headers.get("Location")
        #
        # # User ID and Password
        # user_id = "xxx"
        # password = "xxx"
        #
        #
        # '''Login into Zerodha Account'''
        # # API URL for login
        # api_url = "https://kite.zerodha.com/api/login"
        #
        # # Payload for the POST request
        # payload = {
        #     "user_id": user_id,
        #     "password": password,
        # }
        #
        # # Send a POST request with payload
        # response = requests.post(api_url, data=payload)
        #
        # # Print the response
        # print("API Response:", response.text)
        #
        # response_data = json.loads(response.text)
        #
        # # Extract request_id
        # request_id = response_data.get("data", {}).get("request_id")

        '''GET TOTP'''
        # Your Zerodha 2FA secret key
        secret_key_2fa = "xxx"

        # Create a TOTP object using the secret key
        totp = pyotp.TOTP(secret_key_2fa)

        # Generate the TOTP code
        totp_code = totp.now()

        print("Generated TOTP Code:", totp_code)

        # '''Enter TOTP'''
        # # URL for the twofa API
        # twofa_api_url = "https://kite.zerodha.com/api/twofa"
        #
        # # Payload for the twofa POST request
        # payload = {
        #     "user_id": user_id,
        #     "request_id": request_id,
        #     "twofa_value": totp_code,  # Replace with your TOTP code
        #     "twofa_type": "totp",
        #     "skip_session": "true"
        # }
        #
        # # Send the twofa POST request
        # response = requests.post(twofa_api_url, data=payload, allow_redirects=False)
        # redirection_url = response.headers.get("Location")
        #
        # # Print the response
        # print(response.headers)
        # print("Redirection URL:", response.url)

        # Redirect the user to the login url obtained
        # from kite.login_url(), and receive the request_token
        # from the registered redirect url after the login flow.
        # Once you have the request_token, obtain the access_token
        # as follows.

        time.sleep(15)
        totp_field = driver.find_element(By.XPATH, "//input[@label='External TOTP']")
        totp_field.send_keys(totp_code)

        time.sleep(15)
        final_url = driver.current_url

        # Extract the request_token from the final URL
        request_token = final_url.split("request_token=")[1].split('&')[0]

        # Print the extracted request_token
        print("Extracted request_token:", request_token)

        driver.quit()
        return request_token
