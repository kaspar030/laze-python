#!/usr/bin/env python3

from setuptools import setup
# To use a consistent encoding
from codecs import open
from os import path

PACKAGE = 'laze'


def get_long_description():
    # Get the long description from the README file
    with open('README.md', encoding='utf-8') as f:
        return f.read()


def get_version():
    """Get the version from package __init__.py file."""
    with open(path.join(PACKAGE, '__init__.py'), encoding='utf-8') as f:
        for line in f:
            if line.startswith('__version__'):
                return eval(line.split('=')[-1])

setup(
    name=PACKAGE,
    version=get_version(),

    description='laze: a ninja buildfile generator',
    long_description=get_long_description(),

    url='https://github.com/kaspar030/laze',

    author='Kaspar Schleiser',
    author_email='kaspar@schleiser.de',

    license='GPLv3',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],

    keywords='build tool',
    packages=[PACKAGE],
    install_requires=['click', 'pyyaml', 'ninja_syntax'],
    entry_points={
        'console_scripts': [
            'laze=laze.laze:cli',
        ],
    },
)