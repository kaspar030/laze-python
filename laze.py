#!/usr/bin/env python3

import click

from generate import generate

@click.group()
def cli():
    pass

cli.add_command(generate)

if __name__ == '__main__':
    cli()
