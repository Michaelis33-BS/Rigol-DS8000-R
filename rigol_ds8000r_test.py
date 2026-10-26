"""Convenient launch script for the DS8000-R command verification utility.

Creator: Jeff Michaelis

This file runs the exact same verification CLI installed by the Python package.
Run `python rigol_ds8000r_test.py --help` for all options.
"""

import sys
from rigol_ds8000r.verification import main

if __name__ == "__main__":
    sys.exit(main())
