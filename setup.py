from setuptools import setup
from fleet_commander import __version__


setup(
    name="amideploying",
    version=__version__,
    author="Scopely",
    author_email="ops@scopely.com",
    description=(
        "A script to deploy server fleets using pre-baked AMIs"
    ),
    include_package_data=True,
    scripts=['scripts/amideploying'],
    keywords="aws cli fleet ec2 ami",
    url="https://github.com/scopely/devops",
    install_requires=['docopt', 'boto', 'PyYAML'],
    packages=['amideploying'],
    classifiers=[
        "Topic :: Utilities",
    ],
)
