# Introduction

Welcome to laze, a ninja build file generator.
Aspires to be the next goto-alternative to make.

# Requirements

- python3
- ninja

# Installation

    $ apt-get install ninja
    $ pip3 install --user laze

# Getting started

Laze is very early in its development, thus getting started currently is way
more complicated (and verbose) than necesary.

Anyhow, there's an example project in the examples folder.
After installing laze, you can check out this repository, then build the example
project with these commands:

    $ cd example
    $ laze generate build.yml
    $ ninja
    $ ./hello/bin/host/hello.elf

# Documentation

TODO.

# License

laze is licensed under the terms of GPLv3.
