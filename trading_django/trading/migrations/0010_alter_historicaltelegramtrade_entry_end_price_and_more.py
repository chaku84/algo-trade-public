# Generated by Django 4.2.10 on 2024-08-09 04:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trading', '0009_alter_combinedusertrade_order_id_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicaltelegramtrade',
            name='entry_end_price',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='historicaltelegramtrade',
            name='entry_start_price',
            field=models.FloatField(),
        ),
        migrations.AlterField(
            model_name='historicaltelegramtrade',
            name='exit_first_target_price',
            field=models.FloatField(),
        ),
        migrations.AlterField(
            model_name='historicaltelegramtrade',
            name='exit_second_target_price',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='historicaltelegramtrade',
            name='exit_stop_loss_price',
            field=models.FloatField(),
        ),
        migrations.AlterField(
            model_name='historicaltelegramtrade',
            name='exit_third_target_price',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='telegramtrade',
            name='entry_end_price',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='telegramtrade',
            name='entry_start_price',
            field=models.FloatField(),
        ),
        migrations.AlterField(
            model_name='telegramtrade',
            name='exit_first_target_price',
            field=models.FloatField(),
        ),
        migrations.AlterField(
            model_name='telegramtrade',
            name='exit_second_target_price',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='telegramtrade',
            name='exit_stop_loss_price',
            field=models.FloatField(),
        ),
        migrations.AlterField(
            model_name='telegramtrade',
            name='exit_third_target_price',
            field=models.FloatField(null=True),
        ),
    ]