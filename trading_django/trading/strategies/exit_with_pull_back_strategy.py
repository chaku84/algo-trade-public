import logging
import bisect
import traceback
import time
from datetime import datetime, timedelta

from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.strategies.instant_exit import InstantExit


class ExitWithPullBackStrategy(InstantExit):
    def __init__(self, entry_obj=None):
        super().__init__(entry_obj)
        self.logger = logging.getLogger(__name__)
