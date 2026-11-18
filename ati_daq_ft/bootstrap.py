"""Set loader paths before starting ROS; load LabVIEW only during acquisition."""

import os
import sys
from .runtime import environment


def main():
    env = os.environ.copy()
    env.update(environment())
    # Keep the working directory from shadowing the installed native library.
    os.execve(
        sys.executable,
        [sys.executable, "-P", "-m", "ati_daq_ft.node", *sys.argv[1:]],
        env,
    )
