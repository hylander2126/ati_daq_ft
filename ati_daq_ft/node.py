"""Single-owner buffered ATI DAQ acquisition; SI wrench + retained health."""

import hashlib
import json
import queue
import signal
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from geometry_msgs.msg import WrenchStamped
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from std_msgs.msg import Bool, String
from std_srvs.srv import SetBool
from rcl_interfaces.msg import ParameterDescriptor

from .core import AnalogReader, Calibration, initialize_runtime
from .model import transform_wrench
from .firmware import ensure_loaded


class ATIDAQNode(Node):
    def __init__(self):
        super().__init__("ati_daq_ft")
        defaults = {
            "device": "Dev1",
            "daq_serial": "",
            "calibration_file": "",
            "sensor_serial": "",
            "calibration_index": 1,
            "terminal": "diff",
            "sample_rate": 500.0,
            "block_size": 5,
            "frame_id": "ft_sensor",
            "axes_frame": "",
            "mount_profile_sha256": "",
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "sensor_origin_in_output_m": [0.0, 0.0, 0.0],
            "allow_driver_tare": False,
            "stale_timeout": 0.25,
        }
        self.cfg = {
            k: self.declare_parameter(k, v, ParameterDescriptor(read_only=True)).value
            for k, v in defaults.items()
        }
        if not 0 < float(self.cfg["sample_rate"]) <= 10000:
            raise ValueError("Invalid sample_rate")
        if not 1 <= int(self.cfg["block_size"]) <= 1000:
            raise ValueError("Invalid block_size")
        if float(self.cfg["block_size"]) / float(self.cfg["sample_rate"]) > 0.1:
            raise ValueError("Acquisition batch must be <=100 ms")
        if self.cfg["stale_timeout"] <= 0:
            raise ValueError("stale_timeout must be positive")
        transform_wrench(
            [0.0] * 6, self.cfg["rotation_xyzw"], self.cfg["sensor_origin_in_output_m"]
        )
        latched = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.wrench_pub = self.create_publisher(WrenchStamped, "wrench", 10)
        self.ready_pub = self.create_publisher(Bool, "ready", latched)
        self.state_pub = self.create_publisher(String, "state", latched)
        self.diag_pub = self.create_publisher(DiagnosticArray, "diagnostics", 10)
        self.tare_srv = self.create_service(SetBool, "set_tare", self.set_tare)
        self.stop = threading.Event()
        self._tare = queue.Queue()
        self.pending = queue.Queue(maxsize=4)
        self.last_valid_publish = None
        self.ready = False
        self.error = "Starting"
        self.last_acquired = None
        self.latest = None
        self.first_acquired = None
        self.first_batch_count = 0
        self.received = 0
        self.dropped = 0
        self.published = 0
        self.started = time.monotonic()
        self.cal = None
        self.cal_hash = None
        self.tare_active = False
        self.daq_serial = None
        self.ended = False
        try:
            self.cal = Calibration(
                self.cfg["calibration_file"], self.cfg["calibration_index"]
            )
            self.cal_hash = hashlib.sha256(
                Path(self.cfg["calibration_file"]).read_bytes()
            ).hexdigest()
            if (
                self.cfg["sensor_serial"]
                and self.cal.serial != self.cfg["sensor_serial"]
            ):
                raise ValueError(
                    f"Expected sensor {self.cfg['sensor_serial']}, calibration is {self.cal.serial}"
                )
        except Exception as e:
            if self.cal:
                self.cal.close()
                self.cal = None
            self.error = f"Calibration unavailable: {e}"
        self.hardware_error = None
        try:
            # ROS/DDS is initialized; keep NI's initializing thread alive to exit.
            initialize_runtime()
        except Exception as e:
            self.hardware_error = str(e)
            self.error = self.hardware_error
        self.publish_state()
        self.thread = threading.Thread(
            target=self.acquire, name="ati-acquisition", daemon=True
        )
        self.thread.start()
        self.create_timer(0.002, self.drain)
        self.create_timer(1.0, self.publish_state)

    def set_tare(self, req, res):
        if not self.cfg["allow_driver_tare"]:
            res.success = False
            res.message = "Driver tare disabled; launch with allow_driver_tare:=true to enable it."
        elif not self.ready:
            res.success = False
            res.message = "Cannot tare without a current calibrated stream."
        else:
            self._tare.put(req.data)
            res.success = True
            res.message = "Tare requested; state reports when it has been applied."
        return res

    def acquire(self):
        reader = None
        try:
            if self.hardware_error:
                raise RuntimeError(self.hardware_error)
            ensure_loaded()
            if self.stop.is_set():
                return
            reader = AnalogReader(
                self.cfg["device"],
                self.cfg["terminal"],
                self.cfg["sample_rate"],
                self.cfg["block_size"],
                self.cfg["daq_serial"],
            )
            self.daq_serial = reader.serial
            anchor = None
            scan = 0
            period = 1e9 / float(self.cfg["sample_rate"])
            tare_rows = []
            taring = False
            while not self.stop.is_set():
                rows = reader.read_block()
                acquired = time.monotonic()
                if anchor is None:
                    anchor = self.get_clock().now().nanoseconds - round(
                        (len(rows) - 1) * period
                    )
                records = []
                while not self._tare.empty():
                    enable = self._tare.get_nowait()
                    tare_rows = []
                    taring = enable
                    if not enable and self.cal:
                        self.cal.clear_bias()
                        self.tare_active = False
                for volts in rows:
                    if taring:
                        tare_rows.append(volts)
                        if len(tare_rows) == 200:
                            self.cal.bias(
                                [
                                    sum(r[i] for r in tare_rows) / len(tare_rows)
                                    for i in range(7)
                                ]
                            )
                            taring = False
                            self.tare_active = True
                    wrench = None
                    if self.cal:
                        wrench = transform_wrench(
                            self.cal.convert(volts),
                            self.cfg["rotation_xyzw"],
                            self.cfg["sensor_origin_in_output_m"],
                        )
                    records.append((anchor + round(scan * period), volts, wrench))
                    scan += 1
                if self.first_acquired is None:
                    self.first_acquired = acquired
                    self.first_batch_count = len(rows)
                self.last_acquired = acquired
                self.received += len(rows)
                # Bounded latency: drop an old batch rather than grow backlog.
                try:
                    self.pending.put_nowait((acquired, records))
                except queue.Full:
                    try:
                        self.dropped += len(self.pending.get_nowait()[1])
                    except queue.Empty:
                        pass
                    self.pending.put_nowait((acquired, records))
            if not self.stop.is_set():
                self.error = "Acquisition stopped"
        except Exception as e:
            self.error = str(e)
            self.get_logger().error("Acquisition stopped: " + self.error)
        finally:
            if reader:
                reader.close()
            self.ended = True

    def drain(self):
        now = time.monotonic()
        while not self.pending.empty():
            try:
                acquired, records = self.pending.get_nowait()
            except queue.Empty:
                break
            if now - acquired > self.cfg["stale_timeout"]:
                self.dropped += len(records)
                continue
            for stamp, volts, wrench in records:
                self.latest = (stamp, volts)
                # Inferred scan times are anchored to host receipt, never refreshed on republish.
                if wrench is None:
                    continue
                age = (self.get_clock().now().nanoseconds - stamp) / 1e9
                if age > self.cfg["stale_timeout"] or age < -0.05:
                    self.dropped += 1
                    continue
                msg = WrenchStamped()
                msg.header.stamp.sec = stamp // 1000000000
                msg.header.stamp.nanosec = stamp % 1000000000
                msg.header.frame_id = self.cfg["frame_id"]
                f, t = msg.wrench.force, msg.wrench.torque
                f.x, f.y, f.z, t.x, t.y, t.z = wrench
                self.wrench_pub.publish(msg)
                self.published += 1
                self.last_valid_publish = now
        ready = (
            not self.ended
            and self.cal is not None
            and self.last_valid_publish is not None
            and now - self.last_valid_publish <= self.cfg["stale_timeout"]
        )
        if ready != self.ready:
            self.ready = ready
            if ready:
                self.error = ""
            self.publish_state()

    def publish_state(self):
        state = {
            "ready": self.ready,
            "error": self.error,
            "source": "hardware",
            "simulated": False,
            "sensor_serial": self.cal.serial if self.cal else None,
            "daq_serial": self.daq_serial,
            "calibration_file": self.cfg["calibration_file"],
            "calibration_sha256": self.cal_hash,
            "temperature_compensation": self.cal.tempcomp if self.cal else None,
            "frame_id": self.cfg["frame_id"],
            "axes_frame": self.cfg["axes_frame"] or self.cfg["frame_id"],
            "mount_profile_sha256": self.cfg["mount_profile_sha256"],
            "sensor_origin_in_output_m": self.cfg["sensor_origin_in_output_m"],
            "rotation_xyzw": self.cfg["rotation_xyzw"],
            "configured_sample_rate_hz": self.cfg["sample_rate"],
            "observed_delivery_rate_hz": (self.received - self.first_batch_count)
            / (self.last_acquired - self.first_acquired)
            if self.first_acquired and self.last_acquired > self.first_acquired
            else None,
            "received_samples": self.received,
            "published_samples": self.published,
            "dropped_samples": self.dropped,
            "tare_active": self.tare_active,
            "timestamp_basis": "host receipt anchor + hardware scan period; not hardware absolute time",
        }
        self.ready_pub.publish(Bool(data=self.ready))
        self.state_pub.publish(String(data=json.dumps(state)))
        diag = DiagnosticArray()
        diag.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus(
            name=self.get_fully_qualified_name(),
            hardware_id=self.daq_serial or "unconnected",
            level=DiagnosticStatus.OK if self.ready else DiagnosticStatus.ERROR,
            message=self.error
            or ("Ready" if self.ready else "No fresh calibrated stream"),
        )
        status.values = [KeyValue(key=k, value=str(v)) for k, v in state.items()]
        if self.latest:
            stamp, volts = self.latest
            status.values.extend(
                [KeyValue(key=f"ai{i}_V", value=str(v)) for i, v in enumerate(volts)]
            )
            status.values.append(
                KeyValue(key="voltage_sample_stamp_ns", value=str(stamp))
            )
        diag.status = [status]
        self.diag_pub.publish(diag)

    def shutdown(self):
        self.stop.set()
        self.thread.join(timeout=3)
        self.ready = False
        self.error = "Stopped"
        self.publish_state()
        if self.cal and not self.thread.is_alive():
            self.cal.close()
            self.cal = None


def main():
    # Keep the context valid until acquisition/NI teardown and final health publish.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, signal.default_int_handler)
    node = None
    try:
        node = ATIDAQNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # A terminal SIGINT can reach both launch and the node; launch then forwards
        # it again. Let the bounded cleanup finish instead of interrupting it twice.
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, signal.SIG_IGN)
        if node:
            if rclpy.ok():
                node.shutdown()
            else:
                node.stop.set()
                node.thread.join(timeout=3)
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
