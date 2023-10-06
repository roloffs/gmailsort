import argparse
import os
import textwrap


def __wrap(text, width):
    return "\n".join(
        ["\n".join(textwrap.wrap(p, width)) for p in text.split("\n")]
    )


def wrap_long(text):
    return __wrap(text, 80)


def wrap_short(text):
    return __wrap(text, 56)


def checked_file_path(path):
    if os.path.isfile(os.path.expanduser(path)):
        return path
    raise argparse.ArgumentTypeError(f"File not found: '{path}'")
