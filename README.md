# ati_daq_ft

ROS 2 driver for an ATI DAQ F/T sensor connected through an NI USB-621x DAQ.
Publishes calibrated `geometry_msgs/WrenchStamped` in **N and N·m**, using the
sensor's factory `.cal` file. No robot packages are required.

Tested on Ubuntu 24.04 x86-64 / ROS 2 Jazzy with an ATI Gamma. Other ATI sensors
and NI DAQs have not been verified. This is an analog DAQ driver; Ethernet Net F/T
uses a different interface.

## Install

Start with a ROS 2 Jazzy development environment with `colcon` and initialized
`rosdep`. Clone this repository into your
workspace's `src/ati_daq_ft` directory, then:

```bash
sudo apt install gcc libc6-dev
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
rosdep install --from-paths src/ati_daq_ft --ignore-src -r -y
colcon build --packages-select ati_daq_ft --symlink-install
source install/setup.bash
```

The build compiles the bundled ATI calibration library. Hardware also needs a
one-time [NI runtime setup](docs/hardware.md). Replay and software tests do not
need NI software or a sensor.

## Run

Use the factory calibration for **your sensor's serial number**:

```bash
ros2 launch ati_daq_ft ati_daq_ft.launch.py \
  calibration_file:=/absolute/path/to/your_sensor.cal
ros2 topic echo /ati_daq_ft/wrench
```

Default wiring is differential ai0–ai5 for the six gauges and ai6 for temperature,
with ±10 V inputs. Check your interface/cable wiring before use. Optional
`sensor_serial:=FTxxxxx` checks the calibration identity; `daq_serial:=XXXXXXXX`
checks the DAQ's hexadecimal serial on `device:=Dev1`.

| Interface | Meaning |
| --- | --- |
| `/ati_daq_ft/wrench` | Calibrated force/torque; default frame `ft_sensor` |
| `/ati_daq_ft/ready` | Retained Bool; true only while publishing fresh calibrated data |
| `/ati_daq_ft/state` | Retained JSON: errors, identities, calibration hash, counters |
| `/ati_daq_ft/diagnostics` | Status plus latest voltages and their sample timestamp |
| `/ati_daq_ft/set_tare` | `std_srvs/SetBool`; disabled by default |

There is **no automatic tare or reconnect**. Enable explicit tare with
`allow_driver_tare:=true`; a `data: true` request averages 200 samples. A
`data: false` request clears the bias. Startup defaults to 500 scans/s in batches
of five. Close other readers before starting: one process owns the DAQ.

The wrench is expressed in the sensor's axes at its sensing origin. There is no
gravity/tool compensation. To report at a different frame/origin, set
`rotation_xyzw` and `sensor_origin_in_output_m` from your measured mounting geometry
and set `frame_id` accordingly. The translation is the vector from the output
origin to the sensor origin, expressed in output axes; torque includes `r × F`.
The driver does not publish or look up TF. Optional `axes_frame` and
`mount_profile_sha256` parameters retain externally supplied mapping metadata.

Timestamps are inferred from the hardware scan period and a host-receipt anchor;
they are not synchronized hardware timestamps. A bounded queue drops old batches.
Errors, stale data, and disconnects clear readiness and stop fresh wrench output.
Consult `state` and `ready` when consuming data. Missing/invalid calibration
withholds wrench output while allowing voltage diagnostics.

`ros2 launch ati_daq_ft ati_daq_ft.launch.py --show-args` lists launch options.
With `ros2 run ati_daq_ft ati_daq_node`, use standard ROS `-p name:=value`
parameters and set `ATI_DAQ_FT_RUNTIME` if the runtime is outside its default path.

## Try without hardware

```bash
ros2 launch ati_daq_ft ati_daq_ft.launch.py source:=replay \
  calibration_file:="$(ros2 pkg prefix --share ati_daq_ft)/examples/synthetic.xml" \
  replay_csv:="$(ros2 pkg prefix --share ati_daq_ft)/examples/replay.csv" \
  sample_rate:=40.0 block_size:=1
```

This finite example is **synthetic**, labels state as simulated, and clears
readiness at EOF. Its identity matrix is a test fixture, never a physical sensor
calibration. The fixture uses N and N-mm internally; published torques are N·m.

## Optional desktop / terminal reader

The same acquisition and calibration core also provides a terminal reader:

```bash
ros2 run ati_daq_ft ati_daq_reader --cal /absolute/path/to/your_sensor.cal --seconds 10
```

Add `--gui` for the desktop display, or `--csv capture.csv` to write a new capture
file. The GUI alone needs the optional `python3-tk` Ubuntu package. Its settings
are stored in `~/.config/ati_daq_ft/reader.json`; calibration files stay outside the
repository. Both interfaces use the same exclusive DAQ lock as the ROS node.
After a hardware error, correct the problem and restart the reader. No automatic
tare is performed; `--tare` requests terminal tare, and the GUI has explicit controls.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing NI library | Complete [hardware setup](docs/hardware.md); check `runtime_root` / `ATI_DAQ_FT_RUNTIME`. |
| DAQ not found | `lsusb -d 3923:`; loader ID is `7269`, runtime ID `726f`. Check permissions and replug. |
| Permission denied | Complete the udev step; for remote sessions, join `plugdev` and log in again. |
| Wrong serial | Check `device`, `daq_serial`, and the calibration's sensor serial. |
| No wrench / ready false | Read `/ati_daq_ft/state`; calibration must load and data must be fresh. |
| DAQ already in use | Close other ROS nodes or desktop readers using the device. |
| Channel at ±10 V limit | Check the cable, wiring, terminal mode, and analog signal range. |
| Stream stops | Inspect `state`; correct the error and restart the driver. |

For a late subscriber to retained status:
`ros2 topic echo /ati_daq_ft/ready --qos-durability transient_local`.

## Development

```bash
colcon test --packages-select ati_daq_ft --event-handlers console_direct+
colcon test-result --verbose
```

Tests use synthetic input and do not open USB. See [dependency audit](docs/dependencies.md)
for why each external component is retained and [tested setup](docs/tested-setup.md)
for verification scope. The [Docker test recipe](docs/container-test.md) checks a
fresh userspace installation without replacing your host's NI setup.
The source is MIT licensed. The bundled ATI/Expat sources
retain their original notices; downloaded NI software has separate vendor terms.
