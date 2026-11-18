# ati_daq_ft

ROS 2 driver for an ATI DAQ force/torque sensor connected through an NI USB DAQ.
Publishes `geometry_msgs/WrenchStamped` in **N and N·m**, using the sensor's factory
calibration. Includes an optional terminal/desktop reader using the same core.

Tested with ATI Gamma FT61253 and NI USB-621x, serial 023CF58E, on Ubuntu 24.04
x86-64, Python 3.12 and ROS 2 Jazzy. NI software: DAQmx Base 15, headless LabVIEW
2015 runtime, VISA 26.8. The exact DAQ model suffix was not recorded. Other setups
and physical unplug/firmware reload have not been verified.

## Install

Clone this repository into `~/ros2_ws/src/ati_daq_ft`. From the repository directory,
prepare the NI runtime once (skip this if it is already configured):

```bash
sudo apt install libarchive-tools usbutils udev
python3 scripts/prepare_runtime.py
sudo python3 scripts/setup_system.py \
  --runtime "$HOME/.local/share/ati_daq_ft/runtime" \
  --cache "$HOME/.cache/ati_daq_ft"
```

This downloads pinned NI packages, verifies their hashes, and extracts about 27 MB
of required runtime files. The initial ISO download is about 381 MB. The setup
installs VISA's USB transport, creates NI resource links, and configures USB access.
It refuses to overwrite an existing NI setup. No NI kernel modules are installed.
Keep the runtime directory in place; the NI resource links point into it.

With a ROS 2 Jazzy development environment (`colcon` and initialized `rosdep`):

```bash
sudo apt install gcc libc6-dev
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
rosdep install --from-paths src/ati_daq_ft --ignore-src -r -y
colcon build --packages-select ati_daq_ft --symlink-install
source install/setup.bash
```

The build compiles the bundled ATI calibration library. NI binaries and your
sensor's calibration file are kept outside this repository.

## Run

Use the factory `.cal` file matching the serial number on your sensor:

```bash
ros2 launch ati_daq_ft ati_daq_ft.launch.py \
  calibration_file:=/absolute/path/to/your_sensor.cal
ros2 topic echo /ati_daq_ft/wrench
```

Defaults: `Dev1`, differential ai0–ai5 for gauges / ai6 for temperature, ±10 V,
500 scans/s, frame `ft_sensor`. Check the wiring for your ATI interface/cable.
Optional `sensor_serial` and hexadecimal `daq_serial` parameters check device identity.
Use `--show-args` to list launch options.

| Topic | Content |
| --- | --- |
| `/ati_daq_ft/wrench` | Calibrated force/torque |
| `/ati_daq_ft/ready` | Retained Bool; true while publishing fresh calibrated data |
| `/ati_daq_ft/state` | Retained JSON with errors, identities and counters |
| `/ati_daq_ft/diagnostics` | Status and latest raw voltages |

Close other readers first: one process owns the DAQ. There is no automatic tare
or reconnect. Explicit tare is available through `set_tare` (`std_srvs/SetBool`)
when launched with `allow_driver_tare:=true`; true averages 200 samples, false
clears the bias. Errors and stale data clear readiness and stop fresh wrench output.

The wrench is in sensor axes at its sensing origin. No gravity compensation is
applied. For robot integration, `rotation_xyzw` and `sensor_origin_in_output_m`
apply a known rotation and torque-reference shift (`r × F`); the driver does not
look up TF. Timestamps use a host-receipt anchor plus hardware scan periods.

## Desktop / terminal reader

```bash
ros2 run ati_daq_ft ati_daq_reader --cal /path/to/your_sensor.cal --seconds 10
ros2 run ati_daq_ft ati_daq_reader --gui
```

The GUI alone needs `sudo apt install python3-tk`. It remembers calibration
selection in `~/.config/ati_daq_ft/reader.json` and has explicit tare/clear controls.
For terminal captures, add `--csv capture.csv` (refuses to overwrite); `--tare`
requests a tare. Restart the reader after correcting a hardware error.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Missing NI library | Complete NI setup; default runtime is `~/.local/share/ati_daq_ft/runtime`. Override with `runtime_root` or `ATI_DAQ_FT_RUNTIME`. |
| DAQ absent / permission denied | `lsusb -d 3923:`; tested loader/runtime IDs are `7269` / `726f`. Check the udev rule and replug. Remote users may need membership in `plugdev` and a new login. |
| Wrong serial | Check `device`, `daq_serial`, and the calibration file. |
| No wrench | Read `/ati_daq_ft/state`; calibration must load and acquisition must be fresh. |
| DAQ busy | Close the other ROS or desktop reader. |
| Input at ±10 V limit | Check wiring, signal range, and terminal mode. |

MIT licensed; bundled ATI/Expat source notices are retained. Downloaded NI software
has separate vendor terms.
