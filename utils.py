import subprocess
import re
import tempfile
import os
import pathlib
import signal 
import time
import sys
import typing
import shutil
import threading

def get_tempdir():
    if os.uname().sysname=="Darwin":
        return "/tmp"
    else:
        return tempfile.gettempdir()
    



class DoesNotExist(Exception):
    pass

def get_value(variable,default):
	if not variable:
		return default
	else:
		return variable

def get_root_directory(class_name,root_variable=None,default_value=None):
    root_variable=get_value(root_variable,f"{class_name.upper()}_ROOT")
    default_value=get_value(default_value,f"{os.environ['HOME']}/{class_name.title()}s")
    return os.path.expanduser(os.getenv(root_variable,default_value))

for var in ["ROOT", "NAMES","TEMPDIR"]:
    globals()[var]=None  
    
#ROOT=None
#NAMES=None
#FLAGS=None
#FUNCTION=None
#TEMPDIR=None

def list_items_in_root(names,flags,class_name):
    All=[_ for _ in sorted(os.listdir(ROOT)) if not _.startswith('.') ]
    if "--started" in flags:
        names+=[_ for _ in All if "Started" in eval(f"{class_name}(_).Status()") ]
        flags.remove("--started")
    if "--stopped" in flags:
        names+=[_ for _ in All if "Stopped" in eval(f"{class_name}(_).Status()") ]
        flags.remove("--stopped")
    if "--enabled" in flags:
        names+=[_ for _ in All if "Enabled" in eval(f"{class_name}(_).Status()") ]
        flags.remove("--enabled")
    
    if "--disabled" in flags:
        names+=[_ for _ in All if "Disabled" in eval(f"{class_name}(_).Status()") ]
        flags.remove("--disabled")

    if "--all" in flags:
        names+=All
        flags.remove("--all")
    if names==[]:
        print(f"No {class_name}s specified!")
        exit()
    return names

def flatten_list(items):
    """Yield items from any nested iterable."""
    for x in items:
        if isinstance(x, typing.Iterable) and not isinstance(x, (str, bytes)):
            for sub_x in flatten_list(x):
                yield sub_x
        else:
            yield x

def print_list(l):
    for element in l:
        if element is None:
            print(end='')
        else:
            print(element)

def split_string_by_char(string,char=':'):
    PATTERN = re.compile(rf'''((?:[^\{char}"']|"[^"]*"|'[^']*')+)''')
    return [_ for _ in list(PATTERN.split(string)) if _ not in ['', char]]


def shell_command(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,arbitrary=False,block=True):
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr,universal_newlines=True,shell=arbitrary)
    if block:
        return process.communicate()[0]




def extract_arguments():
    arguments=sys.argv[1:]
    try:
        FUNCTION=arguments[0]
    except IndexError:
        print("No function specified!")
        exit()
    arguments=arguments[1:]
    
    NAMES=[]
    FLAGS=arguments
    for i in range(len(arguments)):
        if not arguments[i].startswith("--"):
            FLAGS=arguments[:i]
            NAMES=arguments[i:]
            break
    return (NAMES,FLAGS,FUNCTION)

def add_environment_variable_to_string(string,env_var):
    return string+f"; export {env_var}"

def wait(delay=None):
    threading.Event().wait(timeout=delay)

def execute_class_method(class_instance,function):
    if not callable(getattr(class_instance, function.title(),None)):
            print(f"Command {function} doesn't exist!")
            exit()
    else:
        return list(flatten_list([getattr(class_instance,function.title())()]))

def export_methods_globally(class_instance_string,globals_dict):
    Class=eval(f"{class_instance_string}.__class__",globals_dict)
    for func in [func for func in dir(Class) if callable(getattr(Class, func)) and not func.startswith('__')]:
        exec(f"global {func}",globals_dict)
        exec(f"{func} = {class_instance_string}.{func}",globals_dict)

def check_if_element_any_is_in_list(elements,_list):
    return any(_ in _list for _ in elements)
    
class Class:
    def __init__(self,class_self,class_name):
        self.self=class_self
        self.name=class_name
    
    def class_init(self,_name,_flags,_function,_workdir):
        self.self.name=_name
        
        self.self.flags=get_value(_flags,[])
        
        self.self.function=get_value(_function,"")
        
        if self.self.function not in ["init"]:
            if not os.path.isdir(f"{ROOT}/{self.self.name}"):
                 raise DoesNotExist()
                 return
            os.chdir(f"{ROOT}/{self.self.name}")
        self.self.workdir=_workdir
        
    def stop(self):
        if "Stopped" in self.self.Status():
            return f"Service {self.self.name} is already stopped"
        
        for process in ["main", "auxiliary"]:
            for pid in self.self.Ps(process):
                try:
                    os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:
                    pass
        
    def cleanup_after_stop(self):
        for ending in ["log","lock"]:
            try:
               os.remove(f"{TEMPDIR}/{self.name}_{self.self.name}.{ending}")
            except FileNotFoundError:
                pass

    def restart(self):
        return [self.self.Stop(),self.self.Start()]
    
    def get_main_process(self):
        if not os.path.isfile(f"{TEMPDIR}/{self.name}_{self.self.name}.lock"):
                return []
        else:
            return list(map(int,[_[1:] for _ in shell_command(["lsof","-Fp","-w",f"{TEMPDIR}/{self.name}_{self.self.name}.lock"]).splitlines()]))
    
    def list(self):
        return self.self.name
        
    def workdir(self,work_dir):
        #Remove trailing slashes, but only for strings that are not /
        if work_dir.endswith('/') and len(work_dir)>1:
            work_dir=work_dir[:-1]
            
        if work_dir.startswith("/"):
            self.self.workdir=work_dir
        else:    
            self.self.workdir+='/'+work_dir
        
        #Remove repeated / in workdir
        self.self.workdir=re.sub(r'(/)\1+', r'\1',self.self.workdir)

    def edit(self):
        if "Enabled" in self.self.Status():
            shell_command([os.getenv("EDITOR","vi"),f"{ROOT}/{self.self.name}/{self.name}.py"],stdout=None)
        else:
            shell_command([os.getenv("EDITOR","vi"),f"{ROOT}/{self.self.name}/.{self.name}.py"],stdout=None)

    def status(self):
        status=[]
        if os.path.isfile(f"{TEMPDIR}/{self.name}_{self.self.name}.log"):
            status+=["Started"]
        else:
            status+=["Stopped"]
        
        if os.path.exists(f"{ROOT}/{self.self.name}/{self.name}.py"):
            status+=["Enabled"]
        else:
            status+=["Disabled"]
        return status
    
    def enable(self):
        if "Enabled" in self.self.Status():
            return [f"{self.name} is already enabled"]
        else:
            os.rename(f"{ROOT}/{self.self.name}/.{self.name}.py",f"{ROOT}/{self.self.name}/{self.name}.py")
        
        if '--now' in self.self.flags:
            return [self.self.Start()]

    def loop(self,command,delay=60):
        if isinstance(command,str):
            def func():
                while True:
                    self.self.Run(command)
                    self.self.Wait(delay)
        else:
            def func():
                while True:  
                    command()
                    self.self.Wait(delay)
        threading.Thread(target=func,daemon=True).start()
       
    def disable(self):
        if "Disabled" in self.self.Status():
            return [f"{self.self.name} is already disabled"]
        else:
            os.rename(f"{ROOT}/{self.self.name}/{self.name}.py",f"{ROOT}/{self.self.name}/.{self.name}.py")
        
        if '--now' in self.self.flags:
            return [self.self.Stop()]

    def log(self):
        shell_command(["less","+G","-f","-r",f"{TEMPDIR}/{self.name}_{self.self.name}.log"],stdout=None)
    
    def delete(self):
        self.self.Stop()
        shutil.rmtree(f"{ROOT}/{self.self.name}")
    
    def watch(self):
        shell_command(["tail","-f",f"{TEMPDIR}/{self.name}_{self.self.name}.log"],stdout=None)

