import redis
import json


class RedisClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._redis_client = redis.Redis(host='localhost', port=6379, db=0)
        return cls._instance

    @property
    def redis_client(self):
        return self._redis_client


class RollingRedisQueue:
    def __init__(self, key, max_size):
        self.redis_client = RedisClient().redis_client
        self.key = key
        self.max_size = max_size

    def enqueue(self, data):
        if self.redis_client.llen(self.key) >= self.max_size:
            self.redis_client.lpop(self.key)  # Remove the oldest element if queue is full
        self.redis_client.rpush(self.key, json.dumps(data, default=str))  # Append new data

    def dequeue(self):
        return self.redis_client.lpop(self.key)

    def fetch_queue(self):
        return [json.loads(data) for data in self.redis_client.lrange(self.key, 0, -1)]

    def get_size(self):
        return self.redis_client.llen(self.key)

    def key_exists(self):
        return self.redis_client.exists(self.key)

    def get_last(self):
        return self.redis_client.lindex(self.key, -1)

    def delete_key(self):
        self.redis_client.delete(self.key)

class RedisMap:
    def __init__(self):
        self.redis_client = RedisClient().redis_client

    def set(self, key, value):
        # Retrieve the existing JSON value from Redis
        existing_json_value = self.redis_client.get(key)
        if existing_json_value:
            existing_value = json.loads(existing_json_value)
        else:
            existing_value = {}

        # Merge the new value with the existing value
        existing_value.update(value)

        # Convert the merged value to a JSON string
        json_value = json.dumps(existing_value, default=str)

        # Set the key in Redis with the merged JSON value
        self.redis_client.set(key, json_value)

    def get(self, key):
        # Retrieve the value from Redis
        json_value = self.redis_client.get(key)
        if json_value is not None:
            # Decode the JSON value
            value = json.loads(json_value)
            if key == 'tick_map_data':
                keys_to_change = list(value.keys())

                # Iterate over the keys to convert string keys to integers
                for key in keys_to_change:
                    # Check if the key is a string representation of an integer
                    if key.isdigit():
                        # Convert the key to an integer and update the dictionary
                        value[int(key)] = value[key]
                        # Delete the original string key
                        del value[key]

                    # del value[i]
            return value
        else:
            return None