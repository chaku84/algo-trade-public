from datetime import datetime, timedelta
import pytz
import math


def get_ist_datetime(utc_datetime):
    # Define UTC and IST timezones
    utc_timezone = pytz.timezone('UTC')
    ist_timezone = pytz.timezone('Asia/Kolkata')  # IST timezone

    # Convert UTC datetime to IST datetime
    ist_datetime = utc_datetime.replace(tzinfo=utc_timezone).astimezone(ist_timezone)

    return ist_datetime


def get_nearest_tens(number):
    if number % 10 > 5:
        return int(math.ceil(number / 10) * 10)
    return int(math.floor(number / 10) * 10)


def get_higher_tens(number):
    return int(math.ceil(number / 10) * 10)


def  my_timedelta(datetime, operator, delta):
    days = delta.days
    new_date = datetime
    if operator not in ('-', '+'):
        print("Unsupported operator")
        return datetime
    while new_date.weekday() in (5, 6):
        if operator == '-':
            new_date -= timedelta(days=1)
        else:
            new_date += timedelta(days=1)
    for _ in range(abs(days)):
        if operator == '-':
            new_date -= timedelta(days=1)
        else:
            new_date += timedelta(days=1)
        while new_date.weekday() in (5, 6):
            if operator == '-':
                new_date -= timedelta(days=1)
            else:
                new_date += timedelta(days=1)
    
    return new_date
