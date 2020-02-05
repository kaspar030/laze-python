# try to use libyaml (faster C-based yaml lib),
# fallback to pure python version
try:
    from yaml import \
        CBaseLoader as BaseLoader, \
        CBaseDumper as BaseDumper, \
        CLoader as Loader, \
        CDumper as Dumper
except ImportError:
    print("laze: warning: using slow python-based yaml loader")
    from yaml import BaseLoader, BaseDumper, Loader, Dumper

import yaml
