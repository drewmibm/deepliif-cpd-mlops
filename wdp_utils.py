import requests
import mimetypes
import json
import os
from tqdm import tqdm

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = os.getenv('BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL','https://cpd-cpd.apps.cpd.mskcc.org'))

ASSETS = '/v2/assets/{asset_id}'
ASSET_DOWNLOAD = '/v2/asset_files/{asset_path}'
ATTACHMENTS = '/v2/assets/{asset_id}/attachments'
ATTACHMENT = '/v2/assets/{asset_id}/attachments/{attachment_id}'
ATTACHMENT_COMPLETE = '/v2/assets/{asset_id}/attachments/{attachment_id}/complete'
REVISIONS = '/v2/assets/{asset_id}/revisions'

HEADERS_POST = {'Content-Type':'application/json',
                'Authorization':'Bearer {access_token}'}
HEADERS_GET = {'Authorization':'Bearer {access_token}'}
HEADERS_PUT = {'Authorization':'Bearer {access_token}'}


def add_asset_revision(asset_name=None,asset_id=None,asset_path=None,commit_message='add new revision',
                       space_id=None,project_id=None,catalog_id=None,
                       access_token=None, host_url=BASE_URL):
    """
    Add a revision to an existing asset.
    """
    assert asset_path is not None, "Specify asset_path, the local path to the file to be added as new revision"
    assert asset_name or asset_id, "Specify either asset_name or asset_id to locate the target asset"
    assert space_id or project_id or catalog_id, "Specify space_id (Waton Machine Learning), project_id (Watson Studio), or catalog_id (Watson Knowledge Catalog)"
    access_token = fill_in_default_if_none(access_token,'USER_ACCESS_TOKEN')
    
    if asset_id is None:
        asset_ids = get_asset_id_from_name(asset_name,space_id,project_id,catalog_id,access_token,host_url)
        print(f"{len(asset_ids)} asset id(s) found for asset name {asset_name}")
        if len(asset_ids) == 1:
            asset_id = asset_ids[0]
        else:
            raise Exception('If your asset name is unique, make sure it is spelled correctly. Otherwise, use asset id to refer to a unique asset to add a revision to.')
    
    headers_get = fill_in_access_token(HEADERS_GET,access_token)
    headers_post = fill_in_access_token(HEADERS_POST,access_token)
    headers_put = fill_in_access_token(HEADERS_PUT,access_token)
    
    # get old attachment id
    attachments = get_attachments(asset_id,space_id,project_id,catalog_id,access_token,host_url)['attachments']
    attachment_id_delete = attachments[0]['id']
    
    # create attachment
    res_json = create_attachment(asset_id,asset_path,space_id,project_id,catalog_id,access_token,host_url)
    attachment_id = res_json['attachment_id']
    attachment_url = res_json['url1']
    
    # upload attachment content
    f = {'file':open(asset_path,'rb')}
    url = host_url + attachment_url
    put(url,headers_put,f)
    
    # mark as complete
    url = host_url + ATTACHMENT_COMPLETE.format(asset_id=asset_id,attachment_id=attachment_id) + infer_suffix(space_id,project_id,catalog_id)
    post(url,headers_post,{})
    
    # delete old attachment
    delete_attachment(asset_id,attachment_id_delete,space_id,project_id,catalog_id,access_token,host_url)
    
    # create new revision
    url = host_url + REVISIONS.format(asset_id=asset_id) + infer_suffix(space_id,project_id,catalog_id)
    res = post(url,headers_post,{'commit_message':commit_message})
    return res

# def revert_asset_revision()

def download_asset_revision(asset_name=None,asset_id=None,revision_id=None,output_filename=None,
                            space_id=None,project_id=None,catalog_id=None,
                            access_token=None, host_url=BASE_URL):
    """
    Download a specific revision of an asset.
    
    output_filename: if None, uses asset_name with "revision" suffix
    """
    assert asset_name or output_filename, 'If asset_name is not specified, you must specify output_filename to be used for the output file.'
    output_filename = f"{'.'.join(asset_name.split('.')[:-1])}_revision{revision_id}.{asset_name.split('.')[-1]}" if output_filename is None else output_filename
    content = get_asset_revision(asset_name,asset_id,revision_id,space_id,project_id,catalog_id,access_token,host_url)
    with open(output_filename,'w') as f:
        f.write(content)
    return output_filename
    
def get_asset_revision(asset_name=None,asset_id=None,revision_id=None,
                       space_id=None,project_id=None,catalog_id=None,
                       access_token=None, host_url=BASE_URL):
    """
    Fetch the content of a specific revision of an asset.
    """
    assert revision_id is not None, "Specify revision_id"
    assert asset_name or asset_id, "Specify either asset_name or asset_id to locate the target asset"
    assert space_id or project_id or catalog_id, "Specify space_id (Waton Machine Learning), project_id (Watson Studio), or catalog_id (Watson Knowledge Catalog)"
    access_token = fill_in_default_if_none(access_token,'USER_ACCESS_TOKEN')
    
    if asset_id is None:
        asset_ids = get_asset_id_from_name(asset_name,space_id,project_id,catalog_id,access_token,host_url)
        print(f"{len(asset_ids)} asset id(s) found for asset name {asset_name}")
        if len(asset_ids) == 1:
            asset_id = asset_ids[0]
        else:
            raise Exception('If your asset name is unique, make sure it is spelled correctly. Otherwise, use asset id to refer to a unique asset to add a revision to.')
    
    try:
        revision_id = int(revision_id)
    except:
        raise Exception('Error: revisino_id should be an integer')
    
    headers_get = fill_in_access_token(HEADERS_GET,access_token)
    
    # get key / asset path for a specific revision
    url = host_url + ASSETS.format(asset_id=asset_id) + infer_suffix(space_id,project_id,catalog_id) + f'&revision_id={revision_id}'
    res_json = get(url,headers_get)
    key = res_json['attachments'][0]['handle']['key']
    
    # get content of attachment for a revision
    url = host_url + ASSET_DOWNLOAD.format(asset_path=key) + infer_suffix(space_id,project_id,catalog_id)
    res_text = get(url,headers_get,return_json=False)
    return res_text
    
def get_attachments(asset_id,revision_id=None,space_id=None,project_id=None,catalog_id=None,access_token=None, host_url=BASE_URL,
                    return_json=True,return_response=False):
    """
    Get attachments for an asset.
    """
    assert space_id or project_id or catalog_id, "Specify wml space id, ws project id, or a catalog id"
    access_token = fill_in_default_if_none(access_token,'USER_ACCESS_TOKEN')
    
    url = host_url + ASSETS.format(asset_id=asset_id) + infer_suffix(space_id,project_id,catalog_id)
    if revision_id is not None:
        try:
            revision_id = int(revision_id)
        except:
            raise Exception('Error: revisino_id should be an integer')
        url += f'&revision_id={revision_id}'
    headers = fill_in_access_token(HEADERS_GET,access_token)
    
    return get(url,headers,return_json,return_response)

def create_attachment(asset_id,asset_path,space_id=None,project_id=None,catalog_id=None,access_token=None, host_url=BASE_URL,
                      return_json=True,return_response=False):
    """
    Create an attachment for the target asset.
    """
    assert space_id or project_id or catalog_id, "Specify wml space id, ws project id, or a catalog id"
    access_token = fill_in_default_if_none(access_token,'USER_ACCESS_TOKEN')
    
    mime_type = mimetypes.MimeTypes().guess_type(asset_path)[0]
    attachment_meta = {"asset_type": "data_asset",
                       "name": get_asset_name_from_id(asset_id,space_id,project_id,catalog_id,access_token,host_url),
                       "mime": mime_type}
    
    url = host_url + ATTACHMENTS.format(asset_id=asset_id) + infer_suffix(space_id,project_id,catalog_id)
    headers = fill_in_access_token(HEADERS_POST,access_token)
    
    return post(url,headers,attachment_meta,return_json,return_response)

def delete_attachment(asset_id,attachment_id,space_id=None,project_id=None,catalog_id=None,access_token=None,host_url=BASE_URL,verbose=0):
    """
    Delete attachment(s).
    
    attachment_id: a string of attachment id or a list of multiple attachment id
    """
    assert space_id or project_id or catalog_id, "Specify wml space id, ws project id, or a catalog id"
    access_token = fill_in_default_if_none(access_token,'USER_ACCESS_TOKEN')
    
    if isinstance(attachment_id,list):
        attachment_ids = attachment_id
    else:
        attachment_ids = [attachment_id]
        
    headers = fill_in_access_token(HEADERS_POST,access_token)
    
    for attachment_id_delete in attachment_ids:
        url = host_url + ATTACHMENT.format(asset_id=asset_id,attachment_id=attachment_id_delete) + infer_suffix(space_id,project_id,catalog_id)
        res = delete(url,headers,return_json=False)
        if verbose > 0:
            print(f'Deleting {attachment_id_delete}...')
            print(res)

def get_asset_id_from_name(asset_name,space_id=None,project_id=None,catalog_id=None,access_token=None, host_url=BASE_URL):
    """
    Get asset id(s) from asset name.
    """
    assert space_id or project_id or catalog_id, "Specify wml space id, ws project id, or a catalog id"
    access_token = fill_in_default_if_none(access_token,'USER_ACCESS_TOKEN')
    
    url = host_url + f'/v3/search?query=metadata.name:{asset_name}' + infer_suffix(space_id,project_id,catalog_id, global_search=True)
    headers = fill_in_access_token(HEADERS_GET,access_token)
    res_json = get(url,headers)
    if res_json['size'] > 0:
        return [x['artifact_id'] for x in res_json['rows']]
    else:
        return []
    
def get_asset_name_from_id(asset_id,space_id=None,project_id=None,catalog_id=None,access_token=None, host_url=BASE_URL):
    """
    Get asset name from asset id.
    """
    assert space_id or project_id or catalog_id, "Specify wml space id, ws project id, or a catalog id"
    access_token = fill_in_default_if_none(access_token,'USER_ACCESS_TOKEN')
    
    url = host_url + f'/v3/search?query=artifact_id:{asset_id}' + infer_suffix(space_id,project_id,catalog_id, global_search=True)
    headers = fill_in_access_token(HEADERS_GET,access_token)
    res_json = get(url,headers)
    if res_json['size'] > 0:
        return res_json['rows'][0]['metadata']['name']
    else:
        return None


#### utils ####
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
    
def fill_in_access_token(headers,access_token):
    return {k:v.format(access_token=access_token) for k,v in headers.items()}

def infer_suffix(space_id,project_id,catalog_id,global_search=False):
    """
    Fill in the parameter of target place.
    Priority: space id > project id > catalog id
    """
    if not global_search:
        if space_id:
            return f'?space_id={space_id}'
        if project_id:
            return f'?project_id={project_id}'
        if catalog_id:
            return f'?catalog_id={catalog_id}'
    else:
        if space_id:
            return f'+AND+entity.assets.space_id:{space_id}'
        if project_id:
            return f'+AND+entity.assets.project_id:{project_id}'
        if catalog_id:
            return f'+AND+entity.assets.catalog_id:{catalog_id}'
    
def get(url,headers,return_json=True,return_response=False):
    res = requests.get(url,headers=headers,verify=False)
    if return_json and not return_response:
        return res.json()
    if return_response:
        return res
    return res.text

def post(url,headers,data,return_json=True,return_response=False):
    res = requests.post(url,headers=headers,data=json.dumps(data),verify=False)
    if return_json and not return_response:
        return res.json()
    if return_response:
        return res
    return res.text

def put(url,headers,file,return_json=True,return_response=False):
    res = requests.put(url,headers=headers,files=file,verify=False)
    if return_json and not return_response:
        return res.json()
    if return_response:
        return res
    return res.text

def delete(url,headers,return_json=True,return_response=False):
    res = requests.delete(url,headers=headers,verify=False)
    if return_json and not return_response:
        return res.json()
    if return_response:
        return res
    return res.text

def download_file(url,headers,local_filename=None):
    if local_filename is None:
        local_filename = url.split('/')[-1] if '?' not in url.split('/')[-1] else url.split('?')[-1]
    with open(local_filename,'wb') as f:
        res = requests.get(url,stream=True,headers=headers,verify=False)
        if r.status_code == 404:
            raise exception(f"FileNotFound: error {res.json()['error']}, reason {res.json()['reason']}")
        for chunk in tqdm(res.iter_content(chunk_size=1024)):
            if chunk:
                f.write(chunk)
        return local_filename