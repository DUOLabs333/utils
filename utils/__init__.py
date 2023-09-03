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
import warnings
import traceback

for var in ["ROOT","GLOBALS","CLASS","get_all_items"]:
    globals()[var]=None
    
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

def get_root_directory(root_variable=None,default_value=None):
    root_variable=get_value(root_variable,f"{CLASS.__name__.upper()}_ROOT")
    default_value=get_value(default_value,f"{os.environ['HOME']}/{CLASS.__name__.title()}s")
    return os.path.expanduser(os.getenv(root_variable,default_value))


def list_items_in_root(names,flags):
    global get_all_items
    if not get_all_items:
        get_all_items = lambda root: [_ for _ in sorted(os.listdir(root)) if not _.startswith('.') ] #Fall back to default if no special function is defined
        
    All=get_all_items(ROOT)
    
    for flag in ["started","stopped","enabled","disabled"]:
        if flag in flags:
            names+=[_ for _ in All if flag.title() in CLASS(_).Status() ]
            del flags[flag]

    if "all" in flags:
        names+=All
        del flags["all"]
    if names==[]:
        print(f"No {CLASS.__name__.lower()}s specified!")
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


def shell_command(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=False,block=True,env=None,stdin=None):
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr,universal_newlines=True,shell=shell,env=env,stdin=stdin)
    if block:
        return process.communicate()[0]

def wait_until_pid_exits(pid):
    
    def pid_exists(pid):   
        """ Check For the existence of a unix pid. """
        if shell_command(["ps", "-ostat=",str(pid)])=="Z\n": #Zombie
        
            return False 
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True
            
    while pid_exists(pid):
        time.sleep(0.25)
        
def kill_process_gracefully(pid):
    print(pid)
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
            
    flags_temp={}
    for flag in FLAGS:
        flag=flag.split('=',1) #Split every flag in FLAGS by '='
        if len(flag)==1:
            flag.append('') #Pad out the flag array
        flag[0]=flag[0][2:] #Remove the '--'
        flags_temp[flag[0]]=flag[1]
        
    FLAGS=flags_temp
    return (NAMES,FLAGS,FUNCTION)

def env_list_to_string(env_list):
    return '; '.join([f"export {_}" for _ in env_list])

def parse_and_call_and_return():
       
def execute_class_method(class_instance,function):
    if not callable(getattr(class_instance, function.title(),None)):
            print(f"Command {function} doesn't exist!")
            exit()
    else:
        return list(flatten_list([getattr(class_instance,function.title())()]))

def check_if_any_element_is_in_list(elements,_list):
    return any(_ in _list for _ in elements)
    

class Class(object):
    def __init__(self,name,flags,kwargs):
        self.class_name=self.__class__.__name__.title()
        self.name=name
        
        try:
            self.ROOT
        except: #Not defined beforehand
            self.ROOT=os.path.join(os.path.expanduser("~"),self.class_name+"s")
            
        self.directory=os.path.join(self.ROOT,self.name)
        
        self.tempdir=os.path.join(get_tempdir(),self.class_name+"s",self.name)
        self.logfile=os.path.join(self.tempdir,"log")
        self.lockfile=os.path.join(self.tempdir,"lock")
        
        
        self.flags=flags
        del kwargs["flags"]
        
        self.parsing=kwargs.get("parsing",False) #A tag stating that this was only constructed for parsing, so should not do some things
        del kwargs["parsing"]
         
#        if not os.path.isdir(f"{ROOT}/{self.self.name}"):
#             raise DoesNotExist()
#             return
                  
        os.makedirs(self.tempdir,exist_ok=True)
        
        self.exit_commands=[exit,self._exit]
        
        self.config_file=[]
        
        self.attributes=set(dir(self))
        
        """Read variables from .lock and overwrite self with them as a way to restart from a state (also avoids overwriting lockfile). However, if it doesn't exist, just make a new one"""
        if os.path.isfile(self.lockfile):
            with open(self.lockfile,"r") as f:
                data=json.load(f)
            
            for key in data:
                setattr(self,key,data[key])
        else:
            self.update_lockfile()
        
        
    #Functions        
    def update_lockfile(self):
        if self.build or self.parsing:
            return #No lock file when building --- no need for it
        
        with open(self.lock,"r") as f:
            data=json.load(f)
            
        for attr in dir(self):
              if callable(getattr(self, attr)) or attr.startswith("__") or attr:
                  continue
              
              try:
                  data[attr]=json.dumps(x)
              except (TypeError, OverflowError):
                  continue
              
        with open(self.lock,"w+") as f:
            json.dump(data,f)
                
    def __getattribute__(self, attr):
        try:
            attribute=object.__getattribute__(self, attr)
        except AttributeError:
            try: #It's possible it is a command (like Start, Stop, etc)
                attr="command_"+attr
                attribute=object.__getattribute__(self, attr)
            except AttributeError as e:
                raise e
                
        if not (callable(attribute) and (attr[0].isupper() or attr.startswith("command_"))): #If they're just variables or functions not related to the application itself (ie, not user-facing or user-level)
            return attribute
        
        
        def wrapper(*args,**kwargs):
            with change_directory(self.directory):
                result=attribute(*args,**kwargs)
                if not attr.startswith("command_"):
                    self.update_lockfile()
                return result
                    
        return wrapper
    
    def get_auxiliary_processes():
        return []
    
    def Env(self,env_var):
        self.env.append(env_var)
        
    def Workdir(self,work_dir):
        self.workdir=os.path.join(self.workdir,work_dir)
        #Remove trailing slashes, but only for strings that are not /
        #if work_dir.endswith('/') and len(work_dir)>1:
            #work_dir=work_dir[:-1]
            #
        #if work_dir.startswith("/"):
            #self.self.workdir=work_dir
        #else:    
            #self.self.workdir+='/'+work_dir
        
        #Remove repeated / in workdir
        #self.self.workdir=re.sub(r'(/)\1+', r'\1',self.self.workdir)
        
    def Wait(delay=None):
        threading.Event().wait(timeout=delay)
    
    def Loop(self,command,delay=60):
        if isinstance(command,str):
            def func():
                while True:
                    self.Run(command)
                    self.Wait(delay)
        else:
            def func():
                while True:  
                    command()
                    self.Wait(delay)
        self.Run("") #Needed to avoid race conditions with a race that's right after --- just run self.self.Run once
        threading.Thread(target=func,daemon=True).start()
    
    def _setup(self):
        return
        
    def Run(self,command="",pipe=False,track=True,shell=False):
        if not self.setup:
            self._setup()
            self.setup=True
        
        if callable(command):
            return command()
            
        if self.build:
            if command.strip()!="":
                print(f"Command: {command}")
        
        with open(self.logfile,"a+") as log_file:
            if track:
                log_file.write(f"Command: {command}\n")
                log_file.flush()
            
            #Pipe output to variable
            if pipe:
                stdout=subprocess.PIPE
                stderr=subprocess.DEVNULL
            #Print output to file
            else:
                stdout=log_file
                stderr=subprocess.STDOUT
            
            return utils.shell_command(command,stdout=stdout,stderr=stderr,shell=shell,stdin=subprocess.DEVNULL)
    
    def command_Start(self):
        if self.parsing:
            return
        
        if "Started" in self.Status():
            return f"{self.class_name} {self.name} is already started"
        

        if os.fork()!=0: #Double fork
            return
        else:
            if os.fork()!=0:
                exit()
        
        with open(self.logfile,"a+") as f:
            pass
        #Open a lock file so I can find it with lsof later
        lock_file=open(self.lockfile,"w+")
        
        with open(self.lockfile,"w+") as f:
            json.dump({},f)
            
        signal.signal(signal.SIGTERM,self.Stop)
             

        try:
            self._exec(self.config)
        except:
            traceback.print_exc()
            self.Stop()
            
        self.Run() #Don't have to put Run() in container-compose.py just to start it
        self.Wait()
        exit()
    
    def _exec(self,code,env=None):
        if env==None:
            env={}
        
        execution_environment={}
        execution_environment["self"]=self
        for attr in self.attributes:
            execution_environment[attr]=getattr(self,attr)
        
        execution_environment |= env
        
        if isinstance(code,str):
            code=[code]
        
        for val in code:
            try:
                exec(val,execution_environment,locals())
            except SystemExit as e:
                exit(e)

    def command_Ps(self,process=None):
        if process=="main" or ("main" in self.flags):
            if not os.path.isfile(self.lockfile):
                    return []
            else:
                return list(map(int,[_ for _ in shell_command(["lsof","-t","-w",self.lockfile]).splitlines()]))
                
        elif process=="auxiliary" or ("auxiliary" in self.flags):
            return self.get_auxiliary_processes()
    
    def command_Stop(self):
        if "Stopped" in self.Status(): #Can return more than one thing
            return f"{self.class_name} {self.name} is already stopped"
        
        for pid in self.Ps("main"):
            kill_process_gracefully(pid)
        
        while self.Ps("auxiliary")!=[]: #If new processes were started during an iteration, go over it again, until you killed them all
            for pid in self.Ps("auxiliary"):
                kill_process_gracefully(pid)
                
        for file in ["log","lock"]:
            try:
               os.remove(getattr(self,file+"file"))
            except FileNotFoundError:
                pass
        for command in reversed(self.exit_commands): #it's a stack, not a queue
            command()

    def command_Restart(self):
        return [self.Stop(),self.__class__(self.name).Start()] #Restart completely new
        
    def command_List(self):
        return self.name

    def command_Status(self):
        if os.path.isfile(self.lockfile):
            return ["Started"]
        else:
            return ["Stopped"]
                
    def command_Log(self):
        shell_command(["less","+G","-f","-r",self.logfile],stdout=None)
    
    def command_Delete(self):
        self.Stop()
        shutil.rmtree(f"{self.ROOT}/{self.name}")
    
    def command_Watch(self):
        try:
            shell_command(["tail","-f","--follow=name",self.logfile],stdout=None)
        except KeyboardInterrupt:
            pass
    

