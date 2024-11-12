import pandas as pd
import json
from datetime import datetime

# Load the two CSV files into DataFrames
nifty_bank_df = pd.read_csv('/Users/chandack/Downloads/NIFTY_BANK_minute.csv', parse_dates=['date'], dayfirst=True)
gocharting_df = pd.read_csv('/Users/chandack/Downloads/MyReport_www.gocharting.com.csv')

# Convert the 'date' column in nifty_bank_df to datetime, handling a 24-hour format without AM/PM
nifty_bank_df['date'] = pd.to_datetime(nifty_bank_df['date'], format='%Y-%m-%d %H:%M:%S')

# Parse date column in gocharting_df, converting it to a datetime object
# Adjust the format to match the structure of the data without AM/PM
gocharting_df['Date'] = pd.to_datetime(
    gocharting_df['Date'],
    format='%a %b %d %Y %H:%M:%S GMT+0530 (India Standard Time)'
)

# Convert the dates in gocharting_df to match the required format
gocharting_df['Date'] = gocharting_df['Date'].dt.strftime('%d/%m/%y %H:%M')

# Filter data from the first file between 1st Jan 2023 and 27th Sep 2024
nifty_bank_filtered = nifty_bank_df[
    (nifty_bank_df['date'] >= '2023-01-01') & (nifty_bank_df['date'] <= '2024-09-27')
]

# Convert date to the required format in the first DataFrame
nifty_bank_filtered['date'] = nifty_bank_filtered['date'].dt.strftime('%d/%m/%y %H:%M')

# Create a dictionary from the first DataFrame
nifty_bank_dict = nifty_bank_filtered.set_index('date').to_dict(orient='index')

# Now convert 'Date' column back to datetime for proper filtering (after formatting for consistency)
gocharting_df['Date'] = pd.to_datetime(gocharting_df['Date'], format='%d/%m/%y %H:%M')

# Filter data from the second file between 27th Sep 2024 and 11th Oct 2024
gocharting_filtered = gocharting_df[
    (gocharting_df['Date'] >= pd.Timestamp('2024-09-27 00:00:00')) & 
    (gocharting_df['Date'] <= pd.Timestamp('2024-10-17 23:59:00'))
]

gocharting_filtered['Date'] = gocharting_filtered['Date'].dt.strftime('%d/%m/%y %H:%M')

gocharting_dict = {
    row['Date']: {
        "open": row['Open'],
        "high": row['High'],
        "low": row['Low'],
        "close": row['Close']
    }
    for _, row in gocharting_filtered.iterrows()
}


# Create a dictionary from the second DataFrame
# gocharting_dict = gocharting_filtered.set_index('Date').to_dict(orient='index')

# Combine both dictionaries
combined_dict = {**nifty_bank_dict, **gocharting_dict}

# Write the combined dictionary to a JSON file
with open('banknifty_minute_data.json', 'w') as json_file:
    json.dump(combined_dict, json_file, indent=4)

print("Data successfully extracted and saved to banknifty_minute_data.json")
