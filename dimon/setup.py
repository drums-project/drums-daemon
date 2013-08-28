try:
    from setuptools.core import setup
except ImportError:
    from distutils.core import setup

setup(
    name='dimon',
    version='0.1.0',
    author='Mani Monajjemi',
    author_email='TODO',
    packages=['dimon', 'dimon.tests'],
    url='TODO',
    license='LICENSE.txt',
    description='TODO',
    test_suite='demon.tests.get_suite'
)
