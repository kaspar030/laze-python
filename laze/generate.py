#!/usr/bin/env python3

import copy
import os
import re
import sys
import time
import yaml

from collections import defaultdict

from string import Template

import click

from .util import (
    merge,
    listify,
    dict_list_product,
    uniquify,
    deep_replace,
    deep_substitute,
    dict_get,
    static_vars,
    split,
)

from ninja_syntax import Writer
import laze.dl as dl

from laze.common import ParseError, InvalidArgument
import laze.constants as const
from laze.project_root import locate_project_root


files_set = set()
short_module_defines = True


def get_data_folder():
    return os.path.join(os.path.dirname(__file__), "data")


def yaml_load(filename, path=None, defaults=None, parent=None, imports=None):
    def do_include(data):
        includes = listify(data.get("include"))
        for include in includes:
            _data = (
                yaml_load(
                    os.path.join(os.path.dirname(filename), include),
                    path,
                    parent=filename,
                    imports=imports,
                )[0]
                or {}
            )
            _data.pop("ignore", None)
            if "template" in _data:
                raise ParseError(
                    "template statement in included file currently not supported!"
                )
            merge(_data, data, override=True)
            data = _data

        data.pop("include", None)
        return data

    def remember_imports():
        _imports = listify(data.get("import"))
        for _import in _imports:
            imports.append((filename, _import))

    path = path or ""

    # print("yaml_load(): loading %s with relpath %s" % (filename, path))

    files_set.add(filename)
    if parent is None:
        imports = []

    try:
        with open(filename, "r") as f:
            datas = yaml.load_all(f.read())
    except FileNotFoundError as e:
        msg = "laze: error: cannot find %s%s" % (
            filename,
            " (included by %s)" % parent if parent else "",
        )
        raise ParseError(msg) from e

    res = []
    for data in datas:
        remember_imports()

        data_defaults = data.get("defaults", {})

        _defaults = defaults
        if _defaults:
            _defaults = copy.deepcopy(_defaults)
            if data_defaults:
                merge(_defaults, data_defaults)
        else:
            _defaults = data_defaults

        def merge_defaults(data, _defaults):
            if _defaults:
                # print("yaml_load(): merging defaults, base:    ", data)
                # print("yaml_load(): merging defaults, defaults:", _defaults)
                for defaults_key in _defaults.keys():
                    if defaults_key not in data:
                        continue
                    data_val = data.get(defaults_key)
                    defaults_val = _defaults[defaults_key]
                    if type(data_val) == list:
                        for entry in data_val:
                            merge(entry, copy.deepcopy(defaults_val), join_lists=True)
                    else:
                        # print("yaml_load(): merging defaults,", data_val)
                        if data_val == None:
                            data_val = {}
                            data[defaults_key] = data_val
                        merge(data_val, defaults_val, override=False, join_lists=True)
                # print("yaml_load(): merging defaults, result:  ", data)

        merge_defaults(data, _defaults)

        template = data.pop("template", None)

        if template:
            result = []
            i = 0
            for repl in dict_list_product(template):
                _data = copy.deepcopy(data)
                _data["_relpath"] = path
                _data = deep_replace(_data, repl)
                _data = do_include(_data)
                _data["template_instance"] = repl
                _data["template_instance_num"] = i

                result.append(_data)
                i += 1
            res.extend(result)
        else:
            data = do_include(data)
            data["_relpath"] = path
            res.append(data)
            for subdir in listify(data.get("subdirs", [])):
                relpath = os.path.join(path, subdir)
                res.extend(
                    yaml_load(
                        os.path.join(relpath, const.BUILDFILE_NAME),
                        path=relpath,
                        defaults=_defaults,
                        parent=filename,
                        imports=imports,
                    )
                )

    if parent is None:
        while imports:
            # print("IMPORTS:", imports)
            imported_list = []
            imports_as_dicts = []

            # unify all imports so they have the form
            # (importer_filename, import name or URL, possible dictionary)
            for _import_tuple in imports:
                importer_filename, _import = _import_tuple
                if type(_import) is dict:
                    for k, v in _import.items():
                        imports_as_dicts.append((importer_filename, k, v))
                else:
                    imports_as_dicts.append((importer_filename, _import, {}))

            for _import_tuple in imports_as_dicts:
                importer_filename, name, import_dict = _import_tuple

                url = import_dict.get("url")
                version = import_dict.get("version")
                folder_override = import_dict.get("folder_override")

                if url is None:
                    url = name
                    name = os.path.basename(name)

                if url.startswith("$laze/"):
                    dl_source = {
                        "local": {
                            "path": os.path.join(
                                get_data_folder(), url[len("$laze/") :]
                            )
                        }
                    }
                else:
                    dl_source = {"git": {"url": url}}

                folder = os.path.join(".laze/imports", name)
                if version is not None:
                    dl_source["git"]["commit"] = version
                    folder = os.path.join(folder, version)
                else:
                    folder = os.path.join(folder, "latest")

                if folder_override is None:
                    dl.add_to_queue(dl_source, folder)
                else:
                    folder = folder_override

                subdir = import_dict.get("subdir")
                if subdir is not None:
                    folder = os.path.join(folder, subdir)

                imported_list.append((name, importer_filename, folder))

            dl.start()

            imports = []
            for imported in imported_list:
                # print("YY", imported_list)
                name, importer_filename, folder = imported
                res.extend(
                    yaml_load(
                        os.path.join(folder, const.BUILDFILE_NAME),
                        path=folder,
                        parent=importer_filename,
                        imports=imports,
                    )
                )

    return res


class Declaration(object):
    def __init__(self, **kwargs):
        self.args = kwargs
        self.relpath = self.args.get("_relpath")
        self.override_source_location = None

        _vars = self.args.get("vars", {})
        for key, value in _vars.items():
            _vars[key] = listify(value)
        self.args["vars"] = _vars

    def post_parse():
        pass

    def locate_source(self, filename):
        if self.override_source_location:
            res = os.path.join(self.override_source_location, filename)
        else:
            res = os.path.join(self.relpath, filename)
        return res.rstrip("/") or "."


class Context(Declaration):
    map = {}

    def __init__(self, add_to_map=True, **kwargs):
        super().__init__(**kwargs)

        self.name = kwargs.get("name")
        self.parent = kwargs.get("parent")
        self.children = []
        self.modules = {}
        self.vars = None
        self.bindir = self.args.get(
            "bindir", "${bindir}/${name}" if self.parent else "build"
        )

        if add_to_map:
            Context.map[self.name] = self

        self.disabled_modules = set(kwargs.get("disable_modules", []))

        depends(self.name)
        # print("CONTEXT", s.name)

    def __repr__(self, nest=False):
        res = "Context(" if not nest else ""
        res += '"' + self.name + '"'
        if self.parent:
            res += "->" + self.parent.__repr__(nest=True)
        else:
            res += ")"
        return res

    def post_parse():
        for name, context in Context.map.items():
            if context.parent:
                context.parent = Context.map[context.parent]
                context.parent.children.append(context)
                depends(context.parent.name, name)

    def get_module(self, module_name):
        #        print("get_module()", s, s.modules.keys())
        if module_name in self.disabled_modules:
            print("DISABLED_MODULE", self.name, module_name)
            return None
        module = self.modules.get(module_name)
        if not module and self.parent:
            return self.parent.get_module(module_name)
        return module

    def get_vars(self):
        if self.vars:
            pass
        elif self.parent:
            _vars = {}
            pvars = self.parent.get_vars()
            merge(_vars, copy.deepcopy(pvars), override=True, change_listorder=False)
            merge(
                _vars, self.args.get("vars", {}), override=True, change_listorder=False
            )
            self.vars = _vars
        else:
            self.vars = self.args.get("vars", {})

        return self.vars

    def get_bindir(self):
        if "$" in self.bindir:
            _dict = defaultdict(lambda: "", name=self.name)
            if self.parent:
                _dict.update(
                    {"parent": self.parent.name, "bindir": self.parent.get_bindir()}
                )

            self.bindir = Template(self.bindir).substitute(_dict)
        return self.bindir

    def get_filepath(self, filename=None):
        if filename is not None:
            return os.path.join(self.get_bindir(), filename)
        else:
            return self.get_bindir()

    def listed(self, _set):
        if self.name in _set:
            return True
        elif self.parent:
            return self.parent.listed(_set)
        else:
            return False


class Builder(Context):
    pass


class Rule(Declaration):
    rule_var_re = re.compile(r"\${\w+}")
    rule_num = 0
    rule_cached = 0
    rule_map = {}
    rule_name_map = {}
    rule_cache = {}
    file_map = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = self.args["name"]
        self.cmd = self.args["cmd"]
        self.depfile = self.args.get("depfile")
        self.deps = self.args.get("deps")

        try:
            in_ext = self.args["in"]
            if in_ext in Rule.rule_map:
                print("error: %s extension already taken")
                return
            Rule.rule_map[in_ext] = self
        except KeyError:
            pass

        Rule.rule_name_map[self.name] = self

        self.create_var_list()
        global writer
        self.to_ninja(writer)

    def get_by_extension(filename):
        filename, file_extension = os.path.splitext(filename)
        return Rule.rule_map[file_extension]

    def get_by_name(name):
        return Rule.rule_name_map[name]

    def create_var_list(self):
        _var_names = Rule.rule_var_re.findall(self.cmd)
        var_names = []
        for name in _var_names:
            name = name[2:-1]
            if not name in {"in", "out"}:
                var_names.append(name)
        # print("RULE", s.name, "vars:", var_names)
        self.var_list = var_names

    def to_ninja(self, writer):
        writer.rule(
            self.name,
            self.cmd,
            description="%s ${out}" % self.name,
            deps=self.deps,
            depfile=self.depfile,
        )

    def process_var_options(self, name, data):
        """ interpret smart options.

        Use like e.g.,
            var_options:
              includes:
                prefix: -I

        to get a list of path names joined as C include arguments.
        [ "include/foo", "include/bar" ] -> "-Iinclude/foo -Iinclude/bar"
        """

        opts = self.args["var_options"][name]

        joiner = opts.get("joiner", " ")
        prefix = opts.get("prefix", "")
        suffix = opts.get("suffix", "")
        start = opts.get("start", "")
        end = opts.get("end", "")

        return (
            start
            + joiner.join([prefix + entry + suffix for entry in listify(data)])
            + end
        )

    def to_ninja_build(self, writer, _in, _out, _vars=None):
        def control_key(x):
            """ var sort helper key function

            Sorts strings starting with < to the beginning,
            starting with > to the end.
            """

            x = x[0]
            if x == "<":
                return 0
            elif x == ">":
                return 2
            return 1

        _vars = _vars or {}
        # print("RULE", s.name, _in, _out, _vars)
        vars = {}
        for name in self.var_list:
            try:
                data = _vars[name]
                try:
                    data = self.process_var_options(name, data)
                except KeyError:
                    if type(data) == list:
                        data.sort(key=control_key)
                        # drop \, < > if it is at the beginning of a string.
                        data[:] = [x[1:] if x[0] in "\<>" else x for x in data]
                        data = " ".join(data)
                vars[name] = data
            except KeyError:
                pass

        cache_key = hash(
            "rule:%s in:%s vars:%s" % (self.name, _in, hash(frozenset(vars.items())))
        )

        Rule.rule_num += 1
        try:
            cached = Rule.rule_cache[cache_key]
            # print("laze: %s using cached %s for %s %s" % (s.name, cached, _in, _out))
            Rule.rule_cached += 1
            return cached

        except KeyError:
            Rule.rule_cache[cache_key] = _out
            # print("laze: NOCACHE: %s %s ->  %s" % (s.name, _in, _out), vars)
            writer.build(outputs=_out, rule=self.name, inputs=_in, variables=vars)
            return _out


@static_vars(map={})
def depends(name, deps=None):
    dict_get(depends.map, name, set()).update(listify(deps))


def list_remove(_list):
    if _list:
        remove = set()
        for entry in _list:
            if entry[0] == "-":
                remove.add(entry)
                remove.add(entry[1:])

        if remove:
            _set = frozenset(_list)
            for entry in _set & remove:
                _list.remove(entry)


_in = "/-"
_out = "__"

transtab = str.maketrans(_in, _out)


class Module(Declaration):
    class NotAvailable(Exception):
        def __init__(self, context, module, dependency):
            self.context = context
            self.module = module
            self.dependency = dependency

        def __str__(self):
            return '%s in %s depends on unavailable module "%s"' % (
                self.module,
                self.context,
                self.dependency,
            )

    list = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Module.list.append(self)
        self.name = self.args.get("name")
        if not self.name:
            if self.relpath:
                self.name = os.path.dirname(self.relpath + "/")
            else:
                raise InvalidArgument("module missing name")
            self.args["name"] = self.name

        uses = dict_get(self.args, "uses", [])
        list_remove(uses)
        list_remove(self.args.get("depends"))

        for name in listify(self.args.get("depends")):
            if name.startswith("?"):
                uses.append(name[1:])

        self.context = None
        self.get_nested_cache = {}
        self.export_vars = {}

    def post_parse():
        for module in Module.list:
            context_name = module.args.get("context", "default")
            context = Context.map.get(context_name)
            if not context:
                print(
                    "laze: error: module %s refers to unknown context %s"
                    % (module.name, context_name)
                )
            module.context = context
            context.modules[module.args.get("name")] = module
            # print("MODULE", module.name, "in", context)
            module.handle_download(module.args.get("download"))

    def handle_download(self, download):
        if download:
            dldir = os.path.join(".laze", "dl", self.relpath, self.name)
            print("DOWNLOAD", self.name, download, dldir)

            # handle possibly passed subdir parameter
            if type(download) == dict:
                subdir = download.get("subdir")
                if subdir:
                    dldir = os.path.join(dldir, subdir)

            # make "locate_source()" return filenames in downloaded folder/[subdir/]
            self.override_source_location = dldir

            dl.add_to_queue(download, dldir)

    def get_nested(self, context, name, notfound_error=True):
        try:
            # print("get_nested(%s) returning cache " % name, s.name, [ x.name for x in s.get_nested_cache[context][name][s]])
            return self.get_nested_cache[context][name][self]
        except KeyError:
            pass

        module_names = set(listify(self.args.get(name, [])))
        modules = set()
        all_module_names = set()
        while module_names:
            all_module_names |= module_names
            for module_name in module_names:
                if module_name == "all":
                    continue

                optional = module_name.startswith("?")

                if optional:
                    module_name = module_name[1:]

                module = context.get_module(module_name)
                if not module:
                    if notfound_error and not optional:
                        raise Module.NotAvailable(context, self.name, module_name)
                    print("NOTFOUND", context, module_name)
                    continue

                if optional:
                    try:
                        list(module.get_deps(context))
                    except Module.NotAvailable:
                        continue

                all_module_names.add(module_name)
                modules.add(module)

            new_module_names = set()
            for module in modules:
                new_module_names |= set(listify(module.args.get(name, [])))

            module_names = new_module_names - all_module_names

        res = sorted(list(modules), key=lambda x: x.name)

        # print("get_nested(%s) setting cache" % name, { s.name : [x.name for x in res] })
        tmp = dict_get(self.get_nested_cache, context, {})
        merge(tmp, {name: {self: res}})

        return res

    def get_deps(self, context):
        return uniquify(self.get_nested(context, "depends"))

    def get_used(self, context, all=False):
        res = []
        res.extend(self.get_nested(context, "uses", notfound_error=False))

        for dep in self.get_nested(context, "depends", notfound_error=False):
            res.extend(dep.get_nested(context, "uses", notfound_error=False))
            if all:
                res.append(dep)
        return uniquify(res)

    def get_vars(self, context):
        vars = self.args.get("vars", {})
        if vars:
            _vars = copy.deepcopy(context.get_vars())
            _vars = self.vars_substitute(_vars, context)

            merge(_vars, vars, override=True)
            return _vars
        else:
            return copy.deepcopy(context.get_vars())

    def get_export_vars(self, context, module_set):
        try:
            return self.export_vars[context]
        except KeyError:
            pass

        vars = self.args.get("export_vars", {})
        vars = self.vars_substitute(vars, context)

        for dep in self.get_used(context, all=True):
            if dep.name in module_set:
                dep_export_vars = dep.args.get("export_vars", {})
                if dep_export_vars:
                    dep_export_vars = dep.vars_substitute(dep_export_vars, context)
                    merge(vars, dep_export_vars, join_lists=True)

        self.export_vars[context] = vars
        return vars

    def vars_substitute(self, _vars, context):
        _dict = {"source_folder": self.locate_source("")}
        return deep_substitute(_vars, _dict)

    def uses_all(self):
        return "all" in listify(self.args.get("uses", []))

    def get_defines(self, context, module_set):
        if self.uses_all():
            deps_available = module_set
        else:
            dep_names = set([x.name for x in self.get_used(context)])
            deps_available = dep_names & module_set

        dep_defines = []
        for dep_name in sorted(deps_available):
            if short_module_defines:
                dep_name = os.path.basename(dep_name)
            dep_defines.append("-DMODULE_" + dep_name.upper().translate(transtab))
        return dep_defines


class App(Module):
    count = 0
    list = []
    global_applist = set()
    global_whitelist = set()
    global_blacklist = set()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__class__.list.append(self)

        self.bindir = self.args.get("bindir", os.path.join("${bindir}", "${name}"))

        def _list(self, name):
            return (
                set(listify(self.args.get(name, []))) | App.__dict__["global_" + name]
                or None
            )

        self.whitelist = _list(self, "whitelist")
        self.blacklist = _list(self, "blacklist")

        # print("APP_", s.name, "path:", s.relpath)

    def post_parse():
        for app in App.list:
            app.build()

    def build(self):
        if App.global_applist and not self.name in App.global_applist:
            return

        print("APP", self.name)

        for name, builder in Context.map.items():
            if builder.__class__ != Builder:
                continue

            if self.whitelist and not builder.listed(self.whitelist):
                print("NOT WHITELISTED:", self.name, builder.name)
                continue

            if self.blacklist and builder.listed(self.blacklist):
                print("BLACKLISTED:", self.name, builder.name)
                continue

            #
            context = Context(
                add_to_map=False,
                name=self.name,
                parent=builder,
                vars={}
            )

            #
            context.bindir = self.bindir
            if "$" in context.bindir:
                context.bindir = Template(context.bindir).substitute(
                    {
                        "bindir": builder.get_bindir(),
                        "name": self.name,
                        "app": self.name,
                        "builder": name,
                    }
                )
            if context.bindir.startswith("./"):
                context.bindir = os.path.join(self.relpath, context.bindir[2:])

            context_vars = context.get_vars()

            print("  build", self.name, "for", name)
            try:
                modules = [self] + uniquify(self.get_deps(context))
            except Module.NotAvailable as e:
                print(
                    "laze: WARNING: skipping app",
                    self.name,
                    "for builder %s:" % context.parent.name,
                    e,
                )
                continue

            App.count += 1

            module_set = set()
            for module in modules:
                module_set.add(module.name)
                print("    %s:" % module.name, module.args.get("sources"))
                _tmp = module.args.get("depends")
                if _tmp:
                    print("    %s: deps:" % module.name, _tmp)
                _tmp = module.args.get("uses")
                if _tmp:
                    print("    %s: uses:" % module.name, _tmp)

                module_global_vars = module.args.get("global_vars", {})
                module_global_vars = module.vars_substitute(module_global_vars, context)
                if module_global_vars:
                    merge(context_vars, module_global_vars, join_lists=True)
                    print("    global_vars:", module_global_vars, context_vars)

            print("    %s:" % context, context_vars)

            global writer
            sources = []
            objects = []
            for module in modules:
                _sources = listify(module.args.get("sources", []))
                sources = []

                # handle optional sources ("- optional_module: file.c")
                use_optional_source_deps = None
                for source in _sources:
                    if type(source) == dict:
                        for key, value in source.items():
                            # splitting by comma enables multiple deps like "- a,b: file.c"
                            key = set(key.split(","))
                            if not key - module_set:
                                print("OPTIONAL sources:", module.name, value)
                                sources.extend(listify(value))
                                if use_optional_source_deps == None:
                                    use_optional_source_deps = module.args.get(
                                        "options", {}
                                    ).get("use_optional_source_deps", False)
                                if use_optional_source_deps:
                                    uses = dict_get(module.args, "uses", [])
                                    print("OPTIONAL USED:", module.name, key)
                                    uses.extend(list(key))
                    else:
                        sources.append(source)

                print("USES", module.name, dict_get(module.args, "uses", []))
                # print("MODULE_DEFINES", module.name, module_defines, module_set)
                module_defines = module.get_defines(context, module_set)

                module_vars = module.get_vars(context)
                # print("EXPORT VARS", module.name, module.get_export_vars(context, module_set))
                merge(
                    module_vars,
                    copy.deepcopy(module.get_export_vars(context, module_set)),
                )

                # add "-DMODULE_<module_name> for each used/depended module
                if module_defines:
                    module_vars = copy.deepcopy(module_vars)
                    cflags = dict_get(module_vars, "CFLAGS", [])
                    cflags.extend(module_defines)

                for source in sources:
                    source_in = module.locate_source(source)
                    rule = Rule.get_by_extension(source)

                    obj = context.get_filepath(
                        os.path.join(module.relpath, source[:-2] + rule.args.get("out"))
                    )
                    obj = rule.to_ninja_build(writer, source_in, obj, module_vars)
                    objects.append(obj)
                    # print ( source) # , module.get_vars(context), rule.name)

            link = Rule.get_by_name("LINK")
            outfile = context.get_filepath(os.path.basename(self.name)) + ".elf"

            res = link.to_ninja_build(writer, objects, outfile, context.get_vars())
            if res != outfile:
                # An identical binary has been built for another Application.
                # As the binary can be considered a final target, create a file
                # symbolic link.
                symlink = Rule.get_by_name("SYMLINK")
                symlink.to_ninja_build(writer, res, outfile)

            depends(context.parent.name, outfile)
            depends(self.name, outfile)


class_map = {
    "context": Context,
    "builder": Builder,
    "rule": Rule,
    "module": Module,
    "app": App,
}


@click.command()
@click.option(
    "--chdir",
    "-C",
    type=click.STRING,
)
@click.option(
    "--project-file",
    "-f",
    type=click.STRING,
    envvar="LAZE_PROJECT_FILE",
)
@click.option("--whitelist", "-W", multiple=True, envvar="LAZE_WHITELIST")
@click.option("--apps", "-A", multiple=True, envvar="LAZE_APPS")
def generate(chdir, project_file, whitelist, apps):
    global writer

    if chdir:
        os.chdir(chdir)

    App.global_whitelist = set(split(list(whitelist)))
    App.global_blacklist = set()  # set(split(list(blacklist or [])))
    App.global_applist = set(split(list(apps)))

    start_dir = os.getcwd()

    if project_file is None:
        project_file = const.PROJECTFILE_NAME
        project_root = locate_project_root()
        if project_root is None:
            print("laze: error: could not locate folder containing \"%s\"" %
                    project_file)

            sys.exit(1)

    before = time.time()
    try:
        data_list = yaml_load(project_file)
    except ParseError as e:
        print(e)
        sys.exit(1)

    print("laze: loading buildfiles took %.2fs" % (time.time() - before))

    writer = Writer(open("build.ninja", "w"))
    #

    # create rule for automatically re-running laze if necessary
    writer.rule(
        "relaze", "laze generate --project-file ${in}", restat=True, generator=True
    )
    writer.build(
        rule="relaze", outputs="build.ninja", implicit=list(files_set), inputs=project_file
    )

    before = time.time()
    # PARSING PHASE
    # create objects
    for data in data_list:
        relpath = data.get("_relpath", "")
        for name, _class in class_map.items():
            datas = listify(data.get(name, []))
            for _data in datas:
                _data["_relpath"] = relpath
                _class(**_data)

    no_post_parse_classes = {Builder}

    # POST_PARSING PHASE
    for name, _class in class_map.items():
        if _class in no_post_parse_classes:
            continue
        _class.post_parse()

    print("laze: processing buildfiles took %.2fs" % (time.time() - before))
    print("laze: configured %s applications" % App.count)
    if Rule.rule_num:
        print(
            "laze: cached: %s/%s (%.2f%%)"
            % (Rule.rule_cached, Rule.rule_num, Rule.rule_cached * 100 / Rule.rule_num)
        )

    for dep, _set in depends.map.items():
        writer.build(rule="phony", outputs=dep, inputs=list(_set))

    # download external sources
    dl.start()
