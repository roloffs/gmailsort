#!/usr/bin/env python3

import json
import sys

from gmail import gmail, history


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

        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")

        except EOFError:
            print()
            break


if __name__ == "__main__":
    main()
