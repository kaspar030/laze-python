# Introduction

Welcome to laze, a ninja build file generator.

# Requirements

- python3
- ninja

    $ sudo apt-get install ninja
    $ pip3 install --user .

# Usage

    $ cd example
    $ laze generate build.yml
    $ ninja
    $ ./hello/bin/host/hello.elf
    Hello World!

# License

laze is licensed under the terms of GPLv3.
