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
    packages=['drums'],
    url='http://autonomylab.org/drums/',
    license='Apache License 2.0',
    install_requires=[
        'pcapy==0.10.8', 'psutil>=2.0', 'setproctitle', 'bottle>=0.10.1', 'pyzmq>=2.2', 'msgpack-python', 'python-daemon==1.6'],
    dependency_links = ['https://github.com/CoreSecurity/pcapy/archive/0.10.8.tar.gz#egg=pcapy-0.10.8'],
    description='drums is a system monitoring tool. It provides an easy to use async API to register system monitoring tasks.',
    download_url = "https://github.com/drums-project/drums-daemon/tarball/%s" % (VERSION,), 
    scripts=["drumsd.py"],
    test_suite='test.test_drums.get_suite'
)
