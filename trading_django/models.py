# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
# from django.db import models
#
#
# class SpringSession(models.Model):
#     primary_id = models.CharField(db_column='PRIMARY_ID', primary_key=True, max_length=36)  # Field name made lowercase.
#     session_id = models.CharField(db_column='SESSION_ID', unique=True, max_length=36)  # Field name made lowercase.
#     creation_time = models.BigIntegerField(db_column='CREATION_TIME')  # Field name made lowercase.
#     last_access_time = models.BigIntegerField(db_column='LAST_ACCESS_TIME')  # Field name made lowercase.
#     max_inactive_interval = models.IntegerField(db_column='MAX_INACTIVE_INTERVAL')  # Field name made lowercase.
#     expiry_time = models.BigIntegerField(db_column='EXPIRY_TIME')  # Field name made lowercase.
#     principal_name = models.CharField(db_column='PRINCIPAL_NAME', max_length=100, blank=True, null=True)  # Field name made lowercase.
#
#     class Meta:
#         managed = False
#         db_table = 'SPRING_SESSION'
#
#
# class SpringSessionAttributes(models.Model):
#     session_primary = models.OneToOneField(SpringSession, models.DO_NOTHING, db_column='SESSION_PRIMARY_ID', primary_key=True)  # Field name made lowercase. The composite primary key (SESSION_PRIMARY_ID, ATTRIBUTE_NAME) found, that is not supported. The first column is selected.
#     attribute_name = models.CharField(db_column='ATTRIBUTE_NAME', max_length=200)  # Field name made lowercase.
#     attribute_bytes = models.TextField(db_column='ATTRIBUTE_BYTES')  # Field name made lowercase.
#
#     class Meta:
#         managed = False
#         db_table = 'SPRING_SESSION_ATTRIBUTES'
#         unique_together = (('session_primary', 'attribute_name'),)
#
#
# class AuthGroup(models.Model):
#     name = models.CharField(unique=True, max_length=150)
#
#     class Meta:
#         managed = False
#         db_table = 'auth_group'
#
#
# class AuthGroupPermissions(models.Model):
#     id = models.BigAutoField(primary_key=True)
#     group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
#     permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)
#
#     class Meta:
#         managed = False
#         db_table = 'auth_group_permissions'
#         unique_together = (('group', 'permission'),)
#
#
# class AuthPermission(models.Model):
#     name = models.CharField(max_length=255)
#     content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
#     codename = models.CharField(max_length=100)
#
#     class Meta:
#         managed = False
#         db_table = 'auth_permission'
#         unique_together = (('content_type', 'codename'),)
#
#
# class AuthUser(models.Model):
#     password = models.CharField(max_length=128)
#     last_login = models.DateTimeField(blank=True, null=True)
#     is_superuser = models.IntegerField()
#     username = models.CharField(unique=True, max_length=150)
#     first_name = models.CharField(max_length=150)
#     last_name = models.CharField(max_length=150)
#     email = models.CharField(max_length=254)
#     is_staff = models.IntegerField()
#     is_active = models.IntegerField()
#     date_joined = models.DateTimeField()
#
#     class Meta:
#         managed = False
#         db_table = 'auth_user'
#
#
# class AuthUserGroups(models.Model):
#     id = models.BigAutoField(primary_key=True)
#     user = models.ForeignKey(AuthUser, models.DO_NOTHING)
#     group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
#
#     class Meta:
#         managed = False
#         db_table = 'auth_user_groups'
#         unique_together = (('user', 'group'),)
#
#
# class AuthUserUserPermissions(models.Model):
#     id = models.BigAutoField(primary_key=True)
#     user = models.ForeignKey(AuthUser, models.DO_NOTHING)
#     permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)
#
#     class Meta:
#         managed = False
#         db_table = 'auth_user_user_permissions'
#         unique_together = (('user', 'permission'),)
#
#
# class Course(models.Model):
#     course_id = models.CharField(primary_key=True, max_length=36)
#     created_at = models.DateTimeField()
#     created_by = models.CharField(max_length=255, blank=True, null=True)
#     updated_at = models.DateTimeField()
#     updated_by = models.CharField(max_length=255, blank=True, null=True)
#     description = models.CharField(max_length=5000, blank=True, null=True)
#     duration_in_weeks = models.IntegerField(blank=True, null=True)
#     name = models.CharField(max_length=255, blank=True, null=True)
#     offer_in_percentage = models.IntegerField(blank=True, null=True)
#     price_in_rupee = models.IntegerField(blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'course'
#
#
# class DjangoAdminLog(models.Model):
#     action_time = models.DateTimeField()
#     object_id = models.TextField(blank=True, null=True)
#     object_repr = models.CharField(max_length=200)
#     action_flag = models.PositiveSmallIntegerField()
#     change_message = models.TextField()
#     content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
#     user = models.ForeignKey(AuthUser, models.DO_NOTHING)
#
#     class Meta:
#         managed = False
#         db_table = 'django_admin_log'
#
#
# class DjangoCeleryBeatClockedschedule(models.Model):
#     clocked_time = models.DateTimeField()
#
#     class Meta:
#         managed = False
#         db_table = 'django_celery_beat_clockedschedule'
#
#
# class DjangoCeleryBeatCrontabschedule(models.Model):
#     minute = models.CharField(max_length=240)
#     hour = models.CharField(max_length=96)
#     day_of_week = models.CharField(max_length=64)
#     day_of_month = models.CharField(max_length=124)
#     month_of_year = models.CharField(max_length=64)
#     timezone = models.CharField(max_length=63)
#
#     class Meta:
#         managed = False
#         db_table = 'django_celery_beat_crontabschedule'
#
#
# class DjangoCeleryBeatIntervalschedule(models.Model):
#     every = models.IntegerField()
#     period = models.CharField(max_length=24)
#
#     class Meta:
#         managed = False
#         db_table = 'django_celery_beat_intervalschedule'
#
#
# class DjangoCeleryBeatPeriodictask(models.Model):
#     name = models.CharField(unique=True, max_length=200)
#     task = models.CharField(max_length=200)
#     args = models.TextField()
#     kwargs = models.TextField()
#     queue = models.CharField(max_length=200, blank=True, null=True)
#     exchange = models.CharField(max_length=200, blank=True, null=True)
#     routing_key = models.CharField(max_length=200, blank=True, null=True)
#     expires = models.DateTimeField(blank=True, null=True)
#     enabled = models.IntegerField()
#     last_run_at = models.DateTimeField(blank=True, null=True)
#     total_run_count = models.PositiveIntegerField()
#     date_changed = models.DateTimeField()
#     description = models.TextField()
#     crontab = models.ForeignKey(DjangoCeleryBeatCrontabschedule, models.DO_NOTHING, blank=True, null=True)
#     interval = models.ForeignKey(DjangoCeleryBeatIntervalschedule, models.DO_NOTHING, blank=True, null=True)
#     solar = models.ForeignKey('DjangoCeleryBeatSolarschedule', models.DO_NOTHING, blank=True, null=True)
#     one_off = models.IntegerField()
#     start_time = models.DateTimeField(blank=True, null=True)
#     priority = models.PositiveIntegerField(blank=True, null=True)
#     headers = models.TextField()
#     clocked = models.ForeignKey(DjangoCeleryBeatClockedschedule, models.DO_NOTHING, blank=True, null=True)
#     expire_seconds = models.PositiveIntegerField(blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'django_celery_beat_periodictask'
#
#
# class DjangoCeleryBeatPeriodictasks(models.Model):
#     ident = models.SmallIntegerField(primary_key=True)
#     last_update = models.DateTimeField()
#
#     class Meta:
#         managed = False
#         db_table = 'django_celery_beat_periodictasks'
#
#
# class DjangoCeleryBeatSolarschedule(models.Model):
#     event = models.CharField(max_length=24)
#     latitude = models.DecimalField(max_digits=9, decimal_places=6)
#     longitude = models.DecimalField(max_digits=9, decimal_places=6)
#
#     class Meta:
#         managed = False
#         db_table = 'django_celery_beat_solarschedule'
#         unique_together = (('event', 'latitude', 'longitude'),)
#
#
# class DjangoContentType(models.Model):
#     app_label = models.CharField(max_length=100)
#     model = models.CharField(max_length=100)
#
#     class Meta:
#         managed = False
#         db_table = 'django_content_type'
#         unique_together = (('app_label', 'model'),)
#
#
# class DjangoMigrations(models.Model):
#     id = models.BigAutoField(primary_key=True)
#     app = models.CharField(max_length=255)
#     name = models.CharField(max_length=255)
#     applied = models.DateTimeField()
#
#     class Meta:
#         managed = False
#         db_table = 'django_migrations'
#
#
# class DjangoSession(models.Model):
#     session_key = models.CharField(primary_key=True, max_length=40)
#     session_data = models.TextField()
#     expire_date = models.DateTimeField()
#
#     class Meta:
#         managed = False
#         db_table = 'django_session'
#
#
# class Funds(models.Model):
#     id = models.CharField(primary_key=True, max_length=36)
#     created_at = models.DateTimeField()
#     created_by = models.CharField(max_length=255, blank=True, null=True)
#     updated_at = models.DateTimeField()
#     updated_by = models.CharField(max_length=255, blank=True, null=True)
#     available_cash = models.FloatField(blank=True, null=True)
#     available_margin = models.FloatField(blank=True, null=True)
#     used_margin = models.FloatField(blank=True, null=True)
#     user_login = models.ForeignKey('UserLogin', models.DO_NOTHING, blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'funds'
#
#
# class Payment(models.Model):
#     id = models.CharField(primary_key=True, max_length=36)
#     created_at = models.DateTimeField()
#     created_by = models.CharField(max_length=255, blank=True, null=True)
#     updated_at = models.DateTimeField()
#     updated_by = models.CharField(max_length=255, blank=True, null=True)
#     amount_in_paise = models.IntegerField()
#     payment_signature = models.CharField(max_length=255, blank=True, null=True)
#     payment_status = models.CharField(max_length=255)
#     razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)
#     razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
#     transaction_type = models.CharField(max_length=255, blank=True, null=True)
#     user_login = models.ForeignKey('UserLogin', models.DO_NOTHING, blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'payment'
#
#
# class RegisteredCourse(models.Model):
#     registered_course_id = models.CharField(primary_key=True, max_length=36)
#     created_at = models.DateTimeField()
#     created_by = models.CharField(max_length=255, blank=True, null=True)
#     updated_at = models.DateTimeField()
#     updated_by = models.CharField(max_length=255, blank=True, null=True)
#     completion_in_weeks = models.IntegerField(blank=True, null=True)
#     completion_percentage = models.IntegerField(blank=True, null=True)
#     payment_payment_id = models.CharField(max_length=36, blank=True, null=True)
#     course_course = models.ForeignKey(Course, models.DO_NOTHING)
#     student_student = models.ForeignKey('Student', models.DO_NOTHING)
#     payment = models.ForeignKey(Payment, models.DO_NOTHING, blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'registered_course'
#
#
# class Student(models.Model):
#     student_id = models.CharField(primary_key=True, max_length=36)
#     created_at = models.DateTimeField()
#     created_by = models.CharField(max_length=255, blank=True, null=True)
#     updated_at = models.DateTimeField()
#     updated_by = models.CharField(max_length=255, blank=True, null=True)
#     contact_no = models.CharField(max_length=255, blank=True, null=True)
#     email = models.CharField(max_length=255, blank=True, null=True)
#     name = models.CharField(max_length=255)
#     user_id = models.CharField(max_length=36, blank=True, null=True)
#     username = models.CharField(max_length=255, blank=True, null=True)
#     highest_qualification = models.CharField(max_length=255, blank=True, null=True)
#     stream = models.CharField(max_length=255, blank=True, null=True)
#     address = models.CharField(max_length=255, blank=True, null=True)
#     role = models.CharField(max_length=255, blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'student'
#
#
# class SubscriptionPlan(models.Model):
#     id = models.CharField(primary_key=True, max_length=36)
#     duration_in_months = models.FloatField()
#     offer_in_percentage = models.FloatField()
#     plan_type = models.CharField(max_length=255, blank=True, null=True)
#     price = models.FloatField()
#
#     class Meta:
#         managed = False
#         db_table = 'subscription_plan'
#
#
# class UserLogin(models.Model):
#     id = models.CharField(primary_key=True, max_length=36)
#     email = models.CharField(max_length=255, blank=True, null=True)
#     name = models.CharField(max_length=255)
#     password = models.CharField(max_length=255)
#     user_name = models.CharField(max_length=255)
#     role = models.CharField(max_length=255, blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'user_login'
#
#
# class UserLoginDetails(models.Model):
#     id = models.CharField(primary_key=True, max_length=36)
#     active = models.TextField()  # This field type is a guess.
#     password = models.CharField(max_length=255, blank=True, null=True)
#     roles = models.CharField(max_length=255, blank=True, null=True)
#     user_name = models.CharField(max_length=255, blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'user_login_details'
#
#
# class UserSubscription(models.Model):
#     id = models.CharField(primary_key=True, max_length=36)
#     created_at = models.DateTimeField()
#     created_by = models.CharField(max_length=255, blank=True, null=True)
#     updated_at = models.DateTimeField()
#     updated_by = models.CharField(max_length=255, blank=True, null=True)
#     payment = models.ForeignKey(Payment, models.DO_NOTHING, blank=True, null=True)
#     subscription_plan = models.ForeignKey(SubscriptionPlan, models.DO_NOTHING, blank=True, null=True)
#     user_login = models.ForeignKey(UserLogin, models.DO_NOTHING, blank=True, null=True)
#
#     class Meta:
#         managed = False
#         db_table = 'user_subscription'
