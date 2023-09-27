import os
import atexit
import readline


class HistoryCompleter(object):
    def __init__(self, cmds):
        self.matches = []
        for cmd in sorted(cmds):
            readline.add_history(cmd)

    def complete(self, text, state):
        response = None
        if state == 0:
            history_values = [readline.get_history_item(i) for i in range(1, readline.get_current_history_length() + 1)]
            if text:
                self.matches = sorted(h for h in history_values if h and h.startswith(text))
            else:
                self.matches = []
        try:
            response = self.matches[state]
        except IndexError:
            response = None
        return response


def init(histfile_dir):
    histfile_path = os.path.join(histfile_dir, 'history.txt')
    print(f'Load command history [{histfile_path}]')
    readline.parse_and_bind('tab: complete')
    readline.read_init_file(os.path.expanduser('~/.inputrc'))
    readline.set_completer(HistoryCompleter([
        'getProfile',
        'history_list',
        'labels_get',
        'labels_list',
        'messages_get',
        'messages_list',
        'threads_get',
        'threads_list'
    ]).complete)
    try:
        readline.read_history_file(histfile_path)
    except FileNotFoundError:
        pass
    readline.set_history_length(1000)
    os.makedirs(histfile_dir, exist_ok=True)
    atexit.register(readline.write_history_file, histfile_path)
