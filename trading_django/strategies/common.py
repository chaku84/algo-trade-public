from datetime import datetime
import bisect

"""
    @atm_type: string (ATM, ITM or OTM)
    @depth: integer (0,1,2,3..)
    @option_type: (CALL OR PUT)
"""
def get_price(atm_type, depth, option_type, strike_price_list, curr_strike_price):
    index = bisect.bisect(strike_price_list, curr_strike_price)
    prev = strike_price_list[index-1]
    next = strike_price_list[index]
    atm_price = -1
    if curr_strike_price - prev > next - curr_strike_price:
        atm_price = next
    else:
        atm_price = prev
        index = index - 1

    if atm_type == 'ATM' or depth == 0:
        return atm_price

    mult = 1 if option_type == 'CALL' else -1

    if atm_type == 'ITM':
        return strike_price_list[index - mult * depth]
    else:
        return strike_price_list[index + mult * depth]


def get_nearest_expiry(sorted_expiry_list, datetime_obj):
    ind = bisect.bisect(sorted_expiry_list, datetime_obj.timestamp())
    time = datetime.fromtimestamp(sorted_expiry_list[ind])
    return time.date().isoformat()