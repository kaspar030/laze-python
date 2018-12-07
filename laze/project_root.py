import os

from laze.constants import PROJECTFILE_NAME as project_filename

def locate_project_root():
    while True:
        cwd = os.getcwd()
        if os.path.isfile(project_filename):
            return cwd
        else:
            if cwd == "/":
                return None
            else:
                os.chdir("..")
