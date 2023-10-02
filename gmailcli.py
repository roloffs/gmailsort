#!/usr/bin/env python3

import sys
import json

from gmail import gmail
from gmail import history


def main() -> None:
    profile_name = "sascha"
    (creds, err) = gmail.authenticate(profile_name)
    if err:
        sys.exit(1)
    profile_dir = gmail.get_profile_dir(profile_name)
    history.init(profile_dir)
    print("Type Ctrl-D to quit")
    while True:
        try:
            line = input(">>> ")
            (response, err) = gmail.execute(creds, line)
            if not err:
                print(
                    json.dumps(
                        response, indent=2, ensure_ascii=False, sort_keys=True
                    )
                )

        except KeyboardInterrupt as err:
            print("\nKeyboardInterrupt")

        except EOFError as err:
            print()
            break


if __name__ == "__main__":
    main()
