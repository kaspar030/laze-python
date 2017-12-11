#!/usr/bin/env python3

from setuptools import setup
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Get the version from file
with open(path.join(here, 'laze/version.py'), encoding='utf-8') as f:
    _version = f.read()

version = _version.split("=")[1].lstrip().rstrip().lstrip('"').rstrip('"')

setup(
    name='laze',
    version=version,

    description='laze: a ninja buildfile generator',
    long_description=long_description,

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

        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

    keywords='build tool',
    packages=['laze'],
    install_requires=['click', 'pyyaml', 'ninja_syntax'],
    entry_points={
        'console_scripts': [
            'laze=laze.laze:cli',
        ],
    },
)
