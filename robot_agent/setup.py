from glob import glob

from setuptools import setup

package = "nclub_agent"

setup(
    name=package,
    version="2.0.0",
    packages=[package],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package}"]),
        (f"share/{package}", ["package.xml"]),
        (f"share/{package}/config", glob("config/*.yaml")),
        (f"share/{package}/launch", glob("launch/*.py")),
    ],
    install_requires=["setuptools", "httpx", "numpy"],
    zip_safe=True,
    description="Agente de recepción N Club para AGIBOT X2 Ultra",
    license="Proprietary",
    entry_points={
        "console_scripts": [
            "reception_agent = nclub_agent.ros_node:main",
            "reception_sim = nclub_agent.sim:main",
        ],
    },
)
