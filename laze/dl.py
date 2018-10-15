import os
import subprocess

from laze.common import InvalidArgument

queue = {}


def git_clone(source, target, commit=None):
    if os.path.isdir(os.path.join(target, ".git")):
        print(
            'laze: skip cloning "%s" to "%s", target already exists.' % (source, target)
        )
        return

    print('laze: cloning "%s" to "%s"' % (source, target))
    subprocess.check_call(["git", "clone", source, target])

    if commit is not None:
        print('laze: setting "%s" to commit %s' % (target, commit))
        subprocess.check_call(["git", "-C", target, "reset", "--hard", commit])


def add_to_queue(download_source, target):
    existing = queue.get(target)
    if existing and (download_source != existing):
        raise InvalidArgument("laze: error: duplicate download target %s" % target)

    queue[target] = download_source


def start():
    for target, source in queue.items():
        error = False
        if type(source) == str:
            if source.startswith("https://github.com/"):
                git_clone(source, target)
            elif source.endswith(".git"):
                git_clone(source, target)
            else:
                error = True

        elif type(source) == dict:
            git = source.get("git")
            if git is not None:
                url = git.get("url")
                if url is None:
                    raise InvalidArgument(
                        "laze: error: git download source %s is missing url"
                    )
                commit = git.get("commit")
                git_clone(url, target, commit)
            else:
                error = True

        if error:
            raise InvalidArgument("laze: error: don't know how to download %s" % source)
