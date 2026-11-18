# Clean installation test with Docker

Run these commands from the repository root. The Docker build copies source and
installs dependencies inside the image. It does not mount your host's NI runtime,
ROS workspace, system configuration, or Docker socket.

## Software, without NI

```bash
docker build --target software -f docker/Dockerfile -t ati-daq-ft:software-test .
```

This starts with ROS Jazzy on Ubuntu 24.04, installs declared dependencies, builds
the calibration library, and runs all software tests, including actual ROS replay
and the documented launch command. No NI software or USB device is provided.

## NI installation

```bash
docker build --target hardware -f docker/Dockerfile -t ati-daq-ft:hardware-test .
```

This independently downloads and verifies the NI packages, extracts the selected
runtime, installs the three VISA packages, and creates NI resource links inside
the image. The system setup uses `--skip-udev-reload`: the rule is written inside
the container, but the host's udev service is not contacted.

## Explicit hardware check

Close other readers. Find the current device path with `lsusb -d 3923:`; bus 001,
device 011 corresponds to `/dev/bus/usb/001/011`. Substitute your path, matching
factory calibration, sensor serial, and DAQ serial below:

```bash
docker run --rm --network none \
  --device /dev/bus/usb/001/011 \
  --mount type=bind,src=/absolute/path/to/your_sensor.cal,dst=/sensor.cal,readonly \
  ati-daq-ft:hardware-test bash -c \
  'source /ws/install/setup.bash &&
   python3 /ws/src/ati_daq_ft/docker/check_hardware.py \
     --calibration /sensor.cal --sensor-serial FTxxxxx --daq-serial XXXXXXXX'
```

The check launches the driver, observes about three seconds of calibrated data,
checks identities/readiness/timestamp order and delivery near 500 Hz, then stops.
It does not request tare or robot motion. The only host file mount is the
read-only calibration. Only the specified USB device is exposed; the command
does not use `--privileged` or host networking.

For a non-root check, add `--user 1000:1000 --group-add 46` when 1000 is the user
UID and 46 is the USB device's group on your host. Also set a writable home with
`-e HOME=/tmp/ati-daq-test-user`. Use `stat` on your device node to find the actual
UID/group values; these numbers are installation-specific.

Containers still share the host kernel and device permissions. A successful test
establishes independent userspace installation and acquisition, but does not
validate installation of host udev rules. The single-device command also does not
test firmware reload after physical unplug/re-enumeration: the USB device number
can change. A fresh OS/VM with USB passthrough is needed for those remaining checks.

Docker background and device options: [Docker run documentation](https://docs.docker.com/engine/containers/run/).
