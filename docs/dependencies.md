# Dependency audit

The public package has no PyPI runtime dependencies beyond the ROS build's
setuptools. It uses Python's standard library for CSV, XML preflight checks,
threading, configuration, and loading the native libraries. There is no NumPy,
SciPy, PyDAQmx, nidaqmx Python package, requests, GUI toolkit, or robot stack.

| Component | Needed for | Why retained / what was removed |
| --- | --- | --- |
| `rclpy`, `rcl_interfaces` | ROS node and read-only parameters | Direct imports. |
| `geometry_msgs`, `std_msgs`, `std_srvs`, `diagnostic_msgs` | Wrench, health, tare, diagnostics | Only the corresponding message/service definitions are used; standard ROS interfaces preserve interoperability. |
| `launch`, `launch_ros` | Optional launch command | Standard ROS parameter/namespace handling; direct `ros2 run` also works. |
| colcon, setuptools, GCC, libc development headers | Build | Compile the bundled C conversion library. No Python C API or Python development headers are used. |
| ATI DAQ C library 1.0.6 and its embedded XML parser | Calibration conversion | About 0.5 MB of source, MIT notices preserved. Compiled automatically. Retaining the established calibration/units/bias/temperature handling is simpler to validate than writing a replacement converter. Vendor sample programs are omitted. |
| DAQmx Base 15 C interface and generated VI binary | Hardware only | Exposes the acquisition API; the API delegates to a LabVIEW-generated binary. Replacing it would require a separate acquisition driver, not one helper function. |
| Headless LabVIEW 2015 runtime and seven support/resource files | Hardware only | Required by the generated acquisition/firmware binaries. No editor, GUI, plotting, OpenGL, analysis plugins, or full runtime installation. |
| DAQmx Base board-support libraries | Hardware only | The generated driver eagerly loads several board libraries during initialization, including boards we do not use. Their loader references make them runtime requirements. |
| NI USB firmware library and USB-621x firmware/FPGA images | Firmware reload and hardware initialization | Uses NI's firmware loader when the device reports loader ID `7269`. FPGA images are also loaded from NI's fixed resource path during acquisition. Other DAQ families' images and standalone NI executables are omitted. |
| `libvisa-data`, `libvisa`, `ni-visa-passport-usb` | Hardware USB transport | Core/configuration and the USB passport are used by DAQmx Base. NI's VISA LabVIEW I/O control package is not loaded and is omitted. |
| `libnipalu.so.1` from ni-pal | Hardware USB transport | The library is loaded by VISA's USB path. Extract this one library; do not install ni-pal, ni-pal-support, or ni-pal-dkms. |
| System `libexpat.so.1` | ROS/native coexistence | Loaded before LabVIEW's old exported expat symbols. All other loader settings remain local to the node. |
| `libarchive-tools` (`bsdtar`), `dpkg-deb` | One-time setup | Read ISO/RPM/deb files. They are not node runtime requirements. `usbutils` is a diagnostic convenience. |
| `udev` | Hardware system setup | Required explicitly by NI's USB package installer and for applying the device-access rule. Containers write the rule and skip daemon reload. |
| pytest, `ament_index_python` | Tests only | Pure conversion tests plus an actual ROS replay subprocess. |

The ATI library includes an old Expat copy, bound internally with `-Bsymbolic` so
its symbols do not interpose on ROS. Its compiled artifact is loaded via ctypes;
it does not require a separate package installation. Unsupported `.cal` files
whose UserAxis and legacy Axis matrices differ are rejected. Sensor-specific
temperature compensation is enabled only when supported by the calibration/library.

Native dependency evidence includes ELF dependency inspection and successful file
opens in acquisition traces from the original working installation. The reduced
runtime recipe keeps the headless files those traces showed. The node is also
checked against that reduced runtime; see [tested setup](tested-setup.md) for the
actual validation performed and its limits. A file opened by NI is conservatively
retained; this is not a proof that every internal NI feature needs every file.

NI download versions and SHA-256 values are pinned in
[`scripts/ni-runtime.json`](../scripts/ni-runtime.json). The current VISA/PAL
combination with Base 15 is a compatibility recipe, not a statement of NI support
for Base 15 on Ubuntu 24.04. Upstream sources:

- [NI DAQmx Base 15 distribution](https://download.ni.com/support/softlib/multifunction_daq/nidaqmxbase/15.0/linux/)
- [NI Noble package index](https://download.ni.com/ni-linux-desktop/2026/Q4/deb/ni/noble/dists/noble/ni/binary-amd64/Packages.gz)
- [ATI calibration C library](https://ati.novanta.com/wp-content/uploads/sites/2/2025/12/ATIDAQ-C-Library.zip)

The NI binaries and sensor-specific calibration/certificate are not redistributed
in this repository. NI terms remain separate from this repository's MIT license.

The GCC/libc header packages are installed explicitly in the README: the local
rosdep database has no direct `gcc` / `libc6-dev` keys. The manifest declares
`python3-setuptools` as the build tool and exports `ament_python` as the build
**type**; `ament_python` is not an installable dependency. CI installs the colcon
plugins it uses rather than the full common-extensions bundle.
