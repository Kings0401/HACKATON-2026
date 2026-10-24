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
    extras_require={"booster": ["boosteros"]},
    zip_safe=True,
    description="Agente de recepción N Club para AGIBOT X2 Ultra y BoosterOS",
    license="Proprietary",
    entry_points={
        "console_scripts": [
            "reception_agent = nclub_agent.ros_node:main",
            "reception_sim = nclub_agent.sim:main",
            "nclub_say = nclub_agent.ros_node:say_main",
            "reception_agent_booster = nclub_agent.booster_camera:main",
        ],
    },
)
