import os
import base64
import re
import smtplib
import json
import traceback
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.message import EmailMessage
from email import encoders
from email import message_from_bytes


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime

from trading.helpers import get_ist_datetime, get_nearest_tens


# Define the necessary scopes and API version
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
API_VERSION = 'v1'
ab_library_app_pwd = 'xxx'

class GmailService(object):
    def __init__(self):
        self.sent_message_id_set = set()

    def create_gmail_service(self):
        # If you have a service account JSON key file, use it to authenticate
        # service_account_credentials = ServiceAccountCredentials.from_service_account_file('/Users/chandack/Documents/algo-trade/tips/client_secret_853669071670-gtv2m20tst5b842ou0gjgdabkfjbpe8c.apps.googleusercontent.com.json', scopes=SCOPES)
        # service_account_credentials = service_account_credentials.with_subject('chandan5284ssb@gmail.com')

        credentials = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        # tokens_file_path = '/home/ec2-user/services/algo-trade/trading_django/tips/tokens.json'
        # client_secret_path = '/home/ec2-user/services/algo-trade/trading_django/tips/client_secret_853669071670-tqkm24gv6tptbhd97g2cngggqpiearu4.apps.googleusercontent.com.json'

        tokens_file_path = '/Users/chandack/Documents/algo-trade/trading_django/tips/tokens.json'
        client_secret_path = '/Users/chandack/Documents/algo-trade/trading_django/tips/client_secret_853669071670-tqkm24gv6tptbhd97g2cngggqpiearu4.apps.googleusercontent.com.json'

        # tokens_file_path = '/Users/chandack/Downloads/tokens.json'
        # client_secret_path = '/Users/chandack/Downloads/client_secret_1052463768751-8jgo87kojocesvfadoiui54ssfsbjsnn.apps.googleusercontent.com.json'
        if os.path.exists(tokens_file_path):
            credentials = Credentials.from_authorized_user_file(tokens_file_path, SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
                credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(tokens_file_path, 'w') as token:
                token.write(credentials.to_json())
        # Use user credentials (OAuth2)
        # flow = InstalledAppFlow.from_client_secrets_file('/Users/chandack/Documents/algo-trade/tips/client_secret_853669071670-tqkm24gv6tptbhd97g2cngggqpiearu4.apps.googleusercontent.com.json', SCOPES)
        # credentials = flow.run_local_server(port=0)

        # Build the Gmail service
        service = build('gmail', API_VERSION, credentials=credentials)
        return service
    
    def create_ablibrary_gmail_service(self):
        # If you have a service account JSON key file, use it to authenticate
        # service_account_credentials = ServiceAccountCredentials.from_service_account_file('/Users/chandack/Documents/algo-trade/tips/client_secret_853669071670-gtv2m20tst5b842ou0gjgdabkfjbpe8c.apps.googleusercontent.com.json', scopes=SCOPES)
        # service_account_credentials = service_account_credentials.with_subject('chandan5284ssb@gmail.com')

        credentials = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        # tokens_file_path = '/home/ec2-user/services/algo-trade/trading_django/tips/ablibrary_tokens.json'
        # client_secret_path = '/home/ec2-user/services/algo-trade/trading_django/tips/client_secret_1052463768751-8jgo87kojocesvfadoiui54ssfsbjsnn.apps.googleusercontent.com.json'

        tokens_file_path = '/Users/chandack/Documents/algo-trade/trading_django/tips/ablibrary_tokens.json'
        client_secret_path = '/Users/chandack/Documents/algo-trade/trading_django/tips/client_secret_1052463768751-8jgo87kojocesvfadoiui54ssfsbjsnn.apps.googleusercontent.com.json'

        if os.path.exists(tokens_file_path):
            credentials = Credentials.from_authorized_user_file(tokens_file_path, SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
                credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(tokens_file_path, 'w') as token:
                token.write(credentials.to_json())
        # Use user credentials (OAuth2)
        # flow = InstalledAppFlow.from_client_secrets_file('/Users/chandack/Documents/algo-trade/tips/client_secret_853669071670-tqkm24gv6tptbhd97g2cngggqpiearu4.apps.googleusercontent.com.json', SCOPES)
        # credentials = flow.run_local_server(port=0)

        # Build the Gmail service
        service = build('gmail', API_VERSION, credentials=credentials)
        return service

    def list_messages(self, service, user_id='me', max_results=50):
        results = service.users().messages().list(userId=user_id, labelIds=['INBOX'], maxResults=max_results).execute()
        messages = results.get('messages', [])
        return messages

    def get_message(self, service, user_id='me', msg_id=''):
        message = service.users().messages().get(userId=user_id, id=msg_id).execute()
        return message

    def get_raw_message_decoded_data(self, service, user_id='me', msg_id=''):
        message = service.users().messages().get(userId=user_id, id=msg_id, format='raw').execute()

        raw_data = message['raw']

        decoded_data = str(base64.urlsafe_b64decode(raw_data).decode('utf-8'))

        # print(decoded_data)
        decoded_data = decoded_data.replace('=3D', '=').replace('=\r\n', '')
        return decoded_data

    def get_telegram_otp(self, otp_sent_timestamp=None):
        service = self.create_gmail_service()
        messages = self.list_messages(service)
        if not messages:
            print('No messages found.')
        else:
            print(len(messages))
            count = 0
            for message in messages:
                # print(message)
                msg = self.get_message(service, msg_id=message['id'])
                # print(msg)
                headers = msg['payload']['headers']
                subject = ''
                date = ''
                for header in headers:
                    if header['name'] == 'Subject':
                        subject = header['value']
                    if header['name'] == 'Date':
                        date = header['value']
                # print('Subject:', subject)
                # print('Date:', date)

                # Define the format of the input date string
                date_format = "%a, %d %b %Y %H:%M:%S"

                splitted_date = date.strip().split(' ')
                if len(splitted_date) > 5:
                    date = ' '.join(splitted_date[0:5])

                # Convert the date string to a datetime object
                datetime_object = datetime.strptime(date, date_format)

                # Get the timestamp (in seconds since the epoch)
                otp_received_timestamp = datetime_object.timestamp()

                if (otp_sent_timestamp is not None and otp_received_timestamp >= otp_sent_timestamp)\
                        or not otp_sent_timestamp:
                    subject = subject.lower()
                    if 'telegram otp' in subject:
                        otp = subject.split(':')[1].strip()
                        return otp

                count = count + 1
                if count >= 20:
                    break
        return '000000000000000'

    def send_email_using_smtp(self, email_message, subject):
        # if isinstance(decoded_data, bytes):
        #     decoded_data = decoded_data.decode('utf-8')
        # Replace with your email credentials and recipient
        smtp_server = 'smtp.gmail.com'
        smtp_port = 587
        sender_email = 'chandan5284ssb@gmail.com'
        password = 'xxx'

        # Create the email message
        # msg = MIMEText(decoded_data)
        # msg['Subject'] = f"Fwd: {subject}"
        # msg['From'] = sender_email
        # msg['To'] = receiver_email

        # Send the email
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, password)
                server.send_message(email_message)
                print("Email Sent successfully!")
        except Exception as e:
            print(f"Error: {e}")

    def forward_message(self, service, user_id, message_id, forward_to):
        # Get the message using the Gmail API in raw format
        message = service.users().messages().get(userId=user_id, id=message_id, format='raw').execute()
        raw_data = message['raw']
        decoded_data = str(base64.urlsafe_b64decode(raw_data).decode('utf-8'))

        # print(decoded_data)
        decoded_data = decoded_data.replace('=3D', '=').replace('=\r\n', '')
        # print(decoded_data)

        # Create a new email message
        msg = MIMEMultipart()
        msg['From'] = 'chandan5284ssb@gmail.com'  # Replace with your email
        msg['To'] = forward_to
        msg['Subject'] = 'Fwd: ' + message['snippet']

        # Attach the decoded email content as a MIMEBase part
        msg.attach(MIMEText(decoded_data, 'html'))

        # Send the multipart email
        self.send_email_using_smtp(msg, 'Fwd: ' + message['snippet'])

    def send_email(self, subject, email_content):
        try:
            # Create a new email message
            msg = MIMEMultipart()
            msg['From'] = 'chandan5284ssb@gmail.com'  # Replace with your email
            msg['To'] = 'chandan5284ssb@gmail.com'
            msg['Subject'] = subject
    
            # Attach the decoded email content as a MIMEBase part
            msg.attach(MIMEText(email_content, 'html'))
    
            # Send the multipart email
            self.send_email_using_smtp(msg, subject)
        except Exception as e:
            traceback.print_exc()
            print("Found Exception while sending email")

    def send_email_with_attachment(self, subject, body, file_path):
        try:
            # Email and attachment details
            sender_email = 'chandan5284ssb@gmail.com'
            receiver_email = 'chandan5284ssb@gmail.com'
            attachment_path = file_path
    
            # Create the email message
            message = MIMEMultipart()
            message['From'] = sender_email
            message['To'] = receiver_email
            message['Subject'] = subject
    
            # Add the body to the message
            message.attach(MIMEText(body, 'plain'))
    
            # Open the file to be sent as binary mode
            with open(attachment_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                # Encode the attachment in base64
                encoders.encode_base64(part)
                # Add header for the attachment
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename={attachment_path.split("/")[-1]}'
                )
                # Attach the part to the message
                message.attach(part)
    
            self.send_email_using_smtp(message, subject)
        except Exception as e:
            traceback.print_exc()
            print("Found Exception while sending email with attachment")

    def transfer_aws_dhan_messages(self):
        service = self.create_gmail_service()
        messages = self.list_messages(service, user_id='me', max_results=10)

        if not messages:
            print('No Email messages found.')
        else:
            print(len(messages))
            count = 0
            pattern = r"\d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}"
            for message in messages:
                # print(message)
                msg = self.get_message(service, msg_id=message['id'])
                # print(msg)
                headers = msg['payload']['headers']
                subject = ''
                date = ''
                for header in headers:
                    if header['name'] == 'Subject':
                        subject = header['value']
                    if header['name'] == 'Date':
                        date = header['value']
                # print('Subject:', subject)
                # print('Date:', date)

                # Convert the date string to a datetime object
                matches = re.findall(pattern, date)
                datetime_object = datetime.strptime(matches[0], '%d %b %Y %H:%M:%S')

                # Get the timestamp (in seconds since the epoch)
                otp_received_timestamp = datetime_object.timestamp()

                # ('amazon web services' in subject.lower() or 'dhan' in subject.lower())
                if ('amazon web services' in subject.lower()) and message['id'] not in self.sent_message_id_set:
                    print("Found Match")
                    self.forward_message(service, user_id='me', message_id=message['id'], forward_to='ablibraryhub@gmail.com')
                    self.sent_message_id_set.add(message['id'])

        return '000000000000000'

    def get_aws_hostname(self):
        service = self.create_ablibrary_gmail_service()
        messages = self.list_messages(service, user_id='me', max_results=50)

        if not messages:
            print('No Email messages found.')
        else:
            print(len(messages))
            count = 0
            pattern = r"\d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}"
            for message in messages:
                print(message)
                msg = self.get_message(service, msg_id=message['id'])
                # print(msg)
                headers = msg['payload']['headers']
                subject = ''
                date = ''
                for header in headers:
                    if header['name'] == 'Subject':
                        subject = header['value']
                    if header['name'] == 'Date':
                        date = header['value']
                print('Subject:', subject)
                print('Date:', date)

                # Convert the date string to a datetime object
                matches = re.findall(pattern, date)
                datetime_object = datetime.strptime(matches[0], '%d %b %Y %H:%M:%S')

                # Get the timestamp (in seconds since the epoch)
                otp_received_timestamp = get_ist_datetime(datetime_object)
                aws_hostname = None
                # try:
                #     if 'aws' in subject.lower() and 'host' in subject.lower() and 'ap-south-1.compute.amazonaws.com' in subject:
                #         aws_hostname = subject.split(':')[-1].strip().replace('/', '')
                #         print("Found AWS Hostname")
                #         return aws_hostname
                # except Exception as e:
                #     traceback.print_exc()
                #     return None
        return None

    def get_dhan_otp_util(self, otp_sent_timestamp=None, otp_type='Password'):
        service = self.create_ablibrary_gmail_service()
        messages = self.list_messages(service, user_id='me', max_results=5)

        if not messages:
            print('No Email messages found.')
        else:
            print(len(messages))
            count = 0
            pattern = r"\d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}"
            for message in messages:
                # print(message)
                msg = self.get_message(service, msg_id=message['id'])
                # print(msg)
                headers = msg['payload']['headers']
                subject = ''
                date = ''
                for header in headers:
                    if header['name'] == 'Subject':
                        subject = header['value']
                    if header['name'] == 'Date':
                        date = header['value']
                # print('Subject:', subject)
                # print('Date:', date)

                # Convert the date string to a datetime object
                matches = re.findall(pattern, date)
                datetime_object = datetime.strptime(matches[0], '%d %b %Y %H:%M:%S')

                # Get the timestamp (in seconds since the epoch)
                otp_received_timestamp = get_ist_datetime(datetime_object)
                
                # print(otp_sent_timestamp)
                # print(otp_received_timestamp)
                
                if (otp_sent_timestamp is not None
                    and otp_received_timestamp.timestamp() >= otp_sent_timestamp.timestamp()
                    and otp_type in subject) \
                        or not otp_sent_timestamp:
                    login_match = re.search(r'\b(\d{6})\b(?=.*OTP)', subject)
                    if login_match:
                        otp = login_match.group(1)
                        print(f"Extracted OTP: {otp}")
                        return otp
                    
                    if 'Dhan' in subject and 'Reset' in subject:
                        message_data = self.get_raw_message_decoded_data(service, user_id='me', msg_id=message['id'])
                        clean_text = re.sub(r'<.*?>', '', message_data)
                        otp_match = re.search(r'OTP\s+to\s+verify\s+your\s+request:\s*(\d+)', clean_text)
    
                        # Extract the OTP if a match is found
                        if otp_match:
                            otp = otp_match.group(1)
                            print(f"Extracted OTP: {otp}")
                            return otp
                        else:
                            print("No OTP found.")
                            return None
        return None
    
    def get_dhan_otp(self, otp_sent_timestamp=None, otp_type='Password'):
        retrial_count = 10
        otp = None
        while otp is None and retrial_count > 0:
            otp = self.get_dhan_otp_util(otp_sent_timestamp, otp_type)
            if otp is not None:
                break
            time.sleep(5)
            retrial_count -= 1
        return otp

    def test_func(self):
        raise ValueError("Testing value error exception!")

if __name__ == '__main__':
    gmail_service = GmailService()
    gmail_service.transfer_aws_dhan_messages()
    # gmail_service.get_dhan_otp()
    test_dict = [
        {"day_diff": -0.5, "start": "14:11", "end": "09:34", "minute_diff": 100}
    ]
    # gmail_service.send_email('Testing Dictionary', json.dumps(test_dict, indent=4))
    # gmail_service.send_email_with_attachment('Celery Worker Log', 'Please check celery Worker Log', 'celery_worker.log')
    # try:
    #     gmail_service.test_func()
    # except Exception as e:
    #     gmail_service.send_email('Testing Exception', traceback.format_exc())
    # get_telegram_otp()
    # gmail_service.get_aws_hostname()
