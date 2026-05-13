import sys


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
