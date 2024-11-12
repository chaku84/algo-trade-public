import jwt
import bcrypt
import requests
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from datetime import datetime, timedelta
from trading.models import UserLogin

User = get_user_model()


class MySQLAuthBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None):
        try:
            user = UserLogin.objects.get(user_name=username)
            if bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
                return user
        except ObjectDoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return UserLogin.objects.get(pk=user_id)
        except UserLogin.DoesNotExist:
            return None


def generate_jwt_token(user):
    payload = {
        'user_id': user.pk,
        'username': user.user_name,
        'exp': datetime.utcnow() + timedelta(days=1)  # Token expiry time
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')


def validate_jwt_token(token):
    try:
        if token.startswith('Bearer='):
            token = token[7:]
        # print(token)
        # payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
        # payload = jwt.decode(token, algorithms=["none"], verify=False)
        # print("is_token_expired: {}".format(is_token_expired(payload)))
        # if not is_token_expired(payload):
        #     username = payload['sub']
        #     print("username: {}".format(username))
        #     user = UserLogin.objects.get(user_name=username)
        #     return user
        url = "http://localhost:8080/userDetails/"

        payload = ""
        headers = {'Authorization': 'Bearer=%s' % token}

        response = requests.request("GET", url, headers=headers, data=payload)

        response_json = json.loads(response.text)
        print(response_json['userName'])
        return response_json['userName']

    except Exception as e:
        print(str(e))
        return None


def is_token_expired(payload):
    expiration_time = payload.get('exp')
    if expiration_time:
        expiration_datetime = datetime.utcfromtimestamp(expiration_time)
        return expiration_datetime < datetime.utcnow()
    return False
