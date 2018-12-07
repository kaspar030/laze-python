#!/usr/bin/env python3

import os
import click

from .generate import generate
from .create import create


@click.group()
@click.option("--chdir", "-C", type=click.STRING)
def cli(chdir):
    if chdir:
        os.chdir(chdir)


cli.add_command(generate)
cli.add_command(create)
