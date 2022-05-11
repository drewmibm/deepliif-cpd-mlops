import os
import requests
import time
import uuid
import shutil
import urllib
import subprocess
import json

# connect to wml space
import wml_sdk_utils as wml_util
wml_client = wml_util.get_client(space_id=space_id)

# download needed assets from wml space
fns = ['storage_volume_utils.py','cpd_utils.py','DeepLIIF_Statistics.zip']
wml_util.download_batch(fns,wml_client)

subprocess.run('unzip DeepLIIF_Statistics.zip',shell=True)

import storage_volume_utils as sv
from cpd_utils import *

# install additional lib
subprocess.run('pip install numba ibm-cloud-sdk-core==3.10.1',shell=True)
subprocess.run('pip install --upgrade ibm-watson-openscale',shell=True)

# headers for openscale's requests
headers = {}
headers["Content-Type"] = "application/json"
headers["Accept"] = "application/json"

#Update the run status to Finished in the custom monitor instance
def update_monitor_instance(base_url, access_token, custom_monitor_instance_id, payload):
    monitor_instance_url = base_url + '/v2/monitor_instances/' + custom_monitor_instance_id + '?update_metadata_only=true'

    patch_payload  = [
        {
            "op": "replace",
            "path": "/parameters",
            "value": payload
        }
    ]
    headers["Authorization"] = "Bearer {}".format(access_token)
    response = requests.patch(monitor_instance_url, headers=headers, json = patch_payload, verify=False)
    monitor_response = response.json()
    return response.status_code, monitor_response


#Add your code to compute the custom metrics. 
def get_metrics(subscription_id):
    #Add the logic here to compute the metrics. Use the below metric names while creating the custom monitor definition
    fn_meta = 'deployment_metadata.yml'
    metadata_all = wml_util.metadata_yml_load(wml_client,fn_meta=fn_meta)
    metadata = [metadata for model_asset_id,metadata in metadata_all.items() if metadata['openscale_subscription_id']==subscription_id]
    if len(metadata) == 0:
        return 0, {'error_msg':f'FAILED: Cannot find deployment associated with subscription id {subscription_id} in deployment metadata file {fn_meta}.'}
    elif len(metadata) > 1:
        return 0, {'error_msg':f'FAILED: Multiple model deployments are found with the same subscription id {subscription_id} in deployment metadata file {fn_meta}. It should be unique.'}
    
    metadata = metadata[0]
    env_name = os.getenv('HOSTNAME','')
    
    flag_local_test = 'jupyter-lab' in env_name
    dir_user = '/userfs' if flag_local_test else '/home/wmlfuser' # the working directory is /opt/ibm/scoring/python/py_scoring_base
    print(dir_user)
    

    path_script = 'DeepLIIF_Statistics/ComputeStatistics.py'
    dir_gt = 'DeepLIIF_Datasets/model_eval/gt_images' if flag_local_test else metadata['openscale_custom_metric_provider']['segmentation_metrics']['dir_gt']
    dir_pred = 'DeepLIIF_Datasets/model_eval/model_images' if flag_local_test else metadata['openscale_custom_metric_provider']['segmentation_metrics']['dir_pred']
    most_recent = 5 if flag_local_test else metadata['openscale_custom_metric_provider']['segmentation_metrics']['most_recent']
    num_files_least = 3
    
    os.environ['VOLUME_DISPLAY_NAME'] = 'AdditionalDeepLIIFVolume' if flag_local_test else metadata['openscale_custom_metric_provider']['segmentation_metrics']['volume_display_name']

    # download images
    files_gt = sv.list_files(dir_gt,most_recent=most_recent)
    files_pred = sv.list_files(dir_pred,most_recent=most_recent)
    num_files = len(files_gt)

    if num_files < num_files_least:
        return 0, {'error_msg': f'FAILED: Needs at least {num_files_least} newly created files in the past {most_recent} days to run the evaluation, currently only {num_files} files can be found.'}
    else:
        l_path_gt_img = [f"{dir_gt}/{x['path']}" for x in files_gt]
        l_path_pred_img = [f"{dir_pred}/{x['path']}" for x in files_pred]
        
        time_s = time.time()
        sv.download_batch(l_path_gt_img)
        print(f'elasped time for downloading gt: {time.time()-time_s}')
        time_s = time.time()
        sv.download_batch(l_path_pred_img)
        print(f'elasped time for downloading pred: {time.time()-time_s}')
        print('Finished downloading all images.')
            
        subprocess.run(f'python {path_script} --gt_path {dir_gt} --model_path {dir_pred} --output_path statistics/ > scores.log',shell=True)
        shutil.rmtree(f'{dir_gt}')
        shutil.rmtree(f'{dir_pred}')

        with open(f'scores.log','r') as f:
            lines = []
            scores = {}
            for line in f:
                lines.append(line)
                l = line.split()
                if len(l) == 2:
                    if l[0].replace('_','').isalnum() and not l[0].isnumeric():
                        try:
                            scores[l[0].lower()] = float(l[1])
                        except:
                            pass

        return scores

# Publishes the Custom Metrics to OpenScale
def publish_metrics(base_url, access_token, data_mart_id, subscription_id, custom_monitor_id, custom_monitor_instance_id, custom_monitoring_run_id, timestamp):
    # Generate an monitoring run id, where the publishing happens against this run id
    custom_metrics = get_metrics(subscription_id)
    measurements_payload = [
              {
                "timestamp": timestamp,
                "run_id": custom_monitoring_run_id,
                "metrics": [custom_metrics]
              }
            ]
    headers["Authorization"] = "Bearer {}".format(access_token)
    measurements_url = base_url + '/v2/monitor_instances/' + custom_monitor_instance_id + '/measurements'
    response = requests.post(measurements_url, headers=headers, json = measurements_payload, verify=False)
    published_measurement = response.json()

    return response.status_code, published_measurement



def score( input_data ):
    import datetime
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    payload = input_data.get("input_data")[0].get("values")
    data_mart_id = payload['data_mart_id']
    subscription_id = payload['subscription_id']
    custom_monitor_id = payload['custom_monitor_id']
    custom_monitor_instance_id = payload['custom_monitor_instance_id']
    custom_monitor_instance_params  = payload['custom_monitor_instance_params']

    base_url = os.environ['RUNTIME_ENV_APSX_URL'] + '/openscale' + '/' + data_mart_id
    access_token = get_access_token({'username':os.environ['USERNAME'],'api_key':os.environ['APIKEY']})
    os.environ['USER_ACCESS_TOKEN'] = access_token
    
    published_measurements = []
    error_msg = []

    custom_monitoring_run_id = custom_monitor_instance_params["run_details"]["run_id"]
        
#     return {'predictions':[{'values':[[get_metrics(subscription_id)]]}]}

    try:
        status_code, published_measurement = publish_metrics(base_url, access_token, data_mart_id, subscription_id, custom_monitor_id, custom_monitor_instance_id, custom_monitoring_run_id, timestamp)
        if int(status_code) in [200, 201, 202]:
            custom_monitor_instance_params["run_details"]["run_status"] = "finished"
            published_measurements.append(published_measurement)
        else:
            custom_monitor_instance_params["run_details"]["run_status"] = "error"
            custom_monitor_instance_params["run_details"]["run_error_msg"] = published_measurement
            error_msg.append(published_measurement)

        custom_monitor_instance_params["last_run_time"] = timestamp
        status_code, response = update_monitor_instance(base_url, access_token, custom_monitor_instance_id, custom_monitor_instance_params)
        if not int(status_code) in [200, 201, 202]:
            error_msg.append(response.text)

    except Exception as ex:
        error_msg.append(str(ex))
    if error_msg is None:
        response_payload = {
            "predictions" : [{ 
                "values" : published_measurements
            }]

        }
    else:
        response_payload = {
            "predictions": [],
            "error_msg": error_msg
        }

    return response_payload