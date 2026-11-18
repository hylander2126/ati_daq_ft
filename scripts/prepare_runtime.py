#!/usr/bin/env python3
"""Download pinned NI packages; extract a small userspace runtime without sudo."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
BASE = Path("usr/local/natinst/nidaqmxbase")
LV = Path("usr/local/lib64/LabVIEW-2015-64")


def verify(path, expected):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise RuntimeError(
            f"SHA-256 mismatch: {path}; remove this cached file and retry"
        )


def download(item, cache):
    path = cache / item["url"].rsplit("/", 1)[1]
    if not path.exists():
        print("Downloading", item["url"], flush=True)
        partial = path.with_suffix(path.suffix + ".partial")
        with (
            urllib.request.urlopen(item["url"], timeout=120) as response,
            partial.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
        verify(partial, item["sha256"])
        partial.replace(path)
    verify(path, item["sha256"])
    return path


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Dereference RPM links so the selected file cannot depend on discarded files.
    shutil.copy2(source, destination)


def prepare(cache, output, bsdtar):
    manifest = json.loads((HERE / "ni-runtime.json").read_text())
    if output.exists():
        raise RuntimeError(f"{output} already exists; select a new --output directory")
    cache.mkdir(parents=True, exist_ok=True)
    iso = download(manifest["iso"], cache)
    debs = {item["name"]: download(item, cache) for item in manifest["deb"]}
    with tempfile.TemporaryDirectory(prefix="ati-daq-extract-") as tmp:
        tmp = Path(tmp)
        subprocess.run(
            [
                bsdtar,
                "-xf",
                str(iso),
                "-C",
                str(tmp),
                *manifest["rpm"],
                "LICENSE.txt",
                "PATENTS.txt",
                "README.txt",
            ],
            check=True,
        )
        extracted = tmp / "extracted"
        extracted.mkdir()
        for name, digest in manifest["rpm"].items():
            verify(tmp / name, digest)
            subprocess.run(
                [bsdtar, "-xf", str(tmp / name), "-C", str(extracted)], check=True
            )
        subprocess.run(
            ["dpkg-deb", "-x", str(debs["ni-pal"]), str(extracted)], check=True
        )

        # Build in a sibling staging directory; never leave a half-prepared runtime.
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".ati-daq-runtime-", dir=output.parent
        ) as staging_directory:
            stage = Path(staging_directory) / "runtime"
            stage.mkdir()
            # DAQmx Base eagerly loads these board libraries even for USB acquisition.
            names = (
                "nidaqmxbase",
                "nidaqmxbaselv",
                "niusb9162",
                "mxBaseSessionTable",
                "MSeries",
                "ESeries",
                "SSeries",
                "67xx",
                "DIO96",
                "USB-92xx",
                "miteDma",
            )
            for name in names:
                versioned = "lib" + name + ".so.15.0.0"
                target = stage / BASE / "lib64" / versioned
                copy_file(extracted / BASE / "lib64" / versioned, target)
                for suffix in (".so", ".so.15", ".so.15.0"):
                    target.with_name("lib" + name + suffix).symlink_to(versioned)
            # Only the headless runtime and the support/resources used by acquisition.
            for name in (
                "liblvrtdark.so.15.0.0",
                "libniCPULib.so",
                "liblksock.so",
                "liblkdynam.so.5",
                "liblksec.so.5",
                "rtapp.rsc",
                "tdtable.tdr",
                "Lv3rdPartyCopyright.htm",
            ):
                copy_file(extracted / LV / name, stage / LV / name)
            for suffix in (".so", ".so.15.0"):
                (stage / LV / ("liblvrtdark" + suffix)).symlink_to(
                    "liblvrtdark.so.15.0.0"
                )
            for name in ("mxbase.cfg", "nimxbase.inf"):
                copy_file(extracted / BASE / "etc" / name, stage / BASE / "etc" / name)
            # Loaded through NI's fixed /usr/local resource path, not LD_LIBRARY_PATH.
            # Include the USB-621x family firmware/FPGA images, not other DAQ families.
            for image in (extracted / BASE / "bin/support").glob("NIUSBMXB621x*.bin"):
                copy_file(image, stage / BASE / "bin/support" / image.name)
            if not (stage / BASE / "bin/support/NIUSBMXB621xFPGA0.bin").is_file():
                raise RuntimeError("NI archive is missing USB-621x FPGA firmware")
            pal = Path("usr/lib/x86_64-linux-gnu")
            copy_file(
                extracted / pal / "libnipalu.so.26.8.0",
                stage / pal / "libnipalu.so.26.8.0",
            )
            (stage / pal / "libnipalu.so.1").symlink_to("libnipalu.so.26.8.0")
            # Preserve notices for the vendor files; they are never committed to Git.
            notices = stage / "licenses"
            notices.mkdir()
            for name in ("LICENSE.txt", "PATENTS.txt", "README.txt"):
                copy_file(tmp / name, notices / name)
            (stage / "ni-runtime.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
            stage.rename(output)
    print(
        f"Prepared {output}\nNext: sudo python3 {HERE / 'setup_system.py'} "
        f"--runtime {output} --cache {cache}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    parser.add_argument("--output", type=Path, default=data / "ati_daq_ft/runtime")
    parser.add_argument("--cache", type=Path, default=cache / "ati_daq_ft")
    parser.add_argument(
        "--bsdtar", default="bsdtar", help="from the libarchive-tools Ubuntu package"
    )
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("This NI runtime recipe targets x86-64 Linux")
    try:
        prepare(
            args.cache.expanduser().resolve(),
            args.output.expanduser().resolve(),
            args.bsdtar,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
