import logging
import bisect
from datetime import datetime, timedelta

from trading.helpers import get_ist_datetime, get_nearest_tens
from trading.strategies.exit import Exit


class DiscountedExit(Exit):
    def __init__(self, entry_obj=None):
        super().__init__(entry_obj)
        self.logger = logging.getLogger(__name__)
