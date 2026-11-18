# NI USB runtime setup

This recipe targets Ubuntu 24.04 x86-64 with the legacy NI USB-621x interface.
It downloads vendor software directly from NI; none of those binaries belong in
the Git repository. Review NI's applicable license terms before use.

## Prepare

From this repository, install the one-time archive extraction tool and USB
diagnostic utility:

```bash
sudo apt install libarchive-tools usbutils
python3 scripts/prepare_runtime.py
```

The Python script uses only the standard library plus `bsdtar` and `dpkg-deb`.
It verifies pinned SHA-256 hashes for the ISO, its five RPMs, and four modern NI
Debian packages. It extracts the selected runtime files to
`~/.local/share/ati_daq_ft/runtime`; downloads stay in `~/.cache/ati_daq_ft`.
The ISO download is about 381 MB, but most of its contents are discarded. The
prepared userspace runtime is about 27 MB.

The script prints the exact system-setup command, including paths. With the
default locations it is:

```bash
sudo python3 scripts/setup_system.py \
  --runtime "$HOME/.local/share/ati_daq_ft/runtime" \
  --cache "$HOME/.cache/ati_daq_ft"
```

This installs only VISA core/data and its USB transport, creates NI's two resource
links, and writes a udev rule for the tested `3923:7269` / `3923:726f` USB IDs.
The ni-pal package is **extracted**, never installed: only `libnipalu.so.1` is
needed here, without its kernel/DKMS dependencies. There is no LabVIEW editor,
VISA LabVIEW control package, NI apt repository, or kernel-module installation.

For a remote/SSH login, add your account to `plugdev` if needed, then log in again:

```bash
sudo usermod -aG plugdev "$USER"
```

For an active local desktop login, the udev `uaccess` tag supplies device access.
Replug the DAQ after setup. Run the ROS node as your normal user.

## Paths and existing NI installations

The legacy NI code expects:

- `/usr/local/natinst/nidaqmxbase` → the prepared runtime's `usr/local/natinst/nidaqmxbase`
- `/etc/natinst/nidaqmxbase` → that directory's `etc` subdirectory

The setup script refuses to replace existing paths pointing elsewhere. If NI is
already configured, inspect those paths before making any changes; don't run a
second installer over a working NI setup. An existing Base 15 installation may
already provide the resources. Keep these system resources in sync with the
runtime you select. A runtime with resource links must remain in a stable location.

To use a different location, pass `--output` / `--cache` to preparation and the
corresponding paths to system setup. Launch with
`runtime_root:=/absolute/path/to/runtime`, or export `ATI_DAQ_FT_RUNTIME` before
using `ros2 run`. `XDG_DATA_HOME` and `XDG_CACHE_HOME` also affect the defaults.
Do not source the old desktop reader's `env.sh` before ROS: LabVIEW must load
after DDS initialization. This package scopes loader settings to its own process.

## Device and wiring

`lsusb -d 3923:` should show the NI device. `7269` means the RAM firmware loader;
the node invokes NI's firmware loader in a subprocess and waits for enumeration.
`726f` is the tested running device. Firmware disappears when USB power is lost.
Firmware reload after unplug must be verified on a new setup.

The acquisition task uses seven channels, `Dev1/ai0:6`, ±10 V. In differential
mode the physical negative terminals follow NI's differential channel mapping;
they are not simply the seven adjacent input pins. Match your ATI cable/interface
documentation. `terminal:=rse` and `terminal:=nrse` are exposed but were not tested.
The sensor requires its ATI signal-conditioning/interface hardware; a bare strain
gauge transducer is not a ±10 V signal source.

Select `device:=Dev1` (or the actual DAQmx Base device name). When several devices
are present, set `daq_serial` to avoid silently selecting the wrong one. The serial
is hexadecimal, without `0x`. The factory calibration identifies the sensor, not
the USB DAQ; these are separate serial numbers.

## Verification scope

The original installation was already configured on the development computer.
The preparation recipe is exercised from the pinned archives, and acquisition is
checked using its reduced runtime. A clean Ubuntu machine and a physical unplug /
firmware reload cycle remain separate verification steps; do not interpret a
successful software build as either check. See [tested setup](tested-setup.md).
