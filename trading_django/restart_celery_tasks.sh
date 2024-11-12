#!/bin/bash

# wget https://images.dhan.co/api-data/api-scrip-master.csv

touch /home/ec2-user/services/algo-trade/trading_django/celery_worker_$(date +%Y-%m-%d).log
mv /home/ec2-user/services/algo-trade/trading_django/celery_worker.log /home/ec2-user/services/algo-trade/trading_django/celery_worker_$(date +%Y-%m-%d).log
touch /home/ec2-user/services/algo-trade/trading_django/celery_worker.log

ps aux | grep chromedriver | awk '{print $2}' | xargs kill -9
lsof -t -i:9222| awk '{print $1}' | xargs kill -9
ps aux | grep python | awk '{print $2}' | xargs kill -9

sleep 5

cd /home/ec2-user/services/algo-trade/
source venv/bin/activate

cd trading_django
python3 manage.py runserver >> server.log 2>&1 &

sleep 10
# lsof -t -i:9223| awk '{print $1}' | xargs kill -9

curl --location --request POST 'localhost:8000/restart_schedule/' --data-raw ''

# sleep 180

# ps aux | grep chromedriver | awk '{print $2}' | xargs kill -9
# lsof -t -i:9222| awk '{print $1}' | xargs kill -9
# lsof -t -i:9223| awk '{print $1}' | xargs kill -9

# sleep 5

# cd /home/ec2-user/services/algo-trade/
# source venv/bin/activate

# cd trading_django
# python3 manage.py runserver >> server.log 2>&1 &

# sleep 10

# curl --location --request POST 'localhost:8000/restart_schedule/' --data-raw ''

# sleep 180

# ps aux | grep chromedriver | awk '{print $2}' | xargs kill -9
# lsof -t -i:9222| awk '{print $1}' | xargs kill -9
# lsof -t -i:9223| awk '{print $1}' | xargs kill -9

# sleep 5

# cd /home/ec2-user/services/algo-trade/
# source venv/bin/activate

# cd trading_django
# python3 manage.py runserver >> server.log 2>&1 &

# sleep 10

# curl --location --request POST 'localhost:8000/restart_schedule/' --data-raw ''

# sleep 180

# curl --location --request POST 'localhost:8000/restart_schedule/' --data-raw ''

# insert into trading_telegramtrade(id, index_name, index_strike_price, option_type, expiry, entry_start_price, exit_first_target_price, exit_stop_loss_price, created_at_time, order_id, order_status, quantity, metadata, entry_type) values('99999', 'BANKNIFTY', -1, 'PE', '21 AUG', -1, -1, -1, NOW(), '', 'ORDER_EXIT_EXECUTED_DHAN', 15, '{}', 'DHAN_PUT_SCALPER');