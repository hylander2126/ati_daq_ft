"""Explicit short acquisition check. Requires a real DAQ and matching calibration.

This is intentionally outside pytest discovery. It never requests tare or robot motion.
"""

import argparse
import json
import os
import signal
import subprocess
import time

import rclpy
from ament_index_python.packages import get_package_prefix
from geometry_msgs.msg import WrenchStamped
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--sensor-serial", required=True)
    parser.add_argument("--daq-serial", required=True)
    args = parser.parse_args()
    rclpy.init()
    observer = rclpy.create_node("ati_container_observer")
    stamps, receipts, states = [], [], []

    def on_wrench(msg):
        stamps.append(msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec)
        receipts.append(time.monotonic())

    retained = QoSProfile(
        depth=1,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        reliability=ReliabilityPolicy.RELIABLE,
    )
    observer.create_subscription(
        WrenchStamped, "/ati_container_check/wrench", on_wrench, 1000
    )
    observer.create_subscription(
        String,
        "/ati_container_check/state",
        lambda msg: states.append(json.loads(msg.data)),
        retained,
    )
    command = [
        "ros2",
        "launch",
        "ati_daq_ft",
        "ati_daq_ft.launch.py",
        "namespace:=ati_container_check",
        "calibration_file:=" + args.calibration,
        "sensor_serial:=" + args.sensor_serial,
        "daq_serial:=" + args.daq_serial,
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and (
            not receipts or time.monotonic() - receipts[0] < 3
        ):
            rclpy.spin_once(observer, timeout_sec=0.02)
            if process.poll() is not None:
                raise RuntimeError("Driver exited before acquisition completed")
            if states and states[-1]["error"] not in ("", "Starting"):
                raise RuntimeError(states[-1]["error"])
        duration = receipts[-1] - receipts[0] if len(receipts) > 1 else 0
        rate = (len(receipts) - 1) / duration if duration else 0
        report = {
            "package_prefix": get_package_prefix("ati_daq_ft"),
            "sample_count": len(stamps),
            "observer_duration_s": duration,
            "observer_rate_hz": rate,
            "scan_stamp_step_ns": sorted(
                set(b - a for a, b in zip(stamps, stamps[1:]))
            ),
            "latest_state": states[-1] if states else None,
        }
        print(json.dumps(report, indent=2), flush=True)
        assert len(stamps) >= 1000, "Expected at least 1000 calibrated samples"
        assert states[-1]["ready"] and not states[-1]["simulated"]
        assert states[-1]["sensor_serial"] == args.sensor_serial
        assert states[-1]["daq_serial"] == args.daq_serial.upper()
        assert all(b > a for a, b in zip(stamps, stamps[1:])), (
            "Non-increasing timestamps"
        )
        assert 450 < rate < 550, "Unexpected delivery rate"
        assert states[-1]["dropped_samples"] == 0, "Driver reported dropped scans"
    finally:
        if process.poll() is None:
            # Launch forwards SIGINT to its node. Signalling the whole group would
            # deliver it twice and can interrupt the node's cleanup.
            process.send_signal(signal.SIGINT)
        try:
            output = process.communicate(timeout=8)[0]
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output = process.communicate(timeout=3)[0]
        print(output, flush=True)
        observer.destroy_node()
        rclpy.shutdown()
        assert process.returncode == 0, "Launch did not exit cleanly"
        assert "Traceback" not in output, "Driver reported an unexpected traceback"
        assert "process has died" not in output, "Driver did not exit cleanly"


if __name__ == "__main__":
    main()
