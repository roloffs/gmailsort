Introduction
------------

`gmailsort` is a simple Python script that uses the Gmail API to sort
your Gmail messages by sender domains. It allows you to automatically
create labels named by the sender domains of the analyzed messages and
then to sort the messages under these labels. This script does not
create Gmail filters, it just sorts your messages at the time of calling
it. In order to use this script and access your Gmail account via API,
you need to have a Google Cloud project. Detailed steps are described
below. Besides that, you just have to install the required Python
dependencies and call the script directly from the project directory.
Take a look at the help dialog of the script for more details about
command-line options.


Requirements to use Gmail API
-----------------------------

Google provides a central location to maintain your used APIs to access
Google services. In order to access the Gmail API, you have to do the
following steps:

1. Create a new [Google Cloud
   project](https://developers.google.com/workspace/guides/create-project).

1. Enable the [Gmail
   API](https://console.cloud.google.com/flows/enableapi?apiid=gmail.googleapis.com)
   for your project.

1. Add yourself as test user at the [OAuth consent
   screen](https://console.cloud.google.com/apis/credentials/consent).

1. Create [OAuth 2.0 client
   credentials](https://console.cloud.google.com/apis/credentials) for
   your project and store them under `credentials.json` in the project
   directory.

Install Python dependencies
---------------------------

```bash
pip install -r requirements.txt
```

Enable autocompletion (bash or zsh)
-----------------------------------

```bash
activate-global-python-argcomplete
eval "$(register-python-argcomplete gmailsort.py)"
```

Usage examples
--------------

1. To analyze the messages of your inbox with resepect to their sender
   domains and to see the envisaged label structure (without actually
   creating labels), call

    ```bash
    ./gmailsort.py -p user analyze -s INBOX -d test -v
    ```

    If this is called for the first time with the given profile name, a
    Gmail login dialog will open and you have to login and allow the app
    to access your messages. Afterwards, an initial message data
    download is issued. This will probably take several minutes
    depending on the amount of messages in your Gmail account. All
    subsequent calls will be much faster and just synchronize the
    differences between local and remote data.

    `INBOX` is a Gmail built-in label name for your inbox. User-defined
    labels can have any name except these and can be organized
    hierarchically. To name a hierarchical label, use a single string
    and separate the hierarchies with slashes, e.g., `foo/bar`.

    Specifying a destination label (as `test` in this case) is optional.
    Otherwise, labels will be created top level. If you are happy with
    the envisaged labels structure, you can actually create it by
    calling the command again and adding the command-line option `-l` or
    `--create-labels`.

1. To find labels matching the sender domains of your inbox messages
   (without modifying message labels), call

    ```bash
    ./gmailsort.py -p user find -s INBOX -v
    ```

    This will only show meaningful results if you have created labels
    with the `analyze` command or by hand beforehand.

    Matching is done by case insensitive name comparison, e.g., if your
    inbox contains multiple messages from the domain `foobar` and a
    label called `test/foobar` is existing, it will be displayed as
    matching target label. Only the lowest hierarchy level will be used
    for name comparision, i.e., a label called `foobar/test` will not be
    displayed as match.

    If the messages from each domain shall be sorted under their
    respective labels, just call the command again and add the
    command-line option `-m` or `--sort-messages`. If multiple labels
    match a domain such as `one/foobar` and `two/foobar`, you can use
    the destination label command-line option `-d` to restrict the
    search to be started at a specific label, e.g., `-d two` will only
    find the second label as single label.
