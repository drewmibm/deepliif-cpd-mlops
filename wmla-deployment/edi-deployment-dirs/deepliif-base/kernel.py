#!/usr/bin/env python

import redhareapiversion
from redhareapi import Kernel

import traceback
import json
import time
from datetime import datetime
import os
import subprocess
import sys
import pickle
import pkg_resources
from packaging import version
import urllib3
from zipfile import ZipFile
import uuid
import base64
from io import BytesIO
from PIL import Image
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import storage_volume_utils as sv
import cpd_utils as cpdu
import wmla_edi_utils as edi

### Expected custom_args
### The following variables are inserted by the cli_mlops.py deploy command
### Ensure the custom_args key names match these variables

# CPD_USERNAME
# CPD_API_KEY
# VOLUME_DISPLAY_NAME


deploy_name = os.environ['REDHARE_MODEL_NAME']
dir_user = os.environ['REDHARE_MODEL_PATH']
filename_model = os.environ['WML_SPACE_MODEL']

dir_python_pkg = f"{dir_user}/python_packages"
os.environ['DEEPLIIF_MODEL_DIR'] = f'{dir_user}/{os.path.splitext(filename_model)[0]}'
os.environ['DEEPLIIF_SEED'] = 'None'
os.environ['VOLUME_DISPLAY_NAME'] = VOLUME_DISPLAY_NAME
os.makedirs(dir_python_pkg,exist_ok=True)
sys.path.insert(0, dir_python_pkg)

os.chdir(dir_user)


# Universe of valid images in response, excluding original IHC
modality_images = ['Hema',
                   'DAPI',
                   'Lap2',
                   'Marker',]
seg_images = ['Seg',
              'SegOverlaid',
              'SegRefined',]
all_images = modality_images + seg_images

image_return_dict = {'all':all_images,
                     'modalities':modality_images,
                     'seg_masks':seg_images}


class MatchKernel(Kernel):

    def on_kernel_start(self, kernel_context):
        t_s = datetime.now()
        
        credentials = {'username':CPD_USERNAME,
                       'api_key':CPD_API_KEY}
        os.environ['USER_ACCESS_TOKEN'] = cpdu.get_access_token(credentials)
        
        KERNEL_LOG_PATH = f'edi_deployments/{deploy_name}/edi_logs/{os.environ["MSD_POD_NAME"]}_inference.log'
        self.kernel_log_path = KERNEL_LOG_PATH
        
        # -------- check and install packages: it's faster to manually check and skip installed ones --------
        with open('requirements.txt') as f:
            requirements = f.readlines()
        pkgs = pkg_resources.parse_requirements(requirements)
        dict_pkg = {i.key:i.specs for i in pkgs}
        
        print(f"Install pip dependencies to {dir_python_pkg}")
        
        idx_to_install = []
        for i,(pkg_name,pkg_specs) in enumerate(dict_pkg.items()):
            # refresh installed packages in case other kernel has installed a new package (lib path is shared)
            installed_packages = pkg_resources.working_set
            installed_packages = {pkg.key:pkg.version for pkg in installed_packages}

            print(i,pkg_name,pkg_specs)
            if pkg_name in installed_packages:
                if len(pkg_specs)>0:
                    code_compare = f"version.parse('{installed_packages[pkg_name]}') {pkg_specs[0][0]} version.parse('{pkg_specs[0][1]}')"
                    if not eval(code_compare):
                        print(f'{pkg_name}: wait to be installed')
                        idx_to_install.append(i)
                    else:
                        print(f'{pkg_name}: already installed')
                else:
                    print(f'{pkg_name}: already installed')
            else:
                print(f'{pkg_name}: wait to be installed')
                idx_to_install.append(i)

        requirements_new = [requirements[i] for i in idx_to_install]
        with open(f'requirements_{os.environ["MSD_POD_NAME"]}.txt','w') as f:
            f.writelines(requirements_new)
        
        if len(idx_to_install)>0:
            out = subprocess.check_output(f'pip install -r requirements_{os.environ["MSD_POD_NAME"]}.txt -f https://download.pytorch.org/whl/torch_stable.html --target={dir_python_pkg}', shell=True, text=True, stderr=subprocess.STDOUT)
            print(out)
        
        # -------- download model file from WML space --------
        # WML client
        import wml_sdk_utils as wml_util
        wml_client = (wml_util
                      .get_client(credentials={'url':os.getenv('BASE_URL',
                                                               os.getenv('RUNTIME_ENV_APSX_URL',
                                                                         'https://cpd-cpd.apps.cpd.mskcc.org')),
                                               'username':CPD_USERNAME,
                                               'apikey':CPD_API_KEY},
                                  space_id=os.environ['WML_SPACE_ID']))
        
        if not os.path.exists(f'{dir_user}/{filename_model}'):
            print("Start downloading model file")
            t_s = datetime.now()
            wml_util.download(filename_model, wml_client, dir_user)
            t_e = datetime.now()
            d = t_e - t_s
            print(f"Model file download complete...elapsed time: {d.seconds}s {d.microseconds}ms", 
                        self.kernel_log_path)

            print("Start unzipping model file")
            with ZipFile(filename_model, 'r') as z:
                z.extractall(dir_user)
        
        # -------- unzip deepliif archive --------
        if not os.path.exists('deepliif'):
            # Unzip deepliif code
            print('Start unzipping deepliif code')
            with ZipFile('deepliif.zip', 'r') as z:
                z.extractall('deepliif')
        
        # -------- add new lib path for running cli.py --------
        with open('cli.py', 'r+') as fd:
            contents = fd.readlines()
            if f"import sys\nsys.path.insert(0, '{dir_python_pkg}')\n" not in contents:
                contents.insert(0, f"import sys\nsys.path.insert(0, '{dir_python_pkg}')\n")
                fd.seek(0)
                fd.writelines(contents)
        
        d = datetime.now() - t_s
        print(f"Kernel initiation complete...elapsed time: {d.seconds}s {d.microseconds}ms")
        
    def on_task_invoke(self, task_context):
        in_invoke_time = datetime.now()
        
        output_data = {'request_id': '',
                       'status': 'submitted',
                       'log': [],
                       'msg': ''}
        
        try:
            # -------- refresh token --------
            credentials = {'username':CPD_USERNAME,
                           'api_key':CPD_API_KEY}   
            os.environ['USER_ACCESS_TOKEN'] = cpdu.get_access_token(credentials)
            
            # parse payload data
            input_data = json.loads(task_context.get_input_data())
            request_id = str(input_data['request_id']) if 'request_id' in input_data else str(uuid.uuid4())
            tile_size = str(input_data['tile_size']) if 'tile_size' in input_data else 512
            images_to_return = str(input_data['images_to_return']) if 'images_to_return' in input_data else 'all'
            path_source = input_data.get('img_path_on_pvc')
            local_image = input_data.get('local_input_image')
            
            output_data['request_id'] = request_id
            edi.log(f'{request_id}: inference request received',self.kernel_log_path)

            # -------- check input --------
            if path_source is None and local_image is None:
                output_data['status'] = 'failed'
                output_data['msg'] = 'Error: no valid input image, provide either path_source or local_image'
                task_context.set_output_data(json.dumps(output_data))
                return
            
            if path_source is not None and local_image is not None:
                output_data['log'].append('Warning: both path_source and local_image are specified; only path_source will be used')
                
            try:
                tile_size = int(tile_size)
            except:
                output_data['status'] = 'failed'
                output_data['msg'] = 'Error: tile size is not integer'
                task_context.set_output_data(json.dumps(output_data))
                return

            if images_to_return not in image_return_dict.keys():
                output_data['status'] = 'failed'
                output_data['msg'] = f"Error: images_to_return is not one of {list(image_return_dict.keys())}"
                task_context.set_output_data(json.dumps(output_data))
                return
            
            # -------- run inference --------
            OUTPUT_DIR = f'edi_deployments/{deploy_name}/output_dir/{request_id}'
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            INPUT_DIR = f'edi_deployments/{deploy_name}/input_dir'
            os.makedirs(INPUT_DIR, exist_ok=True)

            print(f"Getting input image")
            output_data['status'] = 'running'
            output_data['log'].append(f"Getting input image")

            if path_source is not None:  # Default to PVC image
                return_images = False  # whether or not to return images in response
                sv.download(path_source, INPUT_DIR)
                fd = os.path.dirname(path_source)
                print('Using image from storage volume')
            else:  # Otherwise use local image from input payload
                return_images = True
                input_image = Image.open(BytesIO(base64.b64decode(local_image)))
                filename = "local.png"
                input_image.save(os.path.join(INPUT_DIR, filename))
                fd = ""
                print('Using image from input')

            print("Starting inference")
            output_data['log'].append("Starting inference")
            
            t_s = datetime.now()

            cmd = (f"python cli.py test --input-dir {INPUT_DIR}/{fd} "
                   f"--output-dir {OUTPUT_DIR} --tile-size {tile_size}")
            out = subprocess.run(cmd, shell=True, capture_output=True, cwd=dir_user)
            if out.returncode != 0:
                print(out)
                output_data['status'] = 'failed'
                output_data['log'].append(str(out))
                output_data['msg'] = 'Error: inference failed. Check the log field for more information.'
                task_context.set_output_data(json.dumps(output_data))
                return
            
            t_e = datetime.now()
            d = t_e - t_s
            print('Images generated successfully')
            print(f"Inference complete...elapsed time: {d.seconds}s {d.microseconds}ms")
            output_data['log'].append('Images generated successfully')
            output_data['log'].append(f"Inference complete...elapsed time: {d.seconds}s {d.microseconds}ms")

            # remove unneeded images from output dir
            output_images_keepers = image_return_dict[images_to_return].copy()
            drop_files = []
            for f in os.listdir(OUTPUT_DIR):
                tp = f.split('_')[-1].split('.')[0]
                if tp not in output_images_keepers:
                    drop_files.append(f)
            if len(drop_files) > 0:
                for f in drop_files:
                    path = os.path.join(OUTPUT_DIR,f)
                    os.remove(path)
            
            # prepare output response
            if return_images:
                output_data['images'] = {}

                for _, _, files in os.walk(OUTPUT_DIR):
                    for file in files:
                        if file.endswith('.png'):
                            img = Image.open(os.path.join(OUTPUT_DIR, file))
                            buffer = BytesIO()
                            img.save(buffer, 'PNG')
                            serialized = base64.b64encode(buffer.getvalue()).decode('utf-8')
                            basename = os.path.basename(file)
                            output_data['images'][basename] = serialized
               
                output_data['msg'] = f'{request_id}: Inference complete, output images can be found in images field.'
            else:
                print("Sending files to storage volume")
                sv.upload(OUTPUT_DIR)

                output_data['msg'] = f"{request_id}: Inference complete, output files can be found in {OUTPUT_DIR} (storage volume {VOLUME_DISPLAY_NAME})"
                edi.log(output_data['msg'],self.kernel_log_path)
            
            output_data['status'] = 'finished'
            done_invoke_time = datetime.now()
            d = done_invoke_time - in_invoke_time
            print(f"Inference request complete...total elapsed time: {d.seconds}s {d.microseconds}ms")
            
            task_context.set_output_data(json.dumps(output_data))
            
        except Exception as e:
            traceback.print_exc()
            output_data['msg'] = str(e)
            task_context.set_output_data(json.dumps(output_data))
    
    def on_kernel_shutdown(self):
        pass

        
if __name__ == '__main__':
    obj_kernel = MatchKernel()
    obj_kernel.run()
