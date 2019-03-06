#!/usr/bin/env python3

import copy
import os
import re
import subprocess
import sys
import time
import yaml

import click

from laze.util import uniquify, load_dict
from laze.common import determine_dirs

@click.command()
@click.option("--project-file", "-f", type=click.STRING, envvar="LAZE_PROJECT_FILE")
@click.option("--project-root", "-r", type=click.STRING, envvar="LAZE_PROJECT_ROOT")
@click.option(
    "--build-dir", "-B", type=click.STRING, default="build", envvar="LAZE_BUILDDIR"
)
@click.option("--builders", "-b", type=click.STRING, envvar="LAZE_BUILDERS", multiple=True)
@click.option("--tool", "-t", type=click.STRING, envvar="LAZE_TOOL")
@click.option("--no-update", "-n", type=click.BOOL, is_flag=True, envvar="LAZE_NO_UPDATE")
@click.option("--global/--no-global", "-g", "_global", default=False, envvar="LAZE_GLOBAL")
@click.option("--verbose", "-v", type=click.BOOL, is_flag=True, envvar="LAZE_VERBOSE")
@click.argument("targets", nargs=-1)
def build(project_file, project_root, build_dir, tool, targets, builders, no_update, _global, verbose):
    start_dir, build_dir, project_root, project_file = determine_dirs(
        project_file, project_root, build_dir
    )

    targets = list(targets)
    builders = list(builders)
    if builders:
        builder_set = set(builders)
    if targets:
        target_set = set(targets)

    try:
        laze_args = load_dict((build_dir, "laze-args"))
    except FileNotFoundError as e:
        laze_generate_args = ["laze", "generate"]
        if project_file:
            laze_generate_args += ["-f", project_file]
        if project_root:
            laze_generate_args += ["-r", project_root]
        if build_dir:
            laze_generate_args += ["-B", build_dir]
        for builder in builders:
            laze_generate_args += ["-b", builder ]
        subprocess.check_call(laze_generate_args)
        laze_args = load_dict((build_dir, "laze-args"))

    if tool:
        app_target_map = {}

    #
    # target filtering / selection
    #
    # unless "--global" is specified, all builder / app combinations
    # will be filtered by what's defined in the folder from where
    # laze was launched.
    #
    if _global:
        print("global")
        pass
    else:
        rel_start_dir = os.path.relpath(start_dir, project_root)

        # if laze is started from the project root, the relative path will be ".".
        # but "laze generate" uses "" for the root folder, so adjust here.
        if rel_start_dir == ".":
            rel_start_dir = ""

        print("laze: local mode in \"%s\"" % rel_start_dir)

        laze_local = load_dict((build_dir, "laze-app-per-folder"))[rel_start_dir]

        ninja_targets = []
        for app, builder_target in laze_local.items():
            for builder, target in builder_target.items():
                if builders:
                    if not builder in builder_set:
                        continue
                if targets:
                    if not app in targets:
                        continue
                print("laze: building %s for %s" % (app, builder))
                ninja_targets.append(target)
                if tool:
                    app_target_map[target] = (app, builder)

        targets = ninja_targets

    app_builder_tool_target_list = []
    if tool:
        if not ninja_targets:
            print("laze: tool specified but no target given (or locally available).")
            sys.exit(1)

        if len(ninja_targets) > 1:
            print("laze: multiple targets for tool %s specified.")
            print("laze: if this is what you want, add --multi-tool / -m")
            sys.exit(1)

        tools = load_dict((build_dir, "laze-tools"))

        for ninja_target in ninja_targets:
            target_tools = tools.get(ninja_target, {})
            app, builder = app_target_map[ninja_target]


            tool = target_tools.get(tool)
            if not tool:
                print("laze: target %s builder %s doesn't support tool %s" % (ninja_target, builder, tool))
                sys.exit(1)

            app_builder_tool_target_list.append((app, builder, ninja_target, tool))

    if targets and not ninja_targets:
        print("no ninja targets, passing through")
        ninja_targets = targets

    ninja_extra_args = []
    if verbose:
        ninja_extra_args += ["-v"]

    ninja_build_file = os.path.join(build_dir, "build.ninja")

    try:
        subprocess.check_call(["ninja", "-f", ninja_build_file] + ninja_extra_args + ninja_targets, cwd=project_root)
    except subprocess.CalledProcessError:
        sys.exit(1)

    for app, builder, ninja_target, tool in app_builder_tool_target_list:
        for cmd in tool["cmd"]:
            try:
                subprocess.check_call(cmd, shell=True, cwd=project_root)
            except subprocess.CalledProcessError:
                print("laze: error executing \"%s\" (tool=%s, target=%s, builder=%s)" % (cmd, tool, target, builder))
                sys.exit(1)
