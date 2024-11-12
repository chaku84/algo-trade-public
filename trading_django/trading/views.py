import json
import copy
from django.shortcuts import render
from django.http import JsonResponse

# from django_celery_beat.models import PeriodicTask, IntervalSchedule
from django.views import View
from trading.forms import TaskSchedulerForm, OrdersPlacementForm
# from trading.trading_manager import TradingManager
from trading.scheduler_manager import SchedulerManager
from trading.authentication import validate_jwt_token
from trading.kite_manager import KiteManager
from trading.user_trading_manager import UserTradingManager

from trading.constants import GLOBAL_API_RESPONSE

# Create your views here.


class TaskScheduler(View):
    # @method_decorator(permission_required('ATLAS_ASSET_DECOMMISSION_WRITE'))
    def post(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        form_data = json.loads(request.body)
        form = TaskSchedulerForm(form_data)
        if form.is_valid():
            payload = form.cleaned_data
            if SchedulerManager().schedule_task(payload):
                response['success'] = True
                response['message'] = 'Task Scheduled successfully!'
                response['data'] = {}
            else:
                response['success'] = False
                response['message'] = 'Task could not be scheduled.'
        else:
            response['success'] = False
            response['message'] = 'Error with form validation, check the params!'

        return JsonResponse(response)

    def get(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        params = request.GET.dict()
        task_name = params.get('task_name', None)
        response = SchedulerManager().get_scheduled_tasks(name=task_name)
        return JsonResponse(response)

    def delete(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        params = request.GET.dict()
        task_name = params.get('task_name', None)
        response = SchedulerManager().delete_scheduled_task(task_name)
        return JsonResponse(response)


class RestartTaskScheduler(View):
    # @method_decorator(permission_required('ATLAS_ASSET_DECOMMISSION_WRITE'))
    def post(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        if SchedulerManager().reschedule_task():
            response['success'] = True
            response['message'] = 'Task Rescheduled successfully!'
            response['data'] = {}
        else:
            response['success'] = False
            response['message'] = 'Task could not be rescheduled.'

        return JsonResponse(response)


class OrdersView(View):
    def get(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        params = request.GET.dict()
        headers = request.headers
        auth_token = headers.get('Authorization', None)
        user = validate_jwt_token(auth_token)
        response = UserTradingManager().get_orders(user)
        return JsonResponse(response)

    def post(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        params = request.GET.dict()
        headers = request.headers
        auth_token = headers.get('Authorization', None)
        user = validate_jwt_token(auth_token)
        form_data = json.loads(request.body)
        form = OrdersPlacementForm(form_data)
        if user is None:
            response['success'] = False
            response['message'] = 'User Not Authenticated!'
        elif form.is_valid():
            payload = form.cleaned_data
            response = UserTradingManager().place_order(user, payload)
        else:
            response['success'] = False
            response['message'] = 'Error with form validation, check the params!'

        return JsonResponse(response)


class PositionsView(View):
    def get(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        params = request.GET.dict()
        response = SchedulerManager().get_scheduled_tasks(name=task_name)
        return JsonResponse(response)
    
    def post(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        form_data = json.loads(request.body)
        form = TaskSchedulerForm(form_data)
        if form.is_valid():
            payload = form.cleaned_data
            if SchedulerManager().schedule_task(payload):
                response['success'] = True
                response['message'] = 'Task Scheduled successfully!'
                response['data'] = {}
            else:
                response['success'] = False
                response['message'] = 'Task could not be scheduled.'
        else:
            response['success'] = False
            response['message'] = 'Error with form validation, check the params!'

        return JsonResponse(response)


class InstrumentsView(View):
    def get(self, request, *args, **kwargs):
        response = copy.copy(GLOBAL_API_RESPONSE)
        params = request.GET.dict()
        response = KiteManager().get_inst_details()
        return JsonResponse(response)