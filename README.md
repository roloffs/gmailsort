Introduction
------------

`gorganizer` is a simple python script that uses the gmail API to organize your gmail messages by sender domains. It allows you to automatically create labels named by the sender domains of the analyzed messages and then to sort the messages under these labels. This script does not create gmail filters, it just sorts your messages at the time of calling it. Just install the required python dependencies and call the script directly from the current directory. Take a look at the help dialog of the script for more details.

Install python dependencies
---------------------------

```bash
pip install -r requirements.txt
```

Enable autocompletion (bash or zsh)
-----------------------------------

```bash
activate-global-python-argcomplete && eval "$(register-python-argcomplete gorganizer.py)"
```

Usage examples
--------------

1. To analyze the messages of your inbox with resepect to their sender domains and to see the envisaged label structure (without actually creating labels), call

    ```bash
    ./gorganizer.py -p user analyze -s INBOX -d test -v
    ```

    If this is called for the first time with the given profile name, a gmail login dialog will open and you have to login and allow the app to access your messages. Afterwards, an initial message data download is issued. This will probably take several minutes depending on the amount of messages in your gmail account. All subsequent calls will be much faster and just synchronize the differences between local and remote data.

    `INBOX` is a gmail built-in label name for your inbox. User-defined labels can have any name except these and can be organized hierarchically. To name a hierarchical label, use a single string and separate the hierarchies with slashes, e.g., `foo/bar`.

    Specifying a destination label (as `test` in this case) is optional. Otherwise, labels will be created top level. If you are happy with the envisaged labels structure, you can actually create it by calling the command again and adding the command-line option `-c` or `--create-labels`.

1. To find labels matching the sender domains of your inbox messages (without modifying message labels), call

    ```bash
    ./gorganizer.py -p user find -s INBOX -v
    ```

    This will only show meaningful results if you have created labels with the `analyze` command or by hand beforehand.

    Matching is done by case insensitive name comparison, e.g., if your inbox contains multiple messages from the domain `foobar` and a label called `test/foobar` is existing, it will be displayed as matching target label. Only the lowest hierarchy level will be used for name comparision, i.e., a label called `foobar/test` will not be displayed as match.

    If the messages from each domain shall be sorted under their respective labels, just call the command again and add the command-line option `-m` or `--modify-messages`. If multiple labels match a domain such as `one/foobar` and `two/foobar`, you can use the destination label command-line option `-d` to restrict the search to be started at a specific label, e.g., `-d two` will only find the second label as single label.
