#!/usr/bin/env python

import redhareapiversion
from redhareapi import Kernel

import traceback
import json
import time
from datetime import datetime,timezone
import os
import subprocess
import sys
import requests
import urllib
import urllib3
from zipfile import ZipFile
import storage_volume_utils as sv
import cpd_utils as cpdu
import wmla_edi_utils as edi
import config
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

deploy_name = os.environ['REDHARE_MODEL_NAME']
dir_user = os.environ['REDHARE_MODEL_PATH']
filename_model = os.environ['WML_SPACE_MODEL']
DEFAULT_DIR = os.environ['PWD']
dir_python_pkg = f"{dir_user}/python_packages"
os.environ['DEEPLIIF_MODEL_DIR'] = f'{dir_user}/{os.path.splitext(filename_model)[0]}'
os.environ['DEEPLIIF_SEED'] = 'None'
os.makedirs(dir_python_pkg,exist_ok=True)
sys.path.insert(0, dir_python_pkg)

os.chdir(dir_user)

class MatchKernel(Kernel):
    def on_kernel_start(self, kernel_context):
        credentials = {'username':config.username,
                       'api_key':config.api_key}
        os.environ['USER_ACCESS_TOKEN'] = cpdu.get_access_token(credentials)
        
        KERNEL_LOG_PATH = f'edi_deployments/{deploy_name}/edi_logs/{os.environ["MSD_POD_NAME"]}_inference.log'
        self.kernel_log_path = KERNEL_LOG_PATH
        
        edi.log(f"Install non-torch pip dependencies to {dir_python_pkg}", self.kernel_log_path)
        out = subprocess.check_output(f'pip install ibm-watson-machine-learning dominate visdom gpustat numba==0.54.1 --target={dir_python_pkg}',
                                      shell=True, text=True, stderr=subprocess.STDOUT)
        edi.log(out, self.kernel_log_path)
        
        edi.log("Install torch pip dependencies", self.kernel_log_path)
        out = subprocess.check_output(f'pip install torch==1.10.1+cu111 -f https://download.pytorch.org/whl/torch_stable.html --target={dir_python_pkg}',
                                      shell=True, text=True, stderr=subprocess.STDOUT)
        edi.log(out, self.kernel_log_path)
        
        # Unzip deepliif code
        edi.log('Start unzipping deepliif code', self.kernel_log_path)
        with ZipFile('deepliif.zip', 'r') as z:
            z.extractall('deepliif')
        
        # Add new lib path to for running cli.py
        with open('cli.py', 'r+') as fd:
            contents = fd.readlines()
            contents.insert(0, f"import sys\nsys.path.insert(0, '{dir_python_pkg}')\n")
            fd.seek(0)
            fd.writelines(contents)

        # WML client
        import wml_sdk_utils as wml_util
        wml_client = (wml_util
                      .get_client(credentials={'url':os.getenv('BASE_URL',
                                                               os.getenv('RUNTIME_ENV_APSX_URL',
                                                                         'https://cpd-cpd.apps.cpd.mskcc.org')),
                                               'username':config.username,
                                               'apikey':config.api_key},
                                  space_id=os.environ['WML_SPACE_ID']))
        
        edi.log("Start downloading model file", self.kernel_log_path)
        t_s = datetime.now()
        wml_util.download(filename_model, wml_client, dir_user)
        t_e = datetime.now()
        d = t_e - t_s
        edi.log(f"Model file download complete...elapsed time: {d.seconds}s {d.microseconds}ms", 
                    self.kernel_log_path)
        
        edi.log("Start unzipping model file", self.kernel_log_path)
        with ZipFile(filename_model, 'r') as z:
            z.extractall(dir_user)
 
        edi.log("Kernel initiation complete", self.kernel_log_path)
        
    def on_task_invoke(self, task_context):
        try:
            in_invoke_time = datetime.now()
            credentials = {'username':config.username,
                           'api_key':config.api_key}   
            os.environ['USER_ACCESS_TOKEN'] = cpdu.get_access_token(credentials)
            
            edi.log(f"Inference request received with job ID {os.environ['TASK_JOB_ID']}", self.kernel_log_path)

            while task_context != None:
                
                # Parse payload data
                input_data = json.loads(task_context.get_input_data())
                
                ## Tile size
                try:
                    tile_size = int(input_data['tile_size'])
                except:
                    tile_size = 512
                    
                ## Images to return
                try:
                    images_to_return = str(input_data['images_to_return'])
                except:
                    images_to_return = 'all'
                
                path_source = input_data['img_path_on_pvc']
                
                OUTPUT_DIR = f'edi_deployments/{deploy_name}/output_dir/{os.environ["TASK_JOB_ID"]}'
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                
                INPUT_DIR = f'edi_deployments/{deploy_name}/input_dir'
                os.makedirs(INPUT_DIR, exist_ok=True)
                
                edi.log(f"Downloading input image", self.kernel_log_path)
                sv.download(path_source, INPUT_DIR)
                fd = os.path.dirname(path_source)
                        
                edi.log("Starting inference", self.kernel_log_path)
                t_s = datetime.now()

                try:
                    cmd = (f"python cli.py test --input-dir {INPUT_DIR}/{fd} "
                           f"--output-dir {OUTPUT_DIR} --tile-size {tile_size}")
                    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, 
                                                  text=True, cwd=dir_user)
                    edi.log('Images generated successfully', self.kernel_log_path)
                except subprocess.CalledProcessError as e:
                    out = e.output
                    edi.log(out, self.kernel_log_path)
                else:
                    t_e = datetime.now()
                    d = t_e - t_s
                    edi.log(f"Inference complete...elapsed time: {d.seconds}s {d.microseconds}ms", 
                                self.kernel_log_path)
                
                    edi.log("Sending files to storage volume", self.kernel_log_path)
                    edi.prepare_output_images(images_to_return, f"{OUTPUT_DIR}")
                    sv.upload(OUTPUT_DIR)
                    edi.log(f"Output uploaded to {OUTPUT_DIR} on {os.environ['VOLUME_DISPLAY_NAME']}", 
                                self.kernel_log_path)
                
                    output_data = {'msg': [f"Inference complete, output files can be found in {OUTPUT_DIR} (storage volume {os.environ['VOLUME_DISPLAY_NAME']})"]}
                    task_context.set_output_data(json.dumps(output_data))
                    task_context = task_context.next()
                    
            done_invoke_time = datetime.now()
            d = done_invoke_time - in_invoke_time
            edi.log(f"Inference request complete...total elapsed time: {d.seconds}s {d.microseconds}ms", 
                        self.kernel_log_path)
        except Exception as e:
            traceback.print_exc()
            Kernel.log_error(f"Failed due to {str(e)}")
    
    def on_kernel_shutdown(self):
        subprocess.run(f'rm -rf {dir_user}/*', shell=True)
        edi.log(f"Files deleted, closing kernel {os.environ['MSD_POD_NAME']}", 
                    self.kernel_log_path)

        
if __name__ == '__main__':
    obj_kernel = MatchKernel()
    obj_kernel.run()
