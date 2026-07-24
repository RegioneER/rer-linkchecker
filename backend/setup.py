try:
    from setuptools import setup
except ImportError:
    print("setuptools not found, skipping setup()")

    def setup():
        pass


setup()
