"""Convenience wrapper for the Gmail API client library"""
from __future__ import print_function

import html
import os
import random
import time
from multiprocessing.pool import ThreadPool
from socket import timeout
from threading import Lock
from typing import Any, Dict

import ftfy
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2.error import ServerNotFoundError
from progress.bar import Bar

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
    """Customized bar implementation"""

    suffix = (
        "%(index)d/%(max)d (%(percent).1f%%) - %(hours)dh:%(mins)dm:%(secs)ds"
    )

    @property
    def hours(self):
        """Hours format"""
        return self.eta // 3600

    @property
    def mins(self):
        """Minutes format"""
        return (self.eta - self.hours * 3600) // 60

    @property
    def secs(self):
        """Seconds format"""
        return self.eta - self.hours * 3600 - self.mins * 60


def __http_error(err):
    print(f"HTTP error returned by Gmail: {err.reason}")


def __auth_error(err):
    print(f"Authentication error at Gmail: {err}")


def __connection_error(err):
    print(f"Connection error: {err}")


def __execute(creds, func) -> Dict[str, Any]:
    service = build("gmail", "v1", credentials=creds)
    # The attribute 'user' is dynamically added to the object 'service'
    # and thus not known to pylint
    # pylint: disable=no-member
    response = func(service.users).execute()
    if not response:
        return {}
    for key, value in response.items():
        response[key] = __fix_strings(value)
    return response


def __fix_strings(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            obj[key] = __fix_strings(value)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            obj[index] = __fix_strings(value)
    elif isinstance(obj, str):
        obj = ftfy.fix_text(html.unescape(obj))
    return obj


def authenticate(token_file, credentials_file):
    creds = None
    # The file token.json stores the user's access and refresh tokens,
    # and is created automatically when the authorization flow completes
    # for the first time.
    print(f"Authenticate at Gmail with token [{token_file}]")
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
                f"No valid token found: login at Gmail [create '{token_file}']"
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
        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
    return (creds, False)


def get_profile(creds):
    try:
        response = __execute(
            creds, lambda users: users().getProfile(userId="me")
        )
    except HttpError as err:
        __http_error(err)
        return ({}, True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return ({}, True)
    return (response, False)


def get_message_ids(creds):
    # Get number of total messages (does not include TRASH and SPAM)
    (profile, err) = get_profile(creds)
    if err:
        return ([], True)
    num_messages = profile["messagesTotal"]
    if not num_messages:
        return ([], False)

    # Download messages ids (cannot be processed in parallel due to
    # page-based processing)
    messages_ids = []
    print("Get message ids ...")
    with MyBar("Downloading", max=num_messages) as mybar:
        page_token = ""
        while True:
            try:
                response = __execute(
                    creds,
                    lambda users: users()
                    .messages()
                    .list(
                        userId="me",
                        maxResults=MAX_RESULTS,
                        pageToken=page_token,
                        # includeSpamTrash='true'
                    ),
                )
            except HttpError as err:
                __http_error(err)
                return ([], True)
            except ServerNotFoundError as err:
                __connection_error(err)
                return ([], True)
            messages = response.get("messages", [])
            messages = list(map(lambda msg: msg["id"], messages))
            messages_ids.extend(messages)
            mybar.next(len(messages))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    return (messages_ids, False)


def get_messages(creds, message_ids):
    if not message_ids:
        return ([], False)

    # Download message data
    messages = []
    print("Get message data ...")
    with MyBar("Downloading", max=len(message_ids)) as mybar:
        lock = Lock()

        def body(message_id):
            error = None
            for num_retries in range(MAX_RETRIES + 1):
                if num_retries > 0:
                    # Delay task after communication failure
                    # (exponential backoff)
                    sleep_time = random.random() * 2**num_retries
                    time.sleep(sleep_time)

                try:
                    response = __execute(
                        creds,
                        lambda users: users()
                        .messages()
                        .get(
                            userId="me",
                            id=message_id,
                            format="metadata",
                            metadataHeaders=["From", "Subject"],
                        ),
                    )
                except HttpError as err:
                    error = err
                    # HTTP status code 403: quota of queries per minute
                    # exceeded, retry
                    if err.status_code == 403:
                        continue
                    # HTTP status code 404: element not found, continue
                    # without element
                    if err.status_code == 404:
                        response = {}
                    else:
                        break
                except (ServerNotFoundError, timeout) as err:
                    error = err
                    # Network or socket error, retry
                    continue

                error = None
                with lock:
                    if response:
                        messages.append(response)
                    mybar.next()
                break

            if error:
                raise error

        with ThreadPool(16) as pool:
            try:
                pool.map(body, message_ids)
            except HttpError as err:
                __http_error(err)
                return ([], True)
            except (ServerNotFoundError, timeout) as err:
                __connection_error(err)
                return ([], True)
    return (messages, False)


def get_history_items(creds, start_history_id):
    # Download history items (cannot be processed in parallel due to
    # page-based processing)
    history_items = []
    page_token = ""
    print(f"Get history items since history id {start_history_id} ...")
    while True:
        try:
            # Does include TRASH and SPAM
            response = __execute(
                creds,
                lambda users: users()
                .history()
                .list(
                    userId="me",
                    maxResults=MAX_RESULTS,
                    pageToken=page_token,
                    startHistoryId=start_history_id,
                ),
            )
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
    print("Get labels ...")
    try:
        response = __execute(
            creds, lambda users: users().labels().list(userId="me")
        )
    except HttpError as err:
        __http_error(err)
        return ([], True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return ([], True)
    labels = response.get("labels", [])
    return (labels, False)


def create_label(creds, label_name):
    print(f"Create label '{label_name}' ...")
    try:
        response = __execute(
            creds,
            lambda users: users()
            .labels()
            .create(userId="me", body={"name": label_name}),
        )
    except HttpError as err:
        __http_error(err)
        return ({}, True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return ({}, True)
    return (response, False)


def modify_message_labels(creds, message_ids, add_label_ids, remove_label_ids):
    if not message_ids:
        return True

    # Partition message ids into chunks of maximum batch-processible
    # size
    msg_id_chunks = [
        message_ids[i : i + MAX_BATCH_SIZE]
        for i in range(0, len(message_ids), MAX_BATCH_SIZE)
    ]

    # Modify message labels
    print(f"Modify labels of {len(message_ids)} messages ...")
    for msg_ids in msg_id_chunks:
        try:
            # Response is ignored, since it only returns an empty body
            # on success
            __execute(
                creds,
                lambda users: users()
                .messages()
                .batchModify(
                    userId="me",
                    body={
                        # The lambda function is called at the time of
                        # the function call '__execute', so no issues
                        # with the loop variable used in the lambda
                        # pylint: disable=cell-var-from-loop
                        "ids": msg_ids,
                        "addLabelIds": add_label_ids,
                        "removeLabelIds": remove_label_ids,
                    },
                ),
            )
        except HttpError as err:
            __http_error(err)
            return False
        except ServerNotFoundError as err:
            __connection_error(err)
            return False
    return True


def execute_api_call(creds, calls, args):
    def body(resource):
        for call in calls:
            if not hasattr(resource(), call):
                raise ValueError(call)
            resource = getattr(resource(), call)
        return resource(userId="me", **args)

    try:
        response = __execute(creds, body)
    except HttpError as err:
        __http_error(err)
        return ({}, True)
    except ServerNotFoundError as err:
        __connection_error(err)
        return ({}, True)
    except ValueError as err:
        print(f"Unknown command: '{err}'")
        return ({}, True)
    except TypeError as err:
        print(err)
        return ({}, True)
    return (response, False)
