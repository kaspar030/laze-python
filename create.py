import glob, os, sys

import click
from util import uniquify, split

@click.command()
@click.option('_type', '--type', type=click.Choice(['app', 'module', 'subdir']), default='app')
@click.option('--name')
@click.option('--context')
@click.option('--depends', multiple=True)
@click.option('--uses', multiple=True)
@click.option('--sources', multiple=True)
@click.option('--auto-sources', is_flag=True)
def create(_type, name, context, depends, uses, sources, auto_sources):
    if os.path.isfile('build.yml'):
        print("laze: error: 'build.yml' already exists.")
        sys.exit(1)

    with open('build.yml', 'w') as f:
        print("%s:" % _type, file=f)

        if _type=='subdir':
            for dirname in glob.glob('*/'):
                print("        - %s" % dirname.rstrip("/"), file=f)
            return

        if name:
            print("    name: %s" % name, file=f)

        if context:
            print("    context: %s" % name, file=f)

        if depends:
            depends = list(depends)
            split(depends)
            if depends:
                print("    depends:", file=f)
                for dep in uniquify(sorted(depends)):
                    if dep:
                        print("        - %s" % dep, file=f)

        if uses:
            print("    uses:", file=f)
            uses = list(uses)
            split(uses)
            if uses:
                for dep in uniquify(sorted(uses)):
                    if dep:
                        print("        - %s" % dep, file=f)

        if sources:
            sources = list(sources)
            split(sources)

        if not sources and auto_sources:
            sources = []
            for filename in glob.glob('*.c') + glob.glob('*.cpp') + glob.glob('*.s') + glob.glob('*.S'):
                sources.append(filename)

        if sources:
            print("    sources:", file=f)
            for filename in uniquify(sorted(sources)):
                print("        - %s" % filename, file=f)
