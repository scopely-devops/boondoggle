from setuptools import setup
from boondoggle import __version__


setup(
    name="boondoggle",
    version=__version__,
    author="Scopely",
    author_email="ops@scopely.com",
    description=(
        "A script to deploy server fleets using pre-baked AMIs"
    ),
    include_package_data=True,
    scripts=['scripts/boondoggle'],
    keywords="aws cli fleet ec2 ami",
    url="https://github.com/scopely-devops/boondoggle",
    install_requires=['docopt', 'boto', 'PyYAML'],
    packages=['boondoggle'],
    classifiers=[
        "Topic :: Utilities",
    ],
)
