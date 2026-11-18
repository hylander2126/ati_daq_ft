# Clean userspace validation. No host NI installation or ROS workspace is mounted.
FROM ros:jazzy-ros-base AS software
SHELL ["/bin/bash", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev python3-rosdep python3-colcon-ros python3-colcon-bash \
    python3-colcon-package-selection python3-colcon-test-result
COPY . /ws/src/ati_daq_ft
WORKDIR /ws
RUN source /opt/ros/jazzy/setup.bash && rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    colcon build --packages-select ati_daq_ft
RUN source install/setup.bash && \
    colcon test --packages-select ati_daq_ft --event-handlers console_direct+ --return-code-on-test-failure && \
    colcon test-result --verbose
ENTRYPOINT []
CMD ["bash"]

FROM software AS hardware
RUN apt-get update && apt-get install -y --no-install-recommends libarchive-tools usbutils udev
RUN python3 src/ati_daq_ft/scripts/prepare_runtime.py \
    --output /opt/ati_daq_ft/runtime --cache /opt/ati_daq_ft/downloads
RUN python3 src/ati_daq_ft/scripts/setup_system.py \
    --runtime /opt/ati_daq_ft/runtime --cache /opt/ati_daq_ft/downloads --skip-udev-reload
ENV ATI_DAQ_FT_RUNTIME=/opt/ati_daq_ft/runtime
