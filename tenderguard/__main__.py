"""Make `python -m tenderguard` work."""

import sys

from tenderguard.cli import main

if __name__ == "__main__":
    sys.exit(main())