#!/usr/bin/env python3

import copy
import os
import re
import sys
import yaml

from util import merge, listify, dict_list_product, uniquify

from ninja_syntax import Writer

files_set = set()

class InvalidArgument(Exception):
    pass

class ModuleNotAvailable(Exception):
    pass

def yaml_load(filename, path=None, defaults=None):
    path = path or ""

    print("yaml_load(): loading %s with relpath %s" % (filename, path))

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
        datas = yaml.load_all(f.read())

    res = []
    for data in datas:
        data_defaults = data.get("defaults", {})

        _defaults = defaults
        if _defaults:
            _defaults = copy.deepcopy(_defaults)
            if data_defaults:
                defaults.merge(defaults, data_defaults)
        else:
            _defaults = data_defaults

        if _defaults:
            #print("yaml_load(): merging defaults, base:    ", data)
            #print("yaml_load(): merging defaults, defaults:", _defaults)
            merge(data, _defaults, override=False, only_existing=True, join_lists=True)
            #print("yaml_load(): merging defaults, result:  ", data)

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
            res.extend(result)
        else:
            data = do_include(data)
            data["_relpath"] = path
            res.append(data)
            for subdir in listify(data.get("subdir", [])):
                relpath = os.path.join(path, subdir)
                res.extend(yaml_load(os.path.join(relpath, "build.yml"),
                    path=relpath,
                    defaults=_defaults))
    return res

class Declaration(object):
    def __init__(s, **kwargs):
        s.args = kwargs
        s.relpath = s.args.get("_relpath")

        _vars = s.args.get("vars", {})
        for key, value in _vars.items():
            _vars[key] = listify(value)
        s.args["vars"] = _vars

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

        print("CONTEXT", s.name)

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
#        print("get_module()", s, s.modules.keys())
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
    rule_num = 0
    rule_cached = 0
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
        #print("RULE", s.name, _in, _out, _vars)
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

        Rule.rule_num += 1
        try:
            cached = Rule.rule_cache[cache_key]
            #print("laze: %s using cached %s for %s %s" % (s.name, cached, _in, _out))
            Rule.rule_cached += 1
            return cached

        except KeyError:
            Rule.rule_cache[cache_key] = _out
            #print("laze: %s %s ->  %s" % (s.name, _in, _out), vars)
            writer.build(outputs=_out, rule=s.name, inputs=_in, variables=vars)
            return _out

class Module(Declaration):
    list = []
    def __init__(s, **kwargs):
        super().__init__(**kwargs)
        Module.list.append(s)
        s.name = s.args.get("name")
        if not s.name:
            if s.relpath:
                s.name = os.path.dirname(s.relpath + "/")
            else:
                raise InvalidArgument("module missing name")
            s.args["name"] = s.name

        s.context = None
        s.get_nested_cache = {}

    def post_parse():
        for module in Module.list:
            context_name = module.args.get("context", "default")
            context = Context.map.get(context_name)
            module.context = context
            context.modules[module.args.get("name")] = module
            print("MODULE", module.name, "in", context)

    def get_nested(s, context, name, notfound_error=True, seen=None):
        try:
            for module in s.get_nested_cache[context.name][name]:
                yield module
            return
        except KeyError:
            pass

        seen = seen or set()
        if s in seen:
            return

        seen.add(s)

        cache = []

        for module_name in listify(s.args.get(name, [])):
            module = context.get_module(module_name)
            if not module:
                if notfound_error:
                    raise ModuleNotAvailable("module \"%s\" in %s depends on unavailable module \"%s\"" %
                            ( s.name, context, module_name))
                continue

            for _module in module.get_nested(context, name, notfound_error, seen):
                cache.append(_module)
                yield _module
            cache.append(module)
            yield module

        s.get_nested_cache[context] = { name : uniquify(cache) }

    def get_deps(s, context):
        for dep in s.get_nested(context, "depends"):
            yield dep

#        for module_name in listify(s.args.get("depends", [])):
#            module = context.get_module(module_name)
#            if not module:
#                print("module", module_name, "not found in context", context)
#                continue
#
#            for _module in module.get_deps(context):
#                yield _module
#            yield module

    def get_used(s, context):
        for used in s.get_nested(context, "uses", notfound_error=False):
            yield used
        for dep in s.get_nested(context, "depends", notfound_error=False):
            for used in dep.get_nested(context, "uses", notfound_error=False):
                yield used

    def get_vars(s, context):
        vars = s.args.get("vars", {})
        if vars:
            _vars = copy.deepcopy(context.get_vars())
            merge(_vars, vars, override=True)
            return _vars
        else:
            return context.get_vars()

    def get_defines(s, context, module_set):
        dep_names = set([ x.name for x in s.get_used(context)])
        deps_available = dep_names & module_set
        dep_defines = []
        for dep_name in sorted(deps_available):
            dep_defines.append("-DMODULE_" + dep_name.upper())
        return dep_defines

class App(Module):
    count = 0
    list = []
    def __init__(s, **kwargs):
        super().__init__(**kwargs)
        s.__class__.list.append(s)
        print("APP_", s.name, "path:", s.relpath)

    def post_parse():
        for app in App.list:
            app.build()

    def build(s):
        print("APP", s.name)
        for name, context in Context.map.items():
            if context.__class__ != Builder:
                continue

            #
            context = Context(add_to_map=False, name=s.name, parent=context, vars=s.args.get("vars", {}))
            vars = context.get_vars()

            print("  build", s.name, "for", name)
            try:
                modules = [s] + uniquify(s.get_deps(context))
            except ModuleNotAvailable as e:
                print("laze: WARNING: skipping app", s.name, "for builder %s:" % context.parent.name, e)
                continue

            App.count += 1

            module_set = set()
            for module in modules:
                module_set.add(module.name)
                #print("    %s:" % module.name, module.args.get("sources"), "deps:", module.args.get("depends"))
                module_global_vars = module.args.get('global_vars', {})
                if module_global_vars:
                    merge(vars, module_global_vars)
                    #print("    global_vars:", module_global_vars)

            #print("    %s:" % context, vars)

            global writer
            sources = []
            objects = []
            for module in modules:
                module_defines = module.get_defines(context, module_set)
                #print("MODULE_DEFINES", module_defines)
                for source in listify(module.args.get("sources", [])):
                    source = module.locate_source(source)
                    rule = Rule.get_by_extension(source)
                    vars = module.get_vars(context)

                    if module_defines:
                    # add "-DMODULE_<module_name> for each used/depended module
                        vars = copy.deepcopy(vars)
                        cflags = vars.get("CFLAGS", [])
                        if cflags:
                            cflags.extend(module_defines)
                        else:
                            cflags = dep_defines
                        vars["CFLAGS"] = cflags

                    obj = context.get_filepath(source[:-2]+rule.args.get("out"))
                    obj = rule.to_ninja_build(writer, source, obj, vars)
                    objects.append(obj)
                    #print ( source) #, module.get_vars(context), rule.name)


            link = Rule.get_by_name("LINK")
            outfile = context.get_filepath(s.name)+".elf"

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
writer.rule("relaze", "laze ${in}", restat=True, generator=True)
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

print("laze: building %s applications" % App.count)
if Rule.rule_num:
    print("laze: cached: %s/%s (%.2f%%)" % (Rule.rule_cached, Rule.rule_num, Rule.rule_cached*100/Rule.rule_num))
