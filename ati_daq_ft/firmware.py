"""Load NI's RAM firmware in a separate process, without importing ROS."""

import ctypes
from .runtime import require_runtime, runtime_root


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
