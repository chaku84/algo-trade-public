from django.db import models
from simple_history.models import HistoricalRecords

import json

# Create your models here.


class TelegramMessage(models.Model):
    message_id = models.TextField()
    text = models.TextField()
    created_at_time = models.DateTimeField()

    class Meta:
        app_label = 'trading'
        indexes = [
            models.Index(fields=['created_at_time'])
        ]


class TelegramTrade(models.Model):
    index_name = models.TextField()
    index_strike_price = models.IntegerField()
    option_type = models.TextField()
    expiry = models.TextField()
    entry_start_price = models.FloatField()
    entry_end_price = models.FloatField(null=True)
    exit_first_target_price = models.FloatField()
    exit_second_target_price = models.FloatField(null=True)
    exit_third_target_price = models.FloatField(null=True)
    exit_stop_loss_price = models.FloatField()
    quantity = models.IntegerField(default=50)
    created_at_time = models.DateTimeField()
    order_status = models.TextField()
    order_id = models.TextField(null=True)
    metadata = models.TextField(null=True)
    entry_type = models.TextField(null=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Round each float field to 1 decimal place
        if self.entry_start_price is not None:
            self.entry_start_price = round(self.entry_start_price, 1)
        if self.entry_end_price is not None:
            self.entry_end_price = round(self.entry_end_price, 1)
        if self.exit_first_target_price is not None:
            self.exit_first_target_price = round(self.exit_first_target_price, 1)
        if self.exit_second_target_price is not None:
            self.exit_second_target_price = round(self.exit_second_target_price, 1)
        if self.exit_third_target_price is not None:
            self.exit_third_target_price = round(self.exit_third_target_price, 1)
        if self.exit_stop_loss_price is not None:
            self.exit_stop_loss_price = round(self.exit_stop_loss_price, 1)

        # Call the parent class's save method to save the rest of the fields
        super(TelegramTrade, self).save(*args, **kwargs)


    def pre_save(self):
        # Exclude 'metadata' field from history
        super().pre_save()

        # Create a copy of the object without the 'metadata' field
        self._meta.history_manager.create(
            history_id=self.pk,
            history_type='-',
            **{field.attname: getattr(self, field.attname) for field in self._meta.fields if field.name != 'metadata'}
        )

    def get_metadata_as_dict(self):
        if self.metadata is None:
            return None
        return json.loads(self.metadata)

    def set_metadata_from_dict(self, metadata_dict):
        self.metadata = json.dumps(metadata_dict, default=str)


class EntryType(models.Model):
    entry_type = models.TextField()


class UserLogin(models.Model):
    id = models.CharField(primary_key=True, max_length=36)
    email = models.EmailField()
    name = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    user_name = models.CharField(max_length=255)
    role = models.CharField(max_length=255, null=True)  # Assuming role can be nullable

    class Meta:
        # Specify the existing table name
        db_table = 'user_login'


class CombinedUserTrade(models.Model):
    created_at_time = models.DateTimeField()
    index_name = models.TextField()
    index_strike_price = models.IntegerField()
    option_type = models.TextField()
    expiry = models.TextField()
    transaction_type = models.TextField()
    inst_token = models.IntegerField(null=True)
    # entry_price = models.IntegerField()
    # exit_target_price = models.IntegerField()
    # exit_stop_loss_price = models.IntegerField()
    # quantity = models.IntegerField(default=50)
    order_status = models.TextField()
    order_id = models.TextField(null=True)
    metadata = models.TextField(null=True)
    entry_type = models.TextField(null=True)
    history = HistoricalRecords()
    # child_trade is a sell transaction type trade and parent_trade is a but transaction type trade
    child_trade = models.OneToOneField('CombinedUserTrade', related_name='parent_trade', null=True, blank=True, on_delete=models.DO_NOTHING)

    class Meta:
        # Specify the custom table name
        db_table = 'combined_user_trade'

    def pre_save(self):
        # Exclude 'metadata' field from history
        super().pre_save()

        # Create a copy of the object without the 'metadata' field
        self._meta.history_manager.create(
            history_id=self.pk,
            history_type='-',
            **{field.attname: getattr(self, field.attname) for field in self._meta.fields if field.name != 'metadata'}
        )

    def get_metadata_as_dict(self):
        if self.metadata is None:
            return None
        return json.loads(self.metadata)

    def set_metadata_from_dict(self, metadata_dict):
        self.metadata = json.dumps(metadata_dict, default=str)

    # def get_user_trades(self):
    #     # Returns a list of UserTrade instances associated with this CombinedTrade
    #     return list(self.user_trades_1.all()) + list(self.user_trades_2.all())



class UserTrade(models.Model):
    created_at_time = models.DateTimeField()
    updated_at_time = models.DateTimeField()
    updated_by = models.TextField()
    username = models.TextField()
    index_name = models.TextField()
    index_strike_price = models.IntegerField()
    option_type = models.TextField()
    expiry = models.TextField()
    inst_token = models.IntegerField(null=True)
    # entry_price = models.IntegerField()
    # exit_target_price = models.IntegerField()
    # exit_stop_loss_price = models.IntegerField()
    # quantity = models.IntegerField(default=50)
    order_status = models.TextField()
    order_id = models.TextField(null=True)
    metadata = models.TextField(null=True)
    entry_type = models.TextField(null=True)
    # combined_user_trade = models.ForeignKey(CombinedUserTrade, on_delete=models.DO_NOTHING)
    combined_user_trade = models.ForeignKey(CombinedUserTrade, related_name='user_trades', null=True, on_delete=models.DO_NOTHING)
    # combined_user_trade_2 = models.ForeignKey(CombinedUserTrade, related_name='user_trades_2', null=True, on_delete=models.DO_NOTHING)
    history = HistoricalRecords()

    class Meta:
        # Specify the custom table name
        db_table = 'user_trade'

    def pre_save(self):
        # Exclude 'metadata' field from history
        super().pre_save()

        # Create a copy of the object without the 'metadata' field
        self._meta.history_manager.create(
            history_id=self.pk,
            history_type='-',
            **{field.attname: getattr(self, field.attname) for field in self._meta.fields if field.name != 'metadata'}
        )

    def get_metadata_as_dict(self):
        if self.metadata is None:
            return None
        return json.loads(self.metadata)

    def set_metadata_from_dict(self, metadata_dict):
        self.metadata = json.dumps(metadata_dict, default=str)


class Funds(models.Model):
    id = models.CharField(primary_key=True, max_length=36)
    created_at = models.DateTimeField()
    created_by = models.CharField(max_length=255, null=True)
    updated_at = models.DateTimeField()
    updated_by = models.CharField(max_length=255, null=True)
    available_cash = models.FloatField(null=True)
    available_margin = models.FloatField(null=True)
    used_margin = models.FloatField(null=True)
    user_login = models.ForeignKey(UserLogin, on_delete=models.CASCADE, related_name='funds', null=True)
    investment_amount_per_year = models.FloatField(null=True)
    risk_percentage = models.FloatField(null=True)

    class Meta:
        db_table = 'funds'

