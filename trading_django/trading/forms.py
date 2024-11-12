from django import forms
from django.conf import settings
import logging
logger = logging.getLogger(__name__)


class TaskSchedulerForm(forms.Form):
    interval_in_seconds = forms.IntegerField(required=True)
    task_schedule_name = forms.CharField(required=True)
    task_path = forms.CharField(required=True)
    start_time = forms.DateTimeField(required=True)
    # "2023-01-15T14:30:00Z"
    # datetime(2023, 1, 15, 14, 30, 0).isoformat() + "Z"
    # YYYY-MM-DDTHH:MM:SS.sssZ


class OrdersPlacementForm(forms.Form):
    stopLossPercentage = forms.FloatField(required=True)
    stopLossPrice = forms.FloatField(required=True)
    entryStartPrice = forms.FloatField(required=True)
    entryEndPrice = forms.FloatField(required=False)
    targetMap = forms.JSONField(required=True)
    quantityShareMap = forms.JSONField(required=True)
    trailingStopLossMap = forms.JSONField(required=True)
    optionFormDetail = forms.JSONField(required=True)
    risk = forms.FloatField(required=True)