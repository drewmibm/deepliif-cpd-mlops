import os
import subprocess
import pandas as pd
import yaml
import shutil

from ibm_watson_machine_learning import APIClient

FOLDER_TMP = 'tmp'
DEBUG = os.getenv('DEBUG',False)

METADATA_DEPLOYMENT_STRUCTURE = {'MODEL_ASSET_ID':{
                                     'model_asset': '',
                                     'model_name': '',
                                     'deployment_id': '',
                                     'deployment_space_id':'',
                                     'openscale_subscription_id': '',
                                     'openscale_custom_metric_provider': {},
                                     'wmla_deployment':{'deployment_name':'',
                                                        'deployment_url':'',
                                                        'dependency_filename':'',
                                                        'resource_configs':{}}}}

METADATA_MONITOR_STRUCTURE = {'MONITOR_ID':{'integrated_system_id':'',
                                            'wml_deployment_id':''}}

METADATA_DEFAULT={'deployment':{'fn':'deployment_metadata.yml',
                                'structure':METADATA_DEPLOYMENT_STRUCTURE},
                  'monitor':{'fn':'monitor_metadata.yml',
                             'structure':METADATA_MONITOR_STRUCTURE}}

def get_client(credentials=None,space_id=None):
    """
    credentials: a dictionary with either
                 - key "url" and "token"
                 - key "url", "username", and "apikey"
    space_id: wml space id
    """
    if credentials is None:
        if os.getenv('USERNAME') is not None and os.getenv('APIKEY') is not None:
            credentials = {'url':os.getenv('BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL','https://cpd-cpd.apps.cpd.mskcc.org')),
                           'username':os.environ['USERNAME'],
                           'apikey':os.environ['APIKEY'],
                           'instance_id':'openshift',
                           'version':'4.0'}
        else:
            credentials = {'url':os.getenv('BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL','https://cpd-cpd.apps.cpd.mskcc.org')),
                           'token':os.environ['USER_ACCESS_TOKEN'],
                           'instance_id':'openshift',
                           'version':'4.0'}
    else:
        credentials['instance_id'] = 'openshift'
        credentials['version'] = '4.0'
    
    wml_client = APIClient(credentials)
    
    if space_id is not None:
        wml_client.set.default_space(space_id)
    
    return wml_client


# -------- data assets in space --------
def list_files(wml_client,keep_only_latest=False,include_details=False,ext=None):
    """
    output:
    a dictionary with data asset name as value and asset id as key
    because there could be multiple assets with the same name, so
    asset name can't be key
    
    keep_only_latest: when there are multiple entries with the same asset name, whether
                      return only the one created most recently (True) or all (False)
    include_details: whether to return more details than asset id and name
    ext: a string of extensions only with which the asset will be included; default
         to None which does not filter
    """
    data_assets = wml_client.data_assets.get_details()['resources']
    if len(data_assets) > 0:
        df_assets = pd.json_normalize(data_assets)
        df_assets['metadata.usage.last_update_time'] = df_assets['metadata.usage.last_update_time'].apply(lambda x: pd.Timestamp(x,unit='ms'))

        colnames_minimum = ['metadata.name', 'metadata.asset_id', 'metadata.usage.last_update_time']
        colnames_detailed = ['metadata.name', 'metadata.asset_id', 'metadata.usage.last_update_time', 
                         'metadata.created_at', 'metadata.last_updated_at', 'metadata.usage.last_updater_id']

        if include_details:
            df_assets = df_assets[colnames_detailed]
        else:
            df_assets = df_assets[colnames_minimum]

        if keep_only_latest:
            df_assets = df_assets.sort_values('metadata.usage.last_update_time',ascending=False).drop_duplicates('metadata.name')

        df_assets = df_assets.drop(['metadata.usage.last_update_time'],axis=1)
        df_assets.columns = [c.replace('metadata.usage.','').replace('metadata.','') for c in df_assets.columns]

        if ext is not None:
            df_assets = df_assets[df_assets['name'].str.endswith(ext)]

        if include_details:
            return df_assets.set_index('asset_id').to_dict(orient='index')
        else:
            return df_assets.set_index('asset_id').to_dict()['name']
    else:
        return {}


def upload(path,wml_client,fn_target=None,overwrite=False):
    """
    path: source path of the file to be uploaded
                 can be a file path or a directory; if is a directory, the directory
                 will be compressed as a zip file before uploading
    fn_target: the target asset file name
    overwrite: if an asset with the same file name exists, whether to overwrite it
               if multiple assets are found, overwrite=True will essentially delete
               all of them and create a new one
    
    A better way to handle multiple assets with the same name is to create revisions,
    instead of delete-then-create.
    """
    flag_exists_tmp = os.path.exists(FOLDER_TMP)
    
    if os.path.isdir(path):
        os.makedirs(FOLDER_TMP,exist_ok=True)
        dir_archive = os.path.abspath(FOLDER_TMP)
        
        dir_parent = os.path.dirname(os.path.abspath(path))
        dir_base = os.path.basename(path)
        fn = f'{dir_base}.zip' if fn_target is None else fn_target
        path_archive = f'{dir_archive}/{fn}'
        
    else:
        fn = os.path.basename(path) if fn_target is None else fn_target
    
    asset_ids = [k for k,v in list_files(wml_client).items() if v == fn]
    
    if os.path.isdir(path):
        subprocess.run(f'cd {dir_parent}; zip -r {path_archive} {dir_base}',shell=True)
        wml_client.data_assets.create(fn,path_archive)
        delete_tmp_files(path_archive,FOLDER_TMP,flag_exists_tmp)
        print(f'Finished publishing {path_archive} as {fn}')
    else:
        wml_client.data_assets.create(fn,path)
        print(f'Finished publishing {path} as {fn}')
        
    if overwrite:
        for asset_id in asset_ids:
            wml_client.data_assets.delete(asset_id)
        print('Finished deleting existing old assets with the same name')


def upload_batch(l_path,wml_client,overwrite=False):
    for path in l_path:
        upload(path,wml_client,overwrite=overwrite)


def download(fn,wml_client,path_target=None,return_status=False):
    """
    fn: a string of data asset name
    wml_client: a wml client created using wml sdk, with default space id configured
    path_target: the path in your "local"/"current" environment as the destination
                 if a folder is provided instead of a filename, the file(s) will be downloaded to this folder
                 and this has to be an existing folder
    return_status: if True, return a flag indicating whether the action succeeded (True)
                   or not (False)
    """
    if path_target is None:
        path_target = fn
    else:
        if os.path.isdir(path_target):
            path_target = os.path.join(path_target,fn)
            
    asset_ids = [k for k,v in list_files(wml_client).items() if v == fn]
    if len(asset_ids) > 0:
        if len(asset_ids) > 1:
            print(f'Found {len(asset_ids)} data assets with name {fn}, only the first one will be downloaded.')
        asset_id = asset_ids[0]
        wml_client.data_assets.download(asset_id,path_target)
        if return_status:
            return True
    else:
        print(f'Cannot find data asset name {fn} in WML deployment sapce {wml_client.default_space_id}')
        if return_status:
            return False
            
def download_batch(l_fn,wml_client,path_target=None):
    """
    path_target: for downloading a batch of assets, a direcotry is expected if you intend to specify the location
                 otherwise the downloaded files will be overwritten by each other
    """
    for fn in l_fn:
        download(fn,wml_client,path_target)


# -------- deployable function --------
def function_prepare(path,variables={},scripts=[],path_target=None):
    """
    This function inserts essential information to a WML deployable function script, and writes the new version with
    "edited" appended to the filename. 
    
    * Note that you should always share the original script with your colleagues and versioning service (e.g., git), 
    NOT the edited one from this function, in case you bring in your own credentials to be used by the WML deployable 
    function.
    
    path: path to the WML deployable function script
    variables: a dictionary with key as variable name and value as variable value, to be added to the script
        example: 
            variables = {"space_id":"123456",
                         "os.environ['RUNTIME_ENV_APSX_URL']":os.environ['RUNTIME_ENV_APSX_URL']}
    scripts: a list of scripts to be used by the main deployable function script
             if this is used, the deployable function script needs to have a code snippet to consume those scripts
        example:
             # to prepare_function()
             scripts = ["myscript.py"]
             
             # in the main deployable function script, add the following at the top:
             if len(d_scripts) > 0:
                for k,v in d_scripts.items():
                    with open(k,'w') as f:
                        f.write(v)
             
             # in the main deployable function script, afterwards you can call the module as usual
             from myscript import *
    path_target: the output path of the new version; if is None, it adds suffix "_edited" ("abc.py" -> "abc_edited.py")
    """
    
    lines = ['import os']
    for k,v in variables.items():
        lines.append(f'{k} = {repr(v)}')

    lines.append('d_scripts = {}')
    for fn in scripts:
        lines.append(f"d_scripts['{fn}'] = {repr(open(fn).read())}")
        
    if len(scripts) > 0:
        lines.append("""
if len(d_scripts) > 0:
    for k,v in d_scripts.items():
        with open(k,'w') as f:
            f.write(v)
""")
    
    content = open(path).read()
    lines.append(content)
    
    path_target = path.replace('.py','_edited.py') if path_target is None else path_target
    with open(path_target,'w') as f:
        f.write('\n'.join(lines))
        
    print(f'Finished writing essential information into {path_target}')


def function_delete(wml_client,function_name):
    """
    Delete existing function assets with the same name as `function_name`.
    In order to do so, all the associated deployments to the function asset to delete 
    will be removed first, then the function asset can be removed.
    """
    assets = wml_client.repository.get_details()['functions']['resources']
    asset_ids = [x['metadata']['id'] for x in assets if x['metadata']['name']==function_name]
    if len(asset_ids) > 0:
        deployments = wml_client.deployments.get_details()["resources"]
        for deployment in deployments:
            if deployment["entity"]["asset"]["id"] in asset_ids:
                deployment_id = deployment["metadata"]["id"]
                wml_client.deployments.delete(deployment_id)
                print(f'Deleted deployment {deployment["metadata"]["name"]} ({deployment["metadata"]["id"]}) associated with asset {function_name} ({deployment["entity"]["asset"]["id"]}).')
        
        for asset_id in asset_ids:
            wml_client.repository.delete(asset_id)
            print(f'Deleted function asset {function_name} ({asset_id}).')
    else:
        print(f'No function asset found with name {function_name}.')
                

def function_store(path_script,wml_client,function_name=None,overwrite=True):
    """
    Store a script as a deployable function in WML.
    Structure of a script for WML deployable function: https://www.ibm.com/docs/en/cloud-paks/cp-data/4.0?topic=functions-writing-deployable-python
    """
    function_name = 'My Function' if function_name is None else function_name
    
    flag_exists_tmp = os.path.exists(FOLDER_TMP)
    os.makedirs(FOLDER_TMP,exist_ok=True)
    
    fn = os.path.basename(path_script)
    path_archive = f'{FOLDER_TMP}/{fn}.gz'
    subprocess.run(f'gzip -kfc {path_script} > {path_archive}',shell=True)
    
    if overwrite:
        function_delete(wml_client,function_name)
    
    software_spec_id =  wml_client.software_specifications.get_id_by_name('default_py3.8')
    function_meta_props = {
         wml_client.repository.FunctionMetaNames.NAME: function_name,
         wml_client.repository.FunctionMetaNames.SOFTWARE_SPEC_ID: software_spec_id
         }
    
    function_artifact = wml_client.repository.store_function(meta_props=function_meta_props, 
                                                             function=path_archive)
    function_uid = wml_client.repository.get_function_id(function_artifact)
    print("Function UID = " + function_uid)
    
    delete_tmp_files(path_archive,FOLDER_TMP,flag_exists_tmp)
    
    return function_uid


def function_deploy(function_asset_id,wml_client,function_deployment_name=None):
    function_deployment_name = 'My Function Deployment' if function_deployment_name is None else function_deployment_name
    
    hardware_spec_id = wml_client.hardware_specifications.get_id_by_name('L')
    deploy_meta = {
     wml_client.deployments.ConfigurationMetaNames.NAME: function_deployment_name,
     wml_client.deployments.ConfigurationMetaNames.ONLINE: {},
     wml_client.deployments.ConfigurationMetaNames.HARDWARE_SPEC: { "id": hardware_spec_id}
    }
    
    deployment_details = wml_client.deployments.create(function_asset_id, meta_props=deploy_meta)
    
    # Get the scoring URL
    created_at = deployment_details['metadata']['created_at']
    find_string_pos = created_at.find("T")
    if find_string_pos != -1:
        current_date = created_at[0:find_string_pos]
    scoring_url = wml_client.deployments.get_scoring_href(deployment_details)
    scoring_url = scoring_url + "?version="+current_date

    deployment_id = deployment_details['metadata']['id']
    
    return deployment_id,scoring_url
    
# -------- metadata yaml file --------

def metadata_yml_initialize(wml_client,metadata_type='deployment',fn_meta=None):
    """
    metadata_type: deployment or monitor
                   deployment: used to store metadata information for a model asset (key)
                               values include deployment id, openscale subscription id, openscale monitor config
                   monitor: used to store metadata information for a custom metric provider/monitor
                            values include
    """
    assert metadata_type in METADATA_DEFAULT.keys(), f'metadata type {metadata_type} is not one of {METADATA_DEFAULT.keys()}'
    fn_meta = METADATA_DEFAULT[metadata_type]['fn'] if fn_meta is None else fn_meta
    path = f'{FOLDER_TMP}/{fn_meta}'
    
    flag_exists_tmp = os.path.exists(FOLDER_TMP)
    os.makedirs(FOLDER_TMP,exist_ok=True)
    
    if metadata_type=='deployment':
        metadata = METADATA_DEPLOYMENT_STRUCTURE
    else:
        metadata = METADATA_MONITOR_STRUCTURE
    
    with open(path,'w') as f:
        f.write(yaml.dump(metadata))
        
    upload(path,wml_client,fn_meta,overwrite=True)
    delete_tmp_files(path,FOLDER_TMP,flag_exists_tmp)


def metadata_yml_add(metadata,wml_client,metadata_type='deployment',fn_meta=None,overwrite=False):
    """
    Add one ore more new entries to the metadata yml.
    
    overwrite: whether to overwrite the existing entry with the same key; if True, it updates the
               existing entry with new values provided in metadata 
    """
    
    assert metadata_type in METADATA_DEFAULT.keys(), f'metadata type {metadata_type} is not one of {METADATA_DEFAULT.keys()}'
    fn_meta = METADATA_DEFAULT[metadata_type]['fn'] if fn_meta is None else fn_meta
    path = f'{FOLDER_TMP}/{fn_meta}'
    
    flag_exists_tmp = os.path.exists(FOLDER_TMP)
    os.makedirs(FOLDER_TMP,exist_ok=True)
    
    flag_downloaded = download(fn_meta,wml_client,FOLDER_TMP,return_status=True)
    if not flag_downloaded:
        print('Initializing deployment metadata yaml file..')
        metadata_yml_initialize(wml_client,metadata_type=metadata_type,fn_meta=fn_meta)
        download(fn_meta,wml_client,FOLDER_TMP)
        
    metadata_existing = yaml.safe_load(open(path).read())
    
    keys_existing = list(metadata.keys())
    for k in keys_existing:
        if k in metadata_existing.keys():
            if overwrite:
                print(f'Key {k} already exists in yaml file {fn_meta}, updating the values...')
                metadata_existing[k] = metadata.pop(k)
            else:
                raise Exception(f'Key {k} already exists in yaml file {fn_meta}. Use overwrite=True if you want to update the values of an existing entry; otherwise, please manually resolve it.')
    
    print('Writing new metadata in..')
    with open(path,'w') as f:
        f.write(yaml.dump({**metadata_existing, **metadata}))
        
    upload(path,wml_client,fn_meta,overwrite=True)
    delete_tmp_files(path,FOLDER_TMP,flag_exists_tmp)


def metadata_yml_update(metadata,wml_client,metadata_type='deployment',fn_meta=None):
    assert metadata_type in METADATA_DEFAULT.keys(), f'metadata type {metadata_type} is not one of {METADATA_DEFAULT.keys()}'
    fn_meta = METADATA_DEFAULT[metadata_type]['fn'] if fn_meta is None else fn_meta
    path = f'{FOLDER_TMP}/{fn_meta}'
    
    flag_exists_tmp = os.path.exists(FOLDER_TMP)
    os.makedirs(FOLDER_TMP,exist_ok=True)
    
    # download existing yml
    flag_downloaded = download(fn_meta,wml_client,FOLDER_TMP,return_status=True)
    if not flag_downloaded:
        raise Exception(f'Cannot find existing deployment metadata yaml file {fn_meta}. Create one before calling the update method.')
    
    # load yml
    conf = yaml.safe_load(open(path).read())
    model_asset_id = list(metadata.keys())[0]
    
    if model_asset_id not in conf.keys():
        raise Exception(f'Cannot find model asset id {model_asset_id} in metadata yml file {fn_meta}. Create an entry before calling the update method.')
    
    # update yml
    for k,v in metadata[model_asset_id].items():
        conf[model_asset_id][k] = v
        
    with open(path,'w') as f:
        f.write(yaml.dump(conf))
        
    upload(path,wml_client,fn_meta,overwrite=True)
    delete_tmp_files(path,FOLDER_TMP,flag_exists_tmp)
    

def metadata_yml_delete_key(key,wml_client,metadata_type='deployment',fn_meta=None):
    """
    Delete entries in the existing metadata yaml.
    
    key: can be a string of a key, or a list of multiple keys
    """
    assert metadata_type in METADATA_DEFAULT.keys(), f'metadata type {metadata_type} is not one of {METADATA_DEFAULT.keys()}'
    fn_meta = METADATA_DEFAULT[metadata_type]['fn'] if fn_meta is None else fn_meta
    path = f'{FOLDER_TMP}/{fn_meta}'
    
    flag_exists_tmp = os.path.exists(FOLDER_TMP)
    os.makedirs(FOLDER_TMP,exist_ok=True)
    
    # download existing yml
    flag_downloaded = download(fn_meta,wml_client,FOLDER_TMP,return_status=True)
    if not flag_downloaded:
        raise Exception(f'Cannot find existing deployment metadata yaml file {fn_meta}. Create one before calling the update method.')
    
    # load yml
    conf = yaml.safe_load(open(path).read())
    
    if isinstance(key,str):
        keys = [key]
    else:
        keys = key
        
    for k in keys:
        conf.pop(k, None)
        
    # write yml
    with open(path,'w') as f:
        f.write(yaml.dump(conf))
        
    upload(path,wml_client,fn_meta,overwrite=True)
    delete_tmp_files(path,FOLDER_TMP,flag_exists_tmp)
    

def metadata_yml_load(wml_client,metadata_type='deployment',fn_meta=None):
    assert metadata_type in METADATA_DEFAULT.keys(), f'metadata type {metadata_type} is not one of {METADATA_DEFAULT.keys()}'
    fn_meta = METADATA_DEFAULT[metadata_type]['fn'] if fn_meta is None else fn_meta

    path = f'{FOLDER_TMP}/{fn_meta}'
    
    flag_exists_tmp = os.path.exists(FOLDER_TMP)
    os.makedirs(FOLDER_TMP,exist_ok=True)
    
    flag_downloaded = download(fn_meta,wml_client,FOLDER_TMP,return_status=True)
    if not flag_downloaded:
        raise Exception(f'Cannot find existing deployment metadata yaml file {fn_meta}. Create one before calling the load method.')
    
    metadata = yaml.safe_load(open(path).read())
    delete_tmp_files(path,FOLDER_TMP,flag_exists_tmp)
    
    return metadata

def metadata_yml_list(wml_client,metadata_type='deployment',fn_meta=None):
    """
    List entries in a yml config. 
    Return only selected fields that are most important:
      - model asset id
      - model asset name
      - deployment name
      - openscale subscription id
    """
    assert metadata_type in METADATA_DEFAULT.keys(), f'metadata type {metadata_type} is not one of {METADATA_DEFAULT.keys()}'
    fn_meta = METADATA_DEFAULT[metadata_type]['fn'] if fn_meta is None else fn_meta
    
    confs = metadata_yml_load(wml_client,fn_meta=fn_meta)
    confs_top_level = get_top_level(confs,keys_ignore=['deployment_space_id','deployment_id','model_name'])
    df_conf = pd.DataFrame.from_dict(confs_top_level,'index')
    return df_conf

def metadata_yml_validate(metadata,with_key=True,metadata_type='deployment'):
    """
    Validate if a metadata dictionary has valid structure.
    
    metadata: a metadata dictionary with one or multiple entries; if multiple entries are
              included, each entry has to have a key (model asset id) to differentiate
    with_key: when metadata has only 1 entry, whether the key is included or not
    """
    assert metadata_type in METADATA_DEFAULT.keys(), f'metadata type {metadata_type} is not one of {METADATA_DEFAULT.keys()}'
    d_structure = METADATA_DEFAULT[metadata_type]['structure']
    
    def validate(d_yml,d_ref,path=''):
        if type(d_yml) != dict: 
            msg.append(f'{path} is not a dictionary')
        for k in d_ref:
            if k not in d_yml:
                msg.append(f'{path}.{k} cannot be found')
            elif type(d_ref[k]) == dict:
                validate(d_yml[k],d_ref[k],path=f'{path}.{k}')
    
    if not with_key:
        metadata = {None:metadata}
    
    d_res = {}
    count_valid = 0
    for key,conf in metadata.items():
        d_res[key] = {}
        msg = []

        validate(conf,d_structure['MODEL_ASSET_ID'])
        
        d_res[key]['msg'] = msg
        d_res[key]['flag_valid'] = len(msg) == 0

        if d_res[key]['flag_valid']:
            count_valid += 1
    
    print(f"{count_valid}/{len(metadata.keys())} entries are valid")
    return count_valid == len(metadata.keys()), d_res
    
    

# -------- util --------
def delete_tmp_files(path,folder_tmp=FOLDER_TMP,keep_folder_tmp=False):
    if DEBUG not in ['True','true','TRUE']:
        print(f'deleting {path}...')
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

        if not keep_folder_tmp and folder_tmp != path:
            shutil.rmtree(folder_tmp,ignore_errors=True)

def get_top_level(d,keys_ignore=[]):
    d_res = {}
    for k1,v1 in d.items():
        if not k1.startswith('TEST_'):
            d_res[k1] = {}
            for k,v in v1.items(): 
                if k not in keys_ignore:
                    if not isinstance(v,dict) and v is not None:
                        d_res[k1][k] = v
                    elif k == 'wmla_deployment':
                        d_res[k1]['deployment_name'] = v['deployment_name']
    return d_res