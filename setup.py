from glob import glob
from setuptools import Extension, setup

setup(
    name="ati_daq_ft",
    version="0.1.0",
    packages=["ati_daq_ft"],
    ext_modules=[
        Extension(
            "ati_daq_ft._atidaq",
            sources=["ati_daq_ft/native/atidaq_wrapper.c"]
            + [
                "ati_daq_ft/native/atidaq/ATIDAQ/" + name + ".c"
                for name in (
                    "ftconfig",
                    "ftrt",
                    "dom",
                    "expatls",
                    "node",
                    "stack",
                    "xmlparse",
                    "xmlrole",
                    "xmltok",
                )
            ],
            libraries=["m"],
            extra_link_args=["-Wl,-Bsymbolic"],
        )
    ],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/ati_daq_ft"]),
        (
            "share/ati_daq_ft",
            ["package.xml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.txt"],
        ),
        ("share/ati_daq_ft/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    package_data={"ati_daq_ft": ["native/atidaq/readme.txt"]},
    zip_safe=False,
    maintainer="Steven Hyland",
    maintainer_email="stevenhyland1@gmail.com",
    description="ATI DAQ F/T sensor driver for ROS 2 and NI USB-621x",
    license="MIT",
    entry_points={
        "console_scripts": [
            "ati_daq_node = ati_daq_ft.bootstrap:main",
            "ati_daq_reader = ati_daq_ft.bootstrap:reader_main",
        ]
    },
)
