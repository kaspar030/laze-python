#!/usr/bin/env python3

import copy
import os
import re
import subprocess
import sys
import time
import yaml

import click

from laze.common import determine_dirs


@click.command()
@click.option("--project-file", "-f", type=click.STRING, envvar="LAZE_PROJECT_FILE")
@click.option(
    "--build-dir", "-B", type=click.STRING, default="build", envvar="LAZE_BUILDDIR"
)
def build(project_file, build_dir):
    start_dir, build_dir, build_dir_rel, project_root, project_file = determine_dirs(
        project_file, build_dir
    )
    subprocess.check_call(["ninja", "-f", os.path.join(build_dir, "build.ninja")])
