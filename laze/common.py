import os
import sys
from laze.debug import dprint
import laze.constants as const


class InvalidArgument(Exception):
    pass


class ParseError(Exception):
    pass


def locate_project_root():
    project_filename = const.PROJECTFILE_NAME
    while True:
        cwd = os.getcwd()
        if os.path.isfile(project_filename):
            return cwd
        else:
            if cwd == "/":
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


def determine_dirs(project_file, build_dir):
    start_dir = os.getcwd()

    if project_file is None:
        project_file = const.PROJECTFILE_NAME
        project_root = locate_project_root()
        if project_root is None:
            print('laze: error: could not locate folder containing "%s"' % project_file)

            sys.exit(1)

    build_dir = determine_builddir(build_dir, start_dir, project_root)
    build_dir_rel = os.path.relpath(build_dir, project_root)
    dprint("verbose", 'laze: using build dir "%s"' % build_dir)

    return start_dir, build_dir, build_dir_rel, project_root, project_file
