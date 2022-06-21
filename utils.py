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
import contextlib

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

for var in ["ROOT", "NAMES","TEMPDIR","GLOBALS"]:
    globals()[var]=None  
    
#ROOT=None
#NAMES=None
#FLAGS=None
#FUNCTION=None
#TEMPDIR=None

def list_items_in_root(names,flags,class_name):
    All=[_ for _ in sorted(os.listdir(ROOT)) if not _.startswith('.') ]
    
    for flag in ["started","stopped","enabled","disabled"]:
        if "--"+flag in flags:
            names+=[_ for _ in All if flag.title() in eval(f"{class_name}(_).Status()",GLOBALS,locals()) ]
            flags.remove("--"+flag)

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


def shell_command(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,arbitrary=False,block=True,env=None):
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr,universal_newlines=True,shell=arbitrary,env=env)
    if block:
        return process.communicate()[0]

def wait_until_pid_exits(pid):
    
    def pid_exists(pid):   
        """ Check For the existence of a unix pid. """
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True
            
    while pid_exists(pid):
        time.sleep(0.25)
def kill_process_gracefully(pid):
    
    try:
        os.kill(pid,signal.SIGTERM)
        try:
            os.waitpid(pid,0)
        except ChildProcessError: #Not a child process so move on
            pass
        wait_until_pid_exits(pid)
    except ProcessLookupError:
        pass
    
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

def check_if_element_any_is_in_list(elements,_list):
    return any(_ in _list for _ in elements)
    
def export_methods_from_self(self):
    methods={}
    for func in [func for func in dir(self) if callable(getattr(self, func)) and not func.startswith('__')]:
        methods[func]=getattr(self,func)
    
    return methods
def wrap_all_methods_in_class_with_chdir_contextmanager(self,path):
    @contextlib.contextmanager
    def set_directory(path):
        """Sets the cwd within the context
    
        Args:
            path (Path): The path to the cwd
    
        Yields:
            None
        """
    
        origin = os.path.abspath(os.getcwd())
        try:
            os.chdir(path)
            yield
        finally:
                os.chdir(origin)
    
    def wrapper(func):
        def new_func(*args, **kwargs):
            with set_directory(path):
                return func(*args, **kwargs)
        return new_func
            
    for func in [func for func in dir(self) if callable(getattr(self, func)) and not func.startswith('__')]:
        setattr(self,func,wrapper(getattr(self,func)))
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
            wrap_all_methods_in_class_with_chdir_contextmanager(self.self,f"{ROOT}/{self.self.name}")
        self.self.workdir=_workdir
        
        self.self.globals=GLOBALS.copy()
        self.self.globals.update(export_methods_from_self(self.self))
        
    def stop(self):
        if "Stopped" in self.self.Status():
            return f"Service {self.self.name} is already stopped"
        
        for pid in self.self.Ps("main"):
            kill_process_gracefully(pid)
        
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
        self.self.Run("") #Needed to avoid race conditions with a race that's right after --- just run self.self.Run once
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
        shell_command(["tail","-f","--follow=name",f"{TEMPDIR}/{self.name}_{self.self.name}.log"],stdout=None)
    

