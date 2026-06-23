from setuptools import setup, find_packages

setup(
    name="protogen",
    version="1.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    entry_points={
        "console_scripts": [
            "protogen=protogen.cli:main",
        ],
    },
)
