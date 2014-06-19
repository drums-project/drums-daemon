#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

try:
    from setuptools.core import setup
except ImportError:
    from distutils.core import setup


def get_version():
    INIT = os.path.abspath(os.path.join(os.path.dirname(__file__), 'drumsd.py'))
    f = open(INIT, 'r')
    try:
        for line in f:
            if line.startswith('__version__'):
                ret = eval(line.strip().split(' = ')[1])
                assert ret.count('.') == 2, ret
                for num in ret.split('.'):
                    assert num.isdigit(), ret
                return ret
        else:
            raise ValueError("couldn't find version string")
    finally:
        f.close()

VERSION = get_version()

setup(
    name='drums-daemon',
    version=VERSION,
    author='Mani Monajjemi',
    author_email='mmonajje@sfu.ca',
    packages=[],
    url='http://autonomylab.org/drums/',
    license='Apache License 2.0',
    install_requires=[
        'bottle >= 0.10', 'drums >= 0.9', 'pyzmq >= 2.2', 'msgpack-python', 'python-daemon==1.6'],
    description='TODO',
    scripts=["drumsd.py"]
    #test_suite= 'test.test_drumsd.get_suite'
)
