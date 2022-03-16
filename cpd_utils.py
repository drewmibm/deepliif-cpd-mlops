import os
import requests
import time
import subprocess

BASE_URL = os.getenv('BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL','https://cpd-cpd.apps.cpd.mskcc.org'))
AUTHENTICATE = '/icp4d-api/v1/authorize'
HEADERS_AUTH = {'Content-Type':'application/json'}

def get_access_token(credentials, host_url=BASE_URL):
    """
    Authenticate using api key and get CPD access token for API authorization.
    
    credentials: a dictionary with key "username" and "api_key"
    """
    requests_args = {'url': host_url+AUTHENTICATE,
                     'headers': HEADERS_AUTH,
                     'json': credentials,
                     'verify': False}
    
    out = run_with_fault_tolerance(requests.post,requests_args,
                                   return_object=".json()['token']")
    return out


def run_with_fault_tolerance(function, params, status_code_pass=[200], 
                             return_raw=False, return_object='None', retry=5):
    """
    Executes a function in a fualt-tolerant manner. Currently it is only feasible for API requests.

    function: a function to execute
    params: a dictionary of parameters/arguments to be passed to the function
    status_code_pass: a list of acceptable status codes indicating success
    return_raw: if True, return the original response object; if False, the returned object is defined by
                parameter return_object
    return_object: a string of what code needs to be executed as the returning object
                   can be a method (starting with dot) such as ".json()" so it finally returns response.json()
                   or, can be arbitrary code (not starting with dot) such as "None" so it finally returns None
    """
    count_trial = 0
    while count_trial < retry:
        count_trial += 1
        res = function(**params)

        if res.status_code in status_code_pass:
            if return_raw:
                return res
            elif return_object.startswith('.'):
                return eval('res'+return_object)
            else:
                return eval(return_object)
        else:
            print(f'FAILED: status code {res.status_code}')
            if count_trial < retry:
                print(f'FAILED: {res.text}; wait for 3s and retry...')
                time.sleep(3)
            else:
                raise Exception(f'FAILED: {res.text}; maximum retry reached')
                
                
def run_cmd(cmd,verbose=0):
    """
    Run terminal cmd using subprocess.run and print the output.
    """
    if verbose > 0:
        print('Executing cmd:',cmd)
    proc = subprocess.run(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    out = proc.stdout.decode()
    if out != '':
        print(out)