import os
import time
import pandas as pd
from ibm_cloud_sdk_core.authenticators import *
from ibm_watson_openscale import APIClient
from ibm_watson_openscale.base_classes.watson_open_scale_v2 import *
from ibm_watson_openscale import *
from ibm_watson_openscale.supporting_classes.enums import *
from ibm_watson_openscale.supporting_classes import *

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_MART_ID = '00000000-0000-0000-0000-000000000000'

def get_client(credentials=None):
    """
    credentials: a dictionary with either
                 - key "url" and "token"
                 - key "url", "username", and "apikey"
    """
    if credentials is None:
        if os.getenv('USERNAME') is not None and os.getenv('APIKEY') is not None:
            credentials = {'url':os.getenv('BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL','https://cpd-cpd.apps.cpd.mskcc.org')),
                           'username': os.environ['USERNAME'],
                           'apikey':os.environ['APIKEY']}
            
            return APIClient(authenticator=CloudPakForDataAuthenticator(**credentials), 
                             service_url=credentials['url'])

        else:
            credentials = {'url':os.getenv('BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL','https://cpd-cpd.apps.cpd.mskcc.org')),
                           'token':os.environ['USER_ACCESS_TOKEN']}
    
            return APIClient(authenticator=BearerTokenAuthenticator(bearer_token=credentials['token']), 
                             service_url=credentials['url'])
    else:
        if 'token' in credentials:
            return APIClient(authenticator=BearerTokenAuthenticator(bearer_token=credentials['token']), 
                             service_url=credentials['url'])
        else:
            return APIClient(authenticator=CloudPakForDataAuthenticator(**credentials), 
                             service_url=credentials['url'])

def service_provider_list(wos_client,return_json=False):
    """
    List service providers.
    
    return_json: if False, return a normalized pandas dataframe
    """
    service_providers = wos_client.service_providers.list().get_result().to_dict()['service_providers']
    if return_json:
        return service_providers
    else:
        return pd.json_normalize(service_providers)

DICT_SERVICE_PROVIDER_TYPE = {'custom':ServiceTypes.CUSTOM_MACHINE_LEARNING,
                              'wml':ServiceTypes.WATSON_MACHINE_LEARNING,
                              'aws':ServiceTypes.AMAZON_SAGEMAKER,
                              'azure':ServiceTypes.AZURE_MACHINE_LEARNING,
                              'spss':ServiceTypes.SPSS_COLLABORATION_AND_DEPLOYMENT_SERVICES}

def service_provider_create(wos_client,name,description='',operational_stage='production', credentials=None,
                            service_provider_type='custom',headless=True,overwrite=False):
    """
    Create a service provider. Currently only supports a headless ml provider.
    A list of service provider ids with matching name and type will be returned instead, if existing ones are found AND
    overwrite = False.
    
    name: name of the new service provider
    description: description of the new service provider
    operational_stage: a string value, either "production" or "pre_production"
    credentials: credentials used to connect to this new service provider; left as None for a headless custom provider
    service_provider_type: currently only supports "custom"
    headless: currently only supports True
    overwrite: whether to overwrite if found any existing one with the same name
    """
    if service_provider_type not in DICT_SERVICE_PROVIDER_TYPE.keys():
        raise Exception(f'service provider_type {service_provider_type} is not one of {list(DICT_SERVICE_PROVIDER_TYPE.keys())}')
    
    if service_provider_type != 'custom':
        raise Exception('not implemented')
    if not headless:
        raise Exception('not implemented')
    
    if credentials is None:
        if service_provider_type == 'custom' and headless:
            credentials = WMLCredentialsCP4D()
    
    service_providers = wos_client.service_providers.list().get_result().to_dict()['service_providers']
    service_provider_ids = [service_provider['metadata']['id'] for service_provider in service_providers if service_provider['entity']['name']==name and service_provider['entity']['service_type']==DICT_SERVICE_PROVIDER_TYPE[service_provider_type]]
    print(f'{len(service_provider_ids)} existing service providers found with the same name {name} and type {service_provider_type}')
    
    if len(service_provider_ids) > 0:
        if not overwrite:
            if len(service_provider_ids) == 1:
                return service_provider_ids[0]
            else:
                return service_provider_ids
        else:
            print('Overwrite is on, deleting the existing one(s)...')
            for service_provider_id in service_provider_ids:
                wos_client.service_providers.delete(service_provider_id)
                print(f'Deleted service provider {service_provider_id}')
    
    added_service_provider_result = wos_client.service_providers.add(
        name=name,
        description=description,
        service_type=DICT_SERVICE_PROVIDER_TYPE[service_provider_type],
        operational_space_id = operational_stage,
        credentials=credentials,
        background_mode=False
     ).result
    
    return added_service_provider_result.metadata.id

def integrated_system_delete(integrated_system_name,wos_client):
    """
    For safety reason, this function only deletes integrated systems of type "custom_metric_provider".
    """
    integrated_systems = IntegratedSystems(wos_client).list().result.integrated_systems
    for system in integrated_systems:
        if system.entity.type == 'custom_metrics_provider' and system.entity.name == integrated_system_name:
            IntegratedSystems(wos_client).delete(integrated_system_id=system.metadata.id)
            print("Deleted integrated system {}".format(system.entity.name))
            
def monitor_definition_delete(monitor_name,wos_client):
    monitor_id = get_monitor_id_by_name(monitor_name,wos_client)
    if isinstance(monitor_id,str):
        wos_client.monitor_definitions.delete(monitor_id)
        print(f'Deleted existing monitor definition {monitor_name} ({monitor_id})')

def monitor_definition_create(monitor_name,d_defaults,wos_client,overwrite=False):
    """
    d_defaults: a dictionary with metric name as key and a sub dictionary as value containing
                information about 
                 - threshold (a list of 2 values, the first for threshold value and the second for type 
                   (either upper or lower, lower means the value functions as a lower limit while upper
                    means the value functions as an upper limit))
                 - tags (optional, a list of 2 values, the first for tag name and the second for tag
                   description)
                example:
                    {"metricA":
                        {"threshold":[10,"upper"],
                         "tag":["projectXYZ_metrics","special metrics used for project XYZ defined as ..."]}}
                * currently if you use tags, make sure you have tag specified for EVERY metric in your definition
    """
    # check if monitor name exists
    monitor_id = get_monitor_id_by_name(monitor_name,wos_client)
    if isinstance(monitor_id,str):
        if overwrite:
            monitor_definition_delete(monitor_name,wos_client)
            time.sleep(3)
        else:
            print(f'Found monitor definition {monitor_name}')
            return monitor_id
    elif isinstance(monitor_id,list):
        raise Exception(f'Multiple definitions are found with the same name {monitor_name}. This is usually wrong, fix your monitor definitions.')
    else:
        pass
    
    metrics = []
    tags = []
    for metric,values in d_defaults.items():
        metrics.append(MonitorMetricRequest(name=metric,
                                            thresholds=[MetricThreshold(type=f'{values["threshold"][1]}_limit', default=values["threshold"][0])]))
        if "tag" in values.keys():
            tags.append(MonitorTagRequest(name=values['tag'][0], description=values['tag'][1]))
        
    if len(tags) < len(metrics) and len(tags) > 0:
        print('Not all metrics have a tag. Force tags to be empty. If you want to specify tags, make sure you do that for all metrics.')
        tags = []
            
    monitor_details = wos_client.monitor_definitions.add(name=monitor_name, 
                                                        metrics=metrics, 
                                                        tags=tags, 
                                                        background_mode=False).result
    return monitor_details.metadata.id


def get_default_thresholds(monitor_id,wos_client):
    """
    Get default thresholds of all metrics defined in a monitor definition. Using this as the base,
    you can modify it to create your custom thresholds for a monitor instance tied to your subscription.
    """
    monitor_definitions = wos_client.monitor_definitions.list().result.to_dict()['monitor_definitions']
    metrics = [x['entity']['metrics'] for x in monitor_definitions if x['metadata']['id']==monitor_id]
    
    if len(metrics) == 0:
        raise Exception(f'Cannot find monitor definition for {monitor_id}')
    elif len(metrics) > 1:
        raise Exception(f'Multiple monitor definitions are found for {monitor_id}. This is usually wrong, check your configurations.')
    else:
        metrics = metrics[0]
        res = {}

        for metric in metrics:
            res[metric['name']] = {'threshold': [metric['thresholds'][0]['default'],
                                                 metric['thresholds'][0]['type'].replace('_limit','')]}
        return res
    
def get_thresholds_from_metadata(metadata,monitor_id,wos_client,monitor_type='custom_metric_provider'):
    """
    Format the thresholds confiuration in metadata to what OpenScale consumes.
    
    metadata: deployment metadata, a dictionary
              example:
                {'deployment_id': None,
                  'model_asset': 'Test_Model_wendy_ws_serialized2.zip',
                  'model_name': 'DeepLIIF wendy serialized test',
                  'openscale_custom_metric_provider': {'generic_metrics': {'dir_gt': 'DeepLIIF_Datasets/model_eval/gt_images',
                    'dir_pred': 'DeepLIIF_Datasets/model_eval/model_images',
                    'most_recent': 1,
                    'thresholds': {'num_images_recent_ground_truth': {'threshold': [100,
                       'lower']},
                     'num_images_recent_predicted': {'threshold': [800, 'lower']},
                     'num_images_total_ground_truth': {'threshold': [5.0, 'lower']},
                     'num_images_total_predicted': {'threshold': [40.0, 'lower']}},
                    'volume_display_name': 'AdditionalDeepLIIFVolume'},
                   'segmentation_metrics': {...}},
                  'openscale_subscription_id': None}
    monitor_id: monitor definition id, used to locate the corresponding thresholds config in metadata
    monitor_type: currently only supports custom_metric_provider; in the future, can extend to ootb monitors
    """
    d_thresholds = metadata[f'openscale_{monitor_type}'][monitor_id]['thresholds']
    d_metrics_name2id = get_monitor_metrics(monitor_id,wos_client)
    
    metrics = []
    for metric,values in d_thresholds.items():
        if metric not in d_metrics_name2id.keys():
            raise Exception(f'metric {metric} cannot be found in monitor {monitor_id}; view all available metric names using \"get_monitor_definition(wos_client,monitor_id=<monitor id>)["entity"]["metrics"]\"')
        metrics.append(MetricThresholdOverride(metric_id=d_metrics_name2id[metric],
                                               value=values["threshold"][0],
                                               type=f'{values["threshold"][1]}_limit'))
    return metrics


def get_monitor_definition(wos_client,monitor_name=None,monitor_id=None):
    """
    Get information of a monitor definition. Provide either monitor name or monitor id.
    For custom metric provider developers, you only have the monitor name before the monitor definition is
    created.
    For custom metric provider users, it's recommended to always use monitor id in the code.
    
    monitor_name: view all monitor definitions and their names using wos_client.monitor_definitions.show()
    monitor_id: view all monitor definitions and their ids using wos_client.monitor_definitions.show()
    """
    assert monitor_name is not None or monitor_id is not None, 'Provide either monitor name or monitor id.'
    
    monitor_definitions = wos_client.monitor_definitions.list().result.to_dict()['monitor_definitions']
    if monitor_id is not None:
        monitor_definition = [x for x in monitor_definitions if x['metadata']['id']==monitor_id]
    else:
        monitor_definition = [x for x in monitor_definitions if x['entity']['name']==monitor_name]
    
    if len(monitor_definition) == 0:
        print(f'No existing definition found for this monitor.')
        return None
    elif len(monitor_definition) > 1:
        print(f'Multiple definitions found for this monitor. This usually is wrong, fix your configurations.')
        return monitor_definition
    else:
        return monitor_definition[0]
    
def get_monitor_id_by_name(monitor_name,wos_client):
    monitor_definitions = wos_client.monitor_definitions.list().result.to_dict()['monitor_definitions']
    monitor_ids = [x['metadata']['id'] for x in monitor_definitions if x['entity']['name']==monitor_name]
    
    if len(monitor_ids) == 0:
        print(f'No existing definition found for this monitor {monitor_name}.')
        return None
    elif len(monitor_ids) > 1:
        print(f'Multiple definitions found for this monitor {monitor_name}. This usually is wrong, fix your configurations.')
        return monitor_ids
    else:
        return monitor_ids[0]

def get_monitor_instance(monitor_id,subscription_id,wos_client):
    """
    Get information of a monitor instance. 
    
    monitor_id: view all monitor definitions and their ids using wos_client.monitor_definitions.show()
    subscription_id: id of the subscription where you want to inspect the monitor instances
    """
    monitor_instances = wos_client.monitor_instances.list().result.to_dict()['monitor_instances']
    monitor_instance = [x for x in monitor_instances 
                        if x['entity']['monitor_definition_id']==monitor_id and 
                        x['entity']['target']['target_id']==subscription_id]
    
    if len(monitor_instance) == 0:
        print(f'No existing instance for monitor {monitor_id} found with subscription {subscription_id}')
        return None
    elif len(monitor_instance) > 1:
        print(f'Multiple instances for monitor {monitor_id} with subscription {subscription_id}. This usually is wrong, fix your configurations.')
        return monitor_instance
    else:
        return monitor_instance[0]


def monitor_instance_update(monitor_instance_id, integrated_system_id, metrics_wait_time, wos_client):
    """
    Updates a monitor instance. Currently only supports custom monitors.
    """
    payload = [
     {
       "op": "replace",
       "path": "/parameters",
       "value": {
           "custom_metrics_provider_id": integrated_system_id,
           "custom_metrics_wait_time":   metrics_wait_time 
       }
     }
    ]
    response = wos_client.monitor_instances.update(monitor_instance_id, payload, update_metadata_only = True)
    result = response.result
    return result


def monitor_instance_create(monitor_id,metadata_deployment,metadata_monitor,metrics_wait_time,wos_client,
                            data_mart_id=DATA_MART_ID):
    """
    Create a monitor instance. Currently only supports custom monitors.
    """
    integrated_system_id = metadata_monitor[monitor_id]['integrated_system_id']
    subscription_id = metadata_deployment['openscale_subscription_id']
    
    # Check if an custom monitor instance already exists
    existing_monitor_instance = get_monitor_instance(monitor_id,subscription_id,wos_client)
    
    # If it does not exist, then create one
    if existing_monitor_instance is None:
        target = Target(
                target_type=TargetTypes.SUBSCRIPTION,
                target_id=subscription_id
            )
        parameters = {
            "custom_metrics_provider_id": integrated_system_id,
            "custom_metrics_wait_time":   metrics_wait_time 
        }
        # create the custom monitor instance id here.
        monitor_instance_details = wos_client.monitor_instances.create(
                    data_mart_id=data_mart_id,
                    background_mode=False,
                    monitor_definition_id=monitor_id,
                    target=target,
                    parameters=parameters,
                    thresholds=get_thresholds_from_metadata(metadata_deployment,monitor_id,wos_client)
        ).result
    else:
        # otherwise, update the existing one with latest integrated system details.
        instance_id = existing_monitor_instance['metadata']['id']
        monitor_instance_details = monitor_instance_update(instance_id, integrated_system_id, metrics_wait_time, wos_client)
    return monitor_instance_details


def get_monitor_metrics(monitor_id,wos_client,key='name'):
    metrics = get_monitor_definition(wos_client,monitor_id=monitor_id)['entity']['metrics']
    if key == 'name':
        return {metric['name']:metric['id'] for metric in metrics}
    elif key == 'id':
        return {metric['id']:metric['name'] for metric in metrics}
    
def subscription_delete(wos_client,subscription_name=None,subscription_id=None):
    """
    Delete a subscription using its name or id (higher priority).
    """
    assert subscription_name is not None or subscription_id is not None, 'Provide either subscription name or id'
    subscriptions = wos_client.subscriptions.list().result.to_dict()['subscriptions']
    
    if subscription_id is None:
        subscription_ids = [subscription['metadata']['id'] for subscription in subscriptions if subscription['entity']['asset']['name']==subscription_name]
        print(f"{len(subscription_ids)} subscriptions found with subscription name {subscription_name}")
    else:
        subscription_ids = [subscription_id]
    
    if len(subscription_ids) > 0:
        for subscription_id in subscription_ids:
            wos_client.subscriptions.delete(subscription_id)
            print(f'Deleted subscription {subscription_id}')