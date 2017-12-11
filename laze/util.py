import traceback
from itertools import product

def listify(something):
    if not something:
        return []
    if not type(something)==list:
        return [something]
    return something

def uniquify(seq):
    # Order preserving
    seen = set()
    return [x for x in seq if x not in seen and not seen.add(x)]

def print_exception():
    traceback.print_exc()

def dict_list_tuples2(_dict):
    for key, value_list in _dict.items():
        for value in value_list:
            yield (key,value)

def dict_list_tuples(_dict):
    _dict = _dict or {}
    for key in _dict.keys():
        yield dict_list_tuples2({key:_dict[key]})

def dict_list_product(_dict):
    for _tuple in product(*dict_list_tuples(_dict)):
        res = {}
        for key, val in _tuple:
            res[key] = val

        yield(res)

def deep_replace(obj, replace):
    if type(obj) == list:
        _obj = []
        for entry in obj:
            _obj.append(deep_replace(entry, replace))
        return _obj
    elif type(obj) == dict:
        _obj = {}
        for key, val in obj.items():
            _obj[key] = deep_replace(val, replace)
        return _obj
    elif type(obj) == str:
        for key, val in replace.items():
            obj = obj.replace(key, val)
        return obj
    else:
        return obj

def merge(a, b, path=None, override=False, change_listorder=False, only_existing=False, join_lists=False):
    "merges b into a"
    if path is None: path = []
    for key in b:
        if key in a:
            if join_lists:
                if isinstance(a[key], list) and not isinstance(b[key], list):
                    b[key] = [b[key]]
                elif (not isinstance(a[key], list)) and isinstance(b[key], list):
                    a[key] = [a[key]]

            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path=path + [str(key)], override=override, join_lists=join_lists)
            elif isinstance(a[key], set) and isinstance(b[key], set):
                a[key] = a[key] | b[key]
            elif isinstance(a[key], list) and isinstance(b[key], list):
                if change_listorder:
                    a[key] = uniquify(b[key] + a[key])
                else:
                    a[key] = uniquify(a[key] + b[key])
            elif a[key] == b[key]:
                pass # same leaf value
            elif a[key] == None:
                a[key] = b[key]
            else:
                if override:
                    a[key] = b[key]
                else:
                    raise Exception('Conflict at %s (%s, %s)' % ('.'.join(path + [str(key)]), a[key], b[key]))
        else:
            if not only_existing:
                a[key] = b[key]
    return a

def deep_replace(obj, replace):
    if type(obj) == list:
        _obj = []
        for entry in obj:
            _obj.append(deep_replace(entry, replace))
        return _obj
    elif type(obj) == dict:
        _obj = {}
        for key, val in obj.items():
            _obj[key] = deep_replace(val, replace)
        return _obj
    elif type(obj) == str:
        for key, val in replace.items():
            obj = obj.replace(key, val)
        return obj
    else:
        return obj

def dict_get(_dict, key, default):
    tmp = _dict.get(key)
    if not tmp:
        _dict[key] = default
        return default
    else:
        return tmp

def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate

def split(_list, splitter=','):
    tmp = []
    for entry in _list:
        tmp.extend(entry.split(splitter))
    _list.clear()
    _list.extend(tmp)

    return _list
