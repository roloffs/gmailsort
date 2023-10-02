from __future__ import print_function

import os
import time
import random
import ftfy
import html

from google.auth.transport.requests import Request
from google.auth.exceptions import GoogleAuthError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from multiprocessing.pool import ThreadPool
from threading import Lock
from progress.bar import Bar
from httplib2.error import ServerNotFoundError


# ------------------------------------------------------------------------------
# Gmail API Python quickstart:
# https://developers.google.com/gmail/api/quickstart/python
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Gmail API reference:
# https://developers.google.com/gmail/api/reference/rest
# ------------------------------------------------------------------------------


# Gmail API access rights
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Maximum results per page
MAX_RESULTS = 500

# Maximum number of messages to be processed in batch mode
MAX_BATCH_SIZE = 1000

# Maximum number of retries for message download
MAX_RETRIES = 10


class MyBar(Bar):
    suffix = (
        "%(index)d/%(max)d (%(percent).1f%%) - %(hours)dh:%(mins)dm:%(secs)ds"
    )

    @property
    def hours(self):
        return self.eta // 3600

    @property
    def mins(self):
        return (self.eta - self.hours * 3600) // 60

    @property
    def secs(self):
        return self.eta - self.hours * 3600 - self.mins * 60


def __http_error(err):
    print(f"HTTP error returned by gmail: {err.reason}")


def __auth_error(err):
    print(f"Authentication error at gmail: {err}")


def __connection_error(err):
    print(f"Connection error: {err}")


def __build_service(creds):
    return build("gmail", "v1", credentials=creds)


def __fix_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            obj[k] = __fix_strings(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            obj[i] = __fix_strings(v)
    elif isinstance(obj, str):
        obj = ftfy.fix_text(html.unescape(obj))
    return obj


def authenticate(token_file, credentials_file):
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    print(f"Authenticate at gmail with token [{token_file}]")
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except GoogleAuthError as err:
                __auth_error(err)
                return (None, True)
        else:
            print(
                f"No valid token found: login at gmail [create '{token_file}']"
            )
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES
            )
            try:
                creds = flow.run_local_server(port=0)
            except GoogleAuthError as err:
                __auth_error(err)
                return (None, True)
        # Save the credentials for the next run
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, "w") as token:
            token.write(creds.to_json())
    return (creds, False)


def get_profile(creds):
    service = __build_service(creds)
    try:
        response = service.users().getProfile(userId="me").execute()
        response = __fix_strings(response)
    except HttpError as err:
        __http_error(err)
        return (None, True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return (None, True)
    return (response, False)


def get_message_ids(creds):
    # Get number of total messages (does not include TRASH and SPAM)
    (profile, err) = get_profile(creds)
    if err:
        return ([], True)
    num_messages = profile["messagesTotal"]

    # Download messages ids (cannot be processed in parallel due to page-based processing)
    messages_ids = list()
    page_token = ""
    bar = MyBar("Downloading", max=num_messages)
    service = __build_service(creds)
    print(f"Get message ids ...")
    while True:
        try:
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=MAX_RESULTS,
                    pageToken=page_token,
                    # includeSpamTrash='true'
                )
                .execute()
            )
            response = __fix_strings(response)
        except HttpError as err:
            __http_error(err)
            return ([], True)
        except ServerNotFoundError as err:
            __connection_error(err)
            return ([], True)
        messages = response.get("messages", [])
        messages = list(map(lambda msg: msg["id"], messages))
        messages_ids.extend(messages)
        bar.next(len(messages))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    if num_messages > 0:
        bar.finish()
    return (messages_ids, False)


def get_messages(creds, message_ids):
    # Download message data
    lock = Lock()
    messages = list()
    bar = MyBar("Downloading", max=len(message_ids))

    def body(message_id):
        num_retries = 0
        while True:
            try:
                service = __build_service(creds)
                response = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject"],
                    )
                    .execute()
                )
                response = __fix_strings(response)
                with lock:
                    messages.append(response)
                    bar.next()
                break
            except (HttpError, ServerNotFoundError) as err:
                if num_retries < MAX_RETRIES:
                    num_retries += 1
                    # Delay task after communication failure (exponential backoff)
                    sleep_time = random.random() * 2**num_retries
                    time.sleep(sleep_time)
                else:
                    raise err

    print(f"Get message data ...")
    with ThreadPool(16) as pool:
        try:
            pool.map(body, message_ids)
        except HttpError as err:
            __http_error(err)
            return ([], True)
        except ServerNotFoundError as err:
            __connection_error(err)
            return ([], True)
    if len(message_ids) > 0:
        bar.finish()
    return (messages, False)


def get_history_items(creds, start_history_id):
    # Download history items (cannot be processed in parallel due to page-based processing)
    history_items = list()
    page_token = ""
    service = __build_service(creds)
    print(f"Get history items since history id {start_history_id} ...")
    while True:
        try:
            # Does include TRASH and SPAM
            response = (
                service.users()
                .history()
                .list(
                    userId="me",
                    maxResults=MAX_RESULTS,
                    pageToken=page_token,
                    startHistoryId=start_history_id,
                )
                .execute()
            )
            response = __fix_strings(response)
        except HttpError as err:
            __http_error(err)
            return ([], True)
        except ServerNotFoundError as err:
            __connection_error(err)
            return ([], True)
        history = response.get("history", [])
        history_items.extend(history)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return (history_items, False)


def get_labels(creds):
    service = __build_service(creds)
    print(f"Get labels ...")
    try:
        response = service.users().labels().list(userId="me").execute()
        response = __fix_strings(response)
    except HttpError as err:
        __http_error(err)
        return ([], True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return ([], True)
    labels = response.get("labels", [])
    return (labels, False)


def create_label(creds, label_name):
    service = __build_service(creds)
    print(f"Create label '{label_name}' ...")
    try:
        response = (
            service.users()
            .labels()
            .create(userId="me", body={"name": label_name})
            .execute()
        )
        response = __fix_strings(response)
    except HttpError as err:
        __http_error(err)
        return (None, True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return (None, True)
    return (response, False)


def modify_message_labels(creds, message_ids, add_label_ids, remove_label_ids):
    # Partition message ids into chunks of maximum batch-processible size
    msg_id_chunks = [
        message_ids[i : i + MAX_BATCH_SIZE]
        for i in range(0, len(message_ids), MAX_BATCH_SIZE)
    ]

    # Modify message labels
    service = __build_service(creds)
    print(f"Modify labels of {len(message_ids)} messages ...")
    for msg_ids in msg_id_chunks:
        try:
            # Response is ignored, since it only returns an empty body on success
            service.users().messages().batchModify(
                userId="me",
                body={
                    "ids": msg_ids,
                    "addLabelIds": add_label_ids,
                    "removeLabelIds": remove_label_ids,
                },
            ).execute()
        except HttpError as err:
            __http_error(err)
            return False
        except ServerNotFoundError as err:
            __connection_error(err)
            return False
    return True


def execute_api_call(creds, calls, args):
    service = __build_service(creds)
    resource = service.users
    for call in calls:
        if not hasattr(resource(), call):
            print(f"Unknown command: '{call}'")
            return (None, True)
        resource = getattr(resource(), call)
    response = None
    try:
        response = resource(userId="me", **args).execute()
        response = __fix_strings(response)
    except HttpError as err:
        __http_error(err)
        return (None, True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return (None, True)
    except TypeError as err:
        print(f"Incomplete command: '{calls}'")
        return (None, True)
    return (response, False)
