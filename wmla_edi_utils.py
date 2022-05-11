import requests
import urllib
import os
from datetime import datetime, timezone
import storage_volume_utils as sv
import cpd_utils as cpdu
from typing import Union, List
import subprocess
from time import sleep
from typing import Optional
from PIL import Image
from io import BytesIO
import base64

if os.environ.get('REDHARE_MODEL_NAME', False):
    from redhareapi import Kernel



def log(message:Union[str,List], path_source:str,
        save_log_to_volume:bool=True, access_token:str=None,
        volume_display_name:str=None) -> None:
    """Upload a message to the log on a remote storage volume.
    
            Parameters:
                    message (str or list): String or list of strings to write to log
                    path_source (str): Path to log file, including log filename
                    save_log_to_volume (bool): Write to storage volume or only to WMLA log?
                    access_token (str): CPD access token
                    volume_display_name (str): Name of the storage volume to write to
    """
    
    if not isinstance(message,list):
        message = [message]
    
    try:
        for m in message:
            Kernel.log_info(m)
    except:
        pass
    
    timestamp_str = (datetime
                     .now(timezone.utc)
                     .strftime("[%Y-%m-%d %H:%M:%S%z]"))
    message.insert(0, timestamp_str)
    message.insert(len(message), '') # double-spacing between log messages
    
    if save_log_to_volume:
        volume_display_name = sv.fill_in_default_if_none(volume_display_name,
                                                         'VOLUME_DISPLAY_NAME',
                                                         'DeepLIIFData')
        access_token = sv.fill_in_default_if_none(access_token,
                                                  'USER_ACCESS_TOKEN')
        
        if os.path.isdir(path_source):
            backup_name =  os.getenv('MSD_POD_NAME','edi_inference') + '.log'
            path_source = path_source.rstrip('/')
            path_source = f"{path_source}/{backup_name}"
            try:
                Kernel.log_info(f'No filename provided for log...defaulting to {backup_name}')
            except:
                pass
        
        LOG_LOCAL_PATH = path_source
        LOG_DIRNAME = os.path.dirname(LOG_LOCAL_PATH)
        LOG_FILENAME = os.path.basename(LOG_LOCAL_PATH)

        try:
            file_list = sv.list_files(LOG_DIRNAME, access_token=access_token)
        except:
            file_list = None
        else:
            if file_list is not None and LOG_FILENAME in file_list:
                sv.download(LOG_LOCAL_PATH, access_token=access_token)

    # Write to internal storage regardless
    os.makedirs(LOG_DIRNAME, exist_ok=True)
    with open(LOG_LOCAL_PATH, 'a') as file:
        file.writelines(f"{x}\n" for x in message)

    if save_log_to_volume:
        sv.upload(LOG_LOCAL_PATH, access_token=access_token)
        
        
def run_subprocess(cmd: str) -> str:
    """Run a subprocess in the current shell
        Args:
            cmd: command to run in shell
        Outputs:
            STDOUT and STDERR string
    """
    try:
        return subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=True).stdout.splitlines()
    except Exception as e:

        return f"Failed due to {str(e)}\n{str(e.output)}".splitlines()


def run_subprocess_and_retry(cmd: str, verification_str: str, delay=3,
                             retries=3, verification_line=0) -> Optional[str]:
    """Run a subprocess and retry if output does not match expectations
        Args:
            cmd: command to run in shell
            verification_str: first line of subprocess output needs
                              to match this string, otherwise retry
            verification_line: line number in output to match
    """
    out = None
    for i in range(retries):
        out = run_subprocess(cmd)

        if out[verification_line] == verification_str:
            return out
        if delay > 0 and i < (retries - 1):
            sleep(delay)
    return out

def get_deployment_view_item(deployment_name: str, search_str: str) -> str:
    """Gets the value of a status item from dlim view API
        Args:
            deployment_name: string identifier of deployment
            search_str: key to look for within returned text from view API
        Returns:
            value of key within text from returned view API
    
    """
    
    view = run_subprocess(f"dlim model view {deployment_name} -s -a --rest-server $REST_SERVER --jwt-token $USER_ACCESS_TOKEN")
    if view:
        for line in view:
            if line.startswith(search_str):
                return line.split(":")[1].strip() # Get value after colon and remove whitespace

def wait_for_model_idle_status(deployment_name: str, retries: int = 60, delay: int = 5):
    """Wait for the deployed model to return a Started status
        Args:
            deployment_name: string identifier of deployment
            retries: number of API attempts to determine start status
            delay: number of seconds between API calls
    """
    for i in range(retries):

        if get_deployment_view_item(deployment_name, 'Status') == 'IDLE':
            return
        if delay > 0 and i < (retries - 1):
            sleep(delay)


def serialize_image(img: Image) -> str:
    """Serialize a PIL image into a UTF-8 string
        Args:
            img: PIL image
        Returns:
            str
        Notes:
            useful for serializing images for RESTful requests
    """
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


def deserialize_image(bs: str) -> Image:
    """Deserializes a string back into a BytesIO object/Image
        Args:
            bs: string representing bytes
        Returns:
            BytesIO/Image object
    """
    return BytesIO(base64.b64decode(bs))