"""Set loader paths before starting ROS; load LabVIEW only during acquisition."""

import os
import sys
from .runtime import environment


def run(module):
    env = os.environ.copy()
    env.update(environment())
    # Keep the working directory from shadowing the installed native library.
    os.execve(
        sys.executable,
        [sys.executable, "-P", "-m", module, *sys.argv[1:]],
        env,
    )


def main():
    run("ati_daq_ft.node")


def reader_main():
    run("ati_daq_ft.desktop")
