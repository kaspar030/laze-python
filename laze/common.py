import laze.constants as const

class InvalidArgument(Exception):
    pass


class ParseError(Exception):
    pass


def locate_project_root():
    project_filename = const.PROJECT_FILENAME

    while True:
        cwd = os.getcwd()
        if os.path.isfile(project_filename):
            return cwd
        else:
            if cwd == "/":
                return None
            else:
                os.chdir("..")
