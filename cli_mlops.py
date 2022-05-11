#!/usr/bin/env python

"""
Avoid using list() to convert a python object to a list because we re-defined list().
If needed, usse list_builtin() instead.
"""

import click
import os
import sys
import re
import yaml
import subprocess
from ibm_watson_openscale.supporting_classes.enums import TargetTypes

import wml_sdk_utils as wml_util
import wos_sdk_utils as wos_util
import ws_utils as ws_util
import wmla_utils as wmla_util

import warnings
warnings.filterwarnings('ignore')

import pandas as pd # to format tables
pd.options.display.width = 0

USER_ACCESS_TOKEN = os.getenv('USER_ACCESS_TOKEN')
SPACE_ID = os.getenv('SPACE_ID')
BASE_URL = os.getenv('BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL','https://cpd-cpd.apps.cpd.mskcc.org'))
WMLA_HOST = os.getenv('WMLA_HOST','https://wmla-console-cpd-wmla.apps.cpd.mskcc.org')
REST_SERVER = WMLA_HOST + '/dlim/v1/'
DLIM_PATH = os.getenv('DLIM_PATH')
DATA_MART_ID = '00000000-0000-0000-0000-000000000000'
SUBSCRIPTION_NAME = "{DEPLOYMENT_NAME} Monitor"

VERSION = '0.6'

list_builtin = list

@click.group()
def cli():
    pass

@cli.command()
def version():
    click.echo(f"Current version: {color(VERSION)}")


# -------- cli group: prepare --------
@cli.group()
def prepare():
    """
    Prepare for model deployment.
    """
    pass

@prepare.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--path-yml',type=str,default='deployment_metadata.yml',help='path to the yml config file of same structure as the example config')
@click.option('--path-model',type=str,default='model/',help='path to model(s), can point to a file or a folder')
@click.option('--path-dependency',type=str,default='dependency/',help='path to dependency file(s); if you use WMLA for deployment, it needs to be a folder because you will have at least a kernel file and a readme.md to supply to WMLA')
@click.option('--force','-f',is_flag=True,help='force overwrite if assets with the same name are found')
def stage(path_yml,path_model,path_dependency,force):
    """
    Stage model files, dependency files for deployment, and yml config file into the target WML space.
    """
    path_model = path_model[:-1] if path_model.endswith('/') else path_model
    path_dependency = path_dependency[:-1] if path_dependency.endswith('/') else path_dependency
    
    wml_client = wml_util.get_client(space_id=SPACE_ID)
    
    # load deployment config
    conf = yaml.safe_load(open(path_yml).read())
    click.echo(f"Validating yml config {color(path_yml)}...")
    flag_valid,d_res = wml_util.metadata_yml_validate(conf,with_key=False)
    if flag_valid:
        click.echo(color('Pass','pass'))
    else:
        click.echo(f"{color('Error','error')}: structure in yml config {color(path_yml,'error')} is not valid")
        for k,v in d_res.items():
            if not v['flag_valid']:
                click.echo('\n'.join(v['msg']))
        sys.exit(1)
    
    # get final model/dependency name
    model_asset_name = os.path.basename(path_model)
    if os.path.isdir(path_model):
        model_asset_name += '.zip'
        
    dependency_asset_name = os.path.basename(path_dependency)
    if os.path.isdir(path_dependency):
        dependency_asset_name += '.zip'
        
    # upload model/dependencies
    click.echo(f'Uploading model and dependency files to WML space {color(SPACE_ID)}...')
    data_assets = wml_util.list_files(wml_client)
    
    if model_asset_name in data_assets.values() or dependency_asset_name in data_assets.values():
        if force:
            wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=True)
        else:
            value = click.prompt('Asset with same name found in the WML space. Do you want to overwrite? Type "y" to overwrite,"n" to create a new asset with the same name, empty to abort',default='',type=str)
            if value == 'y':
                wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=True)
            elif value == 'n':
                wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=False)
            elif value == '':
                click.echo(color('Aborted','error'))
                sys.exit(1)
            else:
                click.echo(f'input value {value} is not accepted')
                sys.exit(1)
    else:
        wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=False)
    
    # get model asset id
    data_assets = wml_util.list_files(wml_client,keep_only_latest=True)
    model_asset_id = [k for k,v in data_assets.items() if v == model_asset_name][0]
    
    # update yml
    conf['deployment_space_id'] = SPACE_ID
    conf['model_asset'] = model_asset_name
    conf['wmla_deployment']['dependency_filename'] = dependency_asset_name
    
    wml_util.metadata_yml_add({model_asset_id:conf},wml_client,overwrite=True)
    
    conf_loaded = wml_util.metadata_yml_load(wml_client)[model_asset_id]
    click.echo(f"Model asset id: {color(model_asset_id,'pass')}")

# -------- cli group: config --------
@cli.group()
def config():
    """
    Interact with config files.
    """
    pass

@config.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--detail',type=bool,default=False,help='whether to show details in each yml config')
def list(detail):
    wml_client = wml_util.get_client(space_id=SPACE_ID)
    data_assets = wml_util.list_files(wml_client,include_details=True,ext='.yml')
    
    if len(data_assets) == 0:
        click.echo(f"No yml config file is found in WML space {color(SPACE_ID)}")
    else:
        df_assets = pd.DataFrame.from_dict(data_assets,'index')
        print(df_assets)
        if detail:
            fns = df_assets['name'].tolist()
            for fn in fns:
                click.echo('')
                click.echo(f"**** config yml {color(fn)} ****")
                df_conf = wml_util.metadata_yml_list(wml_client,fn_meta=fn)
                click.echo(f"{color(df_conf.shape[0])} entries found")
                print(df_conf)
                click.echo('')
            
@config.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',type=str,default='',help='deployment name, the entry/entries associated with which to delete')
@click.option('--model-asset-id',type=str,default='',help='model asset id, the exact entry to delete')
def delete(name,model_asset_id):
    """
    Delete entry or entries in the deployment metadata config yml. Specify either deployment name or
    model asset id (higher priority than deployment name). 
    """
    if name == '' and model_asset_id == '':
        click.echo(f"{color('Error','error')}: Specify either --name or --model-asset-id.")
        sys.exit(1)
    
    wml_client = wml_util.get_client(space_id=SPACE_ID)
    confs = wml_util.metadata_yml_load(wml_client)
    if model_asset_id != '':
        if model_asset_id not in confs.keys():
            click.echo(f"{color('Error','error')}: model asset id {color(model_asset_id,'error')} cannot be found in the config yml.")
            sys.exit(1)
        keys_to_delete = [model_asset_id]
    else:
        keys_to_delete = [model_asset_id for model_asset_id,conf in confs.items() if conf['wmla_deployment']['deployment_name']==name]
        
    click.echo(f"{color(len(keys_to_delete))} entries to delete.")
    if len(keys_to_delete) > 0:
        wml_util.metadata_yml_delete_key(keys_to_delete,wml_client)

@config.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--path-yml',type=str,required=True,help='path to a deployment metadata yml config with one COMPLETE entry')
@click.option('--force','-f',is_flag=True,help='force overwrite if entry with same key exists')
def add(path_yml,force):
    """
    Add one or more entries into the deployment metadata yml in wml space. 
    Use this when you don't stage the model and files via the "prepare stage" command.
    Unlike the yml config pass to the "prepare stage" command, here it MUST have model asset id as the key.
    """
    metadata = yaml.safe_load(open(path_yml).read())
    
    flag_valid,d_res = wml_util.metadata_yml_validate(metadata,with_key=True)
    if flag_valid:
        click.echo(f"{color('Pass','pass')}")
        
        wml_client = wml_util.get_client(space_id=SPACE_ID)
        wml_util.metadata_yml_add(metadata,wml_client,overwrite = force)
    else:
        click.echo(f"{color('Error','error')}: not all entries are valid")
        for k,v in d_res.items():
            if not v['flag_valid']:
                if with_key:
                    click.echo(f"**** model asset id {color(k,'error')} ****")
                click.echo('\n'.join(v['msg']))
        sys.exit(1)
           
# -------- cli group: deploy --------
@cli.group()
def deploy():
    """
    Deploy staged model and files.
    """
    pass

@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name, only lowercase letters/hyphens/numbers are allowed')
@click.option('--model-asset-id',required=True,type=str,help='model asset id is used to find which model and files to deploy, along with the associated config')
@click.option('--kernel-filename',type=str,default='kernel.py',help='name of WMLA EDI kernel file')
@click.option('--custom-arg',type=str,multiple=True,help='custom key-value pairs needed for this deployment, such as username and apikey to access storage volume; for example, --custom-arg username=<my username> --custom-arg apikey=<my apikey>')
@click.option('--dlim-path',type=str,default=None,help='path to dlim cli')
@click.option('--save-notebook',type=bool,default=False,help='whether to save the executed pipeline notebook')
def create(name, model_asset_id, kernel_filename, custom_arg,
           dlim_path, save_notebook):
    """
    Deploy a model asset using associated config.
    """
    # parse custom arguments
    variables = {}
    for pair in custom_arg:
        pair_parsed = pair.split('=')
        if len(pair_parsed) != 2:
            click.echo(f"{color('Error','error')}: Key-value pair {color(pair,'error')} in custom-arg does not have exactly 1 equal sign")
            sys.exit(1)
        k = pair_parsed[0]
        v = pair_parsed[1]
        if len(k) == 0 or v == 0:
            click.echo(f"{color('Error','error')}: Key-value pair {color(pair,'error')} in custom-arg has an invalid key or value")
            sys.exit(1)
    
    if len(custom_arg) > 0:
        os.environ['CUSTOM_ARG'] = ' '.join(custom_arg)

    # Check validity of name
    valid_pattern = re.compile('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')
    name_check = valid_pattern.match(name)
    if name_check is None:
        raise ValueError(f"{color('Error','error')}: Deployment name {color(pair,'error')} is invalid. Only numbers, hyphens and lowercase letters are allowed.")
    
    # Check for dlim CLI dependency
    dlim_paths = [os.environ['HOME']+'/bin', '/userfs']
    if dlim_path is not None:
        if os.path.isfile(dlim_path):
            dlim_path = os.path.dirname(dlim_path)
        dlim_paths = [dlim_path] + dlim_paths
        
    for path in dlim_paths:
        if os.path.exists(path+'/dlim'):
            if not os.access(path+'/dlim', os.X_OK):
                raise Exception("dlim program not executable...check permissions")
            os.environ['DLIM_PATH'] = path
            break
    else:
        raise FileNotFoundError("dlim program not found...check its location and include as value for dlim_path argument")
            

    wml_client = wml_util.get_client(space_id=SPACE_ID)
    
    confs = wml_util.metadata_yml_load(wml_client)
    if model_asset_id not in confs.keys():
        click.echo(f"{color('Error','error')}: model asset id {color(model_asset_id,'error')} cannot be found in config file")
        sys.exit(1)

    model_asset_ids_matched = [k for k,conf in confs.items() if conf['wmla_deployment']['deployment_name']==name]
    if len(model_asset_ids_matched) > 0:
        click.echo(f"{color('Error','error')}: deployment name {color(name,'error')} is already found in config file, associated with model asset id {color(model_asset_ids_matched[0],'error')}. Stop and delete the existing deployment before creating one with the same name.")
        sys.exit(1)
    
    conf = confs[model_asset_id]
    if conf['wmla_deployment']['deployment_name'] is not None:
        click.echo(f"{color('Error','error')}: model asset id {color(model_asset_id,'error')} is already deployed with deployment name {color(conf['wmla_deployment']['deployment_name'],'error')}. Stop and delete the existing deployment before creating one with the same model asset id.")
        sys.exit(1)
    
    # update yml
    conf['wmla_deployment']['deployment_name'] = name
    conf['wmla_deployment']['deployment_url'] = f'https://wmla-inference-cpd-wmla.apps.cpd.mskcc.org/dlim/v1/inference/{name}'
    
    wml_util.metadata_yml_add({model_asset_id:conf},wml_client,overwrite=True)
    
    click.echo(f'Deploying model asset {color(model_asset_id)} as deployment {color(name)} in WMLA...')
    os.environ['MODEL_ASSET_ID'] = model_asset_id
    os.environ['WML_SPACE_ID'] = SPACE_ID
    os.environ['KERNEL_FILENAME'] = kernel_filename
    os.environ['REST_SERVER'] = WMLA_HOST + '/dlim/v1/'
    
    path_nb = 'A2_WMLA_Model_Deploy.ipynb'
    click.echo(f'Starting notebook A2_WMLA_Model_Deploy.ipynb to deploy model with deployment name {name}...')
    ws_util.run_pipeline_notebook(path_nb,save_notebook=save_notebook)
    
    click.echo(f"Deploymnet url: {color(conf['wmla_deployment']['deployment_url'],'pass')}")


@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name, only lowercase letters/hyphens/numbers are allowed')
def stop(name):
    subprocess.run(f"dlim model stop {name} --rest-server {REST_SERVER} --jwt-token {USER_ACCESS_TOKEN} -f",shell=True)

@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name, only lowercase letters/hyphens/numbers are allowed')
@click.option('--remove-monitor',is_flag=True,help='a flag to remove the associated monitors in openscale')
@click.option('--remove-config',is_flag=True,help='a flag to remove the associated entry in the config yml')
def delete(name,remove_monitor,remove_config):
    res = subprocess.run(f"dlim model undeploy {name} --rest-server {REST_SERVER} --jwt-token {USER_ACCESS_TOKEN} -f",shell=True)
    if res.returncode == 0:
        click.echo(f"Modifying config yml to refect this change..")
        wml_client = wml_util.get_client(space_id=SPACE_ID)
        
        if remove_monitor:
            click.echo('')
            click.echo(f"Removing the associated subscription in openscale..")
            wos_client = wos_util.get_client()
            wos_util.subscription_delete(wos_client,subscription_name=SUBSCRIPTION_NAME.format(DEPLOYMENT_NAME=name))
        
        if remove_config:
            click.echo('')
            click.echo(f"Removing the associated entry in config yml..")
            model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
            wml_util.metadata_yml_delete_key(model_asset_id,wml_client)
        else:
            click.echo('')
            click.echo(f"Removing deployment name from the associated entry in config yml...")
            model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
            if conf is None:
                click.echo(f"No config linked to deployment name {name}. The config might have been deleted already, or the deployment was not created using this cli flow.")
            else:
                conf['wmla_deployment']['deployment_name'] = None
                if remove_monitor:
                    conf['openscale_subscription_id'] = None
                wml_util.metadata_yml_add({model_asset_id:conf},wml_client,overwrite=True)
            

@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
def list():
    subprocess.run(f"dlim model list --rest-server {REST_SERVER} --jwt-token {USER_ACCESS_TOKEN}",shell=True)

# -------- cli group: monitor --------
@cli.group()
def monitor():
    """
    Configure and interact with OpenScale monitors for the deployments.
    """
    pass

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name')
@click.option('--service-provider-name',type=str,default="OpenScale Headless Service Provider",help='deployment service provider configured in OpenScale')
@click.option('--save-notebook',type=bool,default=False,help='whether to save the executed pipeline notebook')
def create(name,service_provider_name,save_notebook):
    """
    Configure monitors for a deployment using the associated config.
    """
    wml_client = wml_util.get_client(space_id=SPACE_ID)
    
    model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
    if conf is None:
        click.echo(f"{color('Error','error')}: no config found for deployment name {color(name,'error')}")
        sys.exit(1)
    
    if conf['openscale_subscription_id'] is not None:
        click.echo(f"{color('Error','error')}: deployment {color(name,'error')} is already configured in OpenScale with subscription id {color(conf['openscale_subscription_id'],'error')}. If you want to re-configure the monitor, at the moment you need to delete the existing subscription.")
        value = click.prompt(f'Have you already deleted the existing subscription and want to proceed? Type "y" to proceed or leave it empty to abort',default='')
        if value == '':
            click.echo(color('Aborted','error'))
        
    print('Model asset id:',model_asset_id)
    os.environ['SERVICE_PROVIDER_NAME'] = service_provider_name
    os.environ['SUBSCRIPTION_NAME'] = f'{name} Monitor'
    os.environ['MODEL_ASSET_ID'] = model_asset_id
    os.environ['WML_SPACE_ID'] = SPACE_ID
    os.environ['WOS_GUID'] = DATA_MART_ID
    
    path_nb = 'A3_OpenScale_Configuration.ipynb'
    click.echo(f'Starting notebook A3_OpenScale_Configuration.ipynb to configure OpenScale monitors for deployment {color(name)} (model asset id {color(model_asset_id)})...')
    ws_util.run_pipeline_notebook(path_nb,save_notebook=save_notebook)

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name')
def delete(name):
    """
    Delete the monitors associated with a deployment. It essentially deletes the openscale subscription.
    """
    wos_client = wos_util.get_client()
    wos_util.subscription_delete(wos_client,subscription_name=SUBSCRIPTION_NAME.format(DEPLOYMENT_NAME=name))

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
def list():
    """
    List monitors configured for deployments.
    """
    wos_client = wos_util.get_client()
    subscriptions = wos_client.subscriptions.list().result.to_dict()['subscriptions']
    click.echo(f"{color(len(subscriptions))} subscriptions found")
    click.echo('')
    if len(subscriptions) > 0:
        df_subscriptions = pd.json_normalize(subscriptions)[['entity.asset.name',
                                                              'metadata.created_at','metadata.created_by','metadata.id']]
        df_subscriptions.columns = ['subscription_name','created_at','created_by','subscription_id']
        df_subscriptions['created_at'] = df_subscriptions['created_at'].apply(lambda x: x.split('.')[0]) 
        df_subscriptions = df_subscriptions.sort_values('created_at',ascending=False).set_index('subscription_id')
        
        monitor_instances = wos_client.monitor_instances.list().result.to_dict()['monitor_instances']
        df_monitor_instances = pd.json_normalize(monitor_instances)[['entity.target.target_id','entity.monitor_definition_id']]
        df_monitor_instances.columns = ['subscription_id','monitor']
        df_monitor_instances = df_monitor_instances.groupby('subscription_id').agg(list_builtin)
        df_monitor_instances['monitor'] = df_monitor_instances['monitor'].apply(lambda x: ', '.join(x))
        
        print(df_subscriptions.join(df_monitor_instances,how='left'))

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name')
def status(name):
    """
    Check monitor status. Basically it queries the evaluation results of the most recent run.
    """
    wos_client = wos_util.get_client()
    wml_client = wml_util.get_client(space_id=SPACE_ID)
    
    model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
    if conf is None:
        click.echo(f"{color('Error','error')}: no config found for deployment name {color(name,'error')}")
        sys.exit(1)
    
    if conf['openscale_subscription_id'] is None:
        click.echo(f"{color('Error','error')}: Config for deployment {color(name,'error')} does not have a subsription id. Have you configured the monitors?")
        sys.exit(1)
    
    click.echo(f'Fetching latest monitor status for deployment {color(name)} (model asset id {color(model_asset_id)})...')
    subscription_id = conf['openscale_subscription_id']
    for monitor_id in conf['openscale_custom_metric_provider'].keys():
        l_measurements = wos_client.monitor_instances.measurements.query(target_id=subscription_id,
                                                                        target_type=TargetTypes.SUBSCRIPTION,
                                                                        monitor_definition_id=monitor_id,
                                                                        recent_count=1).result.to_dict()['measurements']
        if len(l_measurements) == 0:
            click.echo(f'Monitor {color(monitor_id)} does not have any evaluation run yet.')
        else:
            measurements = l_measurements[0]
#             thresholds = conf['openscale_custom_metric_provider'][monitor_id]['thresholds']
            click.echo('')
            click.echo(f"**** Monitor {color(monitor_id)}:")
            click.echo(f"measurement id: {color(measurements['metadata']['id'])}")
            click.echo(f"evaluation run id: {color(measurements['entity']['run_id'])}")
            click.echo(f"evaluation run started at: {color(measurements['entity']['timestamp'])}")
            
            count_issue = measurements['entity']['issue_count']
            click.echo(f"{color(count_issue,'pass') if count_issue == 0 else color(count_issue,'error')} metric(s) violating the threshold.")
            if count_issue > 0:
                metrics = measurements['entity']['values'][0]['metrics']
                
                d_metrics_id2name = wos_util.get_monitor_metrics(monitor_id,wos_client,key='id')
                metrics = sorted(metrics,key=lambda d:d_metrics_id2name[d['id']])
                
                for metric in metrics:
                    try:
                        if metric['value'] < metric['lower_limit']:
                            click.echo(f"{color(d_metrics_id2name[metric['id']],'warning')}: value {color(round(metric['value'],4),'warning')} lower than threshold {color(metric['lower_limit'],'warning')}")
                    except:
                        pass
                    
                    try:
                        if metric['value'] > metric['upper_limit']:
                            click.echo(f"{color(d_metrics_id2name[metric['id']],'warning')}: value {color(round(metric['value'],4),'warning')} higher than threshold {color(metric['upper_limit'],'warning')}")
                    except:
                        pass

# -------- util --------
    
def get_metadata_by_deployment_name(name,wml_client):
    model_asset_id = None
    conf = None
    
    confs = wml_util.metadata_yml_load(wml_client)
    for k,v in confs.items():
        try:
            if v['wmla_deployment']['deployment_name']==name:
                model_asset_id = k
                conf = v
        except:
            pass
    
    return model_asset_id, conf

def color(x,condition='normal'):
    if condition=='normal':
        return click.style(str(x),fg='blue')
    elif condition=='error':
        return click.style(str(x),fg='red')
    elif condition=='warning':
        return click.style(str(x),fg='yellow')
    elif condition=='pass':
        return click.style(str(x),fg='green')
    else:
        raise Exception(f'condition {condition} not supported')

if __name__ == '__main__':
    if USER_ACCESS_TOKEN is None:
        click.echo("\nConfigure user access token by exporting it as an environment variable USER_ACCESS_TOKEN. In terminal, you can do \"export USER_ACCESS_TOKEN=<token>\"; in python, you can do \"os.environ['USER_ACCESS_TOKEN']=<token>\". To get a token, refer to https://cloud.ibm.com/apidocs/cloud-pak-data#getauthorizationtoken or use the \"get_access_token()\" method in cpd_utils.py.")
        sys.exit(1)
    
    if SPACE_ID is None:
        click.echo("\nConfigure wml space id (the target space you want to stage model files and dependencies) by exporting it as an environment variable SPACE_ID. In terminal, you can do \"export SPACE_ID=<id>\"; in python, you can do \"os.environ['SPACE_ID']=<id>\".")
        sys.exit(1)
    
    if DLIM_PATH is None:
        dlim_paths = os.environ['PATH'].split(':')
        for path in dlim_paths:
            if os.path.exists(path+'/dlim'):
                if os.access(path+'/dlim', os.X_OK):
                    DLIM_PATH = path
                    os.environ['DLIM_PATH'] = path
                    break
        if DLIM_PATH is None:
            click.echo('\nCannot find executable dlim. Make sure the parent folder of dlim is included in $PATH and the file is executable. You can add the parent folder of dlim to $PATH by running "export PATH=$PATH:<my folder>", or move the dlim file to a folder already added to $PATH. To make dlim executable, consider command "chmod +x dlim".')
            sys.exit(1)

    click.echo(f"\nDetected env var USER_ACCESS_TOKEN and SPACE_ID.\nYou are working with WML space {color(SPACE_ID)}.\nLocation of executable cli {color('dlim')}: {color(DLIM_PATH)}")
    click.echo('')
    cli()
