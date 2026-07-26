try:
    from setuptools import setup
except ImportError:
    print("setuptools not found, skipping setup()")

    def setup(**kwargs):
        pass


# python_requires/classifiers are duplicated here (kept in sync with
# pyproject.toml) only so that check-python-versions, which statically
# parses this file, doesn't flag a mismatch against pyproject.toml.
setup(
    python_requires=">=3.11,<3.14",
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
