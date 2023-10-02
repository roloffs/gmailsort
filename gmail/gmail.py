import os
import re
import json
import pickle
import tldextract

from json.decoder import JSONDecodeError

from . import gmail_api


class UserData:
    def __init__(self, messages, history_id):
        self.messages = messages
        self.history_id = history_id
        self.labels = None


PROFILE_DIR = ".profiles"


def get_profile_dir(profile_name=""):
    return os.path.join(PROFILE_DIR, profile_name)


def authenticate(profile_name):
    profile_path = os.path.join(PROFILE_DIR, profile_name)
    token_path = os.path.join(profile_path, "token.json")
    return gmail_api.authenticate(token_path, "credentials.json")


def synchronize(creds, profile_name):
    profile_path = os.path.join(PROFILE_DIR, profile_name)
    userdata_path = os.path.join(profile_path, "userdata.pickle")
    print(f"Synchronize local database with Gmail [{userdata_path}]")
    (profile, err) = gmail_api.get_profile(creds)
    if err:
        return (None, True)
    history_id = profile["historyId"]

    # Load userdata for profile (messages, history_id)
    if os.path.exists(userdata_path):
        with open(userdata_path, "rb") as db:
            userdata = pickle.load(db)

        # Fetch history difference from last sync
        if history_id > userdata.history_id:
            (history_items, err) = gmail_api.get_history_items(
                creds, userdata.history_id
            )
            if err:
                return (None, True)
            messages_updated_ids = set()
            messages_deleted_ids = set()
            get_message_id = lambda msg: msg["message"]["id"]
            for history_item in history_items:
                messages_updated_ids.update(
                    set(
                        map(
                            get_message_id,
                            history_item.get("messagesAdded", []),
                        )
                    )
                )
                messages_updated_ids.update(
                    set(
                        map(get_message_id, history_item.get("labelsAdded", []))
                    )
                )
                messages_updated_ids.update(
                    set(
                        map(
                            get_message_id,
                            history_item.get("labelsRemoved", []),
                        )
                    )
                )
                messages_deleted_ids.update(
                    set(
                        map(
                            get_message_id,
                            history_item.get("messagesDeleted", []),
                        )
                    )
                )
            # Do not fetch messages that will be deleted anyway
            messages_updated_ids = messages_updated_ids.difference(
                messages_deleted_ids
            )
            (messages_updated, err) = gmail_api.get_messages(
                creds, messages_updated_ids
            )
            if err:
                return (None, True)
            for message in messages_updated:
                userdata.messages[message["id"]] = message
            for message_id in messages_deleted_ids:
                # SPAM or TRASH messages are not stored in userdata, but
                # can occur in history items
                if message_id in userdata.messages:
                    del userdata.messages[message_id]
            userdata.history_id = history_id

    else:
        print(
            "No local database found: download all messages from Gmail [create"
            f" '{userdata_path}']"
        )
        # Fetch messages and history_id from remote
        (message_ids, err) = gmail_api.get_message_ids(creds)
        if err:
            return (None, True)
        (messages, err) = gmail_api.get_messages(creds, message_ids)
        if err:
            return (None, True)
        messages = dict(map(lambda msg: (msg["id"], msg), messages))
        userdata = UserData(messages, history_id)

    # Store userdata for profile
    os.makedirs(os.path.dirname(userdata_path), exist_ok=True)
    with open(userdata_path, "wb") as db:
        pickle.dump(userdata, db)

    # Always fetch labels, since changes are not reflected in history
    (labels, err) = gmail_api.get_labels(creds)
    if err:
        return (None, True)
    userdata.labels = dict(map(lambda lbl: (lbl["id"], lbl), labels))

    return (userdata, False)


def __label_exists(label_name, labels):
    label_name_tokens = list(filter(None, label_name.lower().split("/")))
    for label in labels.values():
        if label_name_tokens == list(
            filter(None, label["name"].lower().split("/"))
        ):
            return True
    return False


def __is_sublabel(label_name, sublabel_name):
    label_tokens = list(filter(None, label_name.lower().split("/")))
    sublabel_tokens = list(filter(None, sublabel_name.lower().split("/")))
    if len(sublabel_tokens) < len(label_tokens):
        return False
    for i in range(len(label_tokens)):
        if label_tokens[i] != sublabel_tokens[i]:
            return False
    return True


def __get_message_labels_by_prefix(message, labels, prefix):
    msg_labels = list()
    for label_id in message.get("labelIds", []):
        label = labels[label_id]
        if prefix and __is_sublabel(prefix, label["name"]):
            msg_labels.append(label)
    return msg_labels


def __include_messages(messages, labels, label_names):
    # Filter out non-existing labels
    tmp_label_names = list()
    for label_name in label_names:
        if __label_exists(label_name, labels):
            tmp_label_names.append(label_name)
        else:
            print(f"Label '{label_name}' does not exist, ignore")
    label_names = tmp_label_names

    # Include messages by label name (case-insensitive)
    msgs = list()
    for message in messages:
        for label_name in label_names:
            if __get_message_labels_by_prefix(message, labels, label_name):
                break
        else:
            continue
        msgs.append(message)
    return msgs


def __exclude_messages(messages, labels, label_names):
    # Filter out non-existing labels
    tmp_label_names = list()
    for label_name in label_names:
        if __label_exists(label_name, labels):
            tmp_label_names.append(label_name)
        else:
            print(f"Label '{label_name}' does not exist, ignore")
    label_names = tmp_label_names

    # Exclude messages by label name (case-insensitive)
    msgs = list()
    for message in messages:
        for label_name in label_names:
            if __get_message_labels_by_prefix(message, labels, label_name):
                break
        else:
            msgs.append(message)
    return msgs


def __get_sender_address(message):
    for header in message.get("payload", {}).get("headers", {}):
        if header["name"].lower() == "from":
            from_value = header["value"].lower()
            # First, check for email addresses in angle brackets
            match = re.findall("<([^<>]*@[^<>]*)>", from_value)
            if match:
                return match[-1]
            else:
                # Second, check for regular email addresses
                match = re.findall("[^<>]*@[^<>]*", from_value)
                if match:
                    return match[-1]
                else:
                    return None
    return None


def partition_messages_by_sender_domain(userdata, dst_label_name):
    labels = userdata.labels
    messages = userdata.messages.values()

    # Filter messages according to label
    if dst_label_name:
        messages = __include_messages(messages, labels, [dst_label_name])

    # Filter out messages from draft, sent, and chats
    messages = __exclude_messages(messages, labels, ["DRAFT", "SENT", "CHAT"])

    if dst_label_name:
        print(
            f"Analyze sender email addresses of {len(messages)} messages from"
            f" '{dst_label_name}'"
        )
    else:
        print(f"Analyze sender email addresses of all {len(messages)} messages")

    # Partition messages by fully qualified sender domain names
    fq_domains = dict()
    for message in messages:
        sender_address = __get_sender_address(message)
        if sender_address:
            # Extract fully qualified domain name (name@[info.example.com])
            fq_domain = sender_address.split("@")[-1]
            if fq_domain not in fq_domains:
                fq_domains[fq_domain] = list()
            fq_domains[fq_domain].append(message)
        else:
            message_str = json.dumps(
                message, indent=2, ensure_ascii=False, sort_keys=True
            )
            print(f"No sender address found in message, ignore:\n{message_str}")

    # Partition fully qualified domain names by domain names
    domains = dict()
    for fq_domain, messages in fq_domains.items():
        # Extract domain name (name@info.[example].com)
        domain = tldextract.extract(fq_domain).domain
        if domain not in domains:
            domains[domain] = dict()
        domains[domain][fq_domain] = messages

    print(f"Analysis resulted in {len(domains)} sender domains")
    return domains


def label_exists(userdata, label_name):
    return __label_exists(label_name, userdata.labels)


def create_labels(creds, userdata, label_names):
    labels = userdata.labels
    for label_name in label_names:
        if __label_exists(label_name, labels):
            print(f"Label '{label_name}' already exists, ignore")
        else:
            (label, err) = gmail_api.create_label(creds, label_name)
            if err:
                return False
    return True


def find_labels_by_suffix(userdata, label_names, dst_label_name):
    labels = userdata.labels

    # Filter out labels not being sublabel of the specified label
    tmp_labels = list()
    for label in labels.values():
        if not dst_label_name or __is_sublabel(dst_label_name, label["name"]):
            tmp_labels.append(label)
    labels = tmp_labels

    found_labels = dict()
    for label_name in label_names:
        found_labels[label_name] = list()
        for label in labels:
            # Only compare last label component
            last_component = label["name"].lower().split("/")[-1]
            if last_component == label_name.lower():
                found_labels[label_name].append(label)
            elif label_name.lower() in last_component:
                print(
                    f"Found unexact label match for '{label_name.lower()}':"
                    f" '{label['name']}'"
                )

    return found_labels


def partition_messages_by_prefix(userdata, messages, dst_label_name):
    # Create dict with label ids (strings) as keys and lists of messages
    # as values (the empty string as key is a collector for messages
    # with invalid label matches)
    labels = userdata.labels
    label_ids = dict()
    for message in messages:
        msg_labels = __get_message_labels_by_prefix(
            message, labels, dst_label_name
        )
        label_id = msg_labels[0]["id"] if len(msg_labels) == 1 else ""
        if label_id not in label_ids:
            label_ids[label_id] = list()
        label_ids[label_id].append(message)
    return label_ids


def modify_message_labels(creds, messages, add_label_ids, remove_label_ids):
    message_ids = list(map(lambda msg: msg["id"], messages))
    return gmail_api.modify_message_labels(
        creds, message_ids, add_label_ids, remove_label_ids
    )


def execute(creds, line):
    # Parse command line
    words = line.split()
    if len(words) < 1:
        return (None, True)
    cmd = words[0]
    args = dict()
    for word in words[1:]:
        tokens = list(filter(None, word.split("=")))
        if len(tokens) != 2:
            print(f"Wrong argument syntax: '{word}', needs to be <arg>=<value>")
            return (None, True)
        arg = tokens[0]
        value = tokens[1]
        try:
            json_value = json.loads(value)
        except JSONDecodeError as err:
            # Try again to parse argument value with added quotes
            try:
                json_value = json.loads('"' + value + '"')
            except JSONDecodeError as err:
                print(
                    f"Wrong argument value: '{value}', needs to be valid json"
                )
                return (None, True)
        args[arg] = json_value
    calls = cmd.split("_")
    if len(calls) < 1:
        return (None, True)
    return gmail_api.execute_api_call(creds, calls, args)
