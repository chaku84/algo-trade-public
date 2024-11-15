# Generated by Django 4.2.10 on 2024-03-26 11:11

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('trading', '0006_entrytype_historicaltelegramtrade_entry_type_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CombinedUserTrade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at_time', models.DateTimeField()),
                ('index_name', models.TextField()),
                ('index_strike_price', models.IntegerField()),
                ('option_type', models.TextField()),
                ('expiry', models.TextField()),
                ('inst_token', models.IntegerField(null=True)),
                ('order_status', models.TextField()),
                ('order_id', models.TextField()),
                ('metadata', models.TextField(null=True)),
                ('entry_type', models.TextField(null=True)),
            ],
            options={
                'db_table': 'combined_user_trade',
            },
        ),
        migrations.CreateModel(
            name='UserLogin',
            fields=[
                ('id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('name', models.CharField(max_length=255)),
                ('password', models.CharField(max_length=255)),
                ('user_name', models.CharField(max_length=255)),
                ('role', models.CharField(max_length=255, null=True)),
            ],
            options={
                'db_table': 'user_login',
            },
        ),
        migrations.CreateModel(
            name='UserTrade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at_time', models.DateTimeField()),
                ('updated_at_time', models.DateTimeField()),
                ('updated_by', models.TextField()),
                ('username', models.TextField()),
                ('index_name', models.TextField()),
                ('index_strike_price', models.IntegerField()),
                ('option_type', models.TextField()),
                ('expiry', models.TextField()),
                ('inst_token', models.IntegerField(null=True)),
                ('order_status', models.TextField()),
                ('order_id', models.TextField()),
                ('metadata', models.TextField(null=True)),
                ('entry_type', models.TextField(null=True)),
                ('combined_user_trade', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='trading.combinedusertrade')),
            ],
            options={
                'db_table': 'user_trade',
            },
        ),
        migrations.CreateModel(
            name='HistoricalUserTrade',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('created_at_time', models.DateTimeField()),
                ('updated_at_time', models.DateTimeField()),
                ('updated_by', models.TextField()),
                ('username', models.TextField()),
                ('index_name', models.TextField()),
                ('index_strike_price', models.IntegerField()),
                ('option_type', models.TextField()),
                ('expiry', models.TextField()),
                ('inst_token', models.IntegerField(null=True)),
                ('order_status', models.TextField()),
                ('order_id', models.TextField()),
                ('metadata', models.TextField(null=True)),
                ('entry_type', models.TextField(null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('combined_user_trade', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='trading.combinedusertrade')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical user trade',
                'verbose_name_plural': 'historical user trades',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalCombinedUserTrade',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('created_at_time', models.DateTimeField()),
                ('index_name', models.TextField()),
                ('index_strike_price', models.IntegerField()),
                ('option_type', models.TextField()),
                ('expiry', models.TextField()),
                ('inst_token', models.IntegerField(null=True)),
                ('order_status', models.TextField()),
                ('order_id', models.TextField()),
                ('metadata', models.TextField(null=True)),
                ('entry_type', models.TextField(null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical combined user trade',
                'verbose_name_plural': 'historical combined user trades',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='Funds',
            fields=[
                ('id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField()),
                ('created_by', models.CharField(max_length=255, null=True)),
                ('updated_at', models.DateTimeField()),
                ('updated_by', models.CharField(max_length=255, null=True)),
                ('available_cash', models.FloatField(null=True)),
                ('available_margin', models.FloatField(null=True)),
                ('used_margin', models.FloatField(null=True)),
                ('investment_amount_per_year', models.FloatField(null=True)),
                ('risk_percentage', models.FloatField(null=True)),
                ('user_login', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='funds', to='trading.userlogin')),
            ],
            options={
                'db_table': 'funds',
            },
        ),
    ]
