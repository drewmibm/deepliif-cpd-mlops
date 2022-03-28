import os
import subprocess
from cpd_utils import *


# --------- training --------
def get_options_training(wmla_framework):
    """
    List commonly used options for WMLA training with example value.
    
    wml_framework: currently support PyTorch and distPyTorch
    """
    assert wmla_framework in ['PyTorch','distPyTorch'], 'Provide either PyTorch and distPyTorch as wmla_framework.'
    print('exec-start:        the wmla framework to use, such as PyTorch, distPyTorch, etc.')
    print('model-dir:         a local folder to be submitted, with model training scripts')
    print('model-main:        the main file to execute for training')
    print("cs-datastore-meta: location of data, this usually refers to the folder in WMLA's data volume; you can check the content or interact with it from WMLA's notebook server, under the 'data' folder")
    print('workerDeviceNum:   number of GPU devices in one worker pod')
    print('workerMemory:      memory of worker pod, increase the value if needed')
    print('msd-env:           custom environment variables & values; when used in cli, the command looks like this: ')
    print('                   python dlicmd.py --msd-env varA=1 --msd-env varB=mytoken ...')
    
    res = {'exec-start': wmla_framework,
           'model-dir': '/userfs/job_submission',
           'model-main': 'train_command.py',
           'cs-datastore-meta': 'type=fs,data_path=My_Datasets/',
           'workerDeviceNum':1,
           'workerMemory':'8g',
           'msd-env': ['varA=1','varB=mytoken']}
    
    if wmla_framework == 'PyTorch':
        return res
                
    elif wmla_framework == 'distPyTorch':
        print('numWorker:         number of worker pods to use; in the context of distributed deep learning, this is similar to the number of processes to open')
        print("* PyTorch's doc recommends to use 1 GPU per process in DistributedDataParallel. In WMLA, this is equivalent to workerDeviceNum = 1.")
        return {**res, **{'numWorker': 2}}
    
    else:
        raise Exception(f'{wmla_framework} is not supported by this function')


def prepare_submission_folder_training(paths_file=[],paths_folder=[],dir_submission=None,
                                       wmla_framework=None,file_training=None):
    """
    Copy the needed files to the submission folder. Underneath it calls "cp" command so wildcard can be 
    intepreted properly.
    
    paths_file: a list of file paths, wildcard (*) accepted
    paths_folder: a list of folder paths, wildcard (*) accepted and may essentially copy both files and
                  folders (example: /userfs/my-code-* is mapped to command "cp -r /userfs/my-code-*")
    dir_submission: the folder to copy everything to, by default gets the value from env var DIR_job_submission
    wmla_framework: when the value is distPyTorch, a code snippet needs to be inserted into the main training
                    script to initiate process group for multi-processing training
    file_training: the main training script, default to the execution file specified in os.environ['file_exec'] 
                   however, it may NOT be the same as your execution script
                     example:
                       main training script: train.py (pass train.py to this argument)
                       execution script: train_command.py, where it calls subprocess.run("python train.py ...")
                   the code snippet needs to be inserted in the main training file rather than the potential
                   wrapper script for execution, because in this case the real training happens in a sub-process
                   created by subprocess.run and this violates how "initiate process group" method works
    """
    dir_submission = fill_in_default_if_none(dir_submission,'DIR_job_submission','/userfs/job_submission')
    file_training = fill_in_default_if_none(file_training,'file_exec')
    print(f'Copying files and/or folders to {dir_submission}...')
    
    run_cmd(f'rm -rf {dir_submission}')
    run_cmd(f'mkdir -p {dir_submission}')
    
    for path_file in paths_file:
        run_cmd(f'cp {path_file} {dir_submission}')
    for path_folder in paths_folder:
        run_cmd(f'cp -r {path_folder} {dir_submission}')
        
    if wmla_framework == 'distPyTorch':
        if file_training is None:
            raise Exception('Please specify argument file_training for the function to patch this script.')
        else:
            print(f'Patching {dir_submission}/{file_training} for wmla framework {wmla_framework}...')
            content_add = str(
                """
import os
import torch.distributed as dist
def init_process():
    dist.init_process_group(
        backend='nccl',
        init_method='tcp://' + os.environ['MASTER_ADDR'] + ':' + os.environ['MASTER_PORT'],
        rank=int(os.environ['RANK']),
        world_size=int(os.environ['WORLD_SIZE']))
    
print('------ initiate process group... ------')
init_process()
                """
            )
            
            with open(f'{dir_submission}/{file_training}','r') as f:
                content = f.read()
                
            content = '\n\n'.join([content_add,content])
            with open(f'{dir_submission}/{file_training}','w') as f:
                f.write(content)
            
    print('Done')

def submit_training(options,rest_host=None,rest_port=-1,jwt_token=None,path_cli='dlicmd.py'):
    """
    options: options pass to the training submission command; view common options by get_options_training()
    rest_host: host name of your WMLA web console link
    rest_port: -1 as instructed by the doc
    jwt_token: the bearer token used for authentication, available in env var USER_ACCESS_TOKEN if
               you are in a WS environment, or by using cpd_utils.get_access_token(), or follow the API doc: https://cloud.ibm.com/apidocs/cloud-pak-data#getauthorizationtoken
    path_cli: path to the cli file
    """
    rest_host = fill_in_default_if_none(rest_host,'HOST','wmla-console-cpd-wmla.apps.cpd.mskcc.org')
    jwt_token = fill_in_default_if_none(jwt_token,'USER_ACCESS_TOKEN')
    
    assert jwt_token is not None, 'Provide the bearer token to authenticate. You can get it by using cpd_utils.get_access_token(), or follow the API doc: https://cloud.ibm.com/apidocs/cloud-pak-data#getauthorizationtoken'
    
    cmd = [f"python {path_cli}"]
    
    options['rest-host'] = rest_host
    options['rest-port'] = rest_port
    options['jwt-token'] = jwt_token
    
    for k,v in options.items():
        if isinstance(v,list):
            for e in v:
                cmd.append(f"--{k.replace('_','-')} {e}")
        else:
            cmd.append(f"--{k.replace('_','-')} {v}")
    
    run_cmd(' '.join(cmd))

# --------- inference --------
# def get_options_inference():

def kernel_file_prepare(path,variables={}):
    """
    Insert custom key-value pairs into kernel file, similar to function_prepare() in wml_sdk_utils.py.
    
    path: path to the WMLA EDI kernel script
    variables: a dictionary with key as variable name and value as variable value, to be added to the script
        example: 
            variables = {"space_id":"123456",
                         "username":"abcd"}
    """
    lines = []
    for k,v in variables.items():
        lines.append(f'{k} = {repr(v)}')
    
    # insert custom arguments after the first line in the original file
    # because the first line is #!/usr/bin/env python
    lines_file = open(path).readlines()
    lines_final = [lines_file[0]] + lines + [''.join(lines_file[1:])]
        
    with open(path,'w') as f:
        f.write('\n'.join(lines_final))

# --------- util --------
    
    
def fill_in_default_if_none(var,env_var=None,default=None):
    """
    Used to dynamically determine the default value of an argument.
    In this way, the default value is not determined at the time the module is
    imported, but at the time when the function is called.
    
    var: variable to examine
    env_var: the name of environment variable to pull the default value from
    default: if env_var is not defined in this function, or the corresponding 
    environment variable does not exist, fill with this default value
    """
    if var is None:
        if env_var is not None:
            return os.getenv(env_var,default)
        else:
            return default
    else:
        return var