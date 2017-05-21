#!/usr/bin/env python3

import copy
import os
import re
import sys
import yaml

from util import merge, listify, dict_list_product, uniquify

from ninja_syntax import Writer

files_set = set()

def yaml_load(filename, path=None):
    path = path or ""

    print("yaml_load(): loading %s with relpath %s", filename, path)

    files_set.add(filename)

    def do_include(data):
        includes = listify(data.get("include"))
        for include in includes:
            _data = yaml_load(os.path.join(os.path.dirname(filename), include), path)[0]
            _data.pop("ignore", None)
            if "template" in _data:
                raise InvalidJSONException("template statement in included file currently not supported!")
            merge_override(_data, data)
            data = _data

        data.pop("include", None)
        return data

    with open(filename, 'r') as f:
        data = yaml.load(f)

    res = []
    template = data.get('template')

    if template:
        data.pop('template')
        result = []
        i = 0
        for repl in dict_list_product(template):
            _data = copy.deepcopy(data)
            _data = deep_replace(_data, repl)
            _data = do_include(_data)
            _data["template_instance"] = repl
            _data["template_instance_num"] = i
            result.append(_data)
            i += 1
        return result
    else:
        data = do_include(data)
        data["_relpath"] = path
        res = [data]
        for subdir in listify(data.get("subdir", [])):
            relpath = os.path.join(path, subdir)
            res.extend(yaml_load(os.path.join(subdir, "build.yml"), relpath))
        return res

class Declaration(object):
    def __init__(s, **kwargs):
        s.args = kwargs
        s.relpath = s.args.get("_relpath")

    def post_parse():
        pass

    def locate_source(s, filename):
        return "${root}" + os.path.join(s.relpath, filename)

class Context(Declaration):
    map = {}
    def __init__(s, add_to_map=True, **kwargs):
        super().__init__(**kwargs)

        s.name = kwargs.get("name")
        s.parent = kwargs.get("parent")
        s.children = []
        s.modules = {}
        s.vars = None
        s.bindir = s.args.get("bindir")

        if add_to_map:
            Context.map[s.name] = s

    def __repr__(s, nest=False):
        res = "Context(" if not nest else ""
        res += '"' + s.name + '"'
        if s.parent:
            res += "->" + s.parent.__repr__(nest=True)
        else:
            res += ")"
        return res

    def post_parse():
        for name, context in Context.map.items():
            if context.parent:
                context.parent = Context.map[context.parent]
                context.parent.children.append(context)

    def get_module(s, module_name):
        module = s.modules.get(module_name)
        if not module and s.parent:
            return s.parent.get_module(module_name)
        return module

    def get_vars(s):
        if s.vars:
            pass
        elif s.parent:
            _vars = {}
            pvars = s.parent.get_vars()
            merge(_vars, copy.deepcopy(pvars), override=True, change_listorder=False)
            merge(_vars, s.args.get("vars", {}), override=True, change_listorder=False)
            s.vars = _vars
        else:
            s.vars = s.args.get("vars", {})

        return s.vars

    def get_bindir_list(s, _list=None):
        _list = _list or []
        _list += [s.bindir or s.name]

        if s.parent:
            return s.parent.get_bindir_list(_list)
        else:
            return _list

    def get_filepath(s, filename):
        return os.path.join(*reversed(s.get_bindir_list([filename])))

class Builder(Context):
    pass

rule_var_re = re.compile(r'\${\w+}')

class Rule(Declaration):
    rule_map = {}
    rule_name_map = {}
    rule_cache = {}
    file_map = {}

    def __init__(s, **kwargs):
        super().__init__(**kwargs)
        s.name = s.args["name"]
        s.cmd = s.args["cmd"]

        try:
            in_ext = s.args["in"]
            if in_ext in Rule.rule_map:
                print("error: %s extension already taken")
                return
            Rule.rule_map[in_ext] = s
        except KeyError:
            pass

        Rule.rule_name_map[s.name] = s

        s.create_var_list()
        global writer
        s.to_ninja(writer)

    def get_by_extension(filename):
        filename, file_extension = os.path.splitext(filename)
        return Rule.rule_map[file_extension]
    def get_by_name(name):
        return Rule.rule_name_map[name]

    def create_var_list(s):
        _var_names = rule_var_re.findall(s.cmd)
        var_names = []
        for name in _var_names:
            name = name[2:-1]
            if not name in { 'in', 'out' }:
                var_names.append(name)
        print("RULE", s.name, "vars:", var_names)
        s.var_list = var_names

    def to_ninja(s, writer):
        writer.rule(s.name, s.cmd, description="%s ${out}" % s.name)

    def to_ninja_build(s, writer, _in, _out, _vars=None):
        _vars = _vars or {}
        vars = {}
        for name in s.var_list:
            try:
                tmp = _vars[name]
                if type(tmp) == list:
                    tmp = " ".join(tmp)
                vars[name] = tmp
            except KeyError:
                pass

        cache_key = hash("rule:%s in:%s vars:%s" % (s.name, _in, hash(frozenset(vars.items()))))

        try:
            cached = Rule.rule_cache[cache_key]
            print("laze: using cached %s for %s %s %s" % (cached, s.name, _in, _out))
            return cached

        except KeyError:
            Rule.rule_cache[cache_key] = _out
            writer.build(outputs=_out, rule=s.name, inputs=_in, variables=vars)
            return _out

class Module(Declaration):
    list = []
    def __init__(s, **kwargs):
        super().__init__(**kwargs)
        Module.list.append(s)
        s.name = s.args["name"]
        s.context = None

    def post_parse():
        for module in Module.list:
            context_name = module.args.get("context", "default")
            context = Context.map.get(context_name)
            module.context = context
            context.modules[module.args.get("name")] = module

    def get_deps(s, context):
        for module_name in listify(s.args.get("depends", [])):
            module = context.get_module(module_name)
            if not module:
                print("module", module_name, "not found in context", context.name)
                return

            for module in module.get_deps(context):
                yield module
            yield module

    def get_vars(s, context):
        vars = s.args.get("vars", {})
        if vars:
            _vars = copy.deepcopy(context.get_vars())
            merge(_vars, vars, override=True)
            return _vars
        else:
            return context.get_vars()

class App(Declaration):
    list = []
    def __init__(s, **kwargs):
        super().__init__(**kwargs)
        s.__class__.list.append(s)
        s.name = s.args["name"]

    def post_parse():
        for app in App.list:
            app.build()

    def build(s):
        print("APP", s.name)
        for name, context in Context.map.items():
            if context.args.get("ignore"):
                continue

            #
            context = Context(add_to_map=False, name=s.name, parent=context, vars=s.args.get("vars", {}))

            print("  build", s.name, "for", name)
            modules_used_map = {}
            modules = []
            for module_name in listify(s.args.get("depends", [])):
                module = context.get_module(module_name)
                modules.extend(list(module.get_deps(context)))
                modules.append(module)

            for module in modules:
                print("    %s:" % module.name, module.args.get("sources"), "deps:", module.args.get("depends"))

            global writer
            sources = []
            objects = []
            for module in modules:
                for source in listify(module.args.get("sources", [])):
                    source = module.locate_source(source)
                    rule = Rule.get_by_extension(source)
                    vars = module.get_vars(context)
                    obj = context.get_filepath(source[:-2]+rule.args.get("out"))
                    obj = rule.to_ninja_build(writer, source, obj, vars)
                    objects.append(obj)
                    print ( source, module.get_vars(context), rule.name)

            link = Rule.get_by_name("LINK")
            outfile = context.get_filepath(s.name)

            res = link.to_ninja_build(writer, objects, outfile, context.get_vars())
            if res != outfile:
                symlink = Rule.get_by_name("SYMLINK")
                symlink.to_ninja_build(writer, res, outfile)

            print("")

class_map = {
        "context" : Context,
        "builder" : Builder,
        "rule" : Rule,
        "module" : Module,
        "app" : App,
        }

data_list = yaml_load(sys.argv[1])

writer = Writer(open("build.ninja", "w"))
#

files_list = []
for filename in files_set:
    files_list.append("${root}" + filename)
writer.rule("relaze", "./laze.py ${in}", restat=True, generator=True)
writer.build(rule="relaze", outputs="${root}build.ninja", implicit=files_list, inputs="${root}"+sys.argv[1])

# PARSING PHASE
# create objects
for data in data_list:
    relpath = data.get("_relpath", "")
    for name, _class in class_map.items():
        datas = listify(data.get(name, []))
        for _data in datas:
            _data["_relpath"] = relpath
            _class(**_data)

no_post_parse_classes = { Builder }

# POST_PARSING PHASE
for name, _class in class_map.items():
    if _class in no_post_parse_classes:
        continue
    _class.post_parse()

