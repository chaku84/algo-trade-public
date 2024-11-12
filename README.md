# algo-trade


### Program Flow (Code Entry Point: restart_celery_task.sh)
1. restart_celery_task.sh => kills existing tasks
2. Hits restart endpoint in django server
3. Django server - uses 'tasks.py' file to spin new celery workers
4. Inside tasks.py => "update_kite_ticks", "execute_trades"
5. "update_kite_ticks" => Objective is to keep prices updated in redis (kite_tick_updater.py::KiteTickUpdater::on_ticks)
6. "execute_traders" => kite_manager.py::KiteManager::execute_trades_util: Every sec evaluates market and entry/exit can happen
7a. Entry.py =>  check_entry_criteria_and_update_metadata_and_status: Checks if entry criteria if fulfilled 
7b. Entry.py => Once entry criteria is fulfilled => calculate quantity based on risk and price (entry.py::Entry::process_quantities)
8a. Exit => Check exit criteria from entry itself (stop loss/ profit targets should be pre-determined)
8b. Exit.py => "update_targets_status_and_trail_stop_loss" => process exits on the basis of pre-determined stop loss/profit targets


### Known Issues in code
1. If number of instrument > 100 => message drops are happening => leading to stale prices
