#!/usr/bin/env python3

import click

from .generate import generate
from .create import create

@click.group()
def cli():
    pass

cli.add_command(generate)
cli.add_command(create)
