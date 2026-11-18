#!/usr/bin/env python3
"""Replace only the two resource links owned by an existing legacy-reader setup.

The default is a read-only plan. --apply requires root; no packages or USB rules
are changed. All targets and required resources are checked before either switch.
"""

import argparse
import hashlib
import os
from pathlib import Path


def replace_link(link, target):
    temporary = link.with_name(f".{link.name}-ati-daq-ft-{os.getpid()}")
    try:
        temporary.symlink_to(target, target_is_directory=True)
        temporary.replace(link)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    legacy = args.legacy_root.expanduser().resolve()
    runtime = args.runtime.expanduser().resolve()
    old_base = legacy / "legacy-inspect/usr/local/natinst/nidaqmxbase"
    new_base = runtime / "usr/local/natinst/nidaqmxbase"
    if not (runtime / "ni-runtime.json").is_file():
        parser.error("The new runtime has not been prepared")
    pairs = [
        (Path("/usr/local/natinst/nidaqmxbase"), old_base, new_base),
        (Path("/etc/natinst/nidaqmxbase"), old_base / "etc", new_base / "etc"),
    ]
    for relative in (
        "lib64/libnidaqmxbase.so",
        "lib64/libniusb9162.so",
        "etc/mxbase.cfg",
        "etc/nimxbase.inf",
        "bin/support/NIUSBMXB621xFPGA0.bin",
    ):
        new_file = new_base / relative
        if not new_file.is_file():
            parser.error(f"Missing resource: {new_file}")
        old_file = old_base / relative
        if (
            old_file.is_file()
            and hashlib.sha256(old_file.read_bytes()).digest()
            != hashlib.sha256(new_file.read_bytes()).digest()
        ):
            parser.error(
                f"Existing NI resource differs: {old_file}; manual review required"
            )
    previous = {}
    for link, old, new in pairs:
        if not link.is_symlink() or link.resolve() not in (old, new):
            parser.error(f"Refusing unexpected NI installation at {link}")
        previous[link] = link.readlink()
        print(f"{link}: {link.readlink()} -> {new}", flush=True)
    if not args.apply:
        print("Checks passed. Re-run with --apply as root to switch these links.")
        return
    if os.geteuid() != 0:
        parser.error("--apply requires root (sudo or pkexec)")
    switched = []
    try:
        for link, old, new in pairs:
            if link.resolve() != new:
                replace_link(link, new)
                switched.append(link)
    except OSError:
        for link in reversed(switched):
            replace_link(link, previous[link])
        raise
    print(
        "Both NI links now use the independent runtime; packages and USB rules unchanged."
    )


if __name__ == "__main__":
    main()
