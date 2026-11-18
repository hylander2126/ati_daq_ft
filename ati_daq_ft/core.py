"""Shared non-ROS ATI DAQ acquisition and calibration conversion."""

import ctypes as C
import fcntl
import math
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from .runtime import require_runtime
from importlib.machinery import EXTENSION_SUFFIXES


class AnalogReader:
    def __init__(
        self,
        device="Dev1",
        terminal="diff",
        sample_rate=0.0,
        block_size=5,
        expected_serial="",
    ):
        self.sample_rate = float(sample_rate)
        self.block_size = int(block_size) if self.sample_rate else 1
        if (
            not math.isfinite(self.sample_rate)
            or self.sample_rate < 0
            or not 1 <= self.block_size <= 10000
        ):
            raise ValueError("Invalid sampling rate/block size")
        if terminal not in ("diff", "rse", "nrse"):
            raise ValueError("terminal must be diff, rse, or nrse")
        if not device or "/" in device:
            raise ValueError("Expected a DAQ device name such as Dev1")
        if expected_serial:
            int(expected_serial, 16)
        require_runtime()
        self.task = C.c_void_p()
        # Share the original desktop reader's lock name to prevent concurrent access.
        lock_dir = Path(
            os.environ.get("XDG_RUNTIME_DIR", f"/tmp/ati-gamma-{os.getuid()}")
        )
        lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = open(lock_dir / f"ati-gamma-{device}.lock", "a+")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock.close()
            raise RuntimeError(
                "DAQ is already in use. Close the desktop reader or other acquisition node first."
            )
        try:
            self._open(device, terminal, expected_serial)
        except BaseException:
            self.close()
            raise

    def _open(self, device, terminal, expected_serial):
        # LabVIEW resolves generated VI symbols in the global symbol namespace.
        C.CDLL("liblvrtdark.so", mode=C.RTLD_GLOBAL)
        self.lv = C.CDLL("libnidaqmxbaselv.so", mode=C.RTLD_GLOBAL)
        msg = C.create_string_buffer(4096)
        if self.lv.LVDLLStatus(msg, len(msg), None):
            raise RuntimeError(
                "NI runtime could not load: " + msg.value.decode(errors="replace")
            )
        self.lib = C.CDLL("libnidaqmxbase.so")
        self.task = C.c_void_p()
        self.lib.DAQmxBaseCreateTask.argtypes = [C.c_char_p, C.POINTER(C.c_void_p)]
        self.lib.DAQmxBaseCreateAIVoltageChan.argtypes = [
            C.c_void_p,
            C.c_char_p,
            C.c_char_p,
            C.c_int32,
            C.c_double,
            C.c_double,
            C.c_int32,
            C.c_char_p,
        ]
        self.lib.DAQmxBaseReadAnalogF64.argtypes = [
            C.c_void_p,
            C.c_int32,
            C.c_double,
            C.c_uint32,
            C.POINTER(C.c_double),
            C.c_uint32,
            C.POINTER(C.c_int32),
            C.c_void_p,
        ]
        for name in ["DAQmxBaseStartTask", "DAQmxBaseStopTask", "DAQmxBaseClearTask"]:
            getattr(self.lib, name).argtypes = [C.c_void_p]
        self.lib.DAQmxBaseGetDevSerialNum.argtypes = [C.c_char_p, C.POINTER(C.c_uint32)]
        serial = C.c_uint32()
        try:
            self.check(
                self.lib.DAQmxBaseGetDevSerialNum(device.encode(), C.byref(serial))
            )
            self.serial = f"{serial.value:08X}"
            if expected_serial and serial.value != int(expected_serial, 16):
                raise RuntimeError(
                    f"Expected DAQ serial {expected_serial}, found {self.serial} on {device}"
                )
        except BaseException:
            self._lock.close()
            raise
        self.check(self.lib.DAQmxBaseCreateTask(b"ati_daq_ft", C.byref(self.task)))
        if not self.task.value:
            raise RuntimeError("NI returned a null task; no acquisition is available.")
        try:
            self.check(
                self.lib.DAQmxBaseCreateAIVoltageChan(
                    self.task,
                    f"{device}/ai0:6".encode(),
                    b"",
                    {"diff": 10106, "rse": 10083, "nrse": 10078}[terminal],
                    -10.0,
                    10.0,
                    10348,
                    None,
                )
            )
            if self.sample_rate:
                self.lib.DAQmxBaseCfgSampClkTiming.argtypes = [
                    C.c_void_p,
                    C.c_char_p,
                    C.c_double,
                    C.c_int32,
                    C.c_int32,
                    C.c_uint64,
                ]
                self.check(
                    self.lib.DAQmxBaseCfgSampClkTiming(
                        self.task,
                        b"",
                        self.sample_rate,
                        10280,
                        10123,
                        max(1000, self.block_size * 20),
                    )
                )
            self.check(self.lib.DAQmxBaseStartTask(self.task))
            for _ in range(10 if self.sample_rate else 40):
                self.read_block()
                if not self.sample_rate:
                    time.sleep(0.005)
        except BaseException:
            self.close()
            raise

    def check(self, code):
        if code < 0:
            msg = C.create_string_buffer(8192)
            self.lib.DAQmxBaseGetExtendedErrorInfo(msg, len(msg))
            raise RuntimeError(f"NI error {code}: {msg.value.decode(errors='replace')}")

    def read_block(self):
        values = (C.c_double * (7 * self.block_size))()
        count = C.c_int32()
        self.check(
            self.lib.DAQmxBaseReadAnalogF64(
                self.task,
                self.block_size,
                max(0.2, 2 * self.block_size / max(1, self.sample_rate)),
                1,
                values,
                len(values),
                C.byref(count),
                None,
            )
        )
        if count.value != self.block_size or not all(math.isfinite(v) for v in values):
            raise RuntimeError(f"Invalid acquisition: {count.value} samples/channel")
        if any(abs(values[i]) >= 9.9 for i in range(len(values)) if i % 7 < 6):
            raise RuntimeError(
                "A strain-gauge channel is at the ±10 V acquisition limit"
            )
        return [list(values[i : i + 7]) for i in range(0, len(values), 7)]

    def read(self):
        return self.read_block()[-1]

    def close(self):
        if self.task.value:
            self.lib.DAQmxBaseStopTask(self.task)
            self.lib.DAQmxBaseClearTask(self.task)
            self.task = C.c_void_p()
        if hasattr(self, "_lock") and not self._lock.closed:
            self._lock.close()


class Calibration:
    def __init__(self, path, index=1):
        self.path = str(Path(path).resolve())
        # Check dimensions before passing XML to ATI’s fixed-size C arrays.
        tree = ET.parse(self.path).getroot()
        calibrations = tree.findall("Calibration")
        if tree.tag != "FTSensor" or tree.get("NumGages") != "6":
            raise ValueError("Expected an ATI FTSensor file with six strain gauges.")
        if not 1 <= index <= len(calibrations):
            raise ValueError("Calibration index is out of range.")
        axes = calibrations[index - 1].findall("Axis")
        user_axes = calibrations[index - 1].findall("UserAxis")
        if user_axes:
            # Official legacy converter reads Axis. Never silently use an internal-only matrix.
            if len(user_axes) != len(axes) or any(
                u.get("Name") != a.get("Name")
                or [float(v) for v in u.get("values", "").split()]
                != [
                    float(v) / float(a.get("scale", "1"))
                    for v in a.get("values", "").split()
                ]
                for u, a in zip(user_axes, axes)
            ):
                raise ValueError(
                    "Factory UserAxis and legacy Axis matrices differ; this calibration needs a v1.1 converter."
                )
        if len(axes) != 6 or any(len(a.get("values", "").split()) != 6 for a in axes):
            raise ValueError("Expected a six-by-six calibration matrix.")
        if any(
            not math.isfinite(float(v))
            for a in axes
            for v in a.get("values", "").split()
        ):
            raise ValueError("Calibration matrix contains nonfinite values")
        native = next(
            (
                Path(__file__).with_name("_atidaq" + suffix)
                for suffix in EXTENSION_SUFFIXES
                if Path(__file__).with_name("_atidaq" + suffix).is_file()
            ),
            None,
        )
        if native is None:
            raise RuntimeError(
                "ATI conversion library missing. Build this package with colcon first."
            )
        self.lib = C.CDLL(str(native))
        self.lib.createCalibration.argtypes = [C.c_char_p, C.c_ushort]
        self.lib.createCalibration.restype = C.c_void_p
        self.lib.destroyCalibration.argtypes = [C.c_void_p]
        self.lib.ati_serial.argtypes = [C.c_void_p]
        self.lib.ati_serial.restype = C.c_char_p
        for name in ["ati_channels", "ati_axes", "ati_tempcomp"]:
            getattr(self.lib, name).argtypes = [C.c_void_p]
        for name in ["SetForceUnits", "SetTorqueUnits"]:
            getattr(self.lib, name).argtypes = [C.c_void_p, C.c_char_p]
            getattr(self.lib, name).restype = C.c_short
        self.lib.ConvertToFT.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_float),
            C.POINTER(C.c_float),
        ]
        self.lib.ResetDefaults.argtypes = [C.c_void_p]
        self.lib.ResetDefaults.restype = None
        self.lib.Bias.argtypes = [C.c_void_p, C.POINTER(C.c_float)]
        self.cal = self.lib.createCalibration(self.path.encode(), index)
        if not self.cal:
            raise ValueError("ATI could not load this calibration file/index.")
        try:
            if self.lib.ati_axes(self.cal) != 6 or self.lib.ati_channels(self.cal) != 7:
                raise ValueError(
                    "Expected a six-axis ATI DAQ calibration with seven input channels."
                )
            if self.lib.SetForceUnits(self.cal, b"N") or self.lib.SetTorqueUnits(
                self.cal, b"N-m"
            ):
                raise ValueError("Could not set calibration units to N / N-m.")
            self.serial = self.lib.ati_serial(self.cal).decode()
            self.tempcomp = bool(self.lib.ati_tempcomp(self.cal))
        except BaseException:
            self.close()
            raise

    def convert(self, volts):
        result = (C.c_float * 6)()
        self.lib.ConvertToFT(self.cal, (C.c_float * 7)(*volts), result)
        if not all(math.isfinite(v) for v in result):
            raise RuntimeError("Calibration returned a nonfinite force/torque value.")
        return list(result)

    def bias(self, volts):
        self.lib.Bias(self.cal, (C.c_float * 7)(*volts))

    def clear_bias(self):
        # Reset in-memory bias/configuration; never reload changed XML under the old hash.
        self.lib.ResetDefaults(self.cal)
        if self.lib.SetForceUnits(self.cal, b"N") or self.lib.SetTorqueUnits(
            self.cal, b"N-m"
        ):
            raise ValueError("Could not restore SI units after clearing bias")

    def close(self):
        if self.cal:
            self.lib.destroyCalibration(self.cal)
            self.cal = None
