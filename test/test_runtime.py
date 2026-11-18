"""Runtime configuration and lock cleanup without loading NI libraries."""

import ctypes
import fcntl

import pytest

from ati_daq_ft import core
from ati_daq_ft.runtime import environment, require_runtime, runtime_root


def test_missing_runtime_has_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ATI_DAQ_FT_RUNTIME", str(tmp_path / "missing"))
    assert runtime_root() == tmp_path / "missing"
    # Replay bootstrap may prepare loader paths without requiring hardware files.
    assert environment()["ATI_DAQ_FT_RUNTIME"] == str(tmp_path / "missing")
    with pytest.raises(RuntimeError, match="NI runtime missing"):
        require_runtime()


def test_failed_native_initialization_releases_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(core, "require_runtime", lambda: None)

    def missing_library(*args, **kwargs):
        raise OSError("test: native library missing")

    monkeypatch.setattr(ctypes, "CDLL", missing_library)
    with pytest.raises(OSError, match="native library missing"):
        core.AnalogReader()
    with (tmp_path / "ati-gamma-Dev1.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_other_owner_prevents_loading_hardware(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(core, "require_runtime", lambda: None)
    with (tmp_path / "ati-gamma-Dev1.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="already in use"):
            core.AnalogReader()


def test_native_client_released_after_task_and_only_once(monkeypatch):
    from types import SimpleNamespace

    events = []

    class Uninit:
        def __call__(self):
            events.append("uninit")

    monkeypatch.setattr(
        core, "_runtime_libraries", (None, SimpleNamespace(LVDLLUninit=Uninit()), None)
    )
    reader = object.__new__(core.AnalogReader)
    reader.task = ctypes.c_void_p(1)
    reader.lib = SimpleNamespace(
        DAQmxBaseStopTask=lambda task: events.append("stop"),
        DAQmxBaseClearTask=lambda task: events.append("clear"),
    )
    reader.close()
    reader.close()
    assert events == ["stop", "clear", "uninit"]
