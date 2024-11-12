import re
import json
import os
import traceback
from datetime import datetime


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


def process_log_file(log_file_path):
    data_dict = {}

    # Read the log file
    with open(log_file_path, 'r') as log_file:
        lines = log_file.readlines()

    current_date = None
    current_price = None
    current_option_type = None
    current_thread = None

    for i, line in enumerate(lines):
        # print(i)
        # Match the log pattern to extract thread, date, price, and option type
        match = re.search(r'thread: (\d+), start_time: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}), price_str: (\d+), option_type: (PE|CE)', line)
        if match:
            current_thread = match.group(1)
            start_time_str = match.group(2)
            current_price = match.group(3)
            current_option_type = match.group(4)

            # Parse start_time as a datetime object
            start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
            current_date = start_time.strftime('%Y-%m-%d')
            print(current_thread)

            # The next line contains the data (assuming it is a list in the log file)
            if i + 1 < len(lines):
                next_line_data = lines[i + 1].strip()

                # If the data is a valid list, store it in the dictionary
                try:
                    data_list = eval(next_line_data)  # Convert string to list

                    # Ensure the structure exists
                    if current_price not in data_dict:
                        data_dict[current_price] = {"PE": [], "CE": []}

                    # Append data to the correct option type (PE or CE)
                    data_dict[current_price][current_option_type].extend(data_list)

                except Exception as e:
                    traceback.print_exc()
                    # Handle any invalid list parsing here if needed
                    pass

        # Save the data to a JSON file named after the date
        if current_date:
            json_file_name = f"{current_date}.json"
            write_to_file(data_dict, json_file_name)

    return f"Data has been saved to {current_date}.json"
# Example usage
log_file_path = '/home/ec2-user/services/algo-trade/trading_django/go_charting_data.log'
process_log_file(log_file_path)

