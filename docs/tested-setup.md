# Tested setup

Development machine: Ubuntu 24.04 x86-64, Python 3.12, ROS 2 Jazzy.

Original hardware acquisition (2026-11-17):

- ATI Gamma sensor FT61253, its factory calibration dated 2025-07-22.
- NI USB-621x device, serial 023CF58E, runtime USB ID `3923:726f`;
  initial loader ID `3923:7269`.
- Exact NI model suffix and ATI interface/cable part number have not been
  recorded. The USB product descriptor only says `NI USB-621x`.
- Differential ai0–ai6, ±10 V; 500 scans/s in five-scan batches.
- A three-second ROS check observed about 500 Hz with no reported dropped samples.
- This sensor's factory file has no software temperature-compensation coefficients.

NI versions: DAQmx Base 15.0.0-f1, LabVIEW runtime 15.0.0-2;
VISA core/USB 26.8.0.49315-0+f163; PAL userspace 26.8.0.49360-0+f208.
ATI conversion source: 1.0.6. Exact download hashes are committed in the setup
manifest. The personal calibration and its certificate are not test dependencies.

Public-package validation (2026-11-18):

- Colcon builds with `--symlink-install` and a normal install from a fresh copy
  containing only repository source files, in independent workspaces.
- 12 software tests pass: synthetic SI conversion/tare, invalid dimensions,
  quaternion/moment mapping, native scan layout/count checks, missing runtime,
  lock ownership/cleanup, actual ROS replay, retained readiness, EOF, and
  missing-calibration gating, and the documented launch entry point. Replay runs with a nonexistent NI runtime path.
- The runtime preparation recipe succeeds from the pinned ISO/debs. All five
  vendor download URLs respond successfully. ROS dependency resolution passes.
- Short hardware check using the new package and reduced runtime: 1,503 messages
  over 3.0000 seconds, approximately 500.7 Hz; state reports no dropped scans,
  ready true, and the expected sensor/DAQ identities. No tare or robot motion.
- The acquisition trace resolves NI/LabVIEW/PAL libraries from the reduced runtime,
  VISA/USB from the system installation, and configuration/FPGA resources through
  the existing NI system links. Those required resources are included in the new
  preparation recipe and were checked byte-for-byte against the working files.
  The existing system links and working robot workspace were not changed.

The original installation had VISA's LabVIEW control package installed. The new
setup omits it: the acquisition trace does not load it. The new system installer
has not been run over the development machine's existing NI configuration.

Not verified: a clean-machine system installation, physical unplug/reload with the
new package, other DAQs/sensors/OS/ROS distributions, sustained latency, external
time synchronization, robot frame geometry, gravity compensation, or robot control.
