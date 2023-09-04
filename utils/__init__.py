import subprocess
import re
import tempfile
import os
import pathlib
import signal 
import time
import contextlib
import sys
import shutil
import threading
import traceback
import json

def get_tempdir():
    if os.uname().sysname=="Darwin":
        return "/tmp"
    else:
        return tempfile.gettempdir()
    
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

def env_list_to_string(env_list):
    return '; '.join([f"export {_}" for _ in env_list])

def flatten_list(items):
    """Yield items from any nested iterable.""" 
    if isinstance(items,str):
        yield items
        return
        
    for x in items:
        if isinstance(x, list) and not isinstance(x, (str, bytes)):
            for sub_x in flatten_list(x):
                yield sub_x
        else:
            yield x
            
def parse_and_call_and_return(cls):

    """Split arguments into function, names, and flags"""
    arguments=sys.argv[1:]
    try:
        FUNCTION=arguments[0]
    except IndexError:
        raise ValueError("No command specified!")
        
    arguments=arguments[1:]
    
    NAMES=set()
    FLAGS=arguments
    for i in range(len(arguments)):
        if not arguments[i].startswith("--"):
            FLAGS=arguments[:i] #All flags must come before names
            NAMES=set(arguments[i:])
            break
    
    """Convert flags into dictionary"""
    flags_dict={}
    for flag in FLAGS:
        flag=flag.split('=',1) #Split every flag in FLAGS by '='
        if len(flag)==1:
            flag.append('') #Pad out the flag array so it can be accepted
        flag[0]=flag[0][2:] #Remove the '--'
        flags_dict[flag[0]]=flag[1] #--foo=bar becomes {'foo':'bar'}
    FLAGS=flags_dict
    
    all_items=cls.get_all_items()
    
    for flag in ["started","stopped","enabled","disabled"]:
        if flag in FLAGS:
            NAMES.update([_ for _ in all_items if flag.title() in cls(_,{}).Status() ])
            del FLAGS[flag]
            
    if "all" in FLAGS:
        NAMES.update(all_items)
        del FLAGS["all"]
        
    if len(NAMES)==0:
        ValueError(f"No {cls.__name__.lower()}s specified!")
    
    """Call function and print results"""
    for name in NAMES:
        instance=cls(name,FLAGS)
        func=getattr(instance,"command_"+FUNCTION.title(),None)
        if not callable(func):
            raise ValueError(f"Command {function.title()} doesn't exist!")
        
        result=flatten_list(func())
        for elem in result:
            if elem is None:
                print(end='')
            else:
                print(elem)
            
def check_if_any_element_is_in_list(elements,_list):
    return any(_ in _list for _ in elements)

@contextlib.contextmanager
def change_directory(path):
    """Sets the cwd within the context

    Args:
        path (Path): The path to the cwd

    Yields:
        None
    """

    origin = os.path.abspath(os.getcwd())
    try:
        if os.path.isdir(path):
            os.chdir(path)
        yield
    finally:
            os.chdir(origin)

def name_to_filename(name): #For platforms that don't use / as file separator
    return name.replace("/",os.sep)

def filename_to_name(filename):
    return filename.replace(os.sep,"/")
    
class Class(object):
    def __init__(self,name,flags,kwargs):
        if not flags:
            flags={}
            
        self.name=name
        
        self.directory=os.path.join(self._get_root(),name_to_filename(self.name))
        
        self.tempdir=os.path.join(get_tempdir(),self.__class__.__name__.title()+"s",name_to_filename(self.name))
        self.logfile=os.path.join(self.tempdir,"log")
        self.lockfile=os.path.join(self.tempdir,"lock")
        
        
        self.flags=flags
        
        self.exit_commands=[exit,self._exit]
        
        self.setup=False #Whether _setup was run once
        self.attributes=set(dir(self))
        
        """Read variables from .lock and overwrite self with them as a way to restart from a state (also avoids overwriting lockfile). However, if it doesn't exist, just make a new one"""
        if os.path.isfile(self.lockfile):
            with open(self.lockfile,"r") as f:
                data=json.load(f)
            
            for key in data:
                setattr(self,key,data[key])
            
    def __getattribute__(self, attr):
        try:
            attribute=object.__getattribute__(self, attr)
        except AttributeError:  #It's possible it is a command (like Start, Stop, etc)
            attr="command_"+attr
            attribute=object.__getattribute__(self, attr)
                
        if not (callable(attribute) and (attr[0].isupper() or attr.startswith("command_"))): #If they're just variables or functions not related to the application itself (ie, not user-facing or user-level)
            return attribute
        
        
        def wrapper(*args,**kwargs):
            with change_directory(self.directory):
                result=attribute(*args,**kwargs)
                if not attr.startswith("command_"): #Only functions should update the lockfile
                    self.update_lockfile()
                return result
                    
        return wrapper
            
    def _setup(self):
        return
        
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
    
    @classmethod
    def _get_root(cls):  
        try:
            cls.ROOT
        except:
            cls.ROOT=os.path.join(os.path.expanduser("~"),cls.__name__.title()+"s")
        return cls.ROOT
        
    def _get_config(self):
        return
                   
    #Functions        
    def update_lockfile(self):
        if not self.fork: #No lockfile when not forked --- state is kept within one class
            return
        
        with open(self.lockfile,"r") as f:
            data=json.load(f)
            
        for attr in dir(self):
              if callable(getattr(self, attr)) or attr.startswith("__") or attr:
                  continue
              
              try:
                  data[attr]=json.dumps(x)
              except (TypeError, OverflowError):
                  continue
              
        with open(self.lockfile,"w+") as f:
            json.dump(data,f)
    
    def get_auxiliary_processes(self):
        return []
    
    @classmethod
    def get_all_items(cls):
        return [_ for _ in sorted(os.listdir(cls._get_root())) if not _.startswith('.')]
        
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
    
        
    def Run(self,command="",pipe=False,track=True,shell=False):
        if not self.setup:
            self._setup()
            self.setup=True
        
        if callable(command):
            return command()
        
        
        if self.fork:
            stdout=open(self.logfile,"a+")
        else:
            stdout=sys.stdout
        
        if track:
            if command.strip()!="":
                stdout.write(f"Command: {command}\n")
                stdout.flush()
        else:
            stdout=subprocess.DEVNULL #Don't capture stdout
              
        if pipe: #Pipe output to variable 
            stdout=subprocess.PIPE
            stderr=subprocess.DEVNULL
        else:
            stderr=subprocess.STDOUT
            
            
        return utils.shell_command(command,stdout=stdout,stderr=stderr,shell=shell,stdin=subprocess.DEVNULL)
    
    def command_Start(self):
        if "Started" in self.Status():
            return f"{self.__class__.title()} {self.name} is already started"
        
        if self.fork:
            if os.fork()!=0: #Double fork
                return
            else:
                if os.fork()!=0:
                    exit()
            
            os.makedirs(self.tempdir,exist_ok=True)
            
            with open(self.logfile,"a+") as f: #Create file if it doesn't exist
                pass
            
            #Open a lock file so I can find it with lsof later
            lock_file=open(self.lockfile,"w+")
            
            with open(self.lockfile,"w+") as f:
                json.dump({},f)
            
            signal.signal(signal.SIGINT,self.Stop)
               
        signal.signal(signal.SIGTERM,self.Stop)
             

        try:
            self._exec(self._get_config())
        except:
            traceback.print_exc()
            self.Stop()
            
        self.Run() #Don't have to put Run() in container-compose.py just to start it
        self.Wait()
        exit()
    

    def command_Ps(self,process=None):
        if process=="main" or ("main" in self.flags):
            if not os.path.isfile(self.lockfile):
                    return []
            else:
                return list(map(int,[_ for _ in shell_command(["lsof","-t","-w",self.lockfile]).splitlines()]))
                
        elif process=="auxiliary" or ("auxiliary" in self.flags):
            return self.get_auxiliary_processes()
    
    def command_Stop(self): #Just make this an exit command
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
    

