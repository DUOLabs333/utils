import subprocess
import re


class DoesNotExist(Exception):
    pass

def List(names,flags,root,class_name):
    All=sorted(os.listdir(ROOT))
    
    if "--started" in flags:
        names+=[_ for _ in All if "Started" in eval(f"{class_name}(_).Status()") ]
        flags=flags.remove("--started")
    if "--stopped" in flags:
        names+=[_ for _ in All if "Stopped" in eval(f"{class_name}(_).Status()") ]
        flags=flags.remove("--stopped")
    if "--enabled" in flags:
        names+=[_ for _ in All if "Enabled" in eval(f"{class_name}(_).Status()") ]
        flags=flags.remove("--enabled")
    
    if "--disabled" in flags:
        names+=[_ for _ in All if "Disabled" in eval(f"{class_name}(_).Status()") ]
        flags=flags.remove("--disabled")

    if "--all" in flags:
        names+=All
        flags=flags.remove("--all")
    return (names,flags)

def flatten(items):
    """Yield items from any nested iterable; see Reference."""
    for x in items:
        if isinstance(x, typing.Iterable) and not isinstance(x, (str, bytes)):
            for sub_x in flatten(x):
                yield sub_x
        else:
            yield x

def print_result(result):
    for element in result:
        if element is None:
            print(end='')
        else:
            print(element)

def split_by_char(string,char=':'):
    PATTERN = re.compile(rf'''((?:[^\{char}"']|"[^"]*"|'[^']*')+)''')
    return [_ for _ in list(PATTERN.split(string)) if _ not in ['', char]]


def Shell(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=False,block=True):
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr,universal_newlines=True,shell=shell)
    if block:
        return process.communicate()[0]


def default_value(variable,value,default):
    if not variable:
        return default
    else:
        return value

def class_init(self,_name,_flags=None,_env=None,_function=None):
    self.name=_name
    
    self.flags=default_value(self.flags,_flags,FLAGS)
    
    self.function=default_value(self.function,_function,FUNCTION)
    
    if self.function not in ["init"]:
        if not os.path.isdir(f"{ROOT}/{self.name}"):
             raise DoesNotExist()
             return
        os.chdir(f"{ROOT}/{self.name}")

def 