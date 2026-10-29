"""Allow `python -m docs_anchor_checker`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
