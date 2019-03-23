import os
import sys

from laze.debug import dprint
import laze.constants as const
from laze.util import dump_dict


class InvalidArgument(Exception):
    pass


class ParseError(Exception):
    pass


def locate_project_root(start_dir=None):
    if start_dir is None:
        start_dir = os.getcwd()

    project_filename = const.PROJECTFILE_NAME
    while True:
        cwd = os.getcwd()
        if os.path.isfile(project_filename):
            if cwd != start_dir:
                os.chdir(start_dir)
            return cwd
        else:
            if cwd == "/":
                os.chdir(start_dir)
                return None
            else:
                os.chdir("..")


def determine_builddir(path, start_dir, project_root):
    if os.path.isabs(path):
        pass
    elif path.startswith("."):
        path = os.path.abspath(os.path.join(start_dir, path))
    else:
        path = os.path.abspath(os.path.join(project_root, path))

    os.makedirs(path, exist_ok=True)

    return path


def determine_dirs(project_file, project_root, build_dir):
    start_dir = os.getcwd()

    if project_file is None:
        project_file = const.PROJECTFILE_NAME
        project_root = locate_project_root(start_dir)
        if project_root is None:
            print('laze: error: could not locate folder containing "%s"' % project_file)
            sys.exit(1)

        project_file = os.path.normpath(os.path.join(project_root, project_file))

    else:
        project_root = os.path.abspath(project_root)
        project_file = os.path.abspath(project_file)

    dprint("verbose", 'laze: using project root "%s", project file "%s"' % (project_root, project_file))

    project_file = os.path.relpath(project_file, project_root)

    build_dir = determine_builddir(build_dir, start_dir, project_root)
    dprint("verbose", 'laze: using build dir "%s"' % build_dir)
    build_dir = os.path.relpath(build_dir, project_root)

    return start_dir, build_dir, project_root, project_file


def dump_args(builddir, args):
    print("dump_args", args)
    dump_dict((builddir, "laze-args"), args)


def rel_start_dir(start_dir, project_root):
    rel_start_dir = os.path.relpath(start_dir, project_root)

    return rel_start_dir
