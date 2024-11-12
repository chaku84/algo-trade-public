from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.support.ui import Select

import os
import time
import pandas as pd


chrome_driver_path = '/usr/local/bin/chromedriver'

os.environ["PATH"] = os.environ["PATH"] + ":" + chrome_driver_path

chrome_options = Options()
chrome_options.add_argument("--headless")  # Optional: Run in headless mode
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument("--remote-debugging-port=9222")
# chrome_options.add_argument('--disable-gpu')
driver = webdriver.Chrome(options=chrome_options)
driver.get('https://www.nseindia.com/report-detail/fo_eq_security')

time.sleep(30)

input_id = "sign-in-phone-number"
phone_input = driver.find_element(By.ID, input_id)
dropdown = driver.find_element(By.ID, 'hcpFO_instrument')
dropdown = Select(dropdown)
dropdown.select_by_visible_text('Index Options')

time.sleep(5)

dropdown = driver.find_element(By.ID, 'hcpFO_symbol')
dropdown = Select(dropdown)
dropdown.select_by_visible_text('BANKNIFTY')

data = []

year = 2022
year_low = 30000
year_high = 45000

dropdown = driver.find_element(By.ID, 'hcpFO_YEAR')
dropdown = Select(dropdown)
dropdown.select_by_visible_text(str(year))


expiry_dropdown = driver.find_element(By.ID, 'hcpFO_expiryDt')
expiry_dropdown = Select(expiry_dropdown)
options = expiry_dropdown.options
option_texts = [option.text for option in options]

for i in range(1, len(option_texts), 1):
    expiry_dropdown.select_by_visible_text(option_texts[i])

    option_type_dropdown = driver.find_element(By.ID, 'hcpFO_optionType')
    option_type_dropdown = Select(option_type_dropdown)
    option_type_dropdown.select_by_visible_text('CE')

    input_element = driver.find_element(By.ID, 'hcpFO_strikePrice')

    for price in range(30000, 45100, 100):
        input_element = driver.find_element(By.ID, 'hcpFO_strikePrice')
        input_element.send_keys(str(price))

        a_element = driver.find_element(By.CSS_SELECTOR, 'a[data-val="Custom"]')
        a_element.click()

        expiry = datetime.strptime(option_texts[i], "%d-%m-%Y")
        expiry_start_date = expiry - timedelta(days=7)
        expiry_start_date_str = datetime.strftime(expiry_start_date, "%d-%m-%Y")
        
        input_element = driver.find_element(By.ID, 'hcpFO-startDate')
        driver.execute_script("arguments[0].removeAttribute('readonly')", input_element)
        input_element.send_keys(expiry_start_date_str)

        input_element = driver.find_element(By.ID, 'hcpFO-endDate')
        driver.execute_script("arguments[0].removeAttribute('readonly')", input_element)
        input_element.send_keys(option_texts[i])

        button = driver.find_element(By.CLASS_NAME, 'filterbtn')
        button.click()

        table = driver.find_element(By.ID, 'hcpFOTable')

        # Get all rows from the table (skip the header row)
        rows = table.find_elements(By.TAG_NAME, 'tr')[1:]

        # Iterate through each row
        for row in rows:
            # Initialize an empty dictionary for the row data
            row_data = {}

            # Get all cells in the row
            cells = row.find_elements(By.TAG_NAME, 'td')

            # Extract data from each cell and add it to the row dictionary
            row_data['Symbol'] = cells[0].text
            row_data['Date'] = cells[1].text
            row_data['Expiry'] = cells[2].text
            row_data['OptionType'] = cells[3].text
            row_data['StrikePrice'] = cells[4].text
            row_data['Open'] = cells[5].text
            row_data['High'] = cells[6].text
            row_data['Low'] = cells[7].text
            row_data['Close'] = cells[8].text
            row_data['LTP'] = cells[9].text
            row_data['SettlePrice'] = cells[10].text
            row_data['NoOfContracts'] = cells[11].text
            row_data['TurnoverInRsLacs'] = cells[12].text
            row_data['PremiumTurnoverInRsLacs'] = cells[13].text
            row_data['OpenInt'] = cells[14].text
            row_data['ChangeInOI'] = cells[15].text
            row_data['UnderlyingValue'] = cells[16].text

            # Append the row dictionary to the data list
            data.append(row_data)
        time.sleep(1)
    break
df = pd.DataFrame(data)

# Save DataFrame to CSV
df.to_csv('table_data.csv', index=False)


