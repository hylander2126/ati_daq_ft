"""Load NI's RAM firmware in a separate process, without importing ROS."""

import ctypes
import subprocess
import sys
import time
from pathlib import Path
from .runtime import require_runtime, runtime_root


def ensure_loaded():
    """Reload RAM firmware in its own process when the tested loader is present."""
    for product in Path("/sys/bus/usb/devices").glob("*/idProduct"):
        vendor = product.parent / "idVendor"
        if (
            vendor.exists()
            and vendor.read_text().strip() == "3923"
            and product.read_text().strip() == "7269"
        ):
            try:
                subprocess.run(
                    [sys.executable, "-m", "ati_daq_ft.firmware"],
                    check=True,
                    timeout=15,
                )
            except subprocess.SubprocessError as error:
                raise RuntimeError(
                    "NI firmware reload failed: " + str(error)
                ) from error
            time.sleep(2)
            break


def main():
    require_runtime()
    lib = ctypes.CDLL(
        str(runtime_root() / "usr/local/natinst/nidaqmxbase/lib64/libniusb9162.so")
    )
    lib.DownloadFirmwareToUSBDevices.argtypes = []
    lib.DownloadFirmwareToUSBDevices.restype = None
    lib.DownloadFirmwareToUSBDevices()


if __name__ == "__main__":
    main()
