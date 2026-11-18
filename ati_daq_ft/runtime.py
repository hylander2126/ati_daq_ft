"""NI loader settings scoped to the reader process."""

import os
from pathlib import Path


def runtime_root():
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return (
        Path(os.environ.get("ATI_DAQ_FT_RUNTIME", data / "ati_daq_ft/runtime"))
        .expanduser()
        .resolve()
    )


def environment(root=None):
    root = Path(root or runtime_root()).expanduser().resolve()
    paths = [
        root / "usr/local/natinst/nidaqmxbase/lib64",
        root / "usr/local/lib64/LabVIEW-2015-64",
        root / "usr/lib/x86_64-linux-gnu",
    ]
    if os.environ.get("LD_LIBRARY_PATH"):
        paths.append(os.environ["LD_LIBRARY_PATH"])
    env = {
        "ATI_DAQ_FT_RUNTIME": str(root),
        "LD_LIBRARY_PATH": ":".join(map(str, paths)),
    }
    # LabVIEW exports an old expat. ROS needs the system version to win.
    expat = Path("/usr/lib/x86_64-linux-gnu/libexpat.so.1")
    preload = [str(expat)] if expat.is_file() else []
    if os.environ.get("LD_PRELOAD"):
        preload.append(os.environ["LD_PRELOAD"])
    if preload:
        env["LD_PRELOAD"] = ":".join(preload)
    return env


def require_runtime():
    root = runtime_root()
    required = [
        "usr/local/natinst/nidaqmxbase/lib64/libnidaqmxbase.so",
        "usr/local/lib64/LabVIEW-2015-64/liblvrtdark.so",
        "usr/lib/x86_64-linux-gnu/libnipalu.so.1",
    ]
    missing = [str(root / name) for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError(
            "NI runtime missing; follow README.md or set "
            "ATI_DAQ_FT_RUNTIME. Missing: " + ", ".join(missing)
        )
