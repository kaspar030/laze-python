import os
import subprocess

queue = {}


def git_clone(source, target):
    if os.path.isdir(os.path.join(target, ".git")):
        print(
            'laze: skip cloning "%s" to "%s", target already exists.' % (source, target)
        )
        return

    print('laze: cloning "%s" to "%s"' % (source, target))
    subprocess.check_call(["git", "clone", source, target])


def add_to_queue(download_source, target):
    queue[target] = download_source


def start():
    for target, source in queue.items():
        if source.startswith("https://github.com/"):
            git_clone(source, target)
        elif source.endswith(".git"):
            git_clone(source, target)
