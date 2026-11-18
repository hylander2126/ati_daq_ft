"""Test the built package, including its native library, rather than the checkout.

Colcon invokes pytest from the source directory. With a normal (non-symlink)
install that directory contains Python sources but no compiled calibration library.
The sourced workspace supplies the complete installed package on PYTHONPATH.
"""

import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != SOURCE]
