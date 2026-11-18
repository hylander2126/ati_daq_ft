#!/usr/bin/env python3
"""Install the VISA USB transport, NI resource links, and scoped USB permissions."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from prepare_runtime import BASE, HERE, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run this one-time system setup with sudo")
    root = args.runtime.expanduser().resolve()
    if not (root / "ni-runtime.json").is_file():
        parser.error("Prepare the runtime first with prepare_runtime.py")
    links = {
        Path("/usr/local/natinst/nidaqmxbase"): root / BASE,
        Path("/etc/natinst/nidaqmxbase"): root / BASE / "etc",
    }
    # Refuse to replace an existing NI installation or another reader's links.
    for link, target in links.items():
        if (link.exists() or link.is_symlink()) and link.resolve() != target:
            parser.error(
                f"{link} already exists and points elsewhere. See docs/hardware.md."
            )
    manifest = json.loads((HERE / "ni-runtime.json").read_text())
    packages = []
    for name in ("libvisa-data", "libvisa", "ni-visa-passport-usb"):
        item = next(item for item in manifest["deb"] if item["name"] == name)
        path = args.cache.expanduser().resolve() / item["url"].rsplit("/", 1)[1]
        verify(path, item["sha256"])
        packages.append(str(path))
    # Deliberately do not install ni-pal: only libnipalu is used, no kernel modules.
    subprocess.run(["dpkg", "-i", *packages], check=True)
    for link, target in links.items():
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink() and not link.exists():
            link.symlink_to(target, target_is_directory=True)
    rule = Path("/etc/udev/rules.d/70-ati-daq-ft-usb.rules")
    rule.write_text(
        'SUBSYSTEM=="usb", ATTR{idVendor}=="3923", '
        'ATTR{idProduct}=="7269|726f", GROUP="plugdev", '
        'MODE="0660", TAG+="uaccess"\n'
    )
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(
        [
            "udevadm",
            "trigger",
            "--action=change",
            "--subsystem-match=usb",
            "--attr-match=idVendor=3923",
        ],
        check=True,
    )
    subprocess.run(["udevadm", "settle"], check=True)
    print("VISA USB transport and USB-621x permissions configured. Replug the DAQ.")


if __name__ == "__main__":
    main()
