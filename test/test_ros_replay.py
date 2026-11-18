"""Full ROS process check with recorded voltages; never opens USB."""

import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

import pytest

rclpy = pytest.importorskip("rclpy")
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from geometry_msgs.msg import WrenchStamped
from std_msgs.msg import Bool, String
from ati_daq_ft.core import Calibration

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "examples/synthetic.xml"


@pytest.mark.parametrize(
    "missing_calibration,via_launch", [(False, False), (True, False), (False, True)]
)
def test_ros_calibrated_replay_and_retained_health(
    tmp_path, missing_calibration, via_launch
):
    row = next(csv.DictReader((ROOT / "examples/replay.csv").open()))
    replay = tmp_path / "replay.csv"
    with replay.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerows([row] * 100)
    namespace = "/ati_test_" + uuid.uuid4().hex[:8]
    if not rclpy.ok():
        rclpy.init()
    observer = rclpy.create_node("ati_replay_observer")
    received = []
    health = []
    states = []
    latched = QoSProfile(
        depth=1,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        reliability=ReliabilityPolicy.RELIABLE,
    )
    observer.create_subscription(
        WrenchStamped, namespace + "/wrench", received.append, 10
    )
    observer.create_subscription(
        Bool, namespace + "/ready", lambda m: health.append(m.data), latched
    )
    observer.create_subscription(
        String,
        namespace + "/state",
        lambda m: states.append(json.loads(m.data)),
        latched,
    )
    from ament_index_python.packages import get_package_prefix

    executable = str(
        Path(get_package_prefix("ati_daq_ft")) / "lib/ati_daq_ft/ati_daq_node"
    )
    parameters = {
        "source": "replay",
        "replay_csv": str(replay),
        "sample_rate": "40.0",
        "block_size": "1",
        "calibration_file": str(
            tmp_path / "missing.cal" if missing_calibration else CAL
        ),
    }
    if via_launch:
        command = [
            "ros2",
            "launch",
            "ati_daq_ft",
            "ati_daq_ft.launch.py",
            "namespace:=" + namespace,
        ]
        command += [name + ":=" + value for name, value in parameters.items()]
    else:
        command = [executable, "--ros-args", "-r", "__ns:=" + namespace]
        for name, value in parameters.items():
            command += ["-p", name + ":=" + value]
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env={**os.environ, "ATI_DAQ_FT_RUNTIME": str(tmp_path / "NO_NI_RUNTIME")},
    )
    try:
        end = time.monotonic() + 6
        while time.monotonic() < end:
            rclpy.spin_once(observer, timeout_sec=0.05)
            if states and states[-1]["error"] == "Replay complete":
                break
        assert proc.poll() is None, "Driver process failed before shutdown"
        if missing_calibration:
            assert not received and not any(health)
            assert states[-1]["sensor_serial"] is None
            return
        assert len(received) >= 10
        cal = Calibration(CAL)
        try:
            expected = cal.convert([float(row[f"ai{i}_V"]) for i in range(7)])
        finally:
            cal.close()
        m = received[0]
        f, t = m.wrench.force, m.wrench.torque
        assert [f.x, f.y, f.z, t.x, t.y, t.z] == pytest.approx(expected)
        assert m.header.frame_id == "ft_sensor"
        stamps = [m.header.stamp.sec * 10**9 + m.header.stamp.nanosec for m in received]
        assert all(b > a for a, b in zip(stamps, stamps[1:]))
        assert True in health and health[-1] is False
        assert (
            states[-1]["simulated"]
            and states[-1]["sensor_serial"] == "SYNTHETIC_TEST_ONLY"
        )
        assert states[-1]["calibration_sha256"]
        # A late subscriber must also receive the final not-ready state.
        late = []
        observer.create_subscription(
            Bool, namespace + "/ready", lambda m: late.append(m.data), latched
        )
        end = time.monotonic() + 1
        while not late and time.monotonic() < end:
            rclpy.spin_once(observer, timeout_sec=0.05)
        assert late == [False]
        count = len(received)
        for _ in range(5):
            rclpy.spin_once(observer, timeout_sec=0.03)
        assert len(received) == count, "Wrench messages continued after EOF"
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
        try:
            output = proc.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            output = proc.communicate(timeout=2)[0]
        observer.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        print(output)
        assert proc.returncode == 0, "Driver/launch failed during shutdown"
        assert "Traceback" not in output
        assert "process has died" not in output
