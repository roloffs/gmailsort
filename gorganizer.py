#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

import sys
import json
import argparse
import argcomplete
import textwrap

from argparse import RawTextHelpFormatter
from gmail import gmail


def __wrap(text, width):
    return '\n'.join(['\n'.join(textwrap.wrap(p, width)) for p in text.split('\n')])


def wrap_long(text):
    return __wrap(text, 80)


def wrap_short(text):
    return __wrap(text, 56)


def cmd_analyze_messages(args):
    profile = args.profile
    src_label = args.src_label
    dst_label = args.dst_label
    include_domains = args.include
    exclude_domains = args.exclude
    verbosity = args.verbose
    create_labels = args.create_labels

    try:
        (creds, err) = gmail.authenticate(profile)
        if err:
            sys.exit(1)
        (userdata, err) = gmail.synchronize(creds, profile)
        if err:
            sys.exit(1)
        # Label existency check
        if src_label and not gmail.label_exists(userdata, src_label):
            print(f'Label \'{src_label}\' does not exist')
            sys.exit(1)
        domains = gmail.partition_messages_by_sender_domain(userdata, src_label)

        if include_domains:
            print(f'Only process {len(include_domains)} domains: {include_domains}')
            tmp_domains = dict()
            for domain in include_domains:
                if domain in domains:
                    tmp_domains[domain] = domains[domain]
                else:
                    print(f'Domain \'{domain}\' not found, ignore')
            domains = tmp_domains

        if exclude_domains:
            print(f'Process all except {len(exclude_domains)} domains: {exclude_domains}')
            for domain in exclude_domains:
                if domain in domains:
                    del domains[domain]
                else:
                    print(f'Domain \'{domain}\' not found, ignore')

        dst_label_str = f'under \'{dst_label}\'' if dst_label else 'top level'
        print(f'{len(domains)} envisaged labels {dst_label_str}')

        # Print results
        get_domain_str = lambda domain: f'{dst_label}/{domain}' if dst_label else f'{domain}'
        if verbosity > 0:
            for domain, fq_domains in sorted(domains.items()):
                print(get_domain_str(domain))
                if verbosity > 1:
                    for fq_domain, messages in sorted(fq_domains.items()):
                        print(f'    {fq_domain}: {len(messages)} messages')
                        if verbosity > 2:
                            for message in messages:
                                if verbosity == 3:
                                    print(f'        {message["snippet"]}')
                                else:
                                    print(json.dumps(message, indent=2, ensure_ascii=False, sort_keys=True))

        # Create labels
        if create_labels:
            print('Create labels')
            if dst_label and not gmail.create_labels(creds, userdata, [dst_label]):
                sys.exit(1)
            label_names = list()
            for domain in sorted(domains.keys()):
                label_names.append(get_domain_str(domain))
            if not gmail.create_labels(creds, userdata, label_names):
                sys.exit(1)

    except KeyboardInterrupt as err:
        print()
        sys.exit(1)


def cmd_find_labels(args):
    profile = args.profile
    src_label = args.src_label
    dst_label = args.dst_label
    include_domains = args.include
    exclude_domains = args.exclude
    verbosity = args.verbose
    modify_messages = args.modify_messages

    try:
        (creds, err) = gmail.authenticate(profile)
        if err:
            sys.exit(1)
        (userdata, err) = gmail.synchronize(creds, profile)
        if err:
            sys.exit(1)
        # Label existency check
        for label in [src_label, dst_label]:
            if label and not gmail.label_exists(userdata, label):
                print(f'Label \'{label}\' does not exist')
                sys.exit(1)
        domains = gmail.partition_messages_by_sender_domain(userdata, src_label)

        if include_domains:
            print(f'Only process {len(include_domains)} domains: {include_domains}')
            tmp_domains = dict()
            for domain in include_domains:
                if domain in domains:
                    tmp_domains[domain] = domains[domain]
                else:
                    print(f'Domain \'{domain}\' not found, ignore')
            domains = tmp_domains

        if exclude_domains:
            print(f'Process all except {len(exclude_domains)} domains: {exclude_domains}')
            for domain in exclude_domains:
                if domain in domains:
                    del domains[domain]
                else:
                    print(f'Domain \'{domain}\' not found, ignore')

        dst_label_str = f'from \'{dst_label}\'' if dst_label else 'top level'
        print(f'Find labels for {len(domains)} domains {dst_label_str}')

        # Find matching labels for sender domains (only checks last label component)
        found_labels = gmail.find_labels_by_suffix(userdata, domains.keys(), dst_label)

        # Print results
        get_domain_str = lambda domain: f'{src_label}/{domain}' if src_label else f'{domain}'
        if verbosity > 0:
            for domain in sorted(domains.keys()):
                if verbosity == 1 or verbosity > 2:
                    if found_labels[domain]:
                        print(get_domain_str(domain))
                        for label in sorted(found_labels[domain], key=lambda lbl: lbl['name']):
                            print(f'    {label["name"]}')
                if verbosity == 2 or verbosity > 2:
                    if not found_labels[domain]:
                        print(get_domain_str(domain))
                        print('    no label found')

        # Modify message labels
        if modify_messages:
            print('Modify messages')
            for domain, fq_domains in sorted(domains.items()):
                print(f'{get_domain_str(domain)}: ', end='')
                if len(found_labels[domain]) == 1:
                    # Merge messages from domain into single list
                    messages = []
                    list(map(messages.extend, fq_domains.values()))

                    # Partition messages by labels being sublabel of the source label
                    label_ids = gmail.partition_messages_by_prefix(userdata, messages, src_label)

                    # Add and remove message labels
                    add_label_id = found_labels[domain][0]['id']
                    for rm_label_id, messages in label_ids.items():
                        # Ignore removing and adding the same label
                        if rm_label_id == add_label_id:
                            print(f'removing and adding the same label, ignore: \'{userdata.labels[add_label_id]["name"]}\'')
                            continue
                        rm_label_ids = [rm_label_id] if rm_label_id else []
                        rm_label_str = f', remove label \'{userdata.labels[rm_label_id]["name"]}\'' if rm_label_id else ''
                        print(f'modify messages, add label \'{userdata.labels[add_label_id]["name"]}\'{rm_label_str}')
                        if not gmail.modify_message_labels(creds, messages, [add_label_id], rm_label_ids):
                            sys.exit(1)

                else:
                    if len(found_labels[domain]) == 0:
                        print('no labels found, ignore')

                    elif len(found_labels[domain]) > 1:
                        labels = list(map(lambda lbl: lbl['name'], found_labels[domain]))
                        print(f'multiple labels found, ignore: {sorted(labels)}')

    except KeyboardInterrupt as err:
        print()
        sys.exit(1)


def main() -> None:
    # General arguments
    parser = argparse.ArgumentParser(
        description=wrap_long('Organize gmail messages by sender domains. Local profiles are used to store gmail access tokens and message data. Each new profile requires a login at gmail and to fetch all message header data, which might take a while. After the initial message data download, automatic synchronization is done.'),
        formatter_class=RawTextHelpFormatter
    )
    cmd_parser = parser.add_subparsers(
        dest='command',
        required=True
    )
    parser.add_argument('-p', '--profile',
        metavar='NAME',
        help=wrap_short(f'profile name to store gmail access token and message data under \'{gmail.get_profile_dir()}\''),
        required=True
    )

    # analyze-command arguments
    analyze_parser = cmd_parser.add_parser('analyze',
        help=wrap_short('analyze messages (and create labels on demand)'),
        description=wrap_long('Analyzes the sender email addresses of messages specified by a given source label and extracts their domain names (e.g., name@info.[example].com). It then allows to create labels named by these domains.'),
        formatter_class=RawTextHelpFormatter
    )
    analyze_parser.add_argument('-s', '--src-label',
        metavar='LABEL',
        help=wrap_short('only analyze messages from this label excluding SPAM, SENT, and DRAFT (if not specified, all messages are analyzed excluding SPAM, SENT, and DRAFT)')
    )
    analyze_parser.add_argument('-d', '--dst-label',
        metavar='LABEL',
        help=wrap_short('resulting labels are created under this label (if not specified, labels are created top level)')
    )
    analyze_group = analyze_parser.add_mutually_exclusive_group()
    analyze_group.add_argument('-i', '--include',
        metavar='DOMAIN',
        help=wrap_short('only process these domains (if not specified, all domains are processed)'),
        action='append',
        default=[]
    )
    analyze_group.add_argument('-e', '--exclude',
        metavar='DOMAIN',
        help=wrap_short('process all domains except these (if not specified, all domains are processed)'),
        action='append',
        default=[]
    )
    analyze_parser.add_argument('-v', '--verbose',
        help=wrap_short('print details about analysis result (v: label names, vv: fully qualified domain names, vvv: message snippets, vvvv: message data)'),
        action='count',
        default=0
    )
    analyze_parser.add_argument('-c', '--create-labels',
        help=wrap_short('resulting labels are actually created (modifies gmail data)'),
        action='store_true'
    )
    analyze_parser.set_defaults(func=cmd_analyze_messages)

    # find-command arguments
    find_parser = cmd_parser.add_parser('find',
        help=wrap_short('find labels (and modify messages on demand)'),
        description=wrap_long('Analyzes the sender domains of messages specified by a given source label and looks for labels matching these domains. It then allows to modify the labels of the messages according to the search result, i.e., adding the domain label and removing a possible source label.'),
        formatter_class=RawTextHelpFormatter
    )
    find_parser.add_argument('-s', '--src-label',
        metavar='LABEL',
        help=wrap_short('only analyze messages from this label excluding SPAM, SENT, and DRAFT (if not specified, all messages are analyzed excluding SPAM, SENT, and DRAFT)')
    )
    find_parser.add_argument('-d', '--dst-label',
        metavar='LABEL',
        help=wrap_short('look for labels from this label (if not specified, labels are looked up top level)')
    )
    find_group = find_parser.add_mutually_exclusive_group()
    find_group.add_argument('-i', '--include',
        metavar='DOMAIN',
        help=wrap_short('only process these domains (if not specified, all domains are processed)'),
        action='append',
        default=[]
    )
    find_group.add_argument('-e', '--exclude',
        metavar='DOMAIN',
        help=wrap_short('process all domains except these (if not specified, all domains are processed)'),
        action='append',
        default=[]
    )
    find_parser.add_argument('-v', '--verbose',
        help=wrap_short('print details about search result (v: only domains with found labels, vv: only domains with no labels found, vvv: both)'),
        action='count',
        default=0
    )
    find_parser.add_argument('-m', '--modify-messages',
        help=wrap_short('message labels are actually modified (modifies gmail data)'),
        action='store_true'
    )
    find_parser.set_defaults(func=cmd_find_labels)

    # Enable autocompletion
    argcomplete.autocomplete(parser)
    # Parse arguments and dispatch command
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
