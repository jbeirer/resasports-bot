#!/usr/bin/env python3

import sys

from pysportbot.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    """
    Run `pysportbot run` with the given arguments, so `python -m pysportbot.service --config ...` keeps working.

    Args:
        argv: The arguments of `pysportbot run`. None reads them from `sys.argv`.

    Returns:
        The exit code of `pysportbot run`.
    """
    return cli_main(["run", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    sys.exit(main())
