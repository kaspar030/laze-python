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

Create two files:

hello.c:

```

#include <stdio.h>

int main(int argc, const char *argv[])
{
    printf("Laze says hello!\n");
    return 0;
}
```

laze-project.yml:

```
# import default build rules and host context
import:
    - $laze/default

# define an application named "hello"
app:
    name: hello
    sources:
        - hello.c
```

Then compile & run:

    $ laze -t run


# Documentation

TODO.

# License

laze is licensed under the terms of GPLv3.
