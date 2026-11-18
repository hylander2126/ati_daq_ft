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

Docker verification (2026-11-18):

- Fresh ROS Jazzy/Ubuntu 24.04 userspace, without host NI libraries or workspaces
  mounted. The software stage builds and passes all 13 tests before NI is installed.
- The hardware stage downloads the pinned NI packages, prepares its own runtime,
  installs VISA core/data/USB, and creates its own NI resource links. The container
  installer skips udev reload, while writing the rule inside the image.
- A non-root process (UID 1000, supplementary USB group 46) reads FT61253 through
  one explicitly exposed USB device. The final check received 1,506 calibrated
  messages over 3.0078 seconds (about 500.4 Hz), with zero reported drops, and
  the driver exited cleanly. The calibration is a read-only file mount;
  there is no host networking or privileged container mode.
- This exposed NI's installer assumption that `/etc/modprobe.d` exists. The setup
  script now creates that directory without adding an unnecessary tool package.
- The native exit trace exposed a LabVIEW teardown crash after the acquisition
  thread ended. The driver explicitly releases the generated VI client after
  clearing the DAQ task, before the worker exits. Signal handling keeps ROS valid
  through cleanup and tolerates launch forwarding a terminal interrupt twice.
  Software and manual hardware checks assert clean process shutdown as well as
  successful acquisition.
- Host package versions, existing NI configuration/links, USB rules and robot
  workspace link are compared against a saved baseline. The original desktop/CLI
  reader is also checked separately.

Exact metrics and image identity: [validation record](container-validation.json).
See [container commands](container-test.md). Docker validates independent userspace
installation; it still shares the host kernel and USB permissions.

Single-source migration (2026-11-18):

- The IRB workspace source link now selects this repository. Robot-specific mount
  validation lives in `irb120_control`; the driver reports the supplied axes and
  mounting-profile hash for its provenance checks.
- Both system NI resource links select `~/.local/share/ati_daq_ft/runtime`.
  Calibration/certificate and recorded captures live under
  `~/.local/share/ati_daq_ft/{calibration,records}`; GUI settings are under
  `~/.config/ati_daq_ft`.
- Both ROS packages build, and 23 relevant driver/robot software checks pass with
  the original source folder renamed out of the way. No robot nodes are started.
- With the original folder unavailable, ROS acquisition delivered 1,502 messages
  at about 500.3 Hz with zero reported drops and clean shutdown. The optional
  terminal reader produced calibrated samples; the GUI displayed the calibrated
  FT61253 stream and closed cleanly in a virtual display.
- The original folder was then deleted. Its calibration, certificate, recorded
  captures and hardware-check data were preserved outside the source repository.

Not verified: clean-host udev setup, physical unplug/reload with the new package,
other DAQs/sensors/OS/ROS distributions, sustained latency, external time
synchronization, robot frame geometry, gravity compensation, or robot control.
