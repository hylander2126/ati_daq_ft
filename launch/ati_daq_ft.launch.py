"""Publish in the sensor frame by default; no robot packages are needed."""

import json
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ati_daq_ft.runtime import environment, runtime_root


def launch_setup(context):
    get = lambda name: LaunchConfiguration(name).perform(context)
    params = {
        name: get(name)
        for name in (
            "calibration_file",
            "sensor_serial",
            "daq_serial",
            "device",
            "terminal",
            "frame_id",
            "axes_frame",
            "mount_profile_sha256",
        )
    }
    params.update(
        sample_rate=float(get("sample_rate")),
        block_size=int(get("block_size")),
        calibration_index=int(get("calibration_index")),
        allow_driver_tare=get("allow_driver_tare").lower() == "true",
        rotation_xyzw=list(map(float, json.loads(get("rotation_xyzw")))),
        sensor_origin_in_output_m=list(
            map(float, json.loads(get("sensor_origin_in_output_m")))
        ),
    )
    return [
        Node(
            package="ati_daq_ft",
            executable="ati_daq_node",
            name="ati_daq_ft",
            namespace=get("namespace"),
            output="screen",
            parameters=[params],
            additional_env=environment(get("runtime_root")),
        )
    ]


def generate_launch_description():
    defaults = {
        "runtime_root": str(runtime_root()),
        "namespace": "ati_daq_ft",
        "calibration_file": "",
        "calibration_index": "1",
        "sensor_serial": "",
        "daq_serial": "",
        "device": "Dev1",
        "terminal": "diff",
        "frame_id": "ft_sensor",
        "axes_frame": "",
        "mount_profile_sha256": "",
        "sample_rate": "500.0",
        "block_size": "5",
        "rotation_xyzw": "[0,0,0,1]",
        "sensor_origin_in_output_m": "[0,0,0]",
        "allow_driver_tare": "false",
    }
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=v) for k, v in defaults.items()]
        + [OpaqueFunction(function=launch_setup)]
    )
