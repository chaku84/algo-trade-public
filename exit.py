from dhanhq import dhanhq

tokens_file_path = '/home/ec2-user/services/algo-trade/trading_django/dhan_token.txt'
with open(tokens_file_path, 'r') as token_file:
    api_token = token_file.read()
    
# api_token = ''
    
dhan = dhanhq("1101185196", api_token)

order_list = dhan.get_order_list()['data']
for order in order_list:
    order_id = order['orderId']
    order_status = order['orderStatus']
    if order['orderStatus'] == 'PENDING':
        dhan.cancel_order(order_id)

time.sleep(2)
positions = dhan.get_positions()['data']
# Exit all sell positions first to exit hedge position
for position in positions:
    security_id = position['securityId']
    net_quantity = position['netQty']
    product_type = position['productType']
    if net_quantity < 0:
        dhan.place_slice_order(security_id=security_id, exchange_segment=dhan.NSE_FNO, transaction_type=dhan.BUY, quantity=abs(net_quantity), order_type=dhan.MARKET, product_type=product_type, price=0, validity='DAY')
        time.sleep(1)

# Exit all buy positions
for position in positions:
    security_id = position['securityId']
    net_quantity = position['netQty']
    product_type = position['productType']
    if net_quantity > 0:
        dhan.place_slice_order(security_id=security_id, exchange_segment=dhan.NSE_FNO, transaction_type=dhan.SELL, quantity=abs(net_quantity), order_type=dhan.MARKET, product_type=product_type, price=0, validity='DAY')
        time.sleep(1)
        
# dhan.place_slice_order(security_id='64208', exchange_segment=dhan.NSE_FNO, transaction_type=dhan.SELL, quantity=390, order_type=dhan.LIMIT, product_type=dhan.MARGIN, price=490, validity='DAY')