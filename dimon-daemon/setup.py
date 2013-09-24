import os

try:
    from setuptools.core import setup
except ImportError:
    from distutils.core import setup

def get_version():
    INIT = os.path.abspath(os.path.join(os.path.dirname(__file__), 'dimond.py'))
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
    name = 'dimon-daemon',
    version = VERSION,
    author = 'Mani Monajjemi',
    author_email = 'TODO',
    packages = [],
    url = 'TODO',
    license = 'LICENSE',
    install_requires = ['bottle', 'dimon', 'zmq', 'msgpack'],
    description = 'TODO',
    scripts = ["dimond.py"],
    test_suite = 'test.test_dimond.get_suite'
)
