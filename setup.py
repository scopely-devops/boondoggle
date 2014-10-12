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
    keywords="aws cli fleet ec2 ami",
    url="https://github.com/scopely-devops/boondoggle",
    install_requires=['click', 'boto', 'PyYAML'],
    packages=['boondoggle'],
    classifiers=[
        "Topic :: Utilities",
    ],
    entry_points="""
    [console_scripts]
    boondoggle=boondoggle.cli:cli
    """
)
